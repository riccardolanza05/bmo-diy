"""Prova dell'audio ibrido, con gli adapter veri di bmo-core (issue #77).

Sul Pi: legge qualche secondo dal microfono del PC (adapter d'ingresso del Pi
-> `arecord` finto -> tunnel SSH -> `parec` sul PC) e ne stampa il livello, poi
fa suonare sugli altoparlanti del PC i due suoni di BMO (adapter d'uscita ->
`mpv` finto -> PulseAudio -> tunnel). Si lancia con `avvia_ibrida.sh --solo-audio`.

Mentre legge il microfono, parla o batti le mani: il livello deve salire.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

import bmo_core
from bmo_core.adapters.factory import crea_audio_input, crea_audio_output

SECONDI = 4.0
FREQUENZA = 16000  # l'adapter del Pi restituisce già PCM S16 mono a 16 kHz


def livello_dbfs(pcm: bytes) -> tuple[float, float]:
    campioni = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float64) / 32768
    rms = float(np.sqrt((campioni**2).mean())) if campioni.size else 0.0
    return 20 * np.log10(max(rms, 1e-9)), float(np.abs(campioni).max()) if campioni.size else 0.0


def main() -> None:
    ingresso = crea_audio_input()
    print(f"adapter d'ingresso: {type(ingresso).__name__}", flush=True)
    print(f"leggo {SECONDI:.0f} s dal microfono del PC (parla o batti le mani)...", flush=True)
    voluti = int(SECONDI * FREQUENZA) * 2
    pcm = b""
    inizio = time.monotonic()
    flusso = ingresso.flusso_pcm()
    secondo = 0
    for pezzo in flusso:
        pcm += pezzo
        if len(pcm) // (FREQUENZA * 2) > secondo:
            secondo = len(pcm) // (FREQUENZA * 2)
            db, picco = livello_dbfs(pcm[-FREQUENZA * 2:])
            print(f"  secondo {secondo}: {db:6.1f} dBFS (picco {picco:.3f})", flush=True)
        if len(pcm) >= voluti:
            break
    flusso.close()
    durata = time.monotonic() - inizio
    db, picco = livello_dbfs(pcm)
    print(f"ricevuti {len(pcm)} byte PCM 16 kHz mono in {durata:.1f} s (attesi {SECONDI:.0f} s: tempo reale = "
          f"{'sì' if abs(durata - SECONDI) < 1.0 else 'NO'}); livello medio {db:.1f} dBFS, picco {picco:.3f}", flush=True)

    uscita = crea_audio_output()
    audio = Path(bmo_core.__file__).parent / "audio"
    for nome in ("scatto.ogg", "errore.ogg"):
        print(f"suono sugli altoparlanti del PC: {nome}", flush=True)
        uscita.riproduci(audio / nome)
        uscita.attendi(timeout_s=10)
        time.sleep(0.5)
    print("fine", flush=True)


if __name__ == "__main__":
    main()
