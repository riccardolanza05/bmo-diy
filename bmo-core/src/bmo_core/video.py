"""I video di YouTube su BMO: cercarli, risolverli, decodificarli per lo schermo.

Niente chiavi e niente account: la ricerca e la risoluzione degli indirizzi
passano da `yt-dlp` (gratis, nessuna quota; la YouTube Data API costerebbe 100
unità su 10 000 al giorno per ogni ricerca, cioè ~100 ricerche al giorno, e
chiede una chiave). `yt-dlp` gira sempre in un processo separato che finisce
subito: la sua RAM (Python, e il runtime JavaScript che YouTube ora richiede)
torna al sistema prima che parta la riproduzione, e i 320 MB di budget del Pi
non vedono mai insieme yt-dlp e ffmpeg.

La pipeline di riproduzione è un solo ffmpeg con due uscite, entrambe al ritmo
reale (`-re`), così audio e video restano agganciati senza un orologio nostro:

    indirizzo googlevideo ──ffmpeg──┬─ video: rgb565 raw, LARGHEZZA×ALTEZZA ─> stdout (il blit sullo schermo)
                                    └─ audio: ALSA/ pulse / null              ─> scheda audio

Lo schermo è 240×320 in verticale ma BMO lo usa per terra in orizzontale, come
una console: il video è 320×240 (4:3), con bande nere se il video è 16:9.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Iterator

LARGHEZZA, ALTEZZA = 320, 240
FPS = 15  # il bus SPI a schermo pieno regge ~25-35 fps: 15 lascia margine a bmo-face
BYTE_PER_FOTOGRAMMA = LARGHEZZA * ALTEZZA * 2  # rgb565
QUANTI = 5
DURATA_MASSIMA_S = 2 * 3600  # niente dirette (durata assente) né maratone da 100 ore

# 240p h264 + audio aac (piccoli: ~80 kbit/s + 130 kbit/s), altrimenti il 360p già
# muxato (formato 18), altrimenti il meglio fino a 360p. h264 perché è l'unico codec
# di YouTube che il Pi decodifica senza fatica (VP9/AV1 no).
FORMATO = "bv*[vcodec^=avc1][height<=240]+ba[acodec^=mp4a]/18/b[height<=360]"


@dataclass
class Video:
    id: str
    titolo: str
    durata: int  # secondi
    canale: str = ""

    @property
    def pagina(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


def _esegui_ytdlp(argomenti: list[str], timeout: float = 45.0) -> str:
    """yt-dlp come processo figlio: muore subito e rende tutta la sua memoria."""
    eseguibile = shutil.which("yt-dlp")
    if eseguibile is None:
        raise RuntimeError("yt-dlp non è installato")
    fatto = subprocess.run(
        [eseguibile, "--no-warnings", "--no-playlist", *argomenti],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    if fatto.returncode != 0:
        raise RuntimeError((fatto.stderr.strip().splitlines() or ["yt-dlp fallito"])[-1][:200])
    return fatto.stdout


def cerca_video(
    query: str,
    quanti: int = QUANTI,
    esegui: Callable[[list[str]], str] = _esegui_ytdlp,
) -> list[Video]:
    """Cerca su YouTube; scarta dirette e video lunghissimi."""
    uscita = esegui(["--flat-playlist", "-j", f"ytsearch{quanti * 2}:{query.strip()}"])
    trovati: list[Video] = []
    for riga in uscita.splitlines():
        try:
            dato: dict[str, Any] = json.loads(riga)
        except json.JSONDecodeError:
            continue
        durata = dato.get("duration")
        if not dato.get("id") or not durata or durata > DURATA_MASSIMA_S:
            continue
        trovati.append(Video(dato["id"], (dato.get("title") or "").strip(), int(durata),
                             dato.get("channel") or dato.get("uploader") or ""))
    return trovati[:quanti]


def risolvi_flussi(
    video: Video,
    esegui: Callable[[list[str]], str] = _esegui_ytdlp,
) -> list[str]:
    """Gli indirizzi diretti da dare a ffmpeg: uno (già muxato) o due (video + audio)."""
    indirizzi = [r for r in esegui(["-g", "-f", FORMATO, video.pagina]).splitlines() if r.startswith("http")]
    if not indirizzi:
        raise RuntimeError("nessun flusso riproducibile")
    return indirizzi


def comando_ffmpeg(indirizzi: list[str], uscita_audio: str = "alsa:default", inizio_s: int = 0) -> list[str]:
    """Il comando ffmpeg: video rgb565 su stdout, audio sull'uscita indicata.

    `uscita_audio`: "alsa:<dispositivo>", "pulse", oppure "null" (per i test e le
    misure: si decodifica tutto ma non si suona niente).
    """
    comando = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    for indirizzo in indirizzi:
        comando += ["-re", *(["-ss", str(inizio_s)] if inizio_s else []), "-i", indirizzo]
    # Un solo ingresso: video e audio vengono dallo stesso file; due: video dal primo, audio dal secondo.
    audio = "1:a:0" if len(indirizzi) > 1 else "0:a:0"
    filtro = (
        f"fps={FPS},scale={LARGHEZZA}:{ALTEZZA}:force_original_aspect_ratio=decrease,"
        f"pad={LARGHEZZA}:{ALTEZZA}:(ow-iw)/2:(oh-ih)/2,format=rgb565le"
    )
    comando += ["-map", "0:v:0", "-vf", filtro, "-f", "rawvideo", "pipe:1"]
    if uscita_audio == "null":
        comando += ["-map", audio, "-f", "null", "-"]
    elif uscita_audio == "pulse":
        comando += ["-map", audio, "-f", "pulse", "bmo-video"]
    else:
        comando += ["-map", audio, "-f", "alsa", uscita_audio.split(":", 1)[-1]]
    return comando


def fotogrammi(processo: subprocess.Popen[bytes]) -> Iterator[bytes]:
    """I fotogrammi rgb565 (BYTE_PER_FOTOGRAMMA byte l'uno) che escono da ffmpeg."""
    assert processo.stdout is not None
    while True:
        blocco = processo.stdout.read(BYTE_PER_FOTOGRAMMA)
        if len(blocco) < BYTE_PER_FOTOGRAMMA:
            return
        yield blocco


def riproduci(
    indirizzi: list[str],
    su_fotogramma: Callable[[bytes], None],
    uscita_audio: str = "alsa:default",
) -> int:
    """Suona e mostra finché il video non finisce. Ritorna i fotogrammi consegnati."""
    processo = subprocess.Popen(
        comando_ffmpeg(indirizzi, uscita_audio),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=BYTE_PER_FOTOGRAMMA * 2,
    )
    consegnati = 0
    try:
        for blocco in fotogrammi(processo):
            su_fotogramma(blocco)
            consegnati += 1
    finally:
        if processo.poll() is None:
            processo.terminate()
        processo.wait()
    return consegnati
