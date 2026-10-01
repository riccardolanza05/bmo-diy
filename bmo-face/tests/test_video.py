import socket
import struct
import threading
import time

from bmo_face.animazione import ComandoFaccia
from bmo_face.pannello import SILENZIO_VIDEO_S, UscitaNulla, esegui_pannello
from bmo_face.protocollo import applica, messaggio_video
from bmo_face.servitore import ServitoreFaccia
from bmo_face.video import INTESTAZIONE, RiceviFotogrammi, percorso_socket_video


def _manda(percorso, larghezza, altezza, dati=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.sendto(INTESTAZIONE.pack(larghezza, altezza) + (dati if dati is not None else b"\0" * (larghezza * altezza * 2)), str(percorso))
    s.close()


def test_percorso_socket_video_sta_accanto_a_quello_dei_comandi(tmp_path, monkeypatch):
    monkeypatch.delenv("BMO_SOCKET_VIDEO", raising=False)
    assert percorso_socket_video(tmp_path / "bmo.sock") == tmp_path / "bmo-video.sock"
    monkeypatch.setenv("BMO_SOCKET_VIDEO", "/tmp/altro.sock")
    assert str(percorso_socket_video(tmp_path / "bmo.sock")) == "/tmp/altro.sock"


def test_comando_video_start_pausa_riprendi_stop():
    c = ComandoFaccia()
    applica(c, {"cmd": "video", "action": "start", "title": "Bohemian Rhapsody"}, 0.0)
    assert (c.video_attivo, c.video_in_pausa, c.video_titolo) == (True, False, "Bohemian Rhapsody")
    applica(c, {"cmd": "video", "action": "pause"}, 1.0)
    assert c.video_in_pausa and c.video_attivo
    applica(c, {"cmd": "video", "action": "resume"}, 2.0)
    assert not c.video_in_pausa
    applica(c, {"cmd": "video", "action": "stop"}, 3.0)
    assert (c.video_attivo, c.video_titolo) == (False, None)


def test_comando_video_sconosciuto_si_ignora():
    c = ComandoFaccia()
    applica(c, {"cmd": "video", "action": "boh"}, 0.0)
    applica(c, {"cmd": "video"}, 0.0)
    assert not c.video_attivo


def test_messaggio_video_e_una_riga_json():
    assert messaggio_video("start", "x") == '{"cmd": "video", "action": "start", "title": "x"}\n'


def test_ricevitore_tiene_solo_l_ultimo_fotogramma_e_scarta_i_malformati(tmp_path):
    r = RiceviFotogrammi(tmp_path / "v.sock")
    r.avvia()
    try:
        _manda(r.percorso, 2, 2, b"\x01" * 8)
        _manda(r.percorso, 2, 2, b"\x02" * 8)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(b"xy", str(r.percorso))                                  # troppo corto
        s.sendto(struct.pack("<HH", 4, 4) + b"\0" * 5, str(r.percorso))   # lunghezza sbagliata
        s.close()
        f = r.nuovo(0, 1.0)
        time.sleep(0.2)
        assert f is not None
        ultimo = r.nuovo(0, 0.5)
        assert ultimo.dati == b"\x02" * 8 and ultimo.larghezza == 2
        assert r.nuovo(ultimo.numero, 0.1) is None  # niente di nuovo: aspetta e ritorna None
        assert r.scartati == 2
    finally:
        r.ferma()


def test_pannello_porta_il_video_all_uscita_e_poi_ridisegna_la_faccia(tmp_path):
    from bmo_face.animazione import Renderer
    from bmo_face.build_face import costruisci

    dati, manifesto = costruisci(16, 16)
    renderer = Renderer(manifesto, dati)
    servitore = ServitoreFaccia(percorso=tmp_path / "bmo.sock")
    ricevitore = RiceviFotogrammi(tmp_path / "bmo-video.sock")
    ricevitore.avvia()
    uscita = UscitaNulla()
    passo = {"n": 0}

    def ancora():
        passo["n"] += 1
        return passo["n"] < 60

    def regia():
        time.sleep(0.15)
        with servitore.lock:
            applica(servitore.comando, {"cmd": "video", "action": "start", "title": "t"}, 0.0)
        for _ in range(5):
            _manda(ricevitore.percorso, 4, 2)
            time.sleep(0.05)
        with servitore.lock:
            applica(servitore.comando, {"cmd": "video", "action": "stop"}, 0.0)

    threading.Thread(target=regia, daemon=True).start()
    try:
        esegui_pannello(renderer, servitore, uscita, fps=50.0, ancora=ancora, ricevitore=ricevitore)
    finally:
        ricevitore.ferma()
    assert uscita.video_iniziati == 1 and uscita.video_finiti == 1
    assert 3 <= uscita.fotogrammi_video <= 5
    assert uscita.fotogrammi_inviati >= 2  # la faccia prima e di nuovo dopo il video


def test_pannello_torna_alla_faccia_se_il_video_tace(tmp_path, monkeypatch):
    from bmo_face import pannello
    from bmo_face.animazione import Renderer
    from bmo_face.build_face import costruisci

    dati, manifesto = costruisci(16, 16)
    renderer = Renderer(manifesto, dati)
    servitore = ServitoreFaccia(percorso=tmp_path / "bmo.sock")
    ricevitore = RiceviFotogrammi(tmp_path / "bmo-video.sock")
    ricevitore.avvia()
    with servitore.lock:
        applica(servitore.comando, {"cmd": "video", "action": "start"}, 0.0)
    uscita = UscitaNulla()
    ora = {"t": 0.0}

    def orologio():
        ora["t"] += 1.0  # ogni lettura dell'orologio passa un secondo: niente attese vere
        return ora["t"]

    passo = {"n": 0}
    try:
        esegui_pannello(renderer, servitore, uscita, fps=50.0, orologio=orologio, dormi=lambda s: None,
                        ancora=lambda: passo.__setitem__("n", passo["n"] + 1) or passo["n"] < 30, ricevitore=ricevitore)
    finally:
        ricevitore.ferma()
    assert not servitore.comando.video_attivo
    assert uscita.video_finiti == 1 and uscita.fotogrammi_inviati >= 1
    assert SILENZIO_VIDEO_S > 0
