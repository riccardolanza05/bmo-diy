"""Peso di ffmpeg sul Pi mentre decodifica un video di YouTube già risolto.

yt-dlp sul Pi non ci sta (vedi docs/note-video-youtube.md): gli indirizzi si
risolvono su un'altra macchina (`bmo_core.video.risolvi_flussi`), si scrivono in
un file, uno per riga, e qui si misura solo la riproduzione (audio nullo).

    python3 peso_video_pi.py bmo-core <secondi> <indirizzi.txt>
"""
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "src" / "bmo_core"))
import video  # noqa: E402  (solo stdlib: non serve il venv di bmo-core)

secondi = int(sys.argv[2])
indirizzi = [r.strip() for r in open(sys.argv[3]) if r.strip().startswith("http")]
p = subprocess.Popen(video.comando_ffmpeg(indirizzi, "null"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
picco = [0]
fine = threading.Event()


def campiona():
    while not fine.is_set():
        try:
            for riga in open(f"/proc/{p.pid}/smaps_rollup"):
                if riga.startswith("Pss:"):
                    picco[0] = max(picco[0], int(riga.split()[1]))
        except OSError:
            pass
        time.sleep(0.05)


threading.Thread(target=campiona, daemon=True).start()
inizio = time.monotonic()
primo = None
n = 0
for _ in video.fotogrammi(p):
    primo = primo if primo is not None else time.monotonic() - inizio
    n += 1
    if time.monotonic() - inizio >= secondi:
        break
durata = time.monotonic() - inizio
p.terminate()
errori = p.communicate()[1].decode(errors="replace")[:200]
fine.set()
r = resource.getrusage(resource.RUSAGE_CHILDREN)
cpu = r.ru_utime + r.ru_stime
print(f"PSS picco {picco[0] / 1024:.1f} MB, CPU {cpu:.1f} s su {durata:.1f} s ({100 * cpu / durata:.0f}% di un core), "
      f"primo fotogramma dopo {primo or 0:.2f} s, {n} fotogrammi ({n / max(durata - (primo or 0), 1e-9):.1f} fps)  {errori}")
