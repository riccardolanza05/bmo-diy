"""Quanto ci mette ffmpeg ad arrivare al primo fotogramma, con opzioni di probing diverse.

Risolve un video una volta (~3-4 s) e poi lancia ffmpeg più volte con le
stesse opzioni di base più una variante, cronometrando l'arrivo del primo
fotogramma rgb565 (la latenza che si sente dopo la risoluzione).

    venv/bin/python pi/avvio_ffmpeg_pi.py "queen bohemian rhapsody video ufficiale"
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bmo-core" / "src"))
import os  # noqa: E402

os.environ["PYTHONPATH"] = sys.path[0]
from bmo_core import video  # noqa: E402

VARIANTI = {
    "base": [],
    "probesize 256k": ["-probesize", "256k"],
    "probesize 256k analyzeduration 0": ["-probesize", "256k", "-analyzeduration", "0"],
    "probesize 64k analyzeduration 0": ["-probesize", "64k", "-analyzeduration", "0"],
    "nobuffer + probesize 256k": ["-fflags", "nobuffer", "-probesize", "256k", "-analyzeduration", "0"],
}


def primo_fotogramma(flusso, extra):
    comando = video.comando_ffmpeg(flusso, "null", opzioni_ingresso=tuple(extra))
    t = time.monotonic()
    p = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    blocco = p.stdout.read(flusso.byte_per_fotogramma)
    dt = time.monotonic() - t
    p.kill()  # terminate() lascia ffmpeg appeso se sta leggendo dalla rete
    p.wait()
    return dt if len(blocco) == flusso.byte_per_fotogramma else None


trovati = video.cerca_video(sys.argv[1])
flusso = video.risolvi_flusso(trovati[0])
print(f"{trovati[0].titolo[:50]} -> {flusso.larghezza}x{flusso.altezza}@{flusso.fps}, {len(flusso.indirizzi)} indirizzi", flush=True)
for nome, extra in VARIANTI.items():
    tempi = [primo_fotogramma(flusso, extra) for _ in range(3)]
    print(f"{nome:<36} " + "  ".join(f"{t:.2f}s" if t else "ERRORE" for t in tempi), flush=True)
