"""Quanta RAM *anonima* usa ffmpeg mentre riproduce un video, e cosa la riduce.

Il PSS conta anche le librerie condivise (file, recuperabili dal kernel): per il tetto di memoria del
servizio conta soprattutto la parte anonima. Risolve un video una volta e lancia ffmpeg con opzioni di
decodifica diverse per 12 s ciascuna, a ritmo reale, campionando Pss_Anon / Pss_File / Rss e la CPU.

    venv/bin/python pi/ffmpeg_ram.py "queen bohemian rhapsody video ufficiale"
"""
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "bmo-core" / "src")
sys.path.insert(0, SRC)
os.environ["PYTHONPATH"] = SRC
from bmo_core import video  # noqa: E402

VARIANTI = {
    "base (thread automatici)": ((), ()),
    "decoder -threads 1": (("-threads", "1"), ()),
    "decoder + filtri 1 thread": (("-threads", "1"), ("-filter_threads", "1", "-filter_complex_threads", "1")),
    "-threads 2": (("-threads", "2"), ()),
    "probesize/analyze minimi": (("-probesize", "128k", "-analyzeduration", "0"), ()),
}


def mem(pid):
    v = {}
    try:
        for r in open(f"/proc/{pid}/smaps_rollup"):
            p = r.split()
            if len(p) > 1 and p[1].isdigit():
                v[p[0][:-1]] = int(p[1])
    except OSError:
        pass
    return v


def prova(flusso, in_opts, out_opts, secondi=12):
    comando = video.comando_ffmpeg(flusso, "null", opzioni_ingresso=in_opts)
    if out_opts:
        comando[1:1] = list(out_opts)  # opzioni globali dopo il nome del programma
    p = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    picco = {}
    inizio = time.monotonic()
    prima = resource.getrusage(resource.RUSAGE_CHILDREN)
    n = 0
    while time.monotonic() - inizio < secondi:
        blocco = p.stdout.read(flusso.byte_per_fotogramma)
        if len(blocco) < flusso.byte_per_fotogramma:
            break
        n += 1
        m = mem(p.pid)
        for k in ("Pss", "Pss_Anon", "Pss_File", "Rss"):
            picco[k] = max(picco.get(k, 0), m.get(k, 0))
    durata = time.monotonic() - inizio
    nthread = len(os.listdir(f"/proc/{p.pid}/task")) if os.path.exists(f"/proc/{p.pid}/task") else 0
    p.kill()
    p.wait()
    dopo = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (dopo.ru_utime + dopo.ru_stime) - (prima.ru_utime + prima.ru_stime)
    return picco, 100 * cpu / durata, n / durata, nthread


trovati = video.cerca_video(sys.argv[1])
flusso = video.risolvi_flusso(trovati[0])
print(f"{trovati[0].titolo[:50]}: {flusso.larghezza}x{flusso.altezza}@{flusso.fps}", flush=True)
for nome, (a, b) in VARIANTI.items():
    picco, cpu, fps, thread = prova(flusso, a, b)
    print(f"{nome:<30} anonima {picco['Pss_Anon'] / 1024:5.1f} MB  file {picco['Pss_File'] / 1024:5.1f} MB  "
          f"PSS {picco['Pss'] / 1024:5.1f} MB  RSS {picco['Rss'] / 1024:5.1f} MB  CPU {cpu:3.0f}%  {fps:4.1f} fps  {thread} thread", flush=True)
