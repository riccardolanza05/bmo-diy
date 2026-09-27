"""Peso di bmo-core a tappe, com'è oggi o alleggerito (--leggero). Issue #58.

--leggero: openwakeword senza il suo custom_verifier_model (sklearn/scipy)
e sessioni ONNX senza arena, a un thread. Nessuna chiamata di rete: la
chiave API è finta, serve solo a costruire il client.

Sul Pi, con le dipendenze di bmo-core in un venv e bmo-core copiato accanto:

    venv/bin/python -W ignore peso_bmo_core.py bmo-core
    venv/bin/python -W ignore peso_bmo_core.py bmo-core --leggero
    venv/bin/python -W ignore peso_bmo_core.py bmo-core --leggero --un-modello
"""
import os
import sys
import time
import types
from pathlib import Path

CORE = Path(sys.argv[1])
LEGGERO = "--leggero" in sys.argv
N_MODELLI = 1 if "--un-modello" in sys.argv else 3
os.environ.setdefault("GEMINI_API_KEY", "chiave-finta-nessuna-chiamata")
os.environ.setdefault("BMO_ENV", "dev-linux")
sys.path.insert(0, str(CORE / "src"))


def mem():
    v = {}
    for r in open("/proc/self/smaps_rollup"):
        p = r.split()
        if len(p) > 1 and p[1].isdigit():
            v[p[0][:-1]] = int(p[1])
    return v["Rss"] // 1024, v["Pss"] // 1024


t0 = time.time()
ultimo = mem()
print(f"{'tappa':<44}{'RSS':>6}{'Δ':>6}{'PSS':>6}  tempo")


def tappa(nome):
    global ultimo, t0
    ora = mem()
    print(f"{nome:<44}{ora[0]:>6}{ora[0] - ultimo[0]:>+6}{ora[1]:>6}  {time.time() - t0:5.1f}s", flush=True)
    ultimo, t0 = ora, time.time()


tappa("python nudo")
import numpy as np  # noqa: E402

import onnxruntime as ort  # noqa: E402

tappa("numpy + onnxruntime")
if LEGGERO:
    _originale = ort.InferenceSession.__init__

    def _init(self, percorso, sess_options=None, *a, **k):
        opzioni = sess_options or ort.SessionOptions()
        opzioni.enable_cpu_mem_arena = False
        opzioni.enable_mem_pattern = False
        opzioni.intra_op_num_threads = 1
        opzioni.inter_op_num_threads = 1
        _originale(self, percorso, opzioni, *a, **k)

    ort.InferenceSession.__init__ = _init
    finto = types.ModuleType("openwakeword.custom_verifier_model")
    finto.train_custom_verifier = None
    sys.modules["openwakeword.custom_verifier_model"] = finto
import openwakeword  # noqa: E402,F401

tappa("openwakeword" + (" (senza sklearn/scipy)" if LEGGERO else ""))
import google.genai  # noqa: E402,F401

tappa("google.genai")
import bmo_core.macchina  # noqa: E402,F401

tappa("bmo_core.macchina (+edge_tts, ddgs, ...)")
from bmo_core.richiamo import _carica_rilevatore  # noqa: E402

modello = _carica_rilevatore([str(CORE / "modelli-wake-word" / f"bmo{i}.onnx") for i in (1, 2, 3)][:N_MODELLI])
tappa(f"{N_MODELLI} modelli wake word caricati")
for _ in range(50):
    modello.predict(np.zeros(1280, dtype=np.int16))
tappa("dopo 50 finestre di ascolto (4 s)")
from bmo_core.brain import Cervello  # noqa: E402
from bmo_core.macchina import crea_faccia  # noqa: E402

cervello = Cervello(faccia=crea_faccia(sul_terminale=True))
tappa("Cervello costruito (client Gemini)")
for _ in range(250):
    modello.predict(np.zeros(1280, dtype=np.int16))
tappa("dopo altre 250 finestre (20 s)")
