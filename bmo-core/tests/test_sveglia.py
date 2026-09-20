from datetime import datetime, timedelta

from bmo_core.adapters import STATO_TIMER
from bmo_core.config import FUSO_ORARIO
from bmo_core.sveglia import Sveglia
from bmo_core.timer import ArchivioTimer

ORA = datetime(2026, 9, 20, 20, 0, tzinfo=FUSO_ORARIO)


class OrologioFinto:
    def __init__(self):
        self.adesso = ORA

    def __call__(self):
        return self.adesso

    def avanza(self, secondi):
        self.adesso += timedelta(seconds=secondi)


class AltoparlanteFinto:
    def __init__(self):
        self.riprodotti = []

    def riproduci(self, sorgente):
        self.riprodotti.append(str(sorgente))

    def ferma(self):
        pass


class FacciaFinta:
    def __init__(self):
        self.stati = []

    def mostra(self, stato):
        self.stati.append(stato)


def _sveglia(tmp_path, orologio):
    altoparlante, faccia, dette = AltoparlanteFinto(), FacciaFinta(), []
    sveglia = Sveglia(
        archivio=ArchivioTimer(tmp_path / "timers.json", orologio=orologio),
        altoparlante=altoparlante,
        faccia=faccia,
        annuncia=dette.append,
    )
    return sveglia, altoparlante, faccia, dette


def test_il_timer_scaduto_suona_una_volta_sola(tmp_path):
    orologio = OrologioFinto()
    sveglia, altoparlante, faccia, dette = _sveglia(tmp_path, orologio)
    sveglia.archivio.aggiungi("pasta", 300)

    assert sveglia.controlla() == []  # non è ancora ora
    assert altoparlante.riprodotti == []

    orologio.avanza(300)
    [scaduto] = sveglia.controlla()
    assert scaduto.etichetta == "pasta"
    assert len(altoparlante.riprodotti) == 1
    assert faccia.stati == [STATO_TIMER]
    assert dette == ['È scaduto il timer "pasta".']

    assert sveglia.controlla() == []
    assert len(altoparlante.riprodotti) == 1


def test_il_timer_scaduto_mentre_era_spento_lo_dice(tmp_path):
    orologio = OrologioFinto()
    sveglia, _, _, dette = _sveglia(tmp_path, orologio)
    sveglia.archivio.aggiungi("uova", 90)
    orologio.avanza(3600)  # BMO spento per un'ora

    sveglia.controlla(dopo_una_pausa=True)
    assert dette == ['Il timer "uova" era scaduto alle 20:01, mentre ero spento.']


def test_piu_timer_insieme_un_solo_tono(tmp_path):
    orologio = OrologioFinto()
    sveglia, altoparlante, _, dette = _sveglia(tmp_path, orologio)
    sveglia.archivio.aggiungi("pasta", 300)
    sveglia.archivio.aggiungi("uova", 290)
    orologio.avanza(300)

    assert [t.etichetta for t in sveglia.controlla()] == ["uova", "pasta"]
    # Un tono solo: due mpv in fila si interromperebbero a vicenda.
    assert len(altoparlante.riprodotti) == 1
    assert len(dette) == 2


def test_esegui_si_ferma_dopo_i_giri_chiesti(tmp_path):
    orologio = OrologioFinto()
    sveglia, altoparlante, _, _ = _sveglia(tmp_path, orologio)
    sveglia.archivio.aggiungi("pasta", 0.5)
    orologio.avanza(1)
    sveglia.esegui(intervallo_s=0, giri=2)
    assert len(altoparlante.riprodotti) == 1
