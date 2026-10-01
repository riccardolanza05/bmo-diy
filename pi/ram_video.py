"""RAM del video nelle condizioni del servizio: bmo-core carico + un turno vero + video che parte.

Va lanciato **dentro una cgroup con lo stesso tetto del servizio** (`bmo-core.service`: MemoryMax=280M):

    systemd-run --user --scope --quiet -p MemoryMax=280M \\
        venv/bin/python pi/ram_video.py <repo> "<ricerca>" [--turno-reale] [--senza-video]

Il processo stesso fa da bmo-core: carica come lui (numpy + onnxruntime, google.genai, bmo_core.macchina, i tre
modelli della wake word, il client Gemini) e tiene accesa l'ascolto. Poi, in **fasi** con i picchi separati:

- `riposo`: bmo-core carico che ascolta, niente altro (è la base su cui misurare il video; il picco di
  *caricamento* non conta come base: è un transitorio dell'avvio);
- `turno`: la voce di BMO parla e dopo 3 s si chiede il video. Con `--turno-reale` è un turno vero: Gemini
  (la chiave arriva **solo** da stdin, una riga: `printf %s "$GEMINI_API_KEY" | ssh pi '... --turno-reale'`;
  mai in argv, mai su disco, mai stampata) riceve «metti <ricerca>», chiama `riproduci_video` davvero
  (ricerca, risolutore pre-avviato, ffmpeg) e la risposta è letta da `VoceTts` (edge-tts + mpv). Senza
  `--turno-reale` la voce è un mpv che suona un tono e il video si chiede direttamente;
- `video`: il video suona 10 s, poi si ferma.

Si campiona la cgroup ogni 50 ms: `memory.current` (con la cache di file), `anon` di `memory.stat` (non si
può restituire; la cache sì) e i `Pss_Anon` per processo. Il criterio per dire «ci sta bene» **non è l'assenza
di OOM**: è l'assenza di *thrash*, cioè `workingset_refault_file` e `pgmajfault` che non crescono mentre la
cgroup è vicina al tetto (altrimenti il kernel sta buttando fuori librerie che ffmpeg e mpv stanno usando).
Si stampano anche gli eventi `high`/`max`/`oom_kill`.

Limiti della prova: il processo di prova non ha il microfono né il VAD; `MemorySwapMax` non è impostato (come
nel servizio: la zram di sistema assorbe i picchi — con `-p MemorySwapMax=0` la prova diventa più severa).
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RADICE = Path(sys.argv[1]).resolve()
SENZA_VIDEO = "--senza-video" in sys.argv
TURNO_REALE = "--turno-reale" in sys.argv
RICERCA = next((a for a in sys.argv[2:] if not a.startswith("--")), "queen bohemian rhapsody video ufficiale")
if TURNO_REALE:
    chiave = sys.stdin.readline().strip()
    if not chiave:
        sys.exit("--turno-reale vuole la chiave Gemini su stdin")
    os.environ["GEMINI_API_KEY"] = chiave
    del chiave
else:
    os.environ.setdefault("GEMINI_API_KEY", "chiave-finta-nessuna-chiamata")
os.environ.setdefault("BMO_ENV", "dev-linux")
os.environ["PYTHONPATH"] = str(RADICE / "bmo-core" / "src")
sys.path.insert(0, str(RADICE / "bmo-core" / "src"))
os.environ.setdefault("BMO_VIDEO_AUDIO", "null")

CGROUP = "/sys/fs/cgroup" + open("/proc/self/cgroup").read().strip().split("::")[-1]


def leggi(nome):
    try:
        return open(f"{CGROUP}/{nome}").read()
    except OSError:
        return ""


def coppie(nome):
    return {r.split()[0]: int(r.split()[1]) for r in leggi(nome).splitlines() if len(r.split()) == 2}


def pss_anon_processi():
    totale, dettaglio = 0, {}
    for pid in leggi("cgroup.procs").split():
        try:
            nome = open(f"/proc/{pid}/comm").read().strip()
            for r in open(f"/proc/{pid}/smaps_rollup"):
                if r.startswith("Pss_Anon:"):
                    kb = int(r.split()[1])
                    totale += kb
                    dettaglio[nome] = dettaglio.get(nome, 0) + kb
        except OSError:
            pass
    return totale / 1024, {k: round(v / 1024) for k, v in dettaglio.items()}


fase = {"nome": "avvio"}
picchi = {}   # fase -> dict
fine = threading.Event()
t0 = time.monotonic()
eventi = []


def campiona():
    while not fine.is_set():
        corrente = int(leggi("memory.current") or 0) / 1e6
        anon = coppie("memory.stat").get("anon", 0) / 1e6
        anon_p, dettaglio = pss_anon_processi()
        p = picchi.setdefault(fase["nome"], {"corrente": 0, "anon": 0, "anon_p": 0, "chi": {}, "quando": ""})
        p["corrente"] = max(p["corrente"], corrente)
        p["anon"] = max(p["anon"], anon)
        if anon_p > p["anon_p"]:
            p["anon_p"], p["chi"] = anon_p, dettaglio
            p["quando"] = eventi[-1][1] if eventi else "inizio"
        time.sleep(0.05)


def evento(nome):
    eventi.append((round(time.monotonic() - t0, 1), nome))
    print(f"[{eventi[-1][0]:5.1f}s] ({fase['nome']}) {nome}", flush=True)


def contatori():
    s = coppie("memory.stat")
    e = coppie("memory.events")
    return {"refault_file": s.get("workingset_refault_file", 0), "pgmajfault": s.get("pgmajfault", 0),
            "high": e.get("high", 0), "max": e.get("max", 0), "oom_kill": e.get("oom_kill", 0)}


threading.Thread(target=campiona, daemon=True).start()

# --- bmo-core carico, come peso_bmo_core.py -------------------------------------------------------
import numpy as np  # noqa: E402
import onnxruntime  # noqa: E402,F401
import google.genai  # noqa: E402,F401
import bmo_core.macchina  # noqa: E402,F401
from bmo_core.richiamo import _carica_rilevatore  # noqa: E402

modelli = [str(RADICE / "bmo-core" / "modelli-wake-word" / f"bmo{i}.onnx") for i in (1, 2, 3)]
modelli = [m for m in modelli if os.path.exists(m)]
rilevatore = _carica_rilevatore(modelli)
for _ in range(50):
    rilevatore.predict(np.zeros(1280, dtype=np.int16))
from bmo_core.adapters import crea_audio_output  # noqa: E402
from bmo_core.adapters.audio_output import OPZIONI_MPV_LEGGERE, catena_voce  # noqa: E402
from bmo_core.brain import Cervello  # noqa: E402
from bmo_core.macchina import crea_faccia  # noqa: E402
from bmo_core.radio import Radio  # noqa: E402
from bmo_core import video as v  # noqa: E402

faccia = crea_faccia(sul_terminale=False)
cervello = Cervello(faccia=faccia)
radio = Radio()
strumento = v.VideoYouTube(faccia=faccia, ferma_radio=radio.ferma, precarica=v.RisolutorePronto, in_background=True)
radio.video = strumento
radio.registra(cervello)
strumento.registra(cervello)
evento(f"bmo-core carico ({len(modelli)} modelli wake word, strumenti radio+video registrati)")


def ascolta():  # l'ascolto continuo della wake word: lavoro vero, non solo memoria
    while not fine.is_set():
        rilevatore.predict(np.zeros(1280, dtype=np.int16))
        time.sleep(0.08)


threading.Thread(target=ascolta, daemon=True).start()
fase["nome"] = "riposo"
time.sleep(6)
base = contatori()

# --- il turno --------------------------------------------------------------------------------------
fase["nome"] = "turno"
mpv = None
if TURNO_REALE:
    from bmo_core.macchina import VoceTts  # noqa: E402

    voce = VoceTts(altoparlante=crea_audio_output(), faccia=faccia)
    evento(f"turno reale: «metti {RICERCA}»")
    t = time.monotonic()
    risposta = cervello.rispondi(testo=f"metti {RICERCA}")
    evento(f"Gemini ha risposto in {time.monotonic() - t:.1f} s: strumenti "
           f"{[c.nome for c in risposta.chiamate]}, testo «{(risposta.testo or '')[:60]}»")
    voce(risposta.testo or "Fatto.", risposta.lingua)
    evento("la voce di BMO ha finito di parlare")
else:
    voce_file = Path("/tmp/ram_video_voce.mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=40",
                    "-c:a", "libmp3lame", str(voce_file)], check=True)
    mpv = subprocess.Popen(["mpv", "--no-video", "--really-quiet", "--ao=null", *OPZIONI_MPV_LEGGERE,
                            f"--af=lavfi=[{catena_voce(None, None)}]", str(voce_file)])
    evento("la voce di BMO parla (mpv, tono)")
    time.sleep(3)
    if not SENZA_VIDEO:
        evento("richiesta del video (riproduci_video)")
        risposta = strumento.riproduci(RICERCA)
        evento(f"lo strumento ha risposto: {risposta['stato']}")

fase["nome"] = "video"
if not SENZA_VIDEO:
    inizio = time.monotonic()
    while not strumento.in_riproduzione() and time.monotonic() - inizio < 30:
        time.sleep(0.05)
    evento("il video suona" if strumento.in_riproduzione() else "IL VIDEO NON È PARTITO")
    time.sleep(10)
    strumento.ferma()
    evento("video fermato")
time.sleep(2)
if mpv:
    mpv.terminate()
fine.set()
time.sleep(0.2)
dopo = contatori()

limite = leggi("memory.max").strip()
print()
print(f"tetto della cgroup: {int(limite) / 1e6:.0f} MB" if limite.isdigit() else f"tetto: {limite}")
for nome, p in picchi.items():
    if nome == "avvio":
        print(f"  fase {nome:<6} (caricamento, transitorio): corrente {p['corrente']:.0f} MB, anonima {p['anon']:.0f} MB")
    else:
        print(f"  fase {nome:<6}: picco corrente {p['corrente']:.0f} MB (con cache), picco anonima {p['anon']:.0f} MB; "
              f"per processo {p['anon_p']:.0f} MB {p['chi']} al momento «{p['quando']}»")
print(f"memory.peak finale (include l'avvio): {int(leggi('memory.peak') or 0) / 1e6:.0f} MB")
print("thrash dopo il riposo: " + ", ".join(f"{k} +{dopo[k] - base[k]}" for k in dopo))
print("  (refault_file e pgmajfault che salgono con la cgroup vicina al tetto = il kernel butta fuori librerie in uso)")
