"""Risolve un video YouTube in indirizzi diretti, caricando solo l'estrattore di YouTube.

`python -m yt_dlp` importa ~1800 estrattori prima di fare qualunque cosa: sul
Pi 3 A+ sono ~2-3 s dei ~5 totali. Qui si usa la stessa libreria con un solo
estrattore, e si stampa quello che serve a `video.risolvi_flusso`:

    640|360|25.0          larghezza|altezza|fps
    https://...           uno o due indirizzi (video, e audio se separato)

Uso: `python -m bmo_core.risolvi_youtube <formato> <url>` (oppure `--serve`, vedi `servi`). Esce con 1 e scrive
l'errore su stderr se non c'è un formato riproducibile.
"""
from __future__ import annotations

import json
import os
import sys


def risolvi(formato: str, url: str, cookie: str | None = None) -> tuple[str, list[str]]:
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeIE

    # `skip=hls`: il manifest HLS non serve (si usano gli indirizzi https diretti) e
    # scaricarlo costa ~0,4 s. Saltare la pagina del video invece no: YouTube risponde
    # con il controllo anti-bot (provato).
    opzioni = {"quiet": True, "no_warnings": True, "noplaylist": True, "format": formato, "js_runtimes": {},
               "extractor_args": {"youtube": {"skip": ["hls"]}}}
    if cookie:
        opzioni["cookiefile"] = cookie
    # Per le prove: es. BMO_YT_ARGS='{"youtube": {"skip": ["hls"]}}'
    extra = os.environ.get("BMO_YT_ARGS")
    if extra:
        opzioni["extractor_args"] = json.loads(extra)
    with YoutubeDL(opzioni, auto_init=False) as ydl:
        ydl.add_info_extractor(YoutubeIE())
        info = ydl.extract_info(url, download=False)
    parti = info.get("requested_formats") or [info]
    indirizzi = [p["url"] for p in parti if p.get("url")]
    if not indirizzi:
        raise RuntimeError("nessun flusso riproducibile")
    video = next((p for p in parti if p.get("vcodec") not in (None, "none")), info)
    return f"{video.get('width')}|{video.get('height')}|{video.get('fps')}", indirizzi


def servi() -> int:
    """Modalità "preavviata": carica subito le librerie e poi risolve le richieste che arrivano.

    Una richiesta per riga di stdin, `{"formato": ..., "url": ...}`; una risposta per riga,
    `{"forma": ..., "indirizzi": [...]}` oppure `{"errore": ...}`. `video.RisolutorePronto`
    la avvia mentre la ricerca è ancora in corso: i ~1,3 s di import di yt-dlp passano
    in parallelo invece che in fila.
    """
    import yt_dlp  # noqa: F401  (il caricamento è lo scopo)
    from yt_dlp.extractor.youtube import YoutubeIE  # noqa: F401

    print(json.dumps({"pronto": True}), flush=True)
    for riga in sys.stdin:
        try:
            richiesta = json.loads(riga)
            forma, indirizzi = risolvi(richiesta["formato"], richiesta["url"], os.environ.get("BMO_YT_COOKIES"))
            risposta = {"forma": forma, "indirizzi": indirizzi}
        except Exception as errore:
            risposta = {"errore": (str(errore).splitlines()[-1][:200] if str(errore) else type(errore).__name__)}
        print(json.dumps(risposta), flush=True)
    return 0


def main(argomenti: list[str]) -> int:
    if argomenti and argomenti[0] == "--serve":
        return servi()
    formato, url = argomenti[0], argomenti[1]
    try:
        forma, indirizzi = risolvi(formato, url, os.environ.get("BMO_YT_COOKIES"))
    except Exception as errore:  # yt-dlp solleva tipi diversi: qui si riduce tutto a un messaggio
        print(str(errore).splitlines()[-1][:200] if str(errore) else type(errore).__name__, file=sys.stderr)
        return 1
    print(forma)
    for indirizzo in indirizzi:
        print(indirizzo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
