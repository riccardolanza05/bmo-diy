import json

import pytest
from google.genai import types

from bmo_core.brain import Cervello
from bmo_core.radio import Radio, Stazione, carica_preferite, cerca_stazioni, frequenza_nel_nome


class LettoreFinto:
    def __init__(self, suona=False):
        self.code = []
        self.azioni = []
        self.suona = suona

    def riproduci(self, tracce):
        self.code.append(list(tracce))
        self.suona = True

    def pausa(self):
        self.azioni.append("pausa")

    def riprendi(self):
        self.azioni.append("riprendi")

    def stop(self):
        self.azioni.append("stop")
        self.suona = False

    def successivo(self):
        self.azioni.append("successivo")

    def in_riproduzione(self):
        return self.suona

    def spegni(self):
        self.azioni.append("spegni")
        self.suona = False


class VolumeFinto:
    def __init__(self):
        self.impostati = []

    def imposta(self, percentuale):
        self.impostati.append(percentuale)

    def leggi(self):
        return self.impostati[-1] if self.impostati else None


TROVATE = [
    Stazione("Radio Jazz Italia", "http://stream/jazz1", None, "Italy"),
    Stazione("Jazz 101.7", "http://stream/jazz2", "101.7", "Italy"),
    Stazione("Smooth Jazz", "http://stream/jazz3", None, "Italy"),
]


def _radio(tmp_path, preferite=None, trovate=TROVATE):
    if preferite is not None:
        (tmp_path / "radio.json").write_text(
            json.dumps([{"nome": s.nome, "url": s.url, "frequenza": s.frequenza} for s in preferite]),
            encoding="utf-8",
        )
    lettore, volume = LettoreFinto(), VolumeFinto()
    radio = Radio(
        lettore=lettore,
        volume=volume,
        percorso=tmp_path / "radio.json",
        cercatore=lambda query="", **k: list(trovate),
    )
    return radio, lettore, volume


def test_accende_una_stazione_cercandola_online(tmp_path):
    radio, lettore, _ = _radio(tmp_path)
    esito = radio.riproduci("jazz")
    assert esito["stato"] == "ok"
    assert esito["stazione"] == "Radio Jazz Italia"
    assert esito["posizione"] == "1 di 3"
    assert lettore.code == [["http://stream/jazz1"]]


def test_scorre_avanti_e_indietro_come_una_manopola(tmp_path):
    radio, lettore, _ = _radio(tmp_path)
    radio.riproduci("jazz")
    assert radio.controllo("successivo")["stazione"] == "Jazz 101.7"
    assert radio.controllo("successivo")["stazione"] == "Smooth Jazz"
    # Dopo l'ultima si torna alla prima, e indietro si gira dall'altra parte.
    assert radio.controllo("successivo")["stazione"] == "Radio Jazz Italia"
    assert radio.controllo("precedente")["stazione"] == "Smooth Jazz"
    assert [c[0] for c in lettore.code][-1] == "http://stream/jazz3"


def test_la_frequenza_nel_nome_viene_riconosciuta(tmp_path):
    assert frequenza_nel_nome("Radio Deejay 107.0") == "107.0"
    assert frequenza_nel_nome("Jazz 101,7") == "101.7"
    assert frequenza_nel_nome("Radio Popolare") is None

    radio, _, _ = _radio(tmp_path)
    radio.riproduci("jazz")
    assert radio.controllo("successivo")["frequenza"] == "101.7"


def test_salva_la_stazione_che_sta_suonando(tmp_path):
    radio, _, _ = _radio(tmp_path)
    assert radio.salva_stazione()["stato"] == "niente_in_riproduzione"

    radio.riproduci("jazz")
    radio.controllo("successivo")
    esito = radio.salva_stazione("quella del jazz")
    assert esito["stato"] == "ok"
    assert esito["salvata"] == "quella del jazz"
    assert esito["frequenza"] == "101.7"  # presa dalla stazione, non dal nome scelto
    assert radio.salva_stazione()["stato"] == "gia_salvata"

    # Salvata davvero: un BMO riavviato se la ritrova.
    [salvata] = carica_preferite(tmp_path / "radio.json")
    assert (salvata.nome, salvata.url) == ("quella del jazz", "http://stream/jazz2")


def test_la_frequenza_puo_stare_nel_nome_che_scegli_tu(tmp_path):
    radio, _, _ = _radio(tmp_path)
    radio.riproduci("jazz")  # "Radio Jazz Italia", senza frequenza
    assert radio.salva_stazione("quella sui 101.7")["frequenza"] == "101.7"


def test_le_preferite_vengono_prima_della_ricerca(tmp_path):
    preferite = [Stazione("Radio Deejay", "http://stream/deejay", "107.0")]
    radio, lettore, _ = _radio(tmp_path, preferite=preferite)
    esito = radio.riproduci("deejay")
    assert esito == {
        "stato": "ok",
        "stazione": "Radio Deejay",
        "posizione": "1 di 1",
        "frequenza": "107.0",
        "elenco": "preferite",
    }
    assert lettore.code == [["http://stream/deejay"]]

    # Si può chiedere anche per frequenza.
    assert radio.riproduci("107.0")["stazione"] == "Radio Deejay"
    # Senza query si riaccende sulle preferite, senza andare in rete.
    assert radio.riproduci()["elenco"] == "preferite"


def test_senza_preferite_e_senza_query_cerca(tmp_path):
    radio, _, _ = _radio(tmp_path)
    assert radio.riproduci()["elenco"] == "risultati della ricerca"


def test_elenco_delle_preferite(tmp_path):
    preferite = [Stazione("Radio Deejay", "http://stream/deejay", "107.0"), Stazione("Radio Popolare", "http://p")]
    radio, _, _ = _radio(tmp_path, preferite=preferite)
    assert radio.elenca_stazioni() == {
        "preferite": [{"nome": "Radio Deejay", "frequenza": "107.0"}, {"nome": "Radio Popolare"}]
    }


def test_elenco_online_irraggiungibile_non_fa_morire_bmo(tmp_path):
    def esplode(query="", **k):
        raise ConnectionError("rete giù")

    radio = Radio(
        lettore=LettoreFinto(), volume=VolumeFinto(), percorso=tmp_path / "radio.json", cercatore=esplode
    )
    esito = radio.riproduci("jazz")
    assert esito["stato"] == "errore"
    assert "ConnectionError" in esito["motivo"]


def test_nessuna_stazione_trovata(tmp_path):
    radio, lettore, _ = _radio(tmp_path, trovate=[])
    assert radio.riproduci("una radio che non esiste")["stato"] == "non_trovato"
    assert lettore.code == []  # niente suona: BMO non deve fingere


def test_controlli_e_volume(tmp_path):
    radio, lettore, volume = _radio(tmp_path)
    assert radio.controllo("pausa") == {"stato": "niente_in_riproduzione"}
    assert radio.controllo("successivo") == {"stato": "niente_in_riproduzione"}

    radio.riproduci("jazz")
    assert radio.controllo("pausa") == {"stato": "ok", "azione": "pausa"}
    assert radio.controllo("stop")["stato"] == "ok"
    assert radio.in_ascolto is None

    assert radio.regola_volume(60) == {"stato": "ok", "percentuale": 60}
    assert volume.impostati == [60]
    with pytest.raises(ValueError):
        radio.regola_volume(101)
    with pytest.raises(ValueError):
        radio.controllo("rewind")


def test_file_delle_preferite_rotto_o_vecchio(tmp_path):
    percorso = tmp_path / "radio.json"
    assert carica_preferite(percorso) == []
    percorso.write_text("non è json")
    assert carica_preferite(percorso) == []
    # Vecchio formato {"nome": "indirizzo"}: si legge lo stesso.
    percorso.write_text(json.dumps({"Radio Deejay 107.0": "http://stream/deejay"}))
    [vecchia] = carica_preferite(percorso)
    assert (vecchia.nome, vecchia.frequenza) == ("Radio Deejay 107.0", "107.0")


def test_ricerca_per_genere_se_il_nome_non_da_niente():
    chiamate = []

    def richiesta(parametri):
        chiamate.append(parametri)
        if "name" in parametri and parametri["name"]:
            return []
        return [{"name": "Smooth Jazz", "url_resolved": "http://stream/jazz", "country": "Italy"}]

    [stazione] = cerca_stazioni("jazz", richiesta=richiesta)
    assert stazione.nome == "Smooth Jazz"
    assert chiamate[0]["name"] == "jazz" and chiamate[1]["tag"] == "jazz"


def test_niente_doppioni_nei_risultati():
    """L'elenco pubblico ha più voci per la stessa radio: scorrerle tutte è inutile."""
    doppioni = [
        {"name": "Radio Deejay", "url_resolved": "http://uno", "country": "Italy"},
        {"name": "radio deejay", "url_resolved": "http://due", "country": "Italy"},
        {"name": "Radio Deejay HR", "url_resolved": "http://tre", "country": "Croatia"},
    ]
    nomi = [s.nome for s in cerca_stazioni("deejay", richiesta=lambda p: doppioni)]
    assert nomi == ["Radio Deejay", "Radio Deejay HR"]


def test_gli_strumenti_passano_dal_cervello(tmp_path):
    """Il percorso vero: il modello chiama, il cervello instrada, la radio esegue."""
    radio, lettore, volume = _radio(tmp_path)
    cervello = Cervello(client=object(), microfono=object())
    radio.registra(cervello)

    [accesa] = cervello.strumenti([types.FunctionCall(name="riproduci_musica", args={"query": "jazz"})])
    assert accesa.risultato["stato"] == "ok"
    [avanti] = cervello.strumenti(
        [types.FunctionCall(name="controllo_riproduzione", args={"azione": "precedente"})]
    )
    assert avanti.risultato["stato"] == "ok"
    [salvata] = cervello.strumenti([types.FunctionCall(name="salva_stazione", args={})])
    assert salvata.risultato["stato"] == "ok"
    [elenco] = cervello.strumenti([types.FunctionCall(name="elenca_stazioni", args={})])
    assert len(elenco.risultato["preferite"]) == 1
    [alzato] = cervello.strumenti([types.FunctionCall(name="regola_volume", args={"percentuale": 60})])
    assert alzato.risultato == {"stato": "ok", "percentuale": 60}


def test_sospesa_mette_in_pausa_e_riprende_se_sta_suonando(tmp_path):
    radio, lettore, _ = _radio(tmp_path)
    radio.riproduci("jazz")
    lettore.azioni.clear()  # riproduci() non passa da pausa/riprendi

    with radio.sospesa():
        assert lettore.azioni == ["pausa"]

    assert lettore.azioni == ["pausa", "riprendi"]


def test_sospesa_non_fa_nulla_se_la_radio_non_ha_mai_suonato(tmp_path):
    """Sospendere senza niente in coda non deve accendere un mpv a vuoto."""
    radio, lettore, _ = _radio(tmp_path)

    with radio.sospesa():
        assert lettore.azioni == []

    assert lettore.azioni == []


def test_sospesa_riprende_anche_se_il_blocco_solleva(tmp_path):
    radio, lettore, _ = _radio(tmp_path)
    radio.riproduci("jazz")
    lettore.azioni.clear()

    with pytest.raises(ValueError):
        with radio.sospesa():
            raise ValueError("boom")

    assert lettore.azioni == ["pausa", "riprendi"]
