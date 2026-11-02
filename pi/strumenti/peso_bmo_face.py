"""Peso di bmo-face senza GTK: il renderer che userà anche l'uscita SPI. Issue #58.

Sul Pi, con numpy e pillow in un venv e bmo-face (con assets/) accanto:

    venv/bin/python -W ignore peso_bmo_face.py bmo-face
"""
import sys
import time
from pathlib import Path

FACE = Path(sys.argv[1])
sys.path.insert(0, str(FACE / "src"))


def mem():
    v = {}
    for r in open("/proc/self/smaps_rollup"):
        p = r.split()
        if len(p) > 1 and p[1].isdigit():
            v[p[0][:-1]] = int(p[1])
    return v["Rss"] // 1024, v["Pss"] // 1024


ultimo = mem()


def tappa(nome):
    global ultimo
    ora = mem()
    print(f"{nome:<40}{ora[0]:>6}{ora[0] - ultimo[0]:>+6}{ora[1]:>6}", flush=True)
    ultimo = ora


print(f"{'tappa':<40}{'RSS':>6}{'Δ':>6}{'PSS':>6}")
tappa("python nudo")
from bmo_face.animazione import ComandoFaccia, Renderer  # noqa: E402
from bmo_face.formato import carica_manifesto, mappa_bin  # noqa: E402
from bmo_face.servitore import ServitoreFaccia  # noqa: E402,F401

tappa("import (numpy, PIL, animazione, socket)")
manifesto = carica_manifesto(FACE / "assets" / "faces.json")
with mappa_bin(FACE / "assets" / "faces.bin") as dati:
    renderer = Renderer(manifesto, dati)
    tappa("asset mappati + renderer")
    comando = ComandoFaccia()
    t0 = time.time()
    n = 0
    for stato in ("idle", "ascolto", "pensiero", "parlato") * 25:
        comando.stato = stato
        comando.livello = 0.5
        renderer.disegna(comando, time.time())
        n += 1
    durata = time.time() - t0
    tappa(f"dopo {n} fotogrammi ({n / durata:.0f} fps)")
