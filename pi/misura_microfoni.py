#!/usr/bin/env python3
"""Livello dei due microfoni MEMS del HAT WM8960, canale per canale (issue #79).

Strumento di misura: il servizio NON lo importa. Registra con gli stessi parametri di bmo-core
(`arecord`, S32_LE, 48 kHz, stereo) e stampa per ciascun canale RMS e picco in dBFS, campioni in
clipping, offset continuo. Un microfono morto o scollegato si vede subito (canale a -inf o
molto più basso dell'altro), cosa che una somma in mono nasconderebbe.

    python3 misura_microfoni.py --secondi 5 --etichetta silenzio
    python3 misura_microfoni.py --secondi 5 --etichetta voce-1m
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys

import numpy as np

DISPOSITIVO_PREDEFINITO = "hw:CARD=wm8960soundcard,DEV=0"
PIENA_SCALA = float(2**31)


def registra(dispositivo: str, secondi: float, frequenza: int = 48000) -> np.ndarray:
    campioni = round(secondi * frequenza)
    grezzo = subprocess.run(
        ["arecord", "-q", "-D", dispositivo, "-f", "S32_LE", "-r", str(frequenza), "-c", "2",
         "-s", str(campioni), "-t", "raw", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(grezzo, dtype="<i4").reshape(-1, 2)


def dbfs(x: float) -> float:
    return 20 * math.log10(x / PIENA_SCALA) if x > 0 else float("-inf")


def misura(canale: np.ndarray) -> dict[str, float]:
    f = canale.astype(np.float64)
    rms = float(np.sqrt(np.mean((f - f.mean()) ** 2)))
    picco = float(np.max(np.abs(f)))
    return {
        "rms_dbfs": dbfs(rms),
        "picco_dbfs": dbfs(picco),
        "clipping": int(np.sum(np.abs(canale.astype(np.int64)) >= 2**31 - 2**8)),
        "offset_dbfs": dbfs(abs(float(f.mean()))),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dispositivo", default=DISPOSITIVO_PREDEFINITO)
    p.add_argument("--secondi", type=float, default=5.0)
    p.add_argument("--etichetta", default="")
    a = p.parse_args()
    audio = registra(a.dispositivo, a.secondi)
    print(f"# {a.etichetta or 'misura'}: {len(audio)} campioni, {a.dispositivo}")
    for nome, i in (("sinistro", 0), ("destro", 1)):
        m = misura(audio[:, i])
        print(f"{nome:9s} rms {m['rms_dbfs']:7.1f} dBFS  picco {m['picco_dbfs']:7.1f} dBFS  "
              f"clipping {m['clipping']:6d}  offset {m['offset_dbfs']:7.1f} dBFS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
