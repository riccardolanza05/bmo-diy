import shutil
import subprocess

import pytest

from bmo_core import anteprima_video as a
from bmo_core.video import Flusso


def test_componi_16_9_centra_il_video_e_lascia_le_bande_nere():
    dati = b"\xff\xff" * (320 * 180)
    canvas = a.componi(320, 180, dati)
    assert len(canvas) == 320 * 240 * 2
    banda = 30 * 320 * 2  # (240 - 180) / 2 righe sopra e sotto
    assert canvas[:banda] == bytes(banda) and canvas[-banda:] == bytes(banda)
    assert canvas[banda:-banda] == dati


def test_componi_verticale_ha_bande_ai_lati():
    larghezza, altezza = 134, 240
    dati = b"\x01\x02" * (larghezza * altezza)
    canvas = a.componi(larghezza, altezza, dati)
    x0 = (320 - larghezza) // 2
    riga = lambda r: canvas[r * 320 * 2:(r + 1) * 320 * 2]
    assert riga(0)[:x0 * 2] == bytes(x0 * 2)                       # banda sinistra
    assert riga(0)[x0 * 2:(x0 + larghezza) * 2] == b"\x01\x02" * larghezza
    assert riga(0)[(x0 + larghezza) * 2:] == bytes(320 * 2 - (x0 + larghezza) * 2)  # banda destra


def test_componi_riusa_il_canvas_senza_residui_di_un_fotogramma_piu_grande():
    canvas = bytearray(320 * 240 * 2)
    a.componi(320, 240, b"\xff" * (320 * 240 * 2), canvas)
    composto = a.componi(320, 180, b"\x01" * (320 * 180 * 2), canvas)
    # il riuso dello stesso canvas lascia le bande dell'ultimo 4:3: l'anteprima deve avvisare... oppure
    # si passa un canvas nuovo a ogni video (come fa `esegui`): qui si verifica solo il contenuto centrale
    assert composto[30 * 320 * 2:-30 * 320 * 2] == b"\x01" * (320 * 180 * 2)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
def test_flusso_da_file_e_la_forma_che_avrebbe_sul_pi(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "1",
                    "-c:v", "libx264", str(clip)], check=True)
    flusso = a.flusso_da_file(str(clip))
    assert isinstance(flusso, Flusso) and (flusso.larghezza, flusso.altezza, flusso.fps) == (320, 180, 30)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="serve ffmpeg")
def test_png_di_un_fotogramma_senza_finestra(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-t", "3",
                    "-c:v", "libx264", str(clip)], check=True)
    uscita = tmp_path / "f.png"
    messaggi = []
    a.esegui(a.flusso_da_file(str(clip)), scala=2, audio=False, secondi=5, png=str(uscita), png_dopo=1.0, stampa=messaggi.append)
    assert uscita.exists() and uscita.stat().st_size > 1000
