"""Picco di PSS di mpv sul Pi: voce (catena vecchia e nuova) e radio vera (#58).

Uscita audio nulla (`--ao=null`): si misura mpv, non la scheda audio.

    venv/bin/python -W ignore peso_mpv.py bmo-core <clip.mp3>
"""
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "src"))
from bmo_core.adapters.audio_output import _NORM, OPZIONI_MPV_LEGGERE, catena_voce  # noqa: E402
from bmo_core.radio import cerca_stazioni  # noqa: E402

clip = sys.argv[2]
nuova = catena_voce(None, None)
vecchia = nuova.replace("volume=6.4dB,alimiter=limit=0.84:level=false", _NORM)
RADIO = ["--cache=yes", "--cache-secs=10", "--demuxer-max-bytes=1MiB", "--demuxer-max-back-bytes=0"]


def misura(nome, argomenti, durata=None):
    prima = resource.getrusage(resource.RUSAGE_CHILDREN)
    inizio = time.monotonic()
    p = subprocess.Popen(["mpv", "--no-video", "--really-quiet", "--ao=null", *argomenti],
                         stderr=subprocess.PIPE, text=True)
    picco = 0
    while p.poll() is None and (durata is None or time.monotonic() - inizio < durata):
        try:
            for riga in open(f"/proc/{p.pid}/smaps_rollup"):
                if riga.startswith("Pss:"):
                    picco = max(picco, int(riga.split()[1]))
        except (FileNotFoundError, ProcessLookupError):
            break
        time.sleep(0.05)
    if p.poll() is None:
        p.terminate()
    errori = p.communicate()[1].strip()
    dopo = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (dopo.ru_utime + dopo.ru_stime) - (prima.ru_utime + prima.ru_stime)
    print(f"{nome:<40} picco PSS {picco / 1024:5.1f} MB  CPU {cpu:5.2f} s  in {time.monotonic() - inizio:4.1f} s"
          + (f"  ERRORE: {errori[:120]}" if p.returncode not in (0, -15) else ""))


misura("voce, mpv normale, con loudnorm", [f"--af=lavfi=[{vecchia}]", clip])
misura("voce, mpv leggero, con loudnorm", [*OPZIONI_MPV_LEGGERE, f"--af=lavfi=[{vecchia}]", clip])
misura("voce, mpv leggero, guadagno fisso (nuovo)", [*OPZIONI_MPV_LEGGERE, f"--af=lavfi=[{nuova}]", clip])
stazione = cerca_stazioni("jazz")[0]
misura("radio 30 s, mpv normale", [stazione.url], durata=30)
misura("radio 30 s, mpv leggero + cache corta", [*OPZIONI_MPV_LEGGERE, *RADIO, stazione.url], durata=30)
