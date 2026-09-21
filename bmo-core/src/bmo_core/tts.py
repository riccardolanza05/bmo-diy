"""Sintesi vocale col TTS di Gemini (issue #42).

Qui c'è **solo la sintesi**: testo in ingresso, un file WAV in uscita. Niente
riproduzione, niente ripiego, niente macchina a stati. La separazione non è
estetica: lo stesso `sintetizza()` serve a due padroni diversi —

- a runtime (#42), per dire le risposte del modello, che sono testo libero e
  non si possono pre-generare;
- offline sul PC di sviluppo (#21), per pre-generare le clip fisse di attesa
  e di errore una volta sola e spedirle come file.

Chi suona il WAV è affare di chi chiama (`macchina.VoceTts` a runtime).

**Non-streaming, di proposito** (§2.5 del piano): conoscere l'intera forma
d'onda prima di riprodurla regala la sincronia labiale alla #23, dove la
bocca è pilotata dall'inviluppo RMS. Con uno stream quella sincronia andrebbe
inseguita.

**Niente cascata di modelli.** `CascataModelli` (#12) ripiega da un modello di
testo a un altro modello di testo. Per il TTS non c'è nessun fratello su cui
ripiegare: se la sintesi non riesce, la risposta si dice sul terminale
(`macchina.voce_sul_terminale`), che è il ripiego previsto dalla #42.

**Il modello e la voce non sono verificati.** `gemini-3.1-flash-tts-preview`
viene dal piano (§2.5), scritto prima di questo SDK; il nome della voce è un
valore di partenza fra le ~30 disponibili. Entrambi si cambiano senza toccare
il codice, con `BMO_GEMINI_TTS_MODEL` e `BMO_VOCE`, e la lista vera si chiede
alla propria chiave:

    from google import genai
    print([m.name for m in genai.Client().models.list() if "tts" in m.name])

**La cache non è un'ottimizzazione, è il conto.** §2.5 stima che l'80% del
costo Gemini sia il TTS. Le frasi che BMO ripete (gli errori, le conferme)
si sintetizzano una volta e restano su disco. La chiave comprende modello,
voce e lingua: cambiarne uno deve produrre un file nuovo, non servire
l'audio vecchio.
"""
from __future__ import annotations

import hashlib
import os
import wave
from pathlib import Path
from typing import Any

from google.genai import types

from .config import percorso_dati

# Dal piano §2.5, non verificato con una chiave vera: vedi il docstring.
MODELLO_PREDEFINITO = "gemini-3.1-flash-tts-preview"
VOCE_PREDEFINITA = "Kore"
LINGUA_PREDEFINITA = "it-IT"

# Il formato che l'API restituisce: PCM 16 bit, mono, 24 kHz (§2.5). Non è
# un WAV: manca l'header, e mpv non lo suona così com'è.
FREQUENZA_HZ = 24000
CANALI = 1
BYTE_PER_CAMPIONE = 2

# Più generoso del tetto dei modelli di testo (15 s): qui si genera audio, e
# una frase lunga può metterci di più di una risposta breve.
TIMEOUT_S = 30.0


class TtsNonDisponibile(Exception):
    """La sintesi non è riuscita.

    Chi chiama non deve distinguere i casi per decidere *se* ripiegare — si
    ripiega sempre — ma il messaggio dice quale dei due sospetti guardare
    per primo, perché una chiave rifiutata e un nome di voce sbagliato si
    risolvono in modi opposti.
    """


def modello_configurato() -> str:
    return os.environ.get("BMO_GEMINI_TTS_MODEL") or MODELLO_PREDEFINITO


def voce_configurata() -> str:
    return os.environ.get("BMO_VOCE") or VOCE_PREDEFINITA


def lingua_configurata() -> str:
    return os.environ.get("BMO_LINGUA_TTS") or LINGUA_PREDEFINITA


def cartella_voce(percorso: Path | None = None) -> Path:
    """Dove finiscono i WAV sintetizzati.

    Accanto agli altri dati che sopravvivono a un riavvio, così sul Pi stanno
    in `/var/lib/bmo/voce` e `BMO_DATI` continua a spostare tutto insieme
    (i test non devono mai scrivere nella cartella vera).
    """
    return percorso or (percorso_dati() / "voce")


def _chiave(testo: str, modello: str, voce: str, lingua: str) -> str:
    """Il nome del file di cache.

    Modello, voce e lingua stanno *dentro* la chiave: se cambiano e la chiave
    no, BMO continuerebbe a dire la frase con la voce vecchia e nessuno
    capirebbe perché.
    """
    impronta = hashlib.sha256("\n".join([modello, voce, lingua, testo]).encode("utf-8")).hexdigest()
    return f"{impronta[:32]}.wav"


def scrivi_wav(percorso: Path, pcm: bytes) -> None:
    """Mette l'header RIFF davanti al PCM grezzo che arriva dall'API.

    Il controllo sulla lunghezza non è pedanteria: una risposta troncata
    produrrebbe un file valido e muto, che ha tutta l'aria di un successo
    finché non lo si ascolta — ed è proprio il guasto che i test con un
    client finto non vedono.
    """
    if not pcm:
        raise TtsNonDisponibile("l'API ha restituito audio vuoto")
    if len(pcm) % BYTE_PER_CAMPIONE:
        raise TtsNonDisponibile(f"audio troncato: {len(pcm)} byte non sono campioni interi a 16 bit")
    percorso.parent.mkdir(parents=True, exist_ok=True)
    # Prima un temporaneo e poi rename, come per i timer (#20): un'interruzione
    # a metà non deve lasciare in cache un WAV mezzo scritto che poi verrebbe
    # servito come buono per sempre.
    temporaneo = percorso.with_suffix(".wav.parziale")
    with wave.open(str(temporaneo), "wb") as f:
        f.setnchannels(CANALI)
        f.setsampwidth(BYTE_PER_CAMPIONE)
        f.setframerate(FREQUENZA_HZ)
        f.writeframes(pcm)
    temporaneo.replace(percorso)


def durata_s(percorso: Path) -> float:
    """Quanto dura un WAV. Serve alla #21 per dimensionare le clip."""
    with wave.open(str(percorso), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def _estrai_pcm(risposta: Any) -> bytes:
    """Tira fuori i byte audio dalla risposta.

    Si scorrono le parti invece di prendere la prima: il modello può
    anteporre una parte di testo, e in quel caso `parts[0].inline_data`
    sarebbe `None`.
    """
    for candidato in getattr(risposta, "candidates", None) or []:
        contenuto = getattr(candidato, "content", None)
        for parte in getattr(contenuto, "parts", None) or []:
            dati = getattr(getattr(parte, "inline_data", None), "data", None)
            if dati:
                return dati
    raise TtsNonDisponibile("nessun audio nella risposta del modello")


def crea_client() -> Any:
    from google import genai

    # Come il cervello, legge GEMINI_API_KEY dall'ambiente.
    return genai.Client(http_options=types.HttpOptions(timeout=int(TIMEOUT_S * 1000)))


def sintetizza(
    testo: str,
    client: Any = None,
    cartella: Path | None = None,
    modello: str | None = None,
    voce: str | None = None,
    lingua: str | None = None,
    usa_cache: bool = True,
) -> Path:
    """Sintetizza `testo` e restituisce il percorso del WAV.

    Se la frase è già in cache non chiama nessuna rete: è il caso comune per
    le frasi che BMO ripete. `usa_cache=False` forza la risintesi, che serve
    quando si sta provando una voce diversa.

    Solleva `TtsNonDisponibile` per qualunque guaio. Chi chiama ripiega, non
    decide.
    """
    testo = (testo or "").strip()
    if not testo:
        raise ValueError("testo non può essere vuoto")

    modello = modello or modello_configurato()
    voce = voce or voce_configurata()
    lingua = lingua or lingua_configurata()
    percorso = cartella_voce(cartella) / _chiave(testo, modello, voce, lingua)
    if usa_cache and percorso.exists():
        return percorso

    client = client or crea_client()
    configurazione = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code=lingua,
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voce)),
        ),
    )
    try:
        risposta = client.models.generate_content(model=modello, contents=testo, config=configurazione)
    except TtsNonDisponibile:
        raise
    except Exception as errore:  # errori dell'SDK, di rete, di quota: per chi chiama sono la stessa cosa
        raise TtsNonDisponibile(
            f"sintesi fallita con modello={modello!r} voce={voce!r}: {errore}. "
            "Un 400 o un 404 di solito è il nome del modello (BMO_GEMINI_TTS_MODEL) "
            "o della voce (BMO_VOCE); un 401/403 è la chiave (GEMINI_API_KEY)."
        ) from errore

    scrivi_wav(percorso, _estrai_pcm(risposta))
    return percorso


def main() -> None:
    """Prova la sintesi da riga di comando, senza tirare in ballo BMO intero."""
    import argparse
    import subprocess
    import sys
    import time

    parser = argparse.ArgumentParser(description="Sintetizza una frase col TTS di Gemini (#42).")
    parser.add_argument("testo", help="la frase da far dire a BMO")
    parser.add_argument("--voce", help=f"nome della voce (default: {VOCE_PREDEFINITA}, o BMO_VOCE)")
    parser.add_argument("--modello", help=f"modello TTS (default: {MODELLO_PREDEFINITO}, o BMO_GEMINI_TTS_MODEL)")
    parser.add_argument("--senza-cache", action="store_true", help="risintetizza anche se la frase è già su disco")
    parser.add_argument("--zitto", action="store_true", help="scrive il WAV senza riprodurlo")
    argomenti = parser.parse_args()

    inizio = time.monotonic()
    try:
        percorso = sintetizza(
            argomenti.testo,
            modello=argomenti.modello,
            voce=argomenti.voce,
            usa_cache=not argomenti.senza_cache,
        )
    except TtsNonDisponibile as errore:
        print(f"TTS non disponibile: {errore}", file=sys.stderr)
        raise SystemExit(1) from errore
    sintesi_s = time.monotonic() - inizio

    print(f"{percorso}  ({durata_s(percorso):.1f} s di audio, sintesi in {sintesi_s:.2f} s)")
    if not argomenti.zitto:
        subprocess.run(["mpv", "--no-video", "--really-quiet", str(percorso)], check=False)


if __name__ == "__main__":
    main()
