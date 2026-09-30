"""Video di YouTube sul Pi: riproduzione completa e matrice dei formati.

Usa `bmo_core.video` così com'è (ricerca e risoluzione con yt-dlp senza JS,
poi ffmpeg -> rgb565, audio nullo: si misura la decodifica, non la scheda
audio). Da lanciare col venv che ha yt-dlp:

    venv/bin/python pi/peso_video_pi.py completi [massimo_secondi]   # 3 video interi, in tempo reale
    venv/bin/python pi/peso_video_pi.py matrice "<ricerca>" [secondi]  # fps e scaler a confronto

`completi` controlla che un video intero regga (nessun 403 a metà, nessun
rallentamento): fotogrammi consegnati contro durata × fps.
"""
import resource
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "bmo-core" / "src")
sys.path.insert(0, SRC)
import os  # noqa: E402

os.environ["PYTHONPATH"] = SRC  # anche per yt-dlp, che parte come processo figlio
from bmo_core import video  # noqa: E402


def pss(pid):
    try:
        for riga in open(f"/proc/{pid}/smaps_rollup"):
            if riga.startswith("Pss:"):
                return int(riga.split()[1])
    except OSError:
        pass
    return 0


def suona(flusso, secondi, flag_scala=""):
    """Decodifica per `secondi` (o fino alla fine) a ritmo reale. Ritorna le misure."""
    p = subprocess.Popen(video.comando_ffmpeg(flusso, "null", flag_scala), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    picco = [0]
    fine = threading.Event()

    def campiona():
        while not fine.is_set():
            picco[0] = max(picco[0], pss(p.pid))
            time.sleep(0.1)

    threading.Thread(target=campiona, daemon=True).start()
    prima = resource.getrusage(resource.RUSAGE_CHILDREN)
    inizio = time.monotonic()
    primo, n = None, 0
    for _ in video.fotogrammi(p, flusso.byte_per_fotogramma):
        primo = primo if primo is not None else time.monotonic() - inizio
        n += 1
        if time.monotonic() - inizio >= secondi:
            break
    durata = time.monotonic() - inizio
    p.terminate()
    errori = p.communicate()[1].decode(errors="replace").strip()[-150:]
    fine.set()
    dopo = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = dopo.ru_utime + dopo.ru_stime - prima.ru_utime - prima.ru_stime
    return dict(pss=picco[0] / 1024, cpu=100 * cpu / durata, n=n, durata=durata, primo=primo or 0, errori=errori)


def temperatura():
    try:
        return subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def completi(massimo):
    for ricerca in ("queen bohemian rhapsody videoclip ufficiale", "adele hello official", "daft punk get lucky official video"):
        trovati = [v for v in video.cerca_video(ricerca) if 60 < v.durata]
        for v in trovati:
            try:
                flusso = video.risolvi_flusso(v)
                break
            except RuntimeError as e:
                print(f"   (salto {v.titolo[:30]}: {e})")
        else:
            print(ricerca, "NON RISOLTO")
            continue
        durata = min(v.durata, massimo)
        m = suona(flusso, durata + 5)
        attesi = durata * flusso.fps
        print(f"{v.titolo[:38]:<38} {flusso.larghezza}x{flusso.altezza}@{flusso.fps}  {m['durata']:5.1f}/{durata:3d} s  "
              f"fotogrammi {m['n']}/{attesi}  PSS {m['pss']:4.1f} MB  CPU {m['cpu']:3.0f}%  {temperatura()}  {m['errori']}", flush=True)


def matrice(ricerca, secondi):
    v = next(x for x in video.cerca_video(ricerca) if x.durata > secondi + 10)
    base = video.risolvi_flusso(v)
    print(f"{v.titolo[:50]}  sorgente -> {base.larghezza}x{base.altezza}  (fps scelto dal modulo: {base.fps})")
    for fps in (15, 20, 25, 30):
        for scala in ("", "fast_bilinear", "lanczos"):
            m = suona(replace(base, fps=fps), secondi, scala)
            print(f"fps {fps:2} scaler {scala or 'bicubic':<14} PSS {m['pss']:5.1f} MB  CPU {m['cpu']:4.0f}% di un core  "
                  f"fotogrammi {m['n']:3}/{fps * secondi} ({m['n'] / max(m['durata'] - m['primo'], 1e-9):4.1f}/s)  {temperatura()}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "completi":
        completi(int(sys.argv[2]) if len(sys.argv) > 2 else 400)
    else:
        matrice(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20)
