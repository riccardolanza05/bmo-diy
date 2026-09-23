"""Sintesi vocale per la voce di BMO (issue #42).

Due motori, scelti con `BMO_TTS_MOTORE`:

- **`edge`** (predefinito) — le voci neurali di Microsoft tramite `edge-tts`.
  È il motore scelto: BMO parla con `it-IT-DiegoNeural` al +20% di velocità.
- **`gemini`** — il TTS di Gemini con la cascata di tre modelli. Resta un
  motore alternativo funzionante, **ma non è più il generatore delle clip**:
  vedi la nota sulla voce unica qui sotto.

**La voce di BMO è una sola, sempre la stessa** (deciso il 23/9). BMO è un
personaggio: una pausa è un difetto minore, una voce diversa a metà
conversazione è un difetto peggiore. Da cui due regole che sembrano dettagli
e non lo sono:

1. **Le clip fisse pre-generate (#21) vanno generate con lo stesso motore e
   la stessa voce delle risposte a runtime.** La issue #21 dice «col TTS di
   Gemini» perché è stata scritta prima di questa decisione: generarle con
   Gemini mentre BMO risponde con Diego darebbe a BMO due voci.
2. **Il ripiego accettabile non è un'altra voce**: è il terminale
   (`macchina.voce_sul_terminale`), o il silenzio, o una clip già registrata
   nella voce giusta.

**Perché edge-tts e non Gemini**: misurato il 22-23/9, Gemini impiega ~1,2 s
fissi più 0,5 s per ogni secondo di audio e concede 3 richieste al minuto per
modello; edge-tts sintetizza in ~0,6 s e ha retto 10 richieste consecutive
senza rallentare. All'ascolto in cieco Riccardo ha scelto Diego.

⚠️ **`edge-tts` è un client non ufficiale** dell'endpoint di lettura di Edge:
nessuna quota documentata, nessun permesso d'uso da terze parti, e si è già
rotto in passato. Se un giorno BMO ammutolisce, è il primo sospetto. La cura
è Azure Speech F0, che serve **la stessa identica voce** `it-IT-DiegoNeural`
ufficialmente (500.000 caratteri al mese gratis): migrare non cambia come
suona BMO, quindi non viola la regola della voce unica.

Qui c'è **solo la sintesi**: testo in ingresso, un file audio in uscita.
Niente riproduzione, niente ripiego, niente macchina a stati. La separazione non è
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

**Anche il TTS ha la sua cascata** (#12), e questo e' il motivo. Su AI Studio
il limite di `gemini-3.1-flash-tts-preview` risulta di **3 richieste al
minuto**, e ogni frase che BMO pronuncia e' una richiesta: una conversazione
un po' vivace lo esaurisce. Ma i modelli TTS sono tre, ciascuno con il suo
contatore, quindi ripiegare sul successivo triplica la capacita' invece di
lasciare BMO muto. (Una versione precedente di questo modulo diceva che per
il TTS non c'era nessun fratello su cui ripiegare: era sbagliato — i fratelli
sono gli altri due modelli TTS, non i modelli di testo, verso cui infatti non
si ripiega.)

La cascata **va tenuta viva fra una frase e l'altra**: e' la memoria di quale
modello e' a quota che le permette di saltarlo direttamente al giro dopo.
Ricrearla a ogni sintesi significherebbe sbattere ogni volta contro lo stesso
429 prima di ripiegare, buttando via una richiesta su tre.

Se falliscono tutti e tre, la risposta si dice sul terminale
(`macchina.voce_sul_terminale`), che e' il ripiego previsto dalla #42.

**Attenzione alla voce quando si ripiega**: i nomi delle ~30 voci sono
documentati per tutti e tre i modelli, ma la resa puo' cambiare. Due frasi di
fila dette da modelli diversi potrebbero non sembrare lo stesso personaggio.

**Modello e voce, verificati il 22/9**: `gemini-3.1-flash-tts-preview` esiste
con la chiave del progetto e `Kore` parla italiano. La lista si chiede sempre
cosi':

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
from .modelli import CascataModelli, GeminiNonDisponibile

# Verificati il 22/9 con la chiave del progetto. L'ordine e' la cascata: il
# 3.1 e' il migliore all'ascolto, i 2.5 servono quando il primo e' a quota.
# Il pro sta per ultimo perche' e' il piu' lento.
MODELLI_TTS_PREDEFINITI = [
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]
MODELLO_PREDEFINITO = MODELLI_TTS_PREDEFINITI[0]
# Codice di lingua breve, non una locale: e' lo stesso che il modello
# dichiara nella risposta (`brain.LINGUE`). La locale per Gemini si ricava
# da `LOCALI`.
LINGUA_PREDEFINITA = "it"

MOTORE_PREDEFINITO = "edge"

# La voce si sceglie dal campo `lingua` che il modello dichiara nella risposta
# (`brain.separa_etichette`): dichiararla e' piu' affidabile che farla
# indovinare al sintetizzatore, e si vede nei log quando sbaglia.
#
# In italiano parla Diego, che e' la voce scelta all'ascolto. Per **tutte le
# altre lingue** parla una voce multilingua sola, non una per lingua: cosi'
# aggiungere una lingua non richiede nessuna riga qui, e BMO non diventa un
# coro di voci diverse.
VOCI_EDGE = {"it": "it-IT-DiegoNeural"}
# Giuseppe e' la multilingua piu' vicina a Diego: stessa lingua madre, quindi
# BMO non cambia carattere passando all'inglese, solo lingua.
VOCE_EDGE_ALTRE_LINGUE = "it-IT-GiuseppeMultilingualNeural"

VOCI_GEMINI: dict[str, str] = {}
VOCE_GEMINI_ALTRE_LINGUE = "Kore"  # Gemini usa la stessa voce per tutte
# Il `language_code` che l'API di Gemini vuole, che e' una locale e non un
# codice di lingua.
LOCALI = {"it": "it-IT", "en": "en-US"}

# La voce di BMO, scelta all'ascolto il 23/9 fra le quattro italiane e le
# multilingua di edge-tts. La velocita' fa parte dell'identita' quanto la
# voce: al naturale i modelli neurali risultano troppo compassati per BMO.
VOCE_EDGE_PREDEFINITA = VOCI_EDGE["it"]
# +35%: il centro della forchetta indicata da Riccardo il 23/9 dopo l'ascolto
# ("fra il 30 e il 40"). Il +20% di partenza risultava ancora compassato.
VELOCITA_PREDEFINITA = "+35%"

# La voce del motore Gemini, che e' un'altra cosa: nomi di voce diversi.
VOCE_GEMINI_PREDEFINITA = VOCE_GEMINI_ALTRE_LINGUE

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


def modelli_configurati() -> list[str]:
    """La cascata TTS, in ordine di preferenza.

    `BMO_GEMINI_TTS_MODELLI` e' un elenco separato da virgole;
    `BMO_GEMINI_TTS_MODEL` (singolare) forza un modello solo, utile per
    provarne uno senza ripieghi.
    """
    elenco = os.environ.get("BMO_GEMINI_TTS_MODELLI", "")
    if modelli := [m.strip() for m in elenco.split(",") if m.strip()]:
        return modelli
    if singolo := os.environ.get("BMO_GEMINI_TTS_MODEL", "").strip():
        return [singolo]
    return list(MODELLI_TTS_PREDEFINITI)


def modello_configurato() -> str:
    """Il primario della cascata."""
    return modelli_configurati()[0]


_cascata: CascataModelli | None = None


def cascata_condivisa() -> CascataModelli:
    """La cascata TTS del processo, creata una volta sola.

    Condivisa di proposito: le sospensioni dopo un 429 devono valere per le
    frasi successive, altrimenti ogni sintesi ricomincia dal modello che si
    sa gia' essere a quota.
    """
    global _cascata
    if _cascata is None:
        _cascata = CascataModelli(modelli_configurati())
    return _cascata


def motore_configurato() -> str:
    """Quale motore sintetizza: `edge` (predefinito) o `gemini`."""
    return (os.environ.get("BMO_TTS_MOTORE") or MOTORE_PREDEFINITO).strip().lower()


def voce_configurata(motore: str | None = None, lingua: str | None = None) -> str:
    """Il nome della voce, che dipende dal motore e dalla lingua.

    I due motori hanno cataloghi diversi e incompatibili: `it-IT-DiegoNeural`
    non esiste su Gemini e `Kore` non esiste su edge-tts.

    Si guarda prima `BMO_VOCE_<LINGUA>` (`BMO_VOCE_EN`, `BMO_VOCE_IT`), poi
    `BMO_VOCE` che vale per tutte le lingue — utile per provare una voce
    sola — e infine la mappa predefinita.
    """
    lingua = codice_lingua(lingua)
    if specifica := os.environ.get(f"BMO_VOCE_{lingua.upper()}"):
        return specifica
    if impostata := os.environ.get("BMO_VOCE"):
        return impostata
    if (motore or motore_configurato()) == "gemini":
        return VOCI_GEMINI.get(lingua, VOCE_GEMINI_ALTRE_LINGUE)
    return VOCI_EDGE.get(lingua, VOCE_EDGE_ALTRE_LINGUE)


def velocita_configurata() -> str:
    """Quanto piu' svelto del naturale parla BMO, in formato SSML (`+20%`)."""
    return os.environ.get("BMO_VOCE_VELOCITA") or VELOCITA_PREDEFINITA


def codice_lingua(lingua: str | None = None) -> str:
    """Normalizza a codice breve: accetta sia "it" sia "it-IT"."""
    return (lingua or lingua_configurata()).strip().lower().split("-")[0]


def lingua_configurata() -> str:
    return os.environ.get("BMO_LINGUA_TTS") or LINGUA_PREDEFINITA


def cartella_voce(percorso: Path | None = None) -> Path:
    """Dove finiscono i WAV sintetizzati.

    Accanto agli altri dati che sopravvivono a un riavvio, così sul Pi stanno
    in `/var/lib/bmo/voce` e `BMO_DATI` continua a spostare tutto insieme
    (i test non devono mai scrivere nella cartella vera).
    """
    return percorso or (percorso_dati() / "voce")


def _chiave(testo: str, modello: str, voce: str, lingua: str, suffisso: str = ".wav") -> str:
    """Il nome del file di cache.

    Motore/modello, voce e lingua stanno *dentro* la chiave: se cambiano e la
    chiave no, BMO continuerebbe a dire la frase con la voce vecchia e nessuno
    capirebbe perché. Per edge-tts la velocità entra nel campo `lingua`, che
    porta anche lei: `+20%` fa parte dell'identità di BMO quanto la voce.

    Il suffisso cambia col motore: Gemini restituisce PCM che diventa WAV,
    edge-tts restituisce mp3 e non offre alternative.
    """
    impronta = hashlib.sha256("\n".join([modello, voce, lingua, testo]).encode("utf-8")).hexdigest()
    return f"{impronta[:32]}{suffisso}"


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


def durata_s(percorso: Path) -> float | None:
    """Quanto dura un WAV, o `None` se il formato non si legge a buon mercato.

    Serve alla #21 per dimensionare le clip e al comando a riga di comando.
    **Non va usata a ogni risposta**: leggere la durata di un mp3 richiederebbe
    di decodificarlo o di lanciare `ffprobe`, e un processo in piu' per frase e'
    esattamente il costo che i filtri di mpv ci hanno permesso di evitare. Per
    questo `VoceTts` stampa solo i due tempi, che sono quello che il criterio
    di uscita della #42 chiede davvero.
    """
    if percorso.suffix.lower() != ".wav":
        return None
    with wave.open(str(percorso), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def _sintetizza_edge(percorso: Path, testo: str, voce: str, velocita: str) -> None:
    """Sintesi con edge-tts, scritta su `percorso` (mp3).

    edge-tts non offre scelta di formato: restituisce mp3 a 24 kHz. Va bene —
    mpv lo suona, e per la sincronia labiale della #23 la forma d'onda si
    ricava decodificandolo, che e' quello che andrebbe fatto comunque.
    """
    import asyncio

    import edge_tts

    percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(percorso.suffix + ".parziale")
    try:
        # `edge_tts` e' asincrono e `bmo-core` no. `asyncio.run` e' sicuro
        # perche' nessuna parte di BMO gira dentro un event loop: e' questo
        # l'unico punto in cui serve. Se un giorno BMO diventasse asincrono
        # qui salterebbe un RuntimeError ("event loop already running") e
        # andrebbe sostituito con un await — non e' una svista.
        asyncio.run(edge_tts.Communicate(testo, voce, rate=velocita).save(str(temporaneo)))
    except Exception as errore:
        temporaneo.unlink(missing_ok=True)
        raise TtsNonDisponibile(
            f"sintesi edge-tts fallita con voce={voce!r} velocita={velocita!r}: {errore}. "
            "edge-tts e' un client non ufficiale: se ha smesso di funzionare del tutto, "
            "il ripiego previsto e' Azure Speech con la stessa voce."
        ) from errore
    if not temporaneo.exists() or temporaneo.stat().st_size == 0:
        temporaneo.unlink(missing_ok=True)
        raise TtsNonDisponibile("edge-tts ha prodotto un file vuoto")
    # Come per i WAV e per i timer (#20): prima il temporaneo, poi il rename.
    # Un'interruzione a meta' non deve lasciare in cache un audio mozzato che
    # verrebbe poi servito come buono per sempre.
    temporaneo.replace(percorso)


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
    modelli: list[str] | None = None,
    cascata: CascataModelli | None = None,
    voce: str | None = None,
    lingua: str | None = None,
    velocita: str | None = None,
    motore: str | None = None,
    usa_cache: bool = True,
) -> Path:
    """Sintetizza `testo` e restituisce il percorso del file audio.

    Se la frase è già in cache non chiama nessuna rete: è il caso comune per
    le frasi che BMO ripete, ed è anche la prima difesa dal limite di 3
    richieste al minuto. **La cache si cerca per tutti i modelli della
    cascata**, non solo per il primario: un WAV già su disco dice la stessa
    frase, e risintetizzarlo per "farlo dire al modello giusto" spenderebbe
    una richiesta che non abbiamo.

    `lingua` e' il codice breve che il modello dichiara nella risposta ("it",
    "en"): decide **quale voce** parla, che e' il punto di tutto il
    meccanismo bilingue. `motore` sceglie fra `edge` e `gemini` (predefinito
    da `BMO_TTS_MOTORE`).
    `modello`, `modelli` e `cascata` riguardano solo Gemini e vengono ignorati
    da edge-tts. `usa_cache=False` forza la risintesi, utile per provare una
    voce diversa o misurare i tempi veri.

    Solleva `TtsNonDisponibile` per qualunque guaio. Chi chiama ripiega, non
    decide.
    """
    testo = (testo or "").strip()
    if not testo:
        raise ValueError("testo non può essere vuoto")

    motore = (motore or motore_configurato()).strip().lower()
    lingua = codice_lingua(lingua)
    voce = voce or voce_configurata(motore, lingua)
    cartella_wav = cartella_voce(cartella)

    if motore != "gemini":
        # La velocita' entra nella chiave: cambiarla deve produrre un file
        # nuovo, non servire l'audio con la cadenza vecchia.
        velocita = velocita or velocita_configurata()
        percorso = cartella_wav / _chiave(testo, "edge", voce, velocita, suffisso=".mp3")
        if usa_cache and percorso.exists():
            return percorso
        _sintetizza_edge(percorso, testo, voce, velocita)
        return percorso

    if modello:
        cascata = CascataModelli([modello])
    elif modelli:
        cascata = CascataModelli(modelli)
    elif cascata is None:
        cascata = cascata_condivisa()

    if usa_cache:
        for candidato in cascata.modelli:
            percorso = cartella_wav / _chiave(testo, candidato, voce, lingua)
            if percorso.exists():
                return percorso

    client = client or crea_client()
    configurazione = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        # Senza questo l'SDK stampa a ogni sintesi un avviso sull'automatic
        # function calling (visto nella prova del 22/9). Qui di strumenti non
        # ce n'è nessuno — si chiede solo di leggere una frase — e quel
        # rumore finirebbe sullo stderr a ogni risposta di BMO.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        speech_config=types.SpeechConfig(
            # Gemini vuole una locale ("it-IT"), non il codice breve che il
            # modello dichiara nella risposta ("it").
            language_code=LOCALI.get(lingua, lingua),
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voce)),
        ),
    )
    try:
        risposta, usato = cascata.genera(client, contents=testo, config=configurazione)
    except TtsNonDisponibile:
        raise
    except GeminiNonDisponibile as errore:
        raise TtsNonDisponibile(
            f"nessuno dei modelli TTS ha risposto ({', '.join(cascata.modelli)}): {errore}. "
            "Con 3 richieste al minuto per modello, parlare troppo in fretta li esaurisce tutti."
        ) from errore
    except Exception as errore:  # errori dell'SDK, di rete, di quota: per chi chiama sono la stessa cosa
        raise TtsNonDisponibile(
            f"sintesi fallita con modelli={cascata.modelli} voce={voce!r}: {errore}. "
            "Un 400 o un 404 di solito è il nome del modello (BMO_GEMINI_TTS_MODELLI) "
            "o della voce (BMO_VOCE); un 401/403 è la chiave (GEMINI_API_KEY)."
        ) from errore

    # La chiave porta il modello che ha davvero prodotto l'audio, non quello
    # che avremmo voluto: altrimenti la ricerca in cache del giro dopo non lo
    # troverebbe e lo pagheremmo due volte.
    percorso = cartella_wav / _chiave(testo, usato, voce, lingua)
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
    parser.add_argument("--voce", help="nome della voce (default: quella del motore, o BMO_VOCE)")
    # Il % va raddoppiato: argparse applica la formattazione %-style al testo
    # d'aiuto, e "+20%" da solo lo fa fallire con "badly formed help string".
    parser.add_argument(
        "--velocita",
        help=f"velocita' SSML (default: {VELOCITA_PREDEFINITA.replace('%', '%%')}, o BMO_VOCE_VELOCITA)",
    )
    parser.add_argument(
        "--motore", choices=["edge", "gemini"],
        help=f"motore di sintesi (default: {MOTORE_PREDEFINITO}, o BMO_TTS_MOTORE)",
    )
    parser.add_argument("--modello", help=f"modello TTS di Gemini (default: {MODELLO_PREDEFINITO})")
    parser.add_argument("--senza-cache", action="store_true", help="risintetizza anche se la frase è già su disco")
    parser.add_argument("--zitto", action="store_true", help="scrive il WAV senza riprodurlo")
    argomenti = parser.parse_args()

    inizio = time.monotonic()
    try:
        percorso = sintetizza(
            argomenti.testo,
            modello=argomenti.modello,
            voce=argomenti.voce,
            velocita=argomenti.velocita,
            motore=argomenti.motore,
            usa_cache=not argomenti.senza_cache,
        )
    except TtsNonDisponibile as errore:
        print(f"TTS non disponibile: {errore}", file=sys.stderr)
        raise SystemExit(1) from errore
    sintesi_s = time.monotonic() - inizio

    durata = durata_s(percorso)
    quanto = f"{durata:.1f} s di audio, " if durata is not None else ""
    print(f"{percorso}  ({quanto}sintesi in {sintesi_s:.2f} s)")
    if not argomenti.zitto:
        subprocess.run(["mpv", "--no-video", "--really-quiet", str(percorso)], check=False)


if __name__ == "__main__":
    main()
