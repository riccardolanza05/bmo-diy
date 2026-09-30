import json
import shutil
import socket
import subprocess

import pytest

from bmo_core import video
from bmo_core.video import (
    Flusso,
    INTESTAZIONE,
    Riproduzione,
    SinkFotogrammi,
    Video,
    cerca_video,
    comando_ffmpeg,
    dimensioni_schermo,
    fps_di_riproduzione,
    risolvi_flusso,
)


def _riga(id, durata, titolo="t", **extra):
    return json.dumps({"id": id, "duration": durata, "title": titolo, **extra})


def _nessuna_diretta(query):
    raise OSError("niente rete nei test")


def test_cerca_ripiega_su_ytdlp_e_scarta_dirette_e_maratone():
    uscita = "\n".join([
        _riga("a", 200, "bello", channel="Canale"),
        _riga("live", None),
        _riga("lungo", video.DURATA_MASSIMA_S + 1),
        "non è json",
        _riga("b", 90),
    ])
    trovati = cerca_video("gatti", esegui=lambda argomenti: uscita, diretta=_nessuna_diretta)
    assert [v.id for v in trovati] == ["a", "b"]
    assert trovati[0].canale == "Canale"
    assert trovati[0].pagina == "https://www.youtube.com/watch?v=a"


def test_cerca_usa_la_ricerca_diretta_se_risponde():
    chiamate = []

    def diretta(query):
        return [{"id": "x", "duration": 100, "title": "Uno", "channel": "C"}, {"id": "y", "duration": None}]

    trovati = cerca_video("qualcosa", esegui=lambda a: chiamate.append(a) or "", diretta=diretta)
    assert [v.id for v in trovati] == ["x"]
    assert chiamate == []  # yt-dlp non si avvia nemmeno


def test_cerca_chiede_a_ytdlp_la_query_giusta():
    visti = []
    cerca_video("  jazz  ", quanti=3, esegui=lambda a: visti.append(a) or "", diretta=_nessuna_diretta)
    assert visti[0][-1] == "ytsearch6:jazz"


@pytest.mark.parametrize("testo,secondi", [("6:00", 360), ("1:02:03", 3723), ("0:45", 45), (None, None), ("LIVE", None)])
def test_durata_in_secondi(testo, secondi):
    assert video._durata_in_secondi(testo) == secondi


def test_risolvi_legge_dimensioni_fps_e_indirizzi():
    uscita = "640|360|25.0\nhttps://v.example/video\nhttps://a.example/audio\n"
    flusso = risolvi_flusso(Video("a", "t", 10), esegui=lambda a: uscita)
    assert flusso.indirizzi == ["https://v.example/video", "https://a.example/audio"]
    assert (flusso.larghezza, flusso.altezza, flusso.fps) == (320, 180, 25)
    assert flusso.byte_per_fotogramma == 320 * 180 * 2
    with pytest.raises(RuntimeError):
        risolvi_flusso(Video("a", "t", 10), esegui=lambda a: "640|360|25\n")


@pytest.mark.parametrize("l,a,atteso", [
    (640, 360, (320, 180)),   # 16:9: bande sopra e sotto
    (640, 480, (320, 240)),   # 4:3: schermo intero
    (360, 640, (134, 240)),   # verticale: bande ai lati
    (0, 0, (320, 180)),       # sconosciuto: si assume 16:9
])
def test_dimensioni_schermo(l, a, atteso):
    assert dimensioni_schermo(l, a) == atteso
    assert all(n % 2 == 0 for n in atteso)


@pytest.mark.parametrize("sorgente,atteso", [(24, 24), (25, 25), (30, 30), (50, 25), (60, 30), (None, 25), (120, 30)])
def test_fps_di_riproduzione_16_9(sorgente, atteso):
    assert fps_di_riproduzione(sorgente, 320 * 180 * 2) == atteso  # 115 kB a fotogramma: il bus regge 30 fps


@pytest.mark.parametrize("sorgente,atteso", [(24, 24), (25, 25), (30, 26), (60, 26)])
def test_fps_di_riproduzione_4_3_ha_meno_bus(sorgente, atteso):
    assert fps_di_riproduzione(sorgente, 320 * 240 * 2) == atteso  # 154 kB a fotogramma: il bus ne regge 26


def test_comando_un_ingresso_prende_l_audio_dal_primo():
    comando = comando_ffmpeg(Flusso(["http://x"], 320, 180, 25), "null")
    assert comando.count("-i") == 1 and "0:a:0" in comando
    assert "scale=320:180" in " ".join(comando) and "format=rgb565le" in " ".join(comando)


def test_comando_due_ingressi_prende_l_audio_dal_secondo():
    comando = comando_ffmpeg(Flusso(["http://v", "http://a"], 320, 180, 25), "alsa:hw:1")
    assert comando.count("-i") == 2 and "1:a:0" in comando
    assert comando[-3:] == ["-f", "alsa", "hw:1"]


def test_sink_senza_bmo_face_scarta_senza_bloccarsi(tmp_path):
    sink = SinkFotogrammi(tmp_path / "non-esiste.sock")
    sink(2, 2, b"\0" * 8)
    assert (sink.consegnati, sink.scartati) == (0, 1)


def test_sink_consegna_un_datagram_per_fotogramma(tmp_path):
    percorso = tmp_path / "v.sock"
    ricevente = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    ricevente.bind(str(percorso))
    sink = SinkFotogrammi(percorso)
    sink(2, 3, b"\x01" * 12)
    datagram = ricevente.recv(65536)
    assert INTESTAZIONE.unpack_from(datagram) == (2, 3)
    assert datagram[INTESTAZIONE.size:] == b"\x01" * 12
    assert sink.consegnati == 1


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
def test_riproduzione_di_un_file_locale_consegna_fotogrammi_della_forma_giusta(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=426x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", str(clip)], check=True)
    blocchi, finito = [], []
    flusso = Flusso([str(clip)], 320, 180, 15)
    riproduzione = Riproduzione(flusso, lambda l, a, dati: blocchi.append((l, a, len(dati))), "null",
                                al_termine=lambda: finito.append(True))
    riproduzione._thread.join(timeout=15)
    assert finito == [True] and not riproduzione.in_corso
    assert 26 <= len(blocchi) <= 32  # 2 s a 15 fps
    assert set(blocchi) == {(320, 180, flusso.byte_per_fotogramma)}


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
def test_pausa_ferma_ffmpeg_e_la_ripresa_riparte_dalla_posizione(tmp_path):
    import time

    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "8", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", str(clip)], check=True)
    terminati = []
    r = Riproduzione(Flusso([str(clip)], 320, 180, 15), lambda *a: None, "null", al_termine=lambda: terminati.append(1))
    try:
        time.sleep(2.0)
        r.pausa()
        time.sleep(0.3)
        fermo, posizione = r.fotogrammi_letti, r.posizione_s
        assert r.in_pausa and r.in_corso and r._processo.poll() is not None  # ffmpeg è morto davvero
        time.sleep(1.5)
        assert r.fotogrammi_letti == fermo and 1.2 <= posizione <= 2.6
        r.riprendi()
        assert r.attendi_partenza(5) and not r.in_pausa
        time.sleep(1.5)
        assert 10 <= r.fotogrammi_letti - fermo <= 30  # a ritmo normale, non a raffica
        assert r.posizione_s > posizione + 0.8
        assert terminati == []  # la pausa non è una fine
    finally:
        r.ferma()
    assert not r.in_corso and terminati == []
