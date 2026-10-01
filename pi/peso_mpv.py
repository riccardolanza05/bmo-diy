"""Picco di PSS di mpv sul Pi: voce (catena vecchia e nuova) e radio vera (#58).

Uscita audio nulla (`--ao=null`): si misura mpv, non la scheda audio.

    venv/bin/python -W ignore peso_mpv.py bmo-core <clip.mp3>

Con un terzo argomento misura anche un video vero di YouTube (pipeline di
`bmo_core.video`: ricerca e risoluzione con yt-dlp, poi ffmpeg -> rgb565
320x240 a 15 fps con audio nullo), dove gira: PSS di yt-dlp e di ffmpeg,
CPU, fotogrammi realmente consegnati contro quelli attesi.

    venv/bin/python -W ignore peso_mpv.py bmo-core <clip.mp3> "nyan cat" [secondi]
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


def picco_pss(pid):
    try:
        for riga in open(f"/proc/{pid}/smaps_rollup"):
            if riga.startswith("Pss:"):
                return int(riga.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        pass
    return 0


def misura_video(query, secondi=30):
    """Video di YouTube: peso di yt-dlp (ricerca + risoluzione) e di ffmpeg mentre decodifica."""
    import threading

    from bmo_core import video

    inizio = time.monotonic()
    prima = resource.getrusage(resource.RUSAGE_CHILDREN)
    trovato = next(v for v in video.cerca_video(query) if v.durata >= secondi)
    indirizzi = video.risolvi_flussi(trovato)
    dopo = resource.getrusage(resource.RUSAGE_CHILDREN)
    print(f"{'yt-dlp: ricerca + risoluzione':<40} picco RSS {dopo.ru_maxrss / 1024:5.1f} MB  "
          f"CPU {(dopo.ru_utime + dopo.ru_stime) - (prima.ru_utime + prima.ru_stime):5.2f} s  "
          f"in {time.monotonic() - inizio:4.1f} s  ({len(indirizzi)} flussi, \"{trovato.titolo[:40]}\")")

    prima = resource.getrusage(resource.RUSAGE_CHILDREN)
    p = subprocess.Popen(video.comando_ffmpeg(indirizzi, "null"), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    picco = [0]
    fine = threading.Event()

    def campiona():
        while not fine.is_set():
            picco[0] = max(picco[0], picco_pss(p.pid))
            time.sleep(0.05)

    threading.Thread(target=campiona, daemon=True).start()
    inizio = time.monotonic()
    n = 0
    for _ in video.fotogrammi(p):
        n += 1
        if time.monotonic() - inizio >= secondi:
            break
    durata = time.monotonic() - inizio
    p.terminate()
    errori = p.communicate()[1].decode(errors="replace").strip()
    fine.set()
    dopo = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (dopo.ru_utime + dopo.ru_stime) - (prima.ru_utime + prima.ru_stime)
    print(f"{'ffmpeg: video 320x240@15 + audio':<40} picco PSS {picco[0] / 1024:5.1f} MB  CPU {cpu:5.2f} s "
          f"({100 * cpu / durata:3.0f}% di un core) in {durata:4.1f} s  "
          f"fotogrammi {n}/{int(durata * video.FPS)} attesi ({n / durata:4.1f} fps)"
          + (f"  ERRORE: {errori[:150]}" if n == 0 else ""))


if len(sys.argv) > 3:
    misura_video(sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 30)
