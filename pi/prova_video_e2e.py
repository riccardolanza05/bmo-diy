"""Prova completa del video sul Pi, senza display: dalla richiesta al fotogramma in uscita.

Stessa catena di produzione: `VideoYouTube.riproduci()` (ricerca, risoluzione,
ffmpeg) -> socket datagram -> `bmo_face.pannello.esegui_pannello` con
`UscitaNulla` al posto dello schermo SPI. Misura:

- **latenza**: dalla chiamata allo strumento al primo fotogramma arrivato all'uscita,
  scomposta in ricerca / risoluzione / partenza di ffmpeg;
- **fluidità**: fotogrammi realmente consegnati contro quelli attesi;
- **RAM**: picco PSS di ffmpeg e del processo Python (bmo-core + bmo-face insieme
  qui, nel servizio vero sono due processi);
- **controlli**: pausa, ripresa, stop e ritorno della faccia.

    python pi/prova_video_e2e.py "queen bohemian rhapsody video ufficiale" [secondi]

Audio nullo (`BMO_VIDEO_AUDIO=null`) di default: la scheda audio non c'è ancora.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "bmo-core" / "src"))
sys.path.insert(0, str(RADICE / "bmo-face" / "src"))
os.environ["PYTHONPATH"] = os.pathsep.join(sys.path[:2])  # anche per i processi figli di bmo-core

from bmo_core import video as v  # noqa: E402
from bmo_core.adapters.faccia import FacciaSocket  # noqa: E402
from bmo_face.animazione import Renderer  # noqa: E402
from bmo_face.build_face import costruisci  # noqa: E402
from bmo_face.pannello import UscitaNulla, esegui_pannello  # noqa: E402
from bmo_face.servitore import ServitoreFaccia  # noqa: E402
from bmo_face.video import RiceviFotogrammi  # noqa: E402


def pss_figli():
    totale, n = 0, 0
    for pid in subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True).stdout.split():
        try:
            for riga in open(f"/proc/{pid}/smaps_rollup"):
                if riga.startswith("Pss:"):
                    totale += int(riga.split()[1])
                    n += 1
        except OSError:
            pass
    return totale / 1024


def pss_proprio():
    for riga in open("/proc/self/smaps_rollup"):
        if riga.startswith("Pss:"):
            return int(riga.split()[1]) / 1024
    return 0.0


def picco_cgroup():
    """`memory.peak` della cgroup in cui gira la prova (con `systemd-run --user --scope`: solo lei e i suoi figli)."""
    try:
        percorso = open("/proc/self/cgroup").read().strip().split("::")[-1]
        return int(open(f"/sys/fs/cgroup{percorso}/memory.peak").read()) / 1e6
    except (OSError, ValueError):
        return None


def main(query, secondi):
    cartella = Path(tempfile.mkdtemp(prefix="bmo-e2e-"))
    os.environ["BMO_SOCKET"] = str(cartella / "bmo.sock")
    os.environ.setdefault("BMO_VIDEO_AUDIO", "null")

    dati, manifesto = costruisci(16, 16)
    servitore = ServitoreFaccia(percorso=cartella / "bmo.sock")
    servitore.avvia()
    ricevitore = RiceviFotogrammi(v.percorso_socket_video())
    ricevitore.avvia()
    uscita = UscitaNulla()
    ferma = threading.Event()
    threading.Thread(target=esegui_pannello, args=(Renderer(manifesto, dati), servitore, uscita),
                     kwargs=dict(fps=25.0, ancora=lambda: not ferma.is_set(), ricevitore=ricevitore), daemon=True).start()

    tempi = {}
    cerca_originale, risolvi_originale = v.cerca_video, v.risolvi_flusso

    def cerca(q):
        t = time.monotonic()
        try:
            return cerca_originale(q)
        finally:
            tempi["ricerca"] = time.monotonic() - t

    def risolvi(video, esegui=None):
        t = time.monotonic()
        try:
            return risolvi_originale(video, esegui=esegui) if esegui else risolvi_originale(video)
        finally:
            tempi["risoluzione"] = tempi.get("risoluzione", 0) + time.monotonic() - t

    sincrono = bool(os.environ.get("SINCRONO"))
    strumento = v.VideoYouTube(faccia=FacciaSocket(cartella / "bmo.sock"), cercatore=cerca, risolutore=risolvi,
                               precarica=None if os.environ.get("SENZA_PRECARICA") else v.RisolutorePronto,
                               in_background=not sincrono)
    t0 = time.monotonic()
    risultato = strumento.riproduci(query)
    chiamata = time.monotonic() - t0
    print(f"riproduci -> {risultato}")
    if risultato.get("stato") != "ok":
        return 1
    fine_attesa = time.monotonic() + 20
    while uscita.fotogrammi_video == 0 and time.monotonic() < fine_attesa:
        time.sleep(0.02)
    primo_uscita = time.monotonic() - t0
    r = strumento._riproduzione
    if r is None:
        print("NON È PARTITO")
        return 1
    modo = "sincrono" if sincrono else "in background"
    print(f"LATENZA ({modo}): lo strumento risponde dopo {chiamata:.1f} s (ricerca {tempi.get('ricerca', 0):.1f} s); "
          f"primo fotogramma all'uscita di bmo-face dopo {primo_uscita:.1f} s in tutto "
          f"(risoluzione {tempi.get('risoluzione', 0):.1f} s)")
    fps = r.flusso.fps
    base = uscita.fotogrammi_video
    inizio = time.monotonic()
    picco_ffmpeg = picco_python = 0.0
    while time.monotonic() - inizio < secondi:
        picco_ffmpeg = max(picco_ffmpeg, pss_figli())
        picco_python = max(picco_python, pss_proprio())
        time.sleep(0.2)
    durata = time.monotonic() - inizio
    consegnati = uscita.fotogrammi_video - base
    print(f"FLUIDITÀ: {consegnati} fotogrammi in {durata:.1f} s = {consegnati / durata:.1f}/s (video a {fps} fps, "
          f"scartati dal sink {strumento.sink.scartati})")
    print(f"RAM: ffmpeg {picco_ffmpeg:.0f} MB PSS, processo Python con bmo-core+bmo-face+pannello {picco_python:.0f} MB PSS")
    strumento.controllo("pausa")
    time.sleep(0.5)
    fermo = uscita.fotogrammi_video
    time.sleep(1.5)
    print(f"PAUSA: {uscita.fotogrammi_video - fermo} fotogrammi in 1,5 s dopo la pausa (atteso 0-1); "
          f"video_attivo={servitore.comando.video_attivo}, in_pausa={servitore.comando.video_in_pausa}")
    t_ripresa = time.monotonic()
    strumento.controllo("riprendi")
    while uscita.fotogrammi_video == fermo and time.monotonic() - t_ripresa < 6:
        time.sleep(0.02)
    ritardo = time.monotonic() - t_ripresa
    prima_ritmo = uscita.fotogrammi_video
    time.sleep(2.0)
    print(f"RIPRESA: primo fotogramma dopo {ritardo:.1f} s; poi {uscita.fotogrammi_video - prima_ritmo} fotogrammi in 2 s "
          f"(attesi ~{2 * fps}, niente raffica); posizione {strumento._riproduzione.posizione_s:.1f} s")
    t = time.monotonic()
    strumento.controllo("stop")
    faccia_prima = uscita.fotogrammi_inviati
    time.sleep(1.0)
    print(f"STOP: video_attivo={servitore.comando.video_attivo}, la faccia è tornata: "
          f"{uscita.fotogrammi_inviati > faccia_prima or uscita.video_finiti >= 1}, "
          f"video_iniziati={uscita.video_iniziati} video_finiti={uscita.video_finiti}")
    ferma.set()
    ricevitore.ferma()
    servitore.ferma()
    picco = picco_cgroup()
    if picco is not None:
        print(f"CGROUP: memory.peak {picco:.0f} MB (yt-dlp, ffmpeg e Python insieme; per il budget di bmo-core "
              f"vanno sommati bmo-core a riposo ~106 MB e la voce mpv ~48 MB, MemoryMax del servizio 280 MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20))
