"""Anteprima sul PC di come BMO mostrerebbe un video sul suo schermo, prima del deploy.

Usa **la stessa catena di produzione** (`video.py`): ricerca e risoluzione su YouTube, poi ffmpeg
con la stessa risoluzione e gli stessi fotogrammi al secondo che sceglierebbe sul Pi (un 16:9 →
320×180 a 30 fps, un 4:3 → 320×240 a 26, ecc.), rgb565 come lo vedrebbe il pannello. I fotogrammi
sono composti su un canvas **320×240** nero, come lo schermo (il video centrato, le bande spente),
e mostrati in una finestra di mpv ingrandita a pixel netti (`--scala`, 3 = 960×720).

    python -m bmo_core.anteprima_video "queen bohemian rhapsody video ufficiale"
    python -m bmo_core.anteprima_video "daft punk get lucky" --scala 2 --senza-audio
    python -m bmo_core.anteprima_video --file clip.mp4              # un file locale, senza YouTube
    python -m bmo_core.anteprima_video "gatti" --png anteprima.png  # solo un fotogramma, senza finestra

Cosa **non** simula: la dimensione fisica (un 2,4" è ~49×37 mm: la finestra ingrandita è più nitida di
quanto sembrerà), la retroilluminazione e il tempo di trasferimento sul bus SPI (l'hardware non è
arrivato: vedi `docs/decisioni-video-youtube.md`, decisione 4). L'audio esce dal PC, non dalla scheda.
Serve `mpv` (per la finestra) e `ffmpeg`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable

from . import video as v

SCHERMO_L, SCHERMO_A = v.SCHERMO_L, v.SCHERMO_A


def componi(larghezza: int, altezza: int, dati: bytes, canvas: bytearray | None = None) -> bytes:
    """Il fotogramma rgb565 `larghezza`×`altezza` centrato su un canvas nero 320×240 (come lo schermo)."""
    canvas = canvas if canvas is not None else bytearray(SCHERMO_L * SCHERMO_A * 2)
    x0 = (SCHERMO_L - larghezza) // 2
    y0 = (SCHERMO_A - altezza) // 2
    riga = larghezza * 2
    if larghezza == SCHERMO_L:
        inizio = y0 * SCHERMO_L * 2
        canvas[inizio:inizio + len(dati)] = dati
    else:
        for r in range(altezza):
            inizio = ((y0 + r) * SCHERMO_L + x0) * 2
            canvas[inizio:inizio + riga] = dati[r * riga:(r + 1) * riga]
    return bytes(canvas)


def flusso_da_file(percorso: str) -> v.Flusso:
    """La forma che avrebbe un file locale: le dimensioni e gli fps veri, ridotti come sul Pi."""
    uscita = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate",
         "-of", "json", percorso], capture_output=True, text=True, check=True).stdout
    flusso = json.loads(uscita)["streams"][0]
    numeratore, _, denominatore = flusso["avg_frame_rate"].partition("/")
    fps = float(numeratore) / float(denominatore or 1)
    larghezza, altezza = v.dimensioni_schermo(flusso["width"], flusso["height"])
    return v.Flusso([percorso], larghezza, altezza, v.fps_di_riproduzione(fps, larghezza * altezza * 2))


def avvia_finestra(scala: int, fps: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["mpv", "--no-terminal", "--force-window=immediate", "--title=Anteprima BMO — schermo 320x240",
         "--demuxer=rawvideo", f"--demuxer-rawvideo-w={SCHERMO_L}", f"--demuxer-rawvideo-h={SCHERMO_A}",
         "--demuxer-rawvideo-mp-format=rgb565le", f"--demuxer-rawvideo-fps={fps}",
         "--untimed", "--no-cache", "--profile=low-latency", "--scale=nearest", "--dscale=nearest",
         f"--geometry={SCHERMO_L * scala}x{SCHERMO_A * scala}", "--keep-open=no", "-"],
        stdin=subprocess.PIPE)


def esegui(
    flusso: v.Flusso,
    scala: int = 3,
    audio: bool = True,
    secondi: float | None = None,
    png: str | None = None,
    png_dopo: float = 12.0,
    stampa: Callable[[str], None] = print,
) -> int:
    """Mostra il video. Ritorna i fotogrammi consegnati."""
    stampa(f"Schermo 320×240; video {flusso.larghezza}×{flusso.altezza} a {flusso.fps} fps "
           f"({flusso.byte_per_fotogramma // 1000} kB a fotogramma, {flusso.byte_per_fotogramma * flusso.fps / 1e6:.1f} MB/s sul bus)")
    canvas = bytearray(SCHERMO_L * SCHERMO_A * 2)
    finestra = None if png else avvia_finestra(scala, flusso.fps)
    contati = {"n": 0}
    fine = threading.Event()
    primo = {"t": None}
    inizio = time.monotonic()

    def sink(larghezza: int, altezza: int, dati: bytes) -> None:
        contati["n"] += 1
        if primo["t"] is None:
            primo["t"] = time.monotonic() - inizio
        composto = componi(larghezza, altezza, dati, canvas)
        if png:
            if contati["n"] == max(1, int(png_dopo * flusso.fps)):
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb565le",
                                "-s", f"{SCHERMO_L}x{SCHERMO_A}", "-i", "-", "-vf", f"scale={SCHERMO_L * scala}:{SCHERMO_A * scala}:flags=neighbor",
                                "-frames:v", "1", png], input=composto, check=True)
                stampa(f"Fotogramma salvato in {png}")
                fine.set()
            return
        try:
            assert finestra is not None and finestra.stdin is not None
            finestra.stdin.write(composto)
            finestra.stdin.flush()
        except (BrokenPipeError, OSError):
            fine.set()  # finestra chiusa

    riproduzione = v.Riproduzione(flusso, sink, "pulse" if audio and not png else "null", al_termine=fine.set)
    if not riproduzione.attendi_partenza(20):
        stampa("Il video non parte.")
        riproduzione.ferma()
        return 0
    stampa(f"Primo fotogramma dopo {primo['t']:.1f} s. Chiudi la finestra (o Ctrl-C) per fermare.")
    try:
        if secondi:
            fine.wait(secondi)
        else:
            while not fine.is_set() and (finestra is None or finestra.poll() is None):
                time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    riproduzione.ferma()
    if finestra is not None:
        if finestra.stdin:
            try:
                finestra.stdin.close()
            except OSError:
                pass
        finestra.terminate()
    return contati["n"]


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ricerca", nargs="?", help="cosa cercare su YouTube (come lo cercherebbe BMO)")
    parser.add_argument("--file", help="un file video locale invece di YouTube")
    parser.add_argument("--scala", type=int, default=3, help="ingrandimento della finestra (3 = 960×720)")
    parser.add_argument("--senza-audio", action="store_true")
    parser.add_argument("--secondi", type=float, help="ferma dopo tanti secondi")
    parser.add_argument("--png", help="salva un fotogramma e finisci, senza finestra")
    parser.add_argument("--png-dopo", type=float, default=12.0, help="a quanti secondi dall'inizio (con --png)")
    a = parser.parse_args(argomenti)
    if not a.ricerca and not a.file:
        parser.error("serve una ricerca o --file")
    for programma in ("ffmpeg",) + (() if a.png else ("mpv",)):
        if shutil.which(programma) is None:
            sys.exit(f"serve {programma}")
    if a.file:
        flusso = flusso_da_file(a.file)
    else:
        trovati = v.cerca_video(a.ricerca)
        if not trovati:
            sys.exit("nessun risultato")
        for candidato in trovati[:3]:
            try:
                print(f"«{candidato.titolo}» ({v.durata_a_voce(candidato.durata)}, {candidato.canale}): risolvo…")
                flusso = v.risolvi_flusso(candidato)
                break
            except RuntimeError as errore:
                print(f"  non va: {errore}")
        else:
            sys.exit("nessun risultato riproducibile")
    esegui(flusso, a.scala, not a.senza_audio, a.secondi, a.png, a.png_dopo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
