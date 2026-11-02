#!/usr/bin/env python3
"""Sensibilità del microfono del HAT alla wake word, col microfono VERO (issue #79).

Strumento di misura: il servizio NON lo importa. Ascolta per `--secondi` con gli stessi
adapter e gli stessi modelli di bmo-core, e per ogni modello stampa: il punteggio massimo al
secondo, gli eventi sopra `--soglia` e, alla fine, quante rilevazioni distinte (rifrattario
2 s) ci sarebbero a 0,3 / 0,5 / 0,7 e il livello medio del microfono. Serve a due cose:

  * vera sensibilità: dire «Hey BMO» N volte a 1 m, 2 m, 3 m (annotando i momenti) e contare;
  * falsi positivi: lasciarlo in ascolto con la stanza normale, la TV, la musica, la radio di BMO.

    PYTHONPATH=~/bmo-test/albero/bmo-core/src python3 prova_sensibilita.py --secondi 60 --etichetta 1m
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from bmo_core.adapters.audio_input import ArecordConvertitoreAdapter
from bmo_core.wake_word import CAMPIONI_PER_PEZZO, RilevatoreLeggero

SOGLIE = (0.3, 0.5, 0.7)
RIFRATTARIO_S = 2.0
PEZZO_S = CAMPIONI_PER_PEZZO / 16000


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--secondi", type=float, default=60.0)
    p.add_argument("--dispositivo", default="hw:CARD=wm8960soundcard,DEV=0")
    p.add_argument("--cartella-modelli", default=str(Path.home() / "bmo-test/albero/bmo-core/modelli-wake-word"))
    p.add_argument("--soglia", type=float, default=0.3, help="stampa gli eventi sopra questa soglia")
    p.add_argument("--etichetta", default="")
    a = p.parse_args()

    modelli = [str(m) for m in sorted(Path(a.cartella_modelli).glob("bmo*.onnx"))]
    rilevatore = RilevatoreLeggero(modelli)
    microfono = ArecordConvertitoreAdapter(dispositivo=a.dispositivo)
    print(f"# {a.etichetta or 'sensibilità'}: {len(modelli)} modelli, {a.secondi:.0f} s, {a.dispositivo}", flush=True)

    resto = np.empty(0, dtype=np.int16)
    t0 = time.time()
    massimi: dict[str, float] = {}
    max_secondo: dict[str, float] = {}
    rilevazioni = {s: {} for s in SOGLIE}  # soglia -> modello -> lista di istanti
    ultimo = {s: {} for s in SOGLIE}
    quadrati = 0.0
    n_campioni = 0
    picco = 0
    prossimo_secondo = 1.0
    flusso = microfono.flusso_pcm()
    try:
        for grezzo in flusso:
            resto = np.concatenate([resto, np.frombuffer(grezzo, dtype=np.int16)])
            while len(resto) >= CAMPIONI_PER_PEZZO:
                pezzo, resto = resto[:CAMPIONI_PER_PEZZO], resto[CAMPIONI_PER_PEZZO:]
                t = time.time() - t0
                quadrati += float(np.sum(pezzo.astype(np.float64) ** 2))
                n_campioni += len(pezzo)
                picco = max(picco, int(np.abs(pezzo.astype(np.int32)).max()))
                for nome, punteggio in rilevatore.predict(pezzo).items():
                    punteggio = float(punteggio)
                    massimi[nome] = max(massimi.get(nome, 0.0), punteggio)
                    max_secondo[nome] = max(max_secondo.get(nome, 0.0), punteggio)
                    for s in SOGLIE:
                        if punteggio >= s and t - ultimo[s].get(nome, -99) >= RIFRATTARIO_S:
                            rilevazioni[s].setdefault(nome, []).append(round(t, 1))
                            ultimo[s][nome] = t
                    if punteggio >= a.soglia and t - ultimo[a.soglia if a.soglia in SOGLIE else SOGLIE[0]].get(nome, -99) < 0.2:
                        print(f"{t:6.1f}s  {nome}  {punteggio:.2f}", flush=True)
                if t >= prossimo_secondo:
                    riga = "  ".join(f"{n}={v:.2f}" for n, v in sorted(max_secondo.items()))
                    print(f"{t:5.0f}s  max {riga}", flush=True)
                    max_secondo = {}
                    prossimo_secondo += 1.0
                if t >= a.secondi:
                    raise StopIteration
    except StopIteration:
        pass
    finally:
        flusso.close()
    rms = 20 * np.log10(max(np.sqrt(quadrati / max(n_campioni, 1)), 1) / 32768)
    print(f"# livello medio {rms:.1f} dBFS, picco {20 * np.log10(max(picco, 1) / 32768):.1f} dBFS")
    for nome, v in sorted(massimi.items()):
        conteggi = "  ".join(f">={s}: {len(rilevazioni[s].get(nome, []))}" for s in SOGLIE)
        print(f"# {nome}: max {v:.2f}   rilevazioni distinte {conteggi}")
    tutte = {s: sorted({t for lista in rilevazioni[s].values() for t in lista}) for s in SOGLIE}
    for s in SOGLIE:
        print(f"# soglia {s}: istanti (qualunque modello) {tutte[s]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
