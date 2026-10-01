import pytest

from bmo_core.radio import Radio, Stazione
from bmo_core.video import Flusso, Video, VideoYouTube


class RiproduzioneFinta:
    """Una Riproduzione senza ffmpeg: `parte` decide se è arrivato un fotogramma."""

    def __init__(self, flusso, sink, uscita_audio, al_termine=None, parte=True):
        self.flusso, self.al_termine, self.parte = flusso, al_termine, parte
        self.in_corso = True
        self.in_pausa = False
        self.eventi = []

    def attendi_partenza(self, timeout):
        return self.parte

    def pausa(self):
        self.in_pausa = True
        self.eventi.append("pausa")

    def riprendi(self):
        self.in_pausa = False
        self.eventi.append("riprendi")

    def ferma(self):
        self.in_corso = False
        self.eventi.append("ferma")


class FacciaFinta:
    def __init__(self):
        self.video_azioni = []

    def video(self, azione, titolo=None):
        self.video_azioni.append((azione, titolo))


class BrainFinto:
    def __init__(self):
        self.strumenti, self.stati = {}, []

    def registra_strumento(self, nome, f):
        self.strumenti[nome] = f

    def registra_stato(self, f):
        self.stati.append(f)


def _video(n, durata=200):
    return Video(f"id{n}", f"Titolo {n}", durata, "Canale")


def _lettore_finto():
    class L:
        suona = False
        azioni = []

        def imposta_volume(self, v): pass
        def riproduci(self, t): self.suona = True
        def pausa(self): self.azioni.append("pausa")
        def riprendi(self): self.azioni.append("riprendi")
        def stop(self): self.suona, _ = False, self.azioni.append("stop")
        def in_riproduzione(self): return self.suona
    return L()


def _tutto(esiti=(True,), trovati=None, risolvi_errori=()):
    """Un VideoYouTube con ricerca, risoluzione e riproduzione finte; `esiti[i]` = parte o no, all'i-esimo tentativo."""
    creati = []
    faccia = FacciaFinta()
    trovati = trovati if trovati is not None else [_video(1), _video(2), _video(3)]
    chiamate = {"n": 0}

    def risolutore(video):
        if video.id in risolvi_errori:
            raise RuntimeError("non si risolve")
        return Flusso(["http://x"], 320, 180, 25)

    def avvia(flusso, sink, uscita, al_termine=None):
        parte = esiti[min(chiamate["n"], len(esiti) - 1)]
        chiamate["n"] += 1
        r = RiproduzioneFinta(flusso, sink, uscita, al_termine, parte)
        creati.append(r)
        return r

    fermate_radio = []
    v = VideoYouTube(faccia=faccia, sink=lambda *a: None, uscita_audio="null",
                     ferma_radio=lambda: fermate_radio.append(1), cercatore=lambda q: trovati,
                     risolutore=risolutore, avvia=avvia)
    return v, faccia, creati, fermate_radio


def test_riproduci_ok_avvia_ferma_la_radio_e_mostra_il_video():
    v, faccia, creati, fermate_radio = _tutto()
    r = v.riproduci("queen bohemian rhapsody video ufficiale")
    assert r == {"stato": "ok", "titolo": "Titolo 1", "canale": "Canale", "durata": "3:20", "posizione": "1 di 3"}
    assert fermate_radio == [1]
    assert faccia.video_azioni == [("start", "Titolo 1")]
    assert v.in_riproduzione() and v.presente()


def test_se_il_primo_non_parte_si_passa_al_successivo():
    v, faccia, creati, _ = _tutto(esiti=(False, True))
    assert v.riproduci("x")["titolo"] == "Titolo 2"
    assert creati[0].eventi == ["ferma"]  # quello appeso è stato fermato


def test_se_un_video_non_si_risolve_si_passa_al_successivo():
    v, *_ = _tutto(risolvi_errori=("id1",))
    assert v.riproduci("x")["titolo"] == "Titolo 2"


def test_nessuno_parte_e_un_errore_chiaro():
    v, faccia, *_ = _tutto(esiti=(False,))
    r = v.riproduci("x")
    assert r["stato"] == "errore" and "non parte" in r["motivo"]
    assert faccia.video_azioni == []  # la faccia non è mai passata al video
    assert not v.presente()


def test_nessun_risultato_e_non_trovato():
    v, *_ = _tutto(trovati=[])
    assert v.riproduci("asdfgh") == {"stato": "non_trovato", "query": "asdfgh"}


def test_ricerca_che_fallisce_e_un_errore_non_un_crollo():
    v, *_ = _tutto()
    v.cercatore = lambda q: (_ for _ in ()).throw(OSError("rete giù"))
    r = v.riproduci("x")
    assert r["stato"] == "errore" and "OSError" in r["motivo"]


def test_query_vuota_e_un_errore():
    v, *_ = _tutto()
    assert v.riproduci("  ")["stato"] == "errore"


def test_controlli_pausa_riprendi_stop():
    v, faccia, creati, _ = _tutto()
    v.riproduci("x")
    assert v.controllo("pausa") == {"stato": "ok", "azione": "pausa"}
    assert creati[0].in_pausa and not v.in_riproduzione() and v.presente()
    v.controllo("riprendi")
    assert v.in_riproduzione()
    v.controllo("stop")
    assert not v.presente() and faccia.video_azioni[-1] == ("stop", None)
    assert v.controllo("pausa") == {"stato": "niente_in_riproduzione"}


def test_successivo_e_precedente_girano_in_tondo():
    v, *_ = _tutto()
    v.riproduci("x")
    assert v.controllo("successivo")["titolo"] == "Titolo 2"
    assert v.controllo("precedente")["titolo"] == "Titolo 1"
    assert v.controllo("precedente")["titolo"] == "Titolo 3"  # da 1 indietro = l'ultimo


def test_azione_sconosciuta():
    v, *_ = _tutto()
    v.riproduci("x")
    with pytest.raises(ValueError):
        v.controllo("salta")


def test_fine_naturale_riporta_la_faccia():
    v, faccia, creati, _ = _tutto()
    v.riproduci("x")
    creati[0].in_corso = False
    creati[0].al_termine()
    assert not v.presente() and faccia.video_azioni[-1] == ("stop", None)


def test_sospeso_mette_in_pausa_e_riprende_solo_se_andava():
    v, faccia, creati, _ = _tutto()
    with v.sospeso():
        pass  # niente video: non fa nulla
    v.riproduci("x")
    with v.sospeso():
        assert creati[0].in_pausa
    assert not creati[0].in_pausa
    v.controllo("pausa")
    with v.sospeso():
        pass
    assert creati[0].in_pausa  # era in pausa per scelta: non si riprende da soli


def test_stato_dice_cosa_sta_andando():
    v, *_ = _tutto()
    assert v.descrivi_stato() == "Video: nessuno."
    v.riproduci("x")
    assert 'in riproduzione "Titolo 1"' in v.descrivi_stato() and "sistema" in v.descrivi_stato()
    v.controllo("pausa")
    assert "(in pausa)" in v.descrivi_stato()


def test_registra_collega_strumento_e_stato():
    v, *_ = _tutto()
    cervello = BrainFinto()
    v.registra(cervello)
    assert cervello.strumenti["riproduci_video"] == v.riproduci and len(cervello.stati) == 1


# --- insieme alla radio -----------------------------------------------------------


def _radio_con_video(tmp_path):
    v, faccia, creati, _ = _tutto()
    lettore = _lettore_finto()
    radio = Radio(lettore=lettore, volume=None, percorso=tmp_path / "radio.json",
                  cercatore=lambda q: [Stazione("Radio Uno", "http://r1")], percorso_volumi=tmp_path / "vol.json", video=v)
    v.ferma_radio = radio.ferma
    return radio, v, lettore, creati


def test_il_video_ferma_la_radio(tmp_path):
    radio, v, lettore, _ = _radio_con_video(tmp_path)
    radio.riproduci("uno")
    assert lettore.suona and radio.in_ascolto is not None
    v.riproduci("x")
    assert not lettore.suona and radio.in_ascolto is None


def test_la_radio_ferma_il_video(tmp_path):
    radio, v, lettore, creati = _radio_con_video(tmp_path)
    v.riproduci("x")
    radio.riproduci("uno")
    assert not v.presente() and creati[0].eventi[-1] == "ferma" and lettore.suona


def test_controllo_della_radio_vale_per_il_video_se_va_il_video(tmp_path):
    radio, v, lettore, creati = _radio_con_video(tmp_path)
    v.riproduci("x")
    assert radio.controllo("pausa") == {"stato": "ok", "azione": "pausa"}
    assert creati[0].in_pausa and lettore.azioni == []  # la radio non è stata toccata
    assert radio.controllo("successivo")["titolo"] == "Titolo 2"


def test_sospesa_della_radio_mette_in_pausa_il_video(tmp_path):
    radio, v, lettore, creati = _radio_con_video(tmp_path)
    v.riproduci("x")
    with radio.sospesa():
        assert creati[0].in_pausa
    assert not creati[0].in_pausa and lettore.azioni == []


def test_stato_della_radio_con_un_video_in_corso(tmp_path):
    radio, v, *_ = _radio_con_video(tmp_path)
    v.riproduci("x")
    assert "sta andando un video" in radio.descrivi_stato()


# --- audio: video_out, volume software e abbassamento mentre BMO parla -----------------------


def test_uscita_audio_predefinita_segue_asound_e_la_variabile(tmp_path, monkeypatch):
    from bmo_core import video as modulo

    monkeypatch.delenv("BMO_VIDEO_AUDIO", raising=False)
    monkeypatch.setattr(modulo.Path, "home", classmethod(lambda cls: tmp_path))
    assert modulo.uscita_audio_predefinita() == "alsa:default"       # niente asound: com'è oggi sul Pi
    (tmp_path / ".asoundrc").write_text("pcm.video_out { type plug }")
    assert modulo.uscita_audio_predefinita() == "alsa:video_out"      # con dmix + volume software installati
    monkeypatch.setenv("BMO_VIDEO_AUDIO", "null")
    assert modulo.uscita_audio_predefinita() == "null"                # la variabile vince sempre


def test_abbassato_regola_il_volume_del_video_e_lo_rimette(monkeypatch):
    from bmo_core import video as modulo

    chiamate = []

    class Esito:
        returncode = 0

    monkeypatch.setattr(modulo.subprocess, "run", lambda cmd, **k: chiamate.append(cmd[-1]) or Esito())
    v, *_ = _tutto()
    v.uscita_audio = "alsa:video_out"
    v.riproduci("x")
    with v.abbassato():
        assert chiamate == ["30%"]
    assert chiamate == ["30%", "100%"]


def test_abbassato_senza_volume_software_non_fa_nulla(monkeypatch):
    from bmo_core import video as modulo

    chiamate = []
    monkeypatch.setattr(modulo.subprocess, "run", lambda cmd, **k: chiamate.append(cmd))
    v, *_ = _tutto()          # uscita "null": niente video_out
    v.riproduci("x")
    with v.abbassato():
        pass
    assert chiamate == []
    with VideoYouTube(sink=lambda *a: None, uscita_audio="null").abbassato():  # e senza video che suona
        pass


def test_se_amixer_fallisce_si_smette_di_provare(monkeypatch):
    from bmo_core import video as modulo

    chiamate = []

    class Esito:
        returncode = 1

    monkeypatch.setattr(modulo.subprocess, "run", lambda cmd, **k: chiamate.append(cmd) or Esito())
    v, *_ = _tutto()
    v.uscita_audio = "alsa:video_out"
    v.riproduci("x")
    with v.abbassato():
        pass
    with v.abbassato():
        pass
    assert len(chiamate) == 1  # il controllo «Video» non c'è: una volta sola


# --- avvio in background (il video parte mentre BMO parla) -----------------------------


def _attendi(condizione, secondi=3.0):
    import time

    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(0.01)
    return False


def test_in_background_risponde_subito_e_il_video_parte_dopo():
    import threading

    via = threading.Event()
    v, faccia, creati, _ = _tutto()
    v.in_background = True
    risolutore_originale = v.risolutore
    v.risolutore = lambda video, esegui=None: (via.wait(3), risolutore_originale(video))[1]
    r = v.riproduci("x")
    assert r["stato"] == "ok" and r["titolo"] == "Titolo 1" and "pochi secondi" in r["nota"]
    assert not v.in_riproduzione() and v.presente()           # sta partendo
    assert 'sta partendo "Titolo 1"' in v.descrivi_stato()
    assert faccia.video_azioni == []                          # la faccia non cambia finché non c'è un fotogramma
    via.set()
    assert _attendi(v.in_riproduzione)
    assert faccia.video_azioni == [("start", "Titolo 1")] and "in riproduzione" in v.descrivi_stato()


def test_in_background_stop_durante_l_avvio_annulla_tutto():
    import threading

    via = threading.Event()
    v, faccia, creati, _ = _tutto()
    v.in_background = True
    risolutore_originale = v.risolutore
    v.risolutore = lambda video, esegui=None: (via.wait(3), risolutore_originale(video))[1]
    v.riproduci("x")
    assert v.controllo("stop") == {"stato": "ok", "azione": "stop"}
    via.set()
    assert _attendi(lambda: not v._in_avvio)
    import time

    time.sleep(0.2)
    assert not v.presente() and creati == []                  # nessun ffmpeg è partito
    assert faccia.video_azioni == []


def test_in_background_durante_l_avvio_gli_altri_controlli_rispondono_sta_partendo():
    import threading

    via = threading.Event()
    v, *_ = _tutto()
    v.in_background = True
    v.risolutore = lambda video, esegui=None: (via.wait(3), Flusso(["http://x"], 320, 180, 25))[1]
    v.riproduci("x")
    assert v.controllo("pausa")["stato"] == "sta_partendo"
    via.set()
    assert _attendi(v.in_riproduzione)


def test_in_background_se_nessuno_parte_avvisa_e_ripulisce():
    avvisi = []
    v, faccia, creati, _ = _tutto(esiti=(False,))
    v.in_background = True
    v.al_fallimento = avvisi.append
    assert v.riproduci("x")["stato"] == "ok"
    assert _attendi(lambda: bool(avvisi))
    assert "non parte" in avvisi[0] and not v.presente() and faccia.video_azioni == []
    assert len(creati) == 3                                   # ha provato i primi tre risultati


def test_in_background_una_nuova_richiesta_annulla_l_avvio_precedente():
    import threading

    via = threading.Event()
    v, faccia, creati, _ = _tutto()
    v.in_background = True
    risolutore_originale = v.risolutore
    chiamate = []

    def lento(video, esegui=None):
        chiamate.append(video.id)
        if len(chiamate) == 1:
            via.wait(3)  # il primo avvio resta fermo finché non parte il secondo
        return risolutore_originale(video)

    v.risolutore = lento
    v.riproduci("uno")
    assert _attendi(lambda: len(chiamate) == 1)
    v.riproduci("due")
    assert _attendi(v.in_riproduzione)
    via.set()
    import time

    time.sleep(0.3)
    assert len([c for c in creati if c.in_corso]) == 1        # solo il secondo video suona


# --- risolutore preavviato ---------------------------------------------------------


class PreRisolutoreFinto:
    def __init__(self):
        self.chiuso = False

    def esegui(self, argomenti):
        return "640|360|25\nhttps://v.example/x"

    def chiudi(self):
        self.chiuso = True


def test_il_risolutore_preavviato_si_usa_e_si_chiude_sempre():
    creati = []

    def precarica():
        creati.append(PreRisolutoreFinto())
        return creati[0]

    v, *_ = _tutto()
    v.precarica = precarica
    usati = []
    v.risolutore = lambda video, esegui=None: usati.append(esegui) or Flusso(["http://x"], 320, 180, 25)
    assert v.riproduci("x")["stato"] == "ok"
    assert usati == [creati[0].esegui] and creati[0].chiuso


def test_il_risolutore_preavviato_si_chiude_anche_se_la_ricerca_fallisce():
    pre = PreRisolutoreFinto()
    v, *_ = _tutto()
    v.precarica = lambda: pre
    v.cercatore = lambda q: (_ for _ in ()).throw(OSError("rete giù"))
    assert v.riproduci("x")["stato"] == "errore" and pre.chiuso


def test_risolutore_pronto_vero_riporta_gli_errori_senza_rete():
    pytest.importorskip("yt_dlp")
    from bmo_core.video import RisolutorePronto

    pronto = RisolutorePronto()
    try:
        with pytest.raises(RuntimeError):
            pronto.esegui(["best", "non un indirizzo"])
        with pytest.raises(RuntimeError):  # il processo resta vivo per una seconda richiesta
            pronto.esegui(["best", "neanche questo"])
    finally:
        pronto.chiudi()
