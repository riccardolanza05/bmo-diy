import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from bmo_core.config import FUSO_ORARIO, Ambiente, percorso_dati
from bmo_core.timer import ArchivioTimer, Timer

ORA = datetime(2026, 9, 20, 20, 0, tzinfo=FUSO_ORARIO)


class OrologioFinto:
    def __init__(self, adesso=ORA):
        self.adesso = adesso

    def __call__(self):
        return self.adesso

    def avanza(self, secondi):
        self.adesso += timedelta(seconds=secondi)


def _archivio(tmp_path, orologio=None):
    return ArchivioTimer(tmp_path / "timers.json", orologio=orologio or OrologioFinto())


def test_il_timer_sopravvive_al_riavvio(tmp_path):
    """Il criterio di uscita della #20: spegnere e riaccendere non perde il timer."""
    orologio = OrologioFinto()
    _archivio(tmp_path, orologio).aggiungi("pasta", 600)

    # "Riavvio": un archivio nuovo sullo stesso file, come dopo un kill.
    dopo = _archivio(tmp_path, orologio)
    [pasta] = dopo.attivi()
    assert pasta.etichetta == "pasta"
    assert pasta.scadenza == ORA + timedelta(minutes=10)


def test_si_salva_la_scadenza_assoluta_non_i_secondi_rimanenti(tmp_path):
    """Regola del piano: cinque minuti di spegnimento non allungano il timer."""
    orologio = OrologioFinto()
    archivio = _archivio(tmp_path, orologio)
    archivio.aggiungi("pasta", 600)

    orologio.avanza(300)  # BMO è stato spento cinque minuti
    [pasta] = _archivio(tmp_path, orologio).attivi()
    assert pasta.scadenza - orologio() == timedelta(minutes=5)

    righe = json.loads((tmp_path / "timers.json").read_text())
    assert righe == [{"etichetta": "pasta", "scadenza": (ORA + timedelta(minutes=10)).isoformat()}]


def test_i_timer_scaduti_durante_lo_spegnimento_restano_da_suonare(tmp_path):
    orologio = OrologioFinto()
    archivio = _archivio(tmp_path, orologio)
    archivio.aggiungi("uova", 90)
    orologio.avanza(3600)  # spento per un'ora

    dopo = _archivio(tmp_path, orologio)
    assert dopo.attivi() == []
    [uova] = dopo.preleva_scaduti()
    assert uova.etichetta == "uova"
    # Prelevato una volta sola: un timer che suona due volte è peggio di uno muto.
    assert dopo.preleva_scaduti() == []


def test_preleva_solo_quelli_scaduti(tmp_path):
    orologio = OrologioFinto()
    archivio = _archivio(tmp_path, orologio)
    archivio.aggiungi("tè", 180)
    archivio.aggiungi("arrosto", 4500)
    orologio.avanza(200)

    assert [t.etichetta for t in archivio.preleva_scaduti()] == ["tè"]
    assert [t.etichetta for t in archivio.attivi()] == ["arrosto"]


def test_annulla_per_etichetta_e_tutti(tmp_path):
    archivio = _archivio(tmp_path)
    archivio.aggiungi("pasta", 300)
    archivio.aggiungi("uova", 90)
    assert archivio.annulla("PASTA") == 1  # l'etichetta non distingue maiuscole
    assert archivio.annulla("inesistente") == 0
    assert [t.etichetta for t in archivio.attivi()] == ["uova"]
    assert archivio.annulla() == 1
    assert archivio.attivi() == []


def test_attivi_in_ordine_di_scadenza(tmp_path):
    archivio = _archivio(tmp_path)
    archivio.aggiungi("arrosto", 4500)
    archivio.aggiungi("uova", 90)
    archivio.aggiungi("pasta", 300)
    assert [t.etichetta for t in archivio.attivi()] == ["uova", "pasta", "arrosto"]


def test_la_scrittura_non_lascia_file_a_meta(tmp_path):
    archivio = _archivio(tmp_path)
    archivio.aggiungi("pasta", 300)
    archivio.annulla("pasta")
    rimasti = [p.name for p in tmp_path.iterdir()]
    # Solo il file dei timer e il file del lock: nessun temporaneo abbandonato.
    assert sorted(rimasti) == ["timers.json", "timers.lock"]


def test_file_illeggibile_non_ferma_bmo(tmp_path):
    (tmp_path / "timers.json").write_text("{ questo non è JSON")
    archivio = _archivio(tmp_path)
    assert archivio.attivi() == []
    # Il file rotto si mette da parte invece di sparire: resta da guardare.
    assert (tmp_path / "timers.rotto").exists()
    archivio.aggiungi("pasta", 300)
    assert [t.etichetta for t in archivio.attivi()] == ["pasta"]


def test_una_riga_malformata_non_butta_via_le_altre(tmp_path):
    buono = {"etichetta": "pasta", "scadenza": (ORA + timedelta(minutes=5)).isoformat()}
    (tmp_path / "timers.json").write_text(json.dumps([{"etichetta": "rotto"}, buono, "boh"]))
    assert [t.etichetta for t in _archivio(tmp_path).attivi()] == ["pasta"]


def test_due_processi_non_si_perdono_i_timer(tmp_path):
    """Senza lock, chi riscrive l'elenco cancella il timer appena aggiunto dall'altro."""
    orologio = OrologioFinto()
    scrittore = _archivio(tmp_path, orologio)
    sveglia = _archivio(tmp_path, orologio)

    def aggiungi_tanti():
        for numero in range(40):
            scrittore.aggiungi(f"t{numero}", 600)

    def controlla_spesso():
        for _ in range(40):
            sveglia.preleva_scaduti()  # nessuno è scaduto: non deve togliere niente

    thread = [threading.Thread(target=aggiungi_tanti), threading.Thread(target=controlla_spesso)]
    for t in thread:
        t.start()
    for t in thread:
        t.join()
    assert len(scrittore.attivi()) == 40


def test_sostituisci_mette_uno_stato_noto(tmp_path):
    archivio = _archivio(tmp_path)
    archivio.aggiungi("vecchio", 300)
    archivio.sostituisci([Timer("pasta", ORA + timedelta(minutes=5))])
    assert [t.etichetta for t in archivio.attivi()] == ["pasta"]


def test_percorso_dei_dati_per_ambiente(monkeypatch):
    """Sul Pi BMO è un servizio di sistema, sul portatile scrive nella home."""
    monkeypatch.delenv("BMO_DATI", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/stato-finto")
    assert percorso_dati(Ambiente.PI) == Path("/var/lib/bmo")
    assert percorso_dati(Ambiente.DEV_LINUX) == Path("/tmp/stato-finto/bmo")
    monkeypatch.setenv("BMO_DATI", "/tmp/forzato")
    assert percorso_dati(Ambiente.PI) == Path("/tmp/forzato")
