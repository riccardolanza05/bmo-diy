#!/usr/bin/env python3
"""Calibrazione guidata della wake word col microfono VERO del HAT (issue #79).

Strumento di misura: il servizio NON lo importa. Sul Pi, con `bmo-core` fermo (il microfono è
esclusivo: `sudo systemctl stop bmo-core`):

    PYTHONPATH=~/bmo-pi/bmo-diy/bmo-core/src ~/bmo-pi/venv/bin/python calibra_wake_word.py \\
        --etichetta 3m --capture 40 --boost 2 --ripetizioni 5

Cosa fa: imposta (senza sudo) il guadagno di cattura e il boost del mixer; ascolta `--base` secondi di
ambiente (i punteggi lì sono falsi positivi), poi per `--ripetizioni` volte suona un BIP dall'altoparlante
e ascolta `--finestra` secondi: nel bip dici «Hey BMO». Per ogni bip stampa il livello della voce
(rms/picco in dBFS) e il punteggio massimo di ciascun modello, e in fondo quante ripetizioni
supererebbero ciascuna soglia e quanti falsi positivi ci sono nell'ambiente.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

SOGLIE = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7)
SCHEDA = "wm8960soundcard"
PEZZO_S = 1280 / 16000


def mixer(*args: str) -> None:
    subprocess.run(["amixer", "-c", SCHEDA, "-q", *args], check=False)


def bip() -> None:
    t = np.arange(int(0.18 * 48000)) / 48000
    onda = (0.35 * np.sin(2 * np.pi * 1000 * t) * 32767).astype("<i2")
    stereo = np.repeat(onda[:, None], 2, axis=1).tobytes()
    subprocess.run(["aplay", "-q", "-D", f"plughw:CARD={SCHEDA},DEV=0", "-t", "raw", "-f", "S16_LE",
                    "-r", "48000", "-c", "2"], input=stereo, check=False)


def dbfs(x: float) -> float:
    return 20 * np.log10(max(x, 1.0) / 32768)


def analizza(registro: list[tuple[float, np.ndarray, dict[str, float]]], cue: list[float], base_s: float,
             finestra_s: float, ritardo_s: float) -> dict:
    """`registro`: (istante, pezzo int16, punteggi per modello). Restituisce basi e ripetizioni."""
    base = [r for r in registro if r[0] < base_s]
    modelli = sorted({m for r in registro for m in r[2]})
    out = {"modelli": modelli, "base": {}, "rip": []}
    if base:
        out["base"]["rms_dbfs"] = dbfs(float(np.sqrt(np.mean(np.concatenate([r[1] for r in base]).astype(np.float64) ** 2))))
        out["base"]["max_punteggio"] = max((max(r[2].values(), default=0.0) for r in base), default=0.0)
    for c in cue:
        w = [r for r in registro if c + ritardo_s <= r[0] < c + ritardo_s + finestra_s]
        if not w:
            continue
        audio = np.concatenate([r[1] for r in w]).astype(np.float64)
        pun = {m: max((r[2].get(m, 0.0) for r in w), default=0.0) for m in modelli}
        out["rip"].append({
            "t": c, "rms_dbfs": dbfs(float(np.sqrt(np.mean(audio ** 2)))),
            "picco_dbfs": dbfs(float(np.abs(audio).max())), "punteggi": pun, "max": max(pun.values()),
        })
    return out


def stampa(r: dict, etichetta: str, capture: str, boost: str) -> None:
    print(f"# {etichetta}: Capture {capture}, boost {boost}")
    print(f"  ambiente: rms {r['base'].get('rms_dbfs', float('nan')):.1f} dBFS, punteggio massimo {r['base'].get('max_punteggio', 0.0):.2f} (falsi positivi sopra la soglia)")
    for i, x in enumerate(r["rip"], 1):
        det = "  ".join(f"{m}={v:.2f}" for m, v in x["punteggi"].items())
        sat = "  SATURA" if x["picco_dbfs"] > -1.0 else ""
        print(f"  #{i}: voce rms {x['rms_dbfs']:6.1f} picco {x['picco_dbfs']:6.1f} dBFS | max {x['max']:.2f} | {det}{sat}")
    n = len(r["rip"])
    if n:
        riga = "  ".join(f">={s}: {sum(1 for x in r['rip'] if x['max'] >= s)}/{n}" for s in SOGLIE)
        print(f"  riconosciute per soglia: {riga}")
        print(f"  punteggio medio {np.mean([x['max'] for x in r['rip']]):.2f}, minimo {min(x['max'] for x in r['rip']):.2f}; "
              f"ambiente max {r['base'].get('max_punteggio', 0.0):.2f}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--etichetta", default="")
    p.add_argument("--capture", default=None, help="guadagno di cattura 0-63 (amixer sset Capture)")
    p.add_argument("--boost", default=None, help="boost LINPUT1/RINPUT1 0-3")
    p.add_argument("--ripetizioni", type=int, default=5)
    p.add_argument("--base", type=float, default=6.0, help="secondi di ambiente prima del primo bip")
    p.add_argument("--finestra", type=float, default=3.0, help="secondi dopo ogni bip in cui dire «Hey BMO»")
    p.add_argument("--pausa", type=float, default=1.5, help="secondi di pausa fra una finestra e il bip dopo")
    p.add_argument("--ritardo", type=float, default=0.35, help="secondi dopo il bip prima della finestra")
    p.add_argument("--dispositivo", default=f"hw:CARD={SCHEDA},DEV=0")
    p.add_argument("--cartella-modelli", default=str(Path.home() / "bmo-pi/bmo-diy/bmo-core/modelli-wake-word"))
    a = p.parse_args()

    from bmo_core.adapters.audio_input import ArecordConvertitoreAdapter
    from bmo_core.wake_word import CAMPIONI_PER_PEZZO, RilevatoreLeggero

    if a.capture is not None:
        mixer("sset", "Capture", str(a.capture))
    if a.boost is not None:
        mixer("cset", "name=Left Input Boost Mixer LINPUT1 Volume", str(a.boost))
        mixer("cset", "name=Right Input Boost Mixer RINPUT1 Volume", str(a.boost))

    modelli = [str(m) for m in sorted(Path(a.cartella_modelli).glob("bmo*.onnx"))]
    rilevatore = RilevatoreLeggero(modelli)
    microfono = ArecordConvertitoreAdapter(dispositivo=a.dispositivo)

    registro: list[tuple[float, np.ndarray, dict[str, float]]] = []
    cue: list[float] = []
    fine = a.base + a.ripetizioni * (0.18 + a.ritardo + a.finestra + a.pausa) + 0.5
    t0 = time.time()
    prossimo = a.base

    def pianifica() -> None:
        nonlocal prossimo
        for _ in range(a.ripetizioni):
            attesa = prossimo - (time.time() - t0)
            if attesa > 0:
                time.sleep(attesa)
            cue.append(time.time() - t0)
            print(f"  >>> {len(cue)}/{a.ripetizioni}: DI' «HEY BMO» ORA", flush=True)
            bip()
            prossimo = (time.time() - t0) + a.ritardo + a.finestra + a.pausa

    threading.Thread(target=pianifica, daemon=True).start()
    resto = np.empty(0, dtype=np.int16)
    flusso = microfono.flusso_pcm()
    try:
        for grezzo in flusso:
            resto = np.concatenate([resto, np.frombuffer(grezzo, dtype=np.int16)])
            while len(resto) >= CAMPIONI_PER_PEZZO:
                pezzo, resto = resto[:CAMPIONI_PER_PEZZO], resto[CAMPIONI_PER_PEZZO:]
                t = time.time() - t0
                registro.append((t, pezzo, {k: float(v) for k, v in rilevatore.predict(pezzo).items()}))
            if time.time() - t0 >= fine:
                break
    finally:
        flusso.close()
    stampa(analizza(registro, cue, a.base, a.finestra, a.ritardo), a.etichetta, str(a.capture), str(a.boost))
    return 0


if __name__ == "__main__":
    sys.exit(main())
