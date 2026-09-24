import threading
import wave

import pytest

from bmo_core.clip import (
    FREQUENZA_HZ,
    RITARDO_ATTESA_S,
    SUONI,
    VERSIONE,
    Clip,
    ClipMute,
    durata_s,
    percorso_clip,
    silenzio_massimo_s,
    suono_attesa,
)


class AltoparlanteFinto:
    """Registra in ordine cosa è stato suonato e fermato."""

    def __init__(self):
        self.eventi = []

    def riproduci(self, sorgente, *, filtro=None, ripeti=False):
        self.eventi.append(("riproduci", str(sorgente), ripeti))

    def attendi(self, timeout_s=None):
        self.eventi.append(("attendi", timeout_s))

    def ferma(self):
        self.eventi.append(("ferma",))


class TimerManuale:
    """Un threading.Timer che scatta solo quando lo dice il test."""

    creati = []

    def __init__(self, ritardo, funzione):
        self.ritardo = ritardo
        self.funzione = funzione
        self.cancellato = False
        self.daemon = False
        TimerManuale.creati.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancellato = True

    def scatta(self):
        # Come un threading.Timer vero: cancel() dopo lo scatto non lo ferma
        # più, ed è proprio la corsa che Clip deve reggere.
        self.funzione()


@pytest.fixture
def clip(tmp_path):
    TimerManuale.creati = []
    altoparlante = AltoparlanteFinto()
    return Clip(altoparlante, cartella=tmp_path, crea_timer=TimerManuale), altoparlante


# --- i suoni ---------------------------------------------------------------


@pytest.mark.parametrize("nome", list(SUONI))
def test_ogni_clip_diventa_un_wav_valido(tmp_path, nome):
    percorso = percorso_clip(nome, tmp_path)
    assert percorso.name == f"{nome}-v{VERSIONE}.wav"
    with wave.open(str(percorso), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getframerate() == FREQUENZA_HZ
    assert 0.5 < durata_s(percorso) < 4
    assert not list(tmp_path.glob("*.parziale"))


def test_una_clip_gia_scritta_non_si_rigenera(tmp_path):
    percorso = percorso_clip("attesa", tmp_path)
    percorso.write_bytes(b"segnaposto")
    assert percorso_clip("attesa", tmp_path).read_bytes() == b"segnaposto"


def test_una_clip_sconosciuta_e_un_errore(tmp_path):
    with pytest.raises(KeyError):
        percorso_clip("fanfara", tmp_path)


def test_l_attesa_copre_il_buco_senza_silenzi_oltre_la_soglia():
    """Criterio della #21: mai muto per più di 0,3 s, anche in loop."""
    campioni = suono_attesa()
    # Il buco tipico è ~1,3 s: la clip deve durare almeno quello.
    assert len(campioni) / FREQUENZA_HZ >= 1.2
    # Due giri di fila, per vedere anche la giunzione del loop.
    assert silenzio_massimo_s(campioni * 2) < 0.3


def test_i_suoni_non_saturano():
    for nome, genera in SUONI.items():
        assert max(abs(c) for c in genera()) <= 0.5, nome


# --- la corsa fra la risposta e la clip -------------------------------------


def test_risposta_veloce_nessun_suono(clip):
    """La risposta arriva prima della soglia: la clip non parte mai."""
    clip, altoparlante = clip
    clip.attesa()
    [timer] = TimerManuale.creati
    assert timer.ritardo == RITARDO_ATTESA_S
    clip.zitto()
    assert timer.cancellato
    assert altoparlante.eventi == []


def test_timer_scattato_dopo_zitto_non_fa_partire_la_clip(clip):
    """La corsa vera: il timer è già scattato quando la voce prende la parola."""
    clip, altoparlante = clip
    clip.attesa()
    [timer] = TimerManuale.creati
    clip.zitto()
    timer.scatta()  # arriva tardi
    assert altoparlante.eventi == []


def test_risposta_lenta_la_clip_suona_in_loop_e_si_ferma(clip):
    clip, altoparlante = clip
    clip.attesa()
    TimerManuale.creati[0].scatta()
    [(azione, sorgente, ripeti)] = altoparlante.eventi
    assert azione == "riproduci" and sorgente.endswith(f"attesa-v{VERSIONE}.wav") and ripeti
    clip.zitto()
    assert altoparlante.eventi[-1] == ("ferma",)
    clip.zitto()  # idempotente: niente secondo ferma
    assert altoparlante.eventi.count(("ferma",)) == 1


def test_attesa_due_volte_non_crea_due_timer(clip):
    clip, _ = clip
    clip.attesa()
    clip.attesa()
    assert len(TimerManuale.creati) == 1


def test_errore_ferma_l_attesa_e_aspetta_la_fine(clip):
    clip, altoparlante = clip
    clip.attesa()
    TimerManuale.creati[0].scatta()
    clip.errore()
    azioni = [e[0] for e in altoparlante.eventi]
    assert azioni == ["riproduci", "ferma", "riproduci", "attendi"]
    assert altoparlante.eventi[2][1].endswith(f"errore-v{VERSIONE}.wav")


def test_mpv_assente_non_blocca(tmp_path):
    class Rotto(AltoparlanteFinto):
        def riproduci(self, sorgente, *, filtro=None, ripeti=False):
            raise FileNotFoundError("mpv")

    clip = Clip(Rotto(), cartella=tmp_path, crea_timer=TimerManuale)
    clip.attesa()
    TimerManuale.creati[-1].scatta()
    clip.zitto()
    clip.errore()


def test_con_threading_timer_vero_e_ritardo_zero(tmp_path):
    """Senza timer finto: la clip parte davvero da un altro thread."""
    altoparlante = AltoparlanteFinto()
    partita = threading.Event()
    originale = altoparlante.riproduci

    def riproduci(*a, **k):
        originale(*a, **k)
        partita.set()

    altoparlante.riproduci = riproduci
    clip = Clip(altoparlante, cartella=tmp_path, ritardo_s=0)
    clip.attesa()
    assert partita.wait(2)
    clip.zitto()
    assert altoparlante.eventi[-1] == ("ferma",)


def test_la_clip_muta_non_fa_niente():
    muta = ClipMute()
    muta.attesa()
    muta.zitto()
    muta.errore()


def test_zitto_aspetta_la_fine_della_nota_in_corso(tmp_path):
    """Troncata a metà nota, la clip farebbe un bip mozzato."""
    adesso = [0.0]
    dormite = []
    clip = Clip(
        AltoparlanteFinto(), cartella=tmp_path, crea_timer=TimerManuale,
        cronometro=lambda: adesso[0], dormi=dormite.append,
    )
    clip.attesa()
    TimerManuale.creati[-1].scatta()
    adesso[0] = 0.32 * 3 + 0.05  # dentro la quarta nota
    clip.zitto()
    assert dormite and 0.07 <= dormite[0] <= 0.1


def test_zitto_in_una_pausa_ferma_subito(tmp_path):
    adesso = [0.0]
    dormite = []
    clip = Clip(
        AltoparlanteFinto(), cartella=tmp_path, crea_timer=TimerManuale,
        cronometro=lambda: adesso[0], dormi=dormite.append,
    )
    clip.attesa()
    TimerManuale.creati[-1].scatta()
    adesso[0] = 0.32 + 0.2  # fra una nota e l'altra
    clip.zitto()
    assert dormite == [0.0]
