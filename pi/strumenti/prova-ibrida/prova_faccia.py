"""Prova di schermo e camera sul Pi, senza microfono né Gemini (issue #77).

Cicla gli stati della faccia sul display, poi scatta una foto con la camera del
Pi (`BMO_CAMERA=grezza`) e la mostra sullo schermo, come fa `scatta_foto` in
conversazione. Va lanciato con `bmo_face.pannello --uscita spi` già in ascolto
sul socket (`BMO_SOCKET`): lo fa `prova_schermo.sh`.

    python prova_faccia.py [--secondi 3] [--senza-foto]
"""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from bmo_core.adapters.base import (
    STATO_ASCOLTO,
    STATO_ASSONNATO,
    STATO_CONFERMA,
    STATO_ERRORE,
    STATO_IDLE,
    STATO_PARLATO,
    STATO_PENSIERO,
)
from bmo_core.adapters.factory import crea_camera, crea_faccia


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--secondi", type=float, default=3.0, help="quanto resta ogni stato")
    parser.add_argument("--senza-foto", action="store_true", help="salta la camera")
    argomenti = parser.parse_args()

    faccia = crea_faccia()
    for stato in (STATO_ASSONNATO, STATO_IDLE, STATO_ASCOLTO, STATO_PENSIERO, STATO_ERRORE, STATO_CONFERMA, STATO_IDLE):
        print(f"stato: {stato}", flush=True)
        faccia.mostra(stato)
        time.sleep(argomenti.secondi)

    print("stato: parlato (bocca che si muove)", flush=True)
    faccia.mostra(STATO_PARLATO)
    faccia.parla([0.1, 0.8, 0.3, 0.9, 0.2, 0.7, 0.1] * 10, fps=10.0)
    time.sleep(argomenti.secondi + 4)

    print("timer: 1:30 'pasta'", flush=True)
    faccia.timer(90, "pasta")
    time.sleep(argomenti.secondi)
    faccia.timer(0, None)
    faccia.mostra(STATO_IDLE)

    if not argomenti.senza_foto:
        print("scatto una foto con la camera del Pi...", flush=True)
        with tempfile.TemporaryDirectory(prefix="bmo-prova-") as cartella:
            inizio = time.monotonic()
            foto = crea_camera().scatta_foto(Path(cartella) / "foto.jpg")
            print(f"foto scattata in {time.monotonic() - inizio:.1f} s ({foto.stat().st_size // 1024} kB): la mostro", flush=True)
            faccia.immagine(foto.read_bytes(), ttl=8.0)
            time.sleep(9)
    faccia.mostra(STATO_IDLE)
    print("fine", flush=True)


if __name__ == "__main__":
    main()
