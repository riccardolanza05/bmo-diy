import json
import shutil
import subprocess

import pytest

from bmo_core import video
from bmo_core.video import BYTE_PER_FOTOGRAMMA, Video, cerca_video, comando_ffmpeg, risolvi_flussi


def _riga(id, durata, titolo="t", **extra):
    return json.dumps({"id": id, "duration": durata, "title": titolo, **extra})


def test_cerca_scarta_dirette_e_maratone():
    uscita = "\n".join([
        _riga("a", 200, "bello", channel="Canale"),
        _riga("live", None),
        _riga("lungo", video.DURATA_MASSIMA_S + 1),
        "non è json",
        _riga("b", 90),
    ])
    trovati = cerca_video("gatti", esegui=lambda argomenti: uscita)
    assert [v.id for v in trovati] == ["a", "b"]
    assert trovati[0].canale == "Canale"
    assert trovati[0].pagina == "https://www.youtube.com/watch?v=a"


def test_cerca_chiede_a_ytdlp_la_query_giusta():
    visti = []
    cerca_video("  jazz  ", quanti=3, esegui=lambda argomenti: visti.append(argomenti) or "")
    assert visti[0][-1] == "ytsearch6:jazz"


def test_risolvi_tiene_solo_gli_indirizzi():
    uscita = "https://v.example/video\nhttps://a.example/audio\n"
    assert risolvi_flussi(Video("a", "t", 10), esegui=lambda a: uscita) == [
        "https://v.example/video", "https://a.example/audio"]
    with pytest.raises(RuntimeError):
        risolvi_flussi(Video("a", "t", 10), esegui=lambda a: "")


def test_comando_un_ingresso_prende_l_audio_dal_primo():
    comando = comando_ffmpeg(["http://x"], "null")
    assert comando.count("-i") == 1 and "0:a:0" in comando and "format=rgb565le" in " ".join(comando)


def test_comando_due_ingressi_prende_l_audio_dal_secondo():
    comando = comando_ffmpeg(["http://v", "http://a"], "alsa:hw:1")
    assert comando.count("-i") == 2 and "1:a:0" in comando
    assert comando[-3:] == ["-f", "alsa", "hw:1"]


def test_fotogrammi_scarta_il_blocco_incompleto():
    dati = [b"x" * BYTE_PER_FOTOGRAMMA, b"y" * BYTE_PER_FOTOGRAMMA, b"z" * 10]

    class Flusso:
        def read(self, n):
            return dati.pop(0) if dati else b""

    class Processo:
        stdout = Flusso()

    assert len(list(video.fotogrammi(Processo()))) == 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
def test_riproduci_file_locale_consegna_fotogrammi_della_misura_giusta(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=426x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", str(clip)], check=True)
    blocchi = []
    n = video.riproduci([str(clip)], blocchi.append, uscita_audio="null")
    assert n == len(blocchi) and 28 <= n <= 32  # 2 s a 15 fps
    assert all(len(b) == BYTE_PER_FOTOGRAMMA for b in blocchi)
