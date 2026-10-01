"""I video di YouTube su BMO: cercarli, risolverli, decodificarli per lo schermo.

Tutto gira sul Pi, senza computer accesi, senza chiavi e senza JavaScript
(misure sul Pi 3 A+, docs/note-video-youtube.md):

- **Ricerca**: una richiesta diretta all'endpoint di ricerca di YouTube,
  solo stdlib, ~0,7 s; se cambia, si ripiega su `yt-dlp` (~3,6 s).
- **Risoluzione** dell'indirizzo con `yt-dlp` in un processo figlio che muore
  subito (la sua RAM torna al sistema prima che parta ffmpeg): ~4,5-5 s e
  46 MB di picco. yt-dlp usa da solo il client `visionos`, che dà indirizzi
  diretti 360p h264 (134 + audio 140) senza la sfida JavaScript del player.
  Quello che **non** ha funzionato, tutto provato: i client `android_vr` e
  `tv_embedded` (indirizzi che rispondono 403 a ffmpeg), il client `web` con
  Node o QuickJS (8-20 s e 180-290 MB, e per molti video senza indirizzi
  senza un PO token) e le istanze pubbliche di Piped/Invidious (0 su 10
  riproducibili).
- **Riproduzione**: un solo ffmpeg con due uscite, entrambe al ritmo reale
  (`-re`), così audio e video restano agganciati senza un orologio nostro:

      indirizzi googlevideo ──ffmpeg──┬─ video: rgb565 raw LxA ─> stdout ─> `SinkFotogrammi` ─> bmo-face
                                      └─ audio: ALSA (o null)  ─> scheda audio

Il video è ridimensionato **alla sua vera proporzione** dentro 320×240 (un
16:9 diventa 320×180): bmo-face ridisegna solo quel rettangolo e le bande
nere restano spente, cioè meno byte sul bus SPI.
"""
from __future__ import annotations

import json
import os
import select
import socket
import struct
import subprocess
import sys
import threading
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

SCHERMO_L, SCHERMO_A = 320, 240
# Il limite è il bus SPI, non la CPU né la RAM (sul Pi, ffmpeg a 30 fps: 43-57% di un core su 4,
# 72 MB): un fotogramma pieno 320×240 costa ~28 ms di bus (docs/02-piano, ~5,5 MB/s). Si tiene
# il 73% di quel bus (4 MB/s): un 16:9 a 320×180 regge 30 fps, un 4:3 a 320×240 ne regge 26.
# La cifra del bus viene dalle note dell'hardware, non da una misura sul display: l'hardware
# non è ancora arrivato — è una costante da ritarare (docs/decisioni-video-youtube.md).
BUS_SPI_BYTE_AL_SECONDO = 4_000_000
FPS_MAX = 30
FPS_MINIMO_DIMEZZATO = 20  # si dimezza (60 -> 30, 50 -> 25) solo se il risultato resta fluido
QUANTI = 5
DURATA_MASSIMA_S = 2 * 3600  # niente dirette (durata assente) né maratone da 100 ore

# Il 18 (360p h264 + aac in un solo file) se c'è; altrimenti video 360p h264 + audio 140
# (l'originale: senza "140" esplicito yt-dlp può prendere una traccia doppiata, "140-17",
# che su un video è rimasta appesa senza dati). h264 perché è l'unico codec di YouTube che
# il Pi decodifica senza fatica (VP9/AV1 no).
FORMATO = ("18/bv*[vcodec^=avc1][height<=360]+140/"
           "bv*[vcodec^=avc1][height<=360]+ba[acodec^=mp4a]/b[height<=360]")
# Un percorso opzionale a un file di cookie (formato Netscape), FUORI dal repo:
# non serve (tutte le misure sono senza), resta come via d'uscita se YouTube cambia.
VARIABILE_COOKIE = "BMO_YT_COOKIES"
# Ridimensionamento: lanczos costa come il bicubic a 30 fps (58% contro 57% di un core sul Pi; il
# fast_bilinear 43%) ed è il più nitido scendendo da 640×360 a 320×180.
FLAG_SCALA = "lanczos"
# Un solo thread per il decoder e per i filtri: sul Pi la RAM anonima di ffmpeg scende da 36,7 a 27,6 MB e la
# CPU da 55% a 42% di un core a parità di fps (pi/ffmpeg_ram.py). Il probing non cambia nulla (pi/avvio_ffmpeg_pi.py).
OPZIONI_INGRESSO: tuple[str, ...] = ("-threads", "1")
OPZIONI_GLOBALI: tuple[str, ...] = ("-filter_threads", "1", "-filter_complex_threads", "1")
TIMEOUT_RETE_US = 10_000_000  # ffmpeg: un indirizzo che non manda dati per 10 s è un errore, non un'attesa infinita

NOME_SOCKET_VIDEO = "bmo-video.sock"
VOLUME_VIDEO_ABBASSATO = 30  # % del video mentre BMO parla (con /etc/asound.conf di pi/asound.conf.modello)


def uscita_audio_predefinita() -> str:
    """Dove suona ffmpeg: `BMO_VIDEO_AUDIO` se c'è; altrimenti `video_out` se l'ALSA di sistema lo definisce
    (dmix + volume software «Video», installato da `pi/installa-audio.sh` con la WM8960), altrimenti `default`."""
    forzata = os.environ.get("BMO_VIDEO_AUDIO")
    if forzata:
        return forzata
    for percorso in (Path("/etc/asound.conf"), Path.home() / ".asoundrc"):
        try:
            if "video_out" in percorso.read_text():
                return "alsa:video_out"
        except OSError:
            pass
    return "alsa:default"


@dataclass
class Video:
    id: str
    titolo: str
    durata: int  # secondi
    canale: str = ""

    @property
    def pagina(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


@dataclass
class Flusso:
    """Un video pronto da riprodurre: gli indirizzi e la forma del fotogramma."""

    indirizzi: list[str]
    larghezza: int  # del fotogramma d'uscita (rgb565)
    altezza: int
    fps: int

    @property
    def byte_per_fotogramma(self) -> int:
        return self.larghezza * self.altezza * 2


def dimensioni_schermo(larghezza: int, altezza: int) -> tuple[int, int]:
    """Il video dentro 320×240 mantenendo la proporzione, in numeri pari (lo vuole ffmpeg)."""
    if larghezza <= 0 or altezza <= 0:
        larghezza, altezza = 16, 9
    scala = min(SCHERMO_L / larghezza, SCHERMO_A / altezza)
    l = max(2, int(larghezza * scala) // 2 * 2)
    a = max(2, int(altezza * scala) // 2 * 2)
    return l, a


def fps_di_riproduzione(fps_sorgente: float | None, byte_per_fotogramma: int = 320 * 180 * 2) -> int:
    """I fotogrammi al secondo da mostrare: quelli del video finché il bus SPI li regge.

    Sopra il limite si dimezza se il risultato resta fluido (60 -> 30, 50 -> 25), altrimenti
    ci si ferma al limite (30 fps su un 4:3 diventa 25: un fotogramma ogni sei scartato).
    """
    tetto = max(1, min(FPS_MAX, BUS_SPI_BYTE_AL_SECONDO // max(byte_per_fotogramma, 1)))
    fps = int(round(fps_sorgente or 25))
    if fps <= tetto:
        return max(fps, 1)
    if fps % 2 == 0 and FPS_MINIMO_DIMEZZATO <= fps // 2 <= tetto:
        return fps // 2
    return tetto


def _comando_ytdlp(argomenti: list[str]) -> list[str]:
    comando = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist", "--js-runtimes", "none"]
    cookie = os.environ.get(VARIABILE_COOKIE)
    if cookie:
        comando += ["--cookies", cookie]
    return comando + argomenti


def _esegui_ytdlp(argomenti: list[str], timeout: float = 45.0) -> str:
    """yt-dlp come processo figlio: muore subito e rende tutta la sua memoria."""
    try:
        fatto = subprocess.run(_comando_ytdlp(argomenti), capture_output=True, text=True,
                               timeout=timeout, check=False)
    except subprocess.TimeoutExpired as errore:
        raise RuntimeError("yt-dlp non risponde") from errore
    if fatto.returncode != 0:
        raise RuntimeError((fatto.stderr.strip().splitlines() or ["yt-dlp fallito"])[-1][:200])
    return fatto.stdout


def _durata_in_secondi(testo: str | None) -> int | None:
    """"6:00" -> 360, "1:02:03" -> 3723; None per le dirette (nessuna durata)."""
    if not testo:
        return None
    try:
        secondi = 0
        for parte in testo.split(":"):
            secondi = secondi * 60 + int(parte)
        return secondi
    except ValueError:
        return None


def _ricerca_diretta(query: str) -> list[dict[str, Any]]:
    """La ricerca di YouTube senza yt-dlp: ~0,7 s sul Pi, solo stdlib, solo video."""
    corpo = json.dumps({
        "context": {"client": {"clientName": "WEB", "clientVersion": "2.20260901.00.00", "hl": "it", "gl": "IT"}},
        "query": query, "params": "EgIQAQ%3D%3D",
    }).encode()
    richiesta = urllib.request.Request(
        "https://www.youtube.com/youtubei/v1/search?prettyPrint=false", corpo,
        {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(richiesta, timeout=10) as risposta:
        dati = json.load(risposta)
    trovati: list[dict[str, Any]] = []

    def visita(nodo: Any) -> None:
        if isinstance(nodo, dict):
            if "videoRenderer" in nodo:
                v = nodo["videoRenderer"]
                trovati.append({
                    "id": v.get("videoId"),
                    "duration": _durata_in_secondi((v.get("lengthText") or {}).get("simpleText")),
                    "title": "".join(p.get("text", "") for p in (v.get("title") or {}).get("runs", [])),
                    "channel": "".join(p.get("text", "") for p in (v.get("ownerText") or {}).get("runs", [])),
                })
            for figlio in nodo.values():
                visita(figlio)
        elif isinstance(nodo, list):
            for figlio in nodo:
                visita(figlio)

    visita(dati)
    return trovati


def _ricerca_ytdlp(query: str, quanti: int, esegui: Callable[[list[str]], str]) -> list[dict[str, Any]]:
    uscita = esegui(["--flat-playlist", "-j", f"ytsearch{quanti * 2}:{query}"])
    trovati = []
    for riga in uscita.splitlines():
        try:
            trovati.append(json.loads(riga))
        except json.JSONDecodeError:
            continue
    return trovati


def cerca_video(
    query: str,
    quanti: int = QUANTI,
    esegui: Callable[[list[str]], str] = _esegui_ytdlp,
    diretta: Callable[[str], list[dict[str, Any]]] | None = _ricerca_diretta,
) -> list[Video]:
    """Cerca su YouTube; scarta dirette e video lunghissimi."""
    query = query.strip()
    dati: list[dict[str, Any]] = []
    if diretta is not None:
        try:
            dati = diretta(query)
        except (OSError, ValueError):
            dati = []  # rete o formato cambiato: si ripiega su yt-dlp
    if not dati:
        dati = _ricerca_ytdlp(query, quanti, esegui)
    trovati: list[Video] = []
    for dato in dati:
        durata = dato.get("duration")
        if not dato.get("id") or not durata or durata > DURATA_MASSIMA_S:
            continue
        trovati.append(Video(dato["id"], (dato.get("title") or "").strip(), int(durata),
                             dato.get("channel") or dato.get("uploader") or ""))
    return trovati[:quanti]


def _esegui_risolutore(argomenti: list[str], timeout: float = 45.0) -> str:
    """`risolvi_youtube` come processo figlio (carica solo l'estrattore di YouTube: ~3,2 s contro ~5)."""
    try:
        fatto = subprocess.run([sys.executable, "-m", "bmo_core.risolvi_youtube", *argomenti],
                               capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as errore:
        raise RuntimeError("yt-dlp non risponde") from errore
    if fatto.returncode != 0:
        raise RuntimeError((fatto.stderr.strip().splitlines() or ["yt-dlp fallito"])[-1][:200])
    return fatto.stdout


class RisolutorePronto:
    """Un processo `risolvi_youtube --serve` avviato in anticipo.

    Si crea *prima* della ricerca: mentre questa gira (~0,7 s) il processo importa
    yt-dlp, e quando c'è l'identificativo del video è già pronto. `esegui` ha la stessa
    forma di `_esegui_risolutore`. Va chiuso con `chiudi()` (lo fa `VideoYouTube`).
    """

    def __init__(self) -> None:
        self._chiuso = False
        self._processo = subprocess.Popen(
            [sys.executable, "-m", "bmo_core.risolvi_youtube", "--serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def _riga(self, timeout: float) -> str:
        assert self._processo.stdout is not None
        pronto, _, _ = select.select([self._processo.stdout], [], [], timeout)
        if not pronto:
            raise RuntimeError("yt-dlp non risponde")
        riga = self._processo.stdout.readline()
        if not riga:
            raise RuntimeError("il risolutore si è fermato")
        return riga

    def esegui(self, argomenti: list[str], timeout: float = 45.0) -> str:
        """Risolve un video. **Una volta sola**: dopo la prima risoluzione riuscita il processo si
        chiude da sé, così i suoi ~48 MB sono già liberi quando parte ffmpeg (e il picco resta
        sotto il MemoryMax del servizio). Le richieste successive usano un processo nuovo."""
        if self._chiuso:
            return _esegui_risolutore(argomenti, timeout)
        formato, url = argomenti
        assert self._processo.stdin is not None
        self._processo.stdin.write(json.dumps({"formato": formato, "url": url}) + "\n")
        self._processo.stdin.flush()
        risposta = json.loads(self._riga(timeout))
        while risposta.get("pronto"):  # la prima riga del processo dice solo che ha finito di caricare
            risposta = json.loads(self._riga(timeout))
        if "errore" in risposta:
            raise RuntimeError(risposta["errore"])
        self.chiudi()
        return "\n".join([risposta["forma"], *risposta["indirizzi"]])

    def chiudi(self) -> None:
        if self._chiuso:
            return
        self._chiuso = True
        try:
            if self._processo.stdin is not None:
                self._processo.stdin.close()
            self._processo.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            self._processo.kill()
            self._processo.wait()


def risolvi_flusso(
    video: Video,
    esegui: Callable[[list[str]], str] = _esegui_risolutore,
) -> Flusso:
    """Gli indirizzi diretti da dare a ffmpeg (uno, già muxato, o due) e la forma del fotogramma."""
    uscita = esegui([FORMATO, video.pagina])
    righe = [r.strip() for r in uscita.splitlines() if r.strip()]
    indirizzi = [r for r in righe if r.startswith("http")]
    if not indirizzi:
        raise RuntimeError("nessun flusso riproducibile")
    dimensioni = next((r for r in righe if not r.startswith("http")), "|")
    try:
        l, a, fps = (None if p in ("", "NA", "None") else float(p) for p in dimensioni.split("|"))
    except ValueError:
        l = a = fps = None
    larghezza, altezza = dimensioni_schermo(int(l or 0), int(a or 0))
    return Flusso(indirizzi, larghezza, altezza, fps_di_riproduzione(fps, larghezza * altezza * 2))


def comando_ffmpeg(flusso: Flusso, uscita_audio: str = "alsa:default", flag_scala: str = FLAG_SCALA, inizio_s: float = 0.0,
                   opzioni_ingresso: tuple[str, ...] = OPZIONI_INGRESSO) -> list[str]:
    """Il comando ffmpeg: video rgb565 su stdout, audio sull'uscita indicata.

    `uscita_audio`: "alsa:<dispositivo>", "pulse", oppure "null" (per i test e le
    misure: si decodifica tutto ma non si suona niente).
    """
    comando = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *OPZIONI_GLOBALI]
    for indirizzo in flusso.indirizzi:
        comando += [*opzioni_ingresso, "-re", "-rw_timeout", str(TIMEOUT_RETE_US)]
        if inizio_s > 0:
            comando += ["-ss", f"{inizio_s:.2f}"]
        comando += ["-i", indirizzo]
    # Un solo ingresso: video e audio vengono dallo stesso file; due: video dal primo, audio dal secondo.
    audio = "1:a:0?" if len(flusso.indirizzi) > 1 else "0:a:0?"
    scala = f"scale={flusso.larghezza}:{flusso.altezza}" + (f":flags={flag_scala}" if flag_scala else "")
    filtro = f"fps={flusso.fps},{scala},format=rgb565le"
    comando += ["-map", "0:v:0", "-vf", filtro, "-f", "rawvideo", "pipe:1"]
    if uscita_audio == "null":
        comando += ["-map", audio, "-f", "null", "-"]
    elif uscita_audio == "pulse":
        comando += ["-map", audio, "-f", "pulse", "bmo-video"]
    else:
        comando += ["-map", audio, "-f", "alsa", uscita_audio.split(":", 1)[-1]]
    return comando


def percorso_socket_video() -> Path:
    """Il socket datagram dei fotogrammi: accanto a quello dei comandi di bmo-face."""
    forzato = os.environ.get("BMO_SOCKET_VIDEO")
    if forzato:
        return Path(forzato)
    comandi = os.environ.get("BMO_SOCKET")
    if comandi:
        return Path(comandi).with_name(NOME_SOCKET_VIDEO)
    if Path("/run").is_dir() and os.access("/run", os.W_OK):
        return Path("/run") / NOME_SOCKET_VIDEO
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return (Path(runtime) if runtime else Path(os.environ.get("TMPDIR", "/tmp"))) / NOME_SOCKET_VIDEO


INTESTAZIONE = struct.Struct("<HH")  # larghezza, altezza: il fotogramma rgb565 segue


class SinkFotogrammi:
    """Manda i fotogrammi a bmo-face con un datagram Unix per fotogramma.

    Un datagram è atomico e, se bmo-face è lento o non c'è, `send` non blocca:
    il fotogramma si scarta e ffmpeg (e l'audio) non se ne accorgono. Uno
    stream o una FIFO farebbero l'opposto: un bmo-face morto bloccherebbe o
    ucciderebbe ffmpeg, rompendo l'isolamento dei guasti (§2.2).
    """

    def __init__(self, percorso: Path | None = None) -> None:
        self.percorso = percorso or percorso_socket_video()
        self._socket: socket.socket | None = None
        self.consegnati = 0
        self.scartati = 0

    def _apri(self) -> socket.socket | None:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
            s.setblocking(False)
            s.connect(str(self.percorso))
            return s
        except OSError:
            return None

    def __call__(self, larghezza: int, altezza: int, dati: bytes) -> None:
        if self._socket is None:
            self._socket = self._apri()
        if self._socket is None:
            self.scartati += 1
            return
        try:
            self._socket.send(INTESTAZIONE.pack(larghezza, altezza) + dati)
            self.consegnati += 1
        except (BlockingIOError, InterruptedError):
            self.scartati += 1  # bmo-face è indietro: si perde un fotogramma, non si aspetta
        except OSError:
            self._socket.close()
            self._socket = None  # bmo-face riavviato: si riconnette al prossimo
            self.scartati += 1

    def chiudi(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None


def fotogrammi(processo: subprocess.Popen[bytes], byte_per_fotogramma: int) -> Iterator[bytes]:
    """I fotogrammi rgb565 che escono da ffmpeg, di `byte_per_fotogramma` byte l'uno."""
    assert processo.stdout is not None
    while True:
        blocco = processo.stdout.read(byte_per_fotogramma)
        if len(blocco) < byte_per_fotogramma:
            return
        yield blocco


class Riproduzione:
    """Un video in corso: ffmpeg più un thread che ne inoltra i fotogrammi.

    La pausa **ferma ffmpeg e ricorda la posizione**; la ripresa lo rilancia
    da lì con `-ss` (~1,3 s di avvio). Non si usa SIGSTOP/SIGCONT: con `-re`
    ffmpeg "recupera" il tempo perso e dopo la ripresa i fotogrammi arrivavano
    a raffica (85 in 1,5 s invece di 37, misurato sul Pi).
    """

    def __init__(
        self,
        flusso: Flusso,
        su_fotogramma: Callable[[int, int, bytes], None],
        uscita_audio: str = "alsa:default",
        al_termine: Callable[[], None] | None = None,
    ) -> None:
        self.flusso = flusso
        self.su_fotogramma = su_fotogramma
        self.uscita_audio = uscita_audio
        self.al_termine = al_termine
        self.fotogrammi_letti = 0
        self._in_pausa = False
        self._fermata = False
        self._posizione_s = 0.0      # dove si è arrivati prima dell'ultimo avvio di ffmpeg
        self._letti_da_avvio = 0
        self._partita = threading.Event()
        self._processo: subprocess.Popen[bytes]
        self._thread: threading.Thread
        self._avvia(0.0)

    def _avvia(self, inizio_s: float) -> None:
        self._posizione_s = inizio_s
        self._letti_da_avvio = 0
        self._processo = subprocess.Popen(
            comando_ffmpeg(self.flusso, self.uscita_audio, inizio_s=inizio_s),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.flusso.byte_per_fotogramma * 2,
        )
        self._thread = threading.Thread(target=self._inoltra, args=(self._processo,), daemon=True)
        self._thread.start()

    def _inoltra(self, processo: subprocess.Popen[bytes]) -> None:
        for blocco in fotogrammi(processo, self.flusso.byte_per_fotogramma):
            if processo is not self._processo:
                return  # è partito un altro ffmpeg (ripresa): questo non conta più
            self.su_fotogramma(self.flusso.larghezza, self.flusso.altezza, blocco)
            self.fotogrammi_letti += 1
            self._letti_da_avvio += 1
            self._partita.set()
        processo.wait()
        self._partita.set()  # anche se è finito senza un solo fotogramma: chi aspetta non resta appeso
        if processo is self._processo and not self._in_pausa and not self._fermata and self.al_termine is not None:
            self.al_termine()

    def attendi_partenza(self, timeout: float) -> bool:
        """True se è arrivato almeno un fotogramma entro `timeout` secondi."""
        self._partita.wait(timeout)
        return self.fotogrammi_letti > 0

    @property
    def posizione_s(self) -> float:
        return self._posizione_s + self._letti_da_avvio / max(self.flusso.fps, 1)

    @property
    def in_corso(self) -> bool:
        """Sta suonando o è in pausa (finché non è finito o fermato)."""
        return not self._fermata and (self._in_pausa or self._processo.poll() is None)

    @property
    def in_pausa(self) -> bool:
        return self._in_pausa and self.in_corso

    def pausa(self) -> None:
        if not self.in_corso or self._in_pausa:
            return
        posizione = self.posizione_s
        self._in_pausa = True
        self._termina_processo()
        self._posizione_s, self._letti_da_avvio = posizione, 0

    def riprendi(self) -> None:
        if not self.in_corso or not self._in_pausa:
            return
        self._in_pausa = False
        self._avvia(self._posizione_s)

    def _termina_processo(self) -> None:
        if self._processo.poll() is None:
            self._processo.terminate()
        try:
            # ffmpeg bloccato in una lettura di rete ignora SIGTERM (visto sul Pi): dopo
            # mezzo secondo si passa a SIGKILL. Non c'è niente da chiudere bene: l'uscita
            # è una pipe e l'audio `null` o ALSA.
            self._processo.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            self._processo.kill()
            self._processo.wait()
        self._thread.join(timeout=2)

    def ferma(self) -> None:
        self._fermata = True
        self._termina_processo()


def durata_a_voce(secondi: int) -> str:
    """185 -> "3:05", 3723 -> "1:02:03": per il risultato dello strumento."""
    ore, resto = divmod(secondi, 3600)
    minuti, sec = divmod(resto, 60)
    return f"{ore}:{minuti:02d}:{sec:02d}" if ore else f"{minuti}:{sec:02d}"


class VideoYouTube:
    """Lo strumento `riproduci_video` e il suo controllo: un video alla volta.

    Il video e la radio non suonano mai insieme: chi parte per ultimo ferma
    l'altro (`ferma_radio` qui, `Radio.video` dall'altra parte). Se il primo
    risultato non parte (alcuni video restano appesi senza dati, visto sul
    Pi) si passa al successivo, fino a `tentativi`.

    Con `in_background` lo strumento risponde appena ha la ricerca (~0,6 s) e il
    video si avvia *mentre BMO dice la sua frase* (risoluzione ~3 s + partenza di
    ffmpeg ~1,3 s): il tempo che si sente dopo la voce scende da ~5,5 s a ~1-2 s, e
    il video non parte sopra le parole di BMO. Se poi nessun risultato parte,
    `al_fallimento` lo segnala (suono di errore e faccia triste).
    """

    def __init__(
        self,
        faccia: Any = None,
        sink: Callable[[int, int, bytes], None] | None = None,
        uscita_audio: str | None = None,
        ferma_radio: Callable[[], None] | None = None,
        cercatore: Callable[[str], list[Video]] = cerca_video,
        risolutore: Callable[[Video], Flusso] = risolvi_flusso,
        avvia: Callable[..., Riproduzione] = Riproduzione,
        tentativi: int = 3,
        timeout_partenza_s: float = 12.0,
        precarica: Callable[[], Any] | None = None,
        in_background: bool = False,
        al_fallimento: Callable[[str], None] | None = None,
    ) -> None:
        self.faccia = faccia
        self.sink = sink if sink is not None else SinkFotogrammi()
        self.uscita_audio = uscita_audio or uscita_audio_predefinita()
        self._volume_software: bool | None = None  # c'è il controllo «Video» in ALSA? (si scopre alla prima volta)
        self.ferma_radio = ferma_radio
        self.cercatore = cercatore
        self.risolutore = risolutore
        self.avvia = avvia
        self.tentativi = tentativi
        self.timeout_partenza_s = timeout_partenza_s
        # Es. `RisolutorePronto`: un oggetto con `esegui` e `chiudi`, creato prima della ricerca.
        self.precarica = precarica
        self.in_background = in_background
        self.al_fallimento = al_fallimento
        self._generazione = 0   # cresce a ogni `ferma`: un avvio in background vecchio si accorge e rinuncia
        self._in_avvio = False
        self.elenco: list[Video] = []
        self.posizione = -1
        self._riproduzione: Riproduzione | None = None
        self._lock = threading.RLock()

    def registra(self, cervello: Any) -> None:
        cervello.registra_strumento("riproduci_video", self.riproduci)
        cervello.registra_stato(self.descrivi_stato)

    # --- stato -----------------------------------------------------------------

    @property
    def in_ascolto(self) -> Video | None:
        if 0 <= self.posizione < len(self.elenco):
            return self.elenco[self.posizione]
        return None

    def in_riproduzione(self) -> bool:
        """Sta andando (un video in pausa non conta: come la radio, vedi `sospesa`)."""
        r = self._riproduzione
        return r is not None and r.in_corso and not r.in_pausa

    def presente(self) -> bool:
        """C'è un video caricato (anche in pausa) o sta partendo."""
        r = self._riproduzione
        return self._in_avvio or (r is not None and r.in_corso)

    def descrivi_stato(self) -> str:
        video = self.in_ascolto
        if self._in_avvio and video is not None:
            return f'Video: sta partendo "{video.titolo}" (pochi secondi).'
        if video is None or not self.presente():
            return "Video: nessuno."
        pausa = " (in pausa)" if self._riproduzione and self._riproduzione.in_pausa else ""
        return (f'Video: in riproduzione "{video.titolo}"{pausa}. Il suo volume è quello del canale '
                f'"sistema" (regola_volume con canale sistema).')

    def _mostra(self, azione: str, titolo: str | None = None) -> None:
        if self.faccia is not None:
            self.faccia.video(azione, titolo)

    # --- riproduzione ----------------------------------------------------------

    def _fermato(self) -> None:
        """Il video è finito da solo (o ffmpeg è morto): la faccia torna."""
        with self._lock:
            if self._riproduzione is not None and not self._riproduzione.in_corso:
                self._riproduzione = None
                self.elenco, self.posizione = [], -1
                self._mostra("stop")

    def ferma(self) -> None:
        with self._lock:
            self._generazione += 1
            self._in_avvio = False
            r, self._riproduzione = self._riproduzione, None
            self.elenco, self.posizione = [], -1
        if r is not None:
            r.ferma()
            self._mostra("stop")

    def _parti(self, posizione: int, pronto: Any = None, generazione: int | None = None) -> dict[str, Any] | None:
        """Prova a far partire il video `posizione`; None se non parte."""
        video = self.elenco[posizione]
        try:
            flusso = self.risolutore(video, esegui=pronto.esegui) if pronto is not None else self.risolutore(video)
        except RuntimeError:
            return None
        if generazione is not None and generazione != self._generazione:
            return None  # nel frattempo: stop, o un'altra richiesta
        riproduzione = self.avvia(flusso, self.sink, self.uscita_audio, al_termine=self._fermato)
        if not riproduzione.attendi_partenza(self.timeout_partenza_s):
            riproduzione.ferma()
            return None
        with self._lock:
            if generazione is not None and generazione != self._generazione:
                riproduzione.ferma()
                return None
            self._riproduzione = riproduzione
            self.posizione = posizione
            self._in_avvio = False
        self._mostra("start", video.titolo)
        return {
            "stato": "ok",
            "titolo": video.titolo,
            "canale": video.canale,
            "durata": durata_a_voce(video.durata),
            "posizione": f"{posizione + 1} di {len(self.elenco)}",
        }

    def riproduci(self, query: str) -> dict[str, Any]:
        """Cerca su YouTube e suona il primo risultato che parte, con audio e video."""
        if not (query or "").strip():
            return {"stato": "errore", "motivo": "serve dire quale video o quale canzone"}
        self.ferma()
        if self.ferma_radio is not None:
            self.ferma_radio()
        pronto = self.precarica() if self.precarica is not None else None
        try:
            try:
                trovati = self.cercatore(query)
            except Exception as errore:  # sotto c'è la rete e un servizio di terzi
                return {"stato": "errore", "motivo": f"non riesco a cercare su YouTube ({type(errore).__name__})"}
            if not trovati:
                return {"stato": "non_trovato", "query": query}
            self.elenco = trovati
            if self.in_background:
                primo = trovati[0]
                self.posizione = 0
                self._in_avvio = True
                generazione = self._generazione
                threading.Thread(target=self._avvia_in_background, args=(generazione, pronto), daemon=True).start()
                pronto = None  # lo chiude il thread quando ha finito
                return {"stato": "ok", "titolo": primo.titolo, "canale": primo.canale,
                        "durata": durata_a_voce(primo.durata), "posizione": f"1 di {len(trovati)}",
                        "nota": "il video sta partendo, ci vogliono pochi secondi"}
            for numero in range(min(self.tentativi, len(trovati))):
                risultato = self._parti(numero, pronto)
                if risultato is not None:
                    return risultato
            self.elenco, self.posizione = [], -1
            return {"stato": "errore", "motivo": "il video non parte: YouTube non mi risponde"}
        finally:
            if pronto is not None:
                pronto.chiudi()

    def _avvia_in_background(self, generazione: int, pronto: Any) -> None:
        """Risolve e avvia il primo risultato che parte; se nessuno parte lo segnala."""
        try:
            for numero in range(min(self.tentativi, len(self.elenco))):
                if generazione != self._generazione:
                    return
                if self._parti(numero, pronto, generazione) is not None:
                    return
            with self._lock:
                if generazione != self._generazione:
                    return
                self._in_avvio = False
                self.elenco, self.posizione = [], -1
            if self.al_fallimento is not None:
                self.al_fallimento("il video non parte: YouTube non mi risponde")
        finally:
            if pronto is not None:
                pronto.chiudi()

    def controllo(self, azione: str) -> dict[str, Any]:
        """pausa / riprendi / stop / successivo / precedente sul video in corso."""
        r = self._riproduzione
        if self._in_avvio and (r is None or not r.in_corso):
            if azione == "stop":
                self.ferma()
                return {"stato": "ok", "azione": azione}
            return {"stato": "sta_partendo", "nota": "il video parte fra pochi secondi"}
        if r is None or not r.in_corso:
            return {"stato": "niente_in_riproduzione"}
        if azione == "pausa":
            r.pausa()
            self._mostra("pause")
        elif azione == "riprendi":
            r.riprendi()
            self._mostra("resume")
        elif azione == "stop":
            self.ferma()
        elif azione in ("successivo", "precedente"):
            return self._scorri(1 if azione == "successivo" else -1)
        else:
            raise ValueError("azione deve essere una fra: pausa, riprendi, stop, successivo, precedente")
        return {"stato": "ok", "azione": azione}

    def _scorri(self, passo: int) -> dict[str, Any]:
        """Il risultato dopo (o prima) nella stessa ricerca, girando in tondo."""
        if not self.elenco:
            return {"stato": "niente_in_riproduzione"}
        elenco, posizione = self.elenco, self.posizione
        with self._lock:
            r, self._riproduzione = self._riproduzione, None
        if r is not None:
            r.ferma()
        for scarto in range(1, len(elenco) + 1):
            candidato = (posizione + passo * scarto) % len(elenco)
            self.elenco = elenco
            risultato = self._parti(candidato)
            if risultato is not None:
                return risultato
        self.elenco, self.posizione = [], -1
        self._mostra("stop")
        return {"stato": "errore", "motivo": "nessun altro video parte"}

    def _regola_volume_video(self, percento: int) -> bool:
        """Il volume software del video (`amixer sset Video`): False se non c'è (nessun asound.conf)."""
        if self._volume_software is False or not self.uscita_audio.endswith("video_out"):
            return False
        try:
            fatto = subprocess.run(["amixer", "-q", "sset", "Video", f"{percento}%"], capture_output=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            fatto = None
        self._volume_software = fatto is not None and fatto.returncode == 0
        return self._volume_software

    @contextmanager
    def abbassato(self, percento: int = VOLUME_VIDEO_ABBASSATO) -> Iterator[None]:
        """Abbassa il video per la durata del blocco (mentre BMO parla) e lo riporta al 100%.

        Non fa nulla se il video non suona o se non c'è il volume software: in quel caso video e voce
        suonano alla pari (o, senza dmix, uno solo dei due).
        """
        if not self.in_riproduzione() or not self._regola_volume_video(percento):
            yield
            return
        try:
            yield
        finally:
            self._regola_volume_video(100)

    @contextmanager
    def sospeso(self) -> Iterator[None]:
        """Mette in pausa il video per la durata del blocco, se sta andando.

        Come `Radio.sospesa()`: il microfono aperto sentirebbe l'audio del
        video come voce. La faccia intanto mostra l'ascolto (il pannello
        lascia il posto al video solo quando lo stato torna a riposo).
        """
        if not self.in_riproduzione():
            yield
            return
        self.controllo("pausa")
        try:
            yield
        finally:
            self.controllo("riprendi")
