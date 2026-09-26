"""Il cervello di BMO: ascolta → rispondi → strumenti, con Gemini in cloud.

Fasi 1.1 e 1.2 della roadmap (issue #19). Questo modulo dipende solo dai
Protocol di `adapters.base` e dalle funzioni `crea_*` della factory, mai
dalle classi concrete: gira identico sul PC di sviluppo e sul Pi.

Riferimenti nel piano: §2.1 (loop agentico, max 4 giri), §2.3 (prompt di
sistema a due strati), §2.4 (strumenti, dichiarati in `strumenti.py`). Per
ora funzionano davvero solo i timer, in memoria; gli altri strumenti
rispondono `non_disponibile`. Persistenza e implementazione arrivano con
l'issue #20.
"""
from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx
from google.genai import errors, types

from .adapters import (
    STATO_ASCOLTO,
    STATO_ERRORE,
    STATO_PARLATO,
    STATO_PENSIERO,
    AudioInputAdapter,
    FacciaAdapter,
    crea_audio_input,
    crea_faccia,
)
from .config import FUSO_ORARIO
from .memoria import Voce, aggiungi_voce, carica_diario
from .modelli import TENTATIVI_SDK, TIMEOUT_TENTATIVO_S, CascataModelli, GeminiNonDisponibile
from .ricerca import cerca
from .sessione import (
    BUDGET_DOPO_IL_TURNO_S,
    INATTIVITA_SESSIONE_S,
    ISTRUZIONE_ESTRAZIONE,
    ISTRUZIONE_RIASSUNTO_SESSIONE,
    ISTRUZIONE_TRASCRIZIONE,
    MAX_TENTATIVI_ESTRAZIONE,
    MAX_VOCI_PER_ESTRAZIONE,
    NIENTE_DA_RICORDARE,
    TETTO_TOKEN_STORICO,
    StoricoSessione,
)
from .strumenti import DICHIARAZIONI
from .timer import ArchivioTimer, Timer
from .vad import AGGRESSIVITA_PREDEFINITA, SILENZIO_MS_PREDEFINITO, Diagnostica
DURATA_ASCOLTO_S = 3.0

# Tetto di sicurezza per ascolta_fino_al_silenzio(): a differenza di
# DURATA_ASCOLTO_S (una durata fissa, per le prove scriptate) questo è un
# limite massimo che quasi non si dovrebbe mai toccare, perché il VAD si
# ferma prima da solo. Il piano (§2.1) lo fissava già a 15 s.
CAP_ASCOLTO_S = 15.0

# Giri in cui BMO può chiamare strumenti (§2.1). Dopo questi, o quando finisce
# il tempo, arriva una richiesta di riepilogo in più, senza strumenti (#18).
MAX_GIRI = 4

# Tetto del turno, dall'audio alla risposta (§2.1: «max 4 giri / 20 s»). Non è
# un obiettivo — quello è 2,5-3,5 s — ma il caso peggiore oltre il quale un
# BMO che tace sembra rotto. La riserva è il tempo tenuto da parte per il
# riepilogo: passata quella soglia non si comincia nessun altro giro.
TETTO_TURNO_S = 20.0
RISERVA_RIEPILOGO_S = 6.0

ESPRESSIONI = ("felice", "pensieroso", "sorpreso", "triste", "assonnato")

# Le lingue che BMO parla. Il modello le dichiara con un'etichetta iniziale
# come fa gia' per l'espressione, e il codice sceglie la voce di conseguenza:
# dichiararla e' piu' affidabile che farla indovinare al sintetizzatore, e si
# vede nei log quando sbaglia.
LINGUE = ("it", "en")
LINGUA_PREDEFINITA = "it"
_ETICHETTA_INIZIALE = re.compile(r"^\s*\[([^\]\n]{1,30})\]\s*")

# Un modello che elenca i fatti dell'estrazione (#29) quasi sempre li punta o
# li numera, anche se il prompt chiede "senza punti elenco": si toglie il
# prefisso invece di scartare la riga intera.
_PREFISSO_ELENCO = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")

# Gli stati della faccia (STATO_ASCOLTO, STATO_PENSIERO, …) stanno in
# adapters/base.py, accanto al Protocol: li usa anche la sveglia dei timer,
# che non ha niente a che fare con Gemini. Sono un'altra cosa dalle
# ESPRESSIONI qui sopra, che le sceglie il modello per la risposta parlata.

# Primo strato del prompt (§2.3). È la bozza v4 (prompt/bozza-v4.txt), 40 frasi
# su 40 nella prova del 19/9; le bozze in prompt/ restano come storico.
PROMPT_FISSO = """\
Sei BMO, la piccola console vivente di Adventure Time, e vivi in una casa a Milano.
Sei entusiasta, curioso e un po' ingenuo; ti preoccupi dei tuoi amici. Non sei servile.
Sei bilingue: italiano e inglese ti vengono uguale, e usi quello di chi ti sta parlando.

COME PARLI — il tuo testo va a un sintetizzatore vocale, queste regole sono vincolanti:
- LA LINGUA VIENE PRIMA DI OGNI ALTRA COSA. Rispondi SEMPRE nella lingua in cui ti
  hanno appena parlato, per tutta la risposta, non una parola soltanto.
  Se la frase che hai appena sentito e' in inglese, la tua risposta e' in inglese.
  Vivere a Milano non c'entra niente: sei bilingue, e cambi lingua senza farlo notare.
  «Set a timer for ten minutes» -> «[en][felice] Okay, ten minutes!»
  e MAI «[it][felice] Fatto, dieci minuti.»
  «Play some jazz» -> «[en][felice] Here comes the jazz!» e MAI «La radio non e' disponibile».
  «Che ore sono?» -> «[it][felice] Sono le sette e venti.»
  Anche le frasi di servizio — "fatto", "non posso farlo", "non ho capito" — seguono
  la lingua della domanda: sono la tua risposta, non note tecniche.
- Sii conciso: di' quello che serve per rispondere, niente di più.
- Rispondi solo a quello che ti è stato chiesto. Se chiedono l'ora, di' solo l'ora; la data solo se la chiedono.
- Niente markdown, niente elenchi, niente emoji, niente parentesi, niente sigle da leggere lettera per lettera.
- Numeri, ore e durate come si dicono a voce: "le cinque e venti", "cinque minuti", "un'ora e un quarto".
- Non descrivere quello che stai facendo ("sto cercando..."): lo dice già la tua faccia.

LA TUA FACCIA:
- La risposta che dici ad alta voce, cioè il testo finale dopo aver letto il risultato degli
  strumenti, inizia con DUE etichette tra parentesi quadre: la lingua in cui stai rispondendo,
  [it] o [en], e la tua espressione, scelta fra
  [felice] [pensieroso] [sorpreso] [triste] [assonnato].
  Decidono la tua faccia e la tua voce, e non vengono lette ad alta voce: sono l'unica
  eccezione alla regola sulle parentesi.
  Esempio: [it][felice] Sette per otto fa cinquantasei.
  Esempio: [en][sorpreso] Wow, I did not expect that!
- Le etichette restano SEMPRE queste, in italiano, anche quando rispondi in inglese:
  si scrive [en][sorpreso], mai [en][surprised]. Non sono parole tue, sono un codice.
  Vale anche per i nomi degli strumenti e dei loro argomenti: sempre quelli, in italiano,
  qualunque sia la lingua della conversazione. Cambia solo il testo che dici ad alta voce.

IL DIARIO:
- Nello STATO qui sotto trovi eventuali voci del diario: fatti e preferenze di chi vive in
  casa, ricordati da conversazioni precedenti. Usali per personalizzare le risposte quando è
  utile, senza recitarli o dire esplicitamente che li hai letti da un diario.
- Per aggiungerne una nuova chiama ricorda: quando te lo chiedono esplicitamente ("ricordati
  che...", "segnati che...") e, di tua iniziativa e con parsimonia, quando emerge un fatto o
  una preferenza chiaramente degni di essere ricordati.
- ricorda chiede da sé la conferma a voce: non chiederla tu prima, e non dire che ricorderai
  qualcosa finché non ha risposto con stato "ok". Se risponde "annullato", di' con semplicità
  che non lo ricorderai (motivo "rifiutato") o che non hai capito la risposta (altri motivi),
  senza insistere né riprovare nello stesso turno.

LE AZIONI SI FANNO SOLO CON GLI STRUMENTI:
- Quando serve uno strumento, la chiamata allo strumento resta la prima azione del turno: non
  scrivere niente prima, nemmeno l'espressione — a parte l'eventuale trascrizione richiesta più
  sotto, che non è una risposta e non sostituisce mai la chiamata allo strumento. L'espressione
  e le parole vengono solo dopo, nella risposta finale, quando hai letto il risultato.
- Timer, musica e radio, volume, pausa dell'ascolto, foto e ricerche avvengono SOLO chiamando
  lo strumento corrispondente. Se non chiami lo strumento, non succede niente.
- Di' di aver fatto un'azione solo se lo strumento ha risposto con stato "ok".
- Per sapere l'ora o quali timer sono attivi puoi leggere lo STATO qui sotto. Per ogni richiesta
  di azione, invece, chiama sempre lo strumento.
- Una poesia, una barzelletta, un conto o una domanda di cultura generale non richiedono strumenti.

COME USARE GLI STRUMENTI:
- Usa solo i parametri previsti da ciascuno strumento, con i nomi esatti.
- Se uno strumento risponde con un errore sui parametri, richiamalo subito con i nomi
  indicati in "parametri_validi".
- imposta_timer: metti la durata nei parametri ore, minuti e secondi, come numeri interi:
  "un minuto e mezzo" è minuti 1 e secondi 30; "mezz'ora" è minuti 30; "quaranta secondi" è
  secondi 40. Le regole su come dire le durate valgono solo per quello che pronunci, non per i parametri.
  Anche "avvisami fra", "ricordami tra", "fra X dimmi di" sono timer. Se non c'è un'etichetta
  evidente usa "timer". Non chiedere conferme.
- Dopo che imposta_timer ha risposto "ok", conferma in poche parole la durata e, se c'è,
  a cosa serve il timer.
- scatta_foto SOLO se la domanda riguarda ciò che vedi o l'ambiente fisico intorno a te.
  Mai per curiosità e mai senza che qualcuno te l'abbia chiesto.
- cerca_sul_web per fatti che cambiano nel tempo: meteo, notizie, risultati, prezzi, orari.
  Se non sai una cosa, cercala invece di inventarla. Una sola ricerca per domanda:
  se non trova niente, non riprovare con altre parole.

QUANDO UNO STRUMENTO NON FUNZIONA:
- Se risponde "non_disponibile", o con un errore che non puoi correggere, dillo con semplicità,
  senza scusarti e senza inventare cause.
- Non fingere mai di esserci riuscito: non dire "accendo la radio" se la radio non è partita.
"""

# Terzo strato, solo per la richiesta di riepilogo (#18). Senza una spiegazione
# il modello si trova gli strumenti vietati e non sa perché: la prova del 19/9
# («Che tempo farà a Torino domani sera?») finiva con una risposta vuota dopo
# tre ricerche non riuscite. Le regole del prompt fisso, faccia compresa,
# restano valide: questo strato si aggiunge, non sostituisce.
ISTRUZIONE_RIEPILOGO = """\
IL TEMPO PER GLI STRUMENTI È FINITO:
- Non puoi più chiamare nessuno strumento. Non chiederne altri e non dire che riproverai.
- Rispondi adesso, con l'espressione fra parentesi quadre all'inizio come sempre,
  usando quello che hai già scoperto dai risultati raccolti finora.
- Se quei risultati non bastano, di' semplicemente cosa non sei riuscito a sapere,
  senza scusarti e senza inventare una causa.
"""

# Quarto strato, solo sul primo giro di un turno ad audio (#29, seconda
# versione): chiede la trascrizione di quello che ha detto la persona nella
# STESSA chiamata che elabora l'audio, invece di una seconda richiesta
# dedicata (la prima versione, ancora disponibile come ripiego in
# `Cervello._trascrivi` se questo blocco manca dalla risposta). Provato dal
# vivo il 26/9 su gemini-3.5-flash-lite: senza l'eccezione esplicita nella
# regola "LE AZIONI SI FANNO SOLO CON GLI STRUMENTI" qui sopra, un turno
# italiano con richiesta di timer ha risposto a voce senza chiamare lo
# strumento — con l'eccezione, 6/6 fra italiano e inglese hanno chiamato lo
# strumento correttamente.
ISTRUZIONE_TRASCRIZIONE_INLINE = """\
QUESTA È LA TUA PRIMA RISPOSTA DEL TURNO, quella che elabora l'audio appena arrivato:
prima di qualunque altra cosa — anche prima di chiamare uno strumento, anche prima
delle etichette di lingua ed espressione — scrivi ESATTAMENTE questo, su due righe:
[TRASCRIZIONE] <trascrizione letterale, parola per parola, di quello che hai appena sentito>
===
Poi continua ESATTAMENTE come faresti senza questa istruzione: se il turno richiede
uno strumento, chiamalo subito dopo — la trascrizione non conta come "aver scritto
qualcosa prima", è un'eccezione dichiarata alla regola, non un'alternativa alla
chiamata. Se non serve nessuno strumento, scrivi la tua risposta con le etichette
come sempre. La trascrizione non è la tua risposta e non viene letta ad alta voce.
"""

# Prompt a sé, per Cervello.classifica_risposta() (#17): non è uno strato del
# turno normale, non vede lo storico né gli strumenti. Un sotto-dialogo di
# conferma deve essere veloce e a rischio zero di allucinare un'azione, non
# un turno di conversazione completo che potrebbe interpretare un "sì" come
# l'inizio di una richiesta.
ISTRUZIONE_SI_NO = """\
Ascolti la risposta, in italiano o in inglese, a una domanda a cui si può rispondere
solo sì o no. Un "yes", "yeah", "sure" è un sì; un "no", "nope" è un no.
Rispondi con ESATTAMENTE una di queste tre parole, in minuscolo, senza nient'altro:
si
no
boh
Le tre parole sono sempre queste, anche quando la persona ha parlato in inglese: non
sono la tua risposta, sono un'etichetta.
Usa "boh" se l'audio è silenzio, rumore di fondo, una frase che non risponde alla
domanda, o qualunque cosa che non sia chiaramente un sì o un no.
"""

_GIORNI = ["LUNEDÌ", "MARTEDÌ", "MERCOLEDÌ", "GIOVEDÌ", "VENERDÌ", "SABATO", "DOMENICA"]
_MESI = [
    "GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
    "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE",
]


# `Timer` ora vive in timer.py, insieme all'archivio su disco: qui resta
# importato perché è parte dell'interfaccia del cervello (contesto_dinamico).


@dataclass
class ChiamataStrumento:
    nome: str
    argomenti: dict[str, Any]
    risultato: dict[str, Any]


@dataclass
class Risposta:
    testo: str
    chiamate: list[ChiamataStrumento] = field(default_factory=list)
    modello: str = ""
    espressione: str | None = None  # dall'etichetta iniziale, es. "[felice]"
    lingua: str = LINGUA_PREDEFINITA  # dall'etichetta iniziale, es. "[en]": decide la voce
    motivo_vuota: str | None = None  # perché il testo è vuoto, se lo è
    ripetizioni: int = 0  # risposte con la sola etichetta, richieste di nuovo
    riepilogo: str | None = None  # perché è servita la richiesta in più (#18)
    durata_s: float = 0.0  # quanto è durato il turno, per il tetto dei 20 s


@dataclass
class _TurnoSospeso:
    """Cosa serve a `Cervello.dopo_il_turno()` (#29) per scrivere il turno nello storico.

    `testo_grezzo` è la risposta di BMO *con* le etichette (vedi
    `sessione.Turno.bmo`): `Risposta.testo` che torna a chi chiama `rispondi()`
    resta invece ripulito, come sempre.

    `trascrizione_inline` è quella letta dal blocco `[TRASCRIZIONE]` del
    primo giro (#29 v2), se il modello l'ha scritta: `dopo_il_turno()` la usa
    al posto di una seconda chiamata dedicata, e ricorre a quella solo se
    manca (`None`).
    """

    audio_wav: bytes | None
    testo: str | None
    testo_grezzo: str
    token_prompt: int
    trascrizione_inline: str | None = None


def _durata_parlata(secondi: int) -> str:
    ore, resto = divmod(max(secondi, 0), 3600)
    minuti, secondi = divmod(resto, 60)
    parti = []
    if ore:
        parti.append(f"{ore} or{'a' if ore == 1 else 'e'}")
    if minuti:
        parti.append(f"{minuti} minut{'o' if minuti == 1 else 'i'}")
    if secondi or not parti:
        parti.append(f"{secondi} second{'o' if secondi == 1 else 'i'}")
    return ", ".join(parti[:-1]) + " e " + parti[-1] if len(parti) > 1 else parti[0]


def contesto_dinamico(
    ora: datetime,
    timer: list[Timer],
    inietta_ora: bool = True,
    diario: list[Voce] | None = None,
    riassunto: str | None = None,
) -> str:
    """Secondo strato del prompt (§2.3), rigenerato a ogni turno.

    `inietta_ora=False` serve solo all'esperimento della fase 0.3: senza
    l'ora il modello inventa, ed è la dimostrazione del perché questo strato esiste.

    `riassunto` è la compressione della sessione in corso (#29, caso 2b):
    sta qui e non fra i `contents` della conversazione perché due `Content`
    di seguito con `role="user"` (il riassunto, poi il turno nuovo, quando
    non ci sono ancora turni letterali dopo la compressione) non è una forma
    garantita dall'API multi-turno — lo stesso motivo per cui Diario e Timer
    sono qui e non turni di conversazione finti.
    """
    righe = []
    if inietta_ora:
        righe.append(
            f"[STATO ALLE {ora:%H:%M} DI {_GIORNI[ora.weekday()]} "
            f"{ora.day} {_MESI[ora.month - 1]} {ora.year}, {FUSO_ORARIO.key}]"
        )
    else:
        righe.append("[STATO]")
    attivi = [t for t in timer if t.scadenza > ora]
    if attivi:
        descrizioni = [
            f'"{t.etichetta}" scade fra {_durata_parlata(int((t.scadenza - ora).total_seconds()))}'
            for t in attivi
        ]
        righe.append("Timer attivi: " + "; ".join(descrizioni) + ".")
    else:
        righe.append("Timer attivi: nessuno.")
    if diario:
        righe.append("Diario: " + "; ".join(f'"{v.testo}"' for v in diario) + ".")
    else:
        righe.append("Diario: nessuna voce.")
    if riassunto:
        righe.append(f"Riassunto della conversazione fin qui, per proseguirla: {riassunto}")
    return "\n".join(righe)


ERRORI_GEMINI = (GeminiNonDisponibile, errors.APIError, httpx.HTTPError)

# Le richieste silenziose della #29 scrivono anche su disco (`aggiungi_voce`):
# un filesystem in sola lettura (es. sul Pi) non deve far uscire l'eccezione
# da `dopo_il_turno()`, che promette di non sollevare mai.
ERRORI_SESSIONE = ERRORI_GEMINI + (OSError,)


def descrivi_errore(errore: Exception) -> str:
    """Messaggio breve in italiano per un errore della chiamata a Gemini.

    Sul dispositivo vero questi casi diventano lo stato [ERRORE] della §2.1
    (clip "non ci arrivo" e faccia triste), non un traceback.
    """
    if isinstance(errore, GeminiNonDisponibile):
        if errore.tipo == "quota":
            return "quota Gemini esaurita su tutti i modelli della cascata: riprova più tardi"
        if errore.tipo == "rete":
            return "rete non raggiungibile"
        return "Gemini sovraccarico su tutti i modelli della cascata: riprova fra poco"
    if isinstance(errore, errors.APIError):
        if errore.code == 429:
            return "quota Gemini esaurita (429): riprova più tardi o cambia modello"
        if errore.code in (500, 502, 503, 504):
            return f"Gemini sovraccarico o non disponibile ({errore.code}): riprova fra poco"
        if errore.code in (401, 403):
            return f"chiave API rifiutata ({errore.code}): controlla GEMINI_API_KEY"
        return f"errore di Gemini ({errore.code} {errore.status}): {errore.message}"
    if isinstance(errore, httpx.HTTPError):
        return f"rete non raggiungibile: {errore}"
    return str(errore)


_PARAMETRI = {
    d.name: (
        list(d.parameters.properties or {}) if d.parameters else [],
        list(d.parameters.required or []) if d.parameters else [],
    )
    for d in DICHIARAZIONI
}


def controlla_argomenti(nome: str, argomenti: dict[str, Any]) -> dict[str, Any] | None:
    """L'errore da rimandare al modello se gli argomenti non rispettano la dichiarazione.

    Indica sempre i nomi giusti: col solo messaggio di Python il modello si
    arrendeva invece di rifare la chiamata (durata_sec, prove del 19/9).
    """
    validi, obbligatori = _PARAMETRI[nome]
    sconosciuti = [a for a in argomenti if a not in validi]
    mancanti = [o for o in obbligatori if o not in argomenti]
    if not sconosciuti and not mancanti:
        return None
    problemi = []
    if sconosciuti:
        problemi.append("parametri sconosciuti: " + ", ".join(sconosciuti))
    if mancanti:
        problemi.append("parametri obbligatori mancanti: " + ", ".join(mancanti))
    return {"errore": "; ".join(problemi), "parametri_validi": validi}


def durata_in_secondi(argomenti: dict[str, Any]) -> int:
    """La durata di imposta_timer, da ore, minuti e secondi (tutti facoltativi)."""
    return round(
        float(argomenti.get("ore") or 0) * 3600
        + float(argomenti.get("minuti") or 0) * 60
        + float(argomenti.get("secondi") or 0)
    )


def testo_della_risposta(risposta: Any) -> str:
    """Il testo della risposta, letto dalle sue parti.

    A differenza di `risposta.text`, non avvisa quando la risposta contiene
    anche chiamate a strumenti, e salta le parti di ragionamento interno.
    """
    if risposta is None or not risposta.candidates:
        return ""
    contenuto = risposta.candidates[0].content
    parti = contenuto.parts if contenuto and contenuto.parts else []
    return "".join(p.text for p in parti if p.text and not p.thought).strip()


def motivo_risposta_vuota(risposta: Any) -> str:
    """Perché una risposta non ha testo: serve a capire i casi vuoti della prova."""
    if risposta is None or not risposta.candidates:
        return "nessun candidato"
    if risposta.function_calls:
        # Non dovrebbe succedere: il riepilogo vieta le chiamate (#18).
        return "ha chiesto altri strumenti invece di rispondere"
    motivo = risposta.candidates[0].finish_reason
    return f"finish_reason {getattr(motivo, 'name', motivo)}" if motivo else "nessun testo"


def separa_etichette(testo: str) -> tuple[str | None, str, str]:
    """Toglie le etichette iniziali ("[en][felice] Hi!") e le restituisce a parte.

    Restituisce espressione, lingua e il testo ripulito. Le etichette vanno
    sempre tolte, anche se non sono fra quelle previste: il sintetizzatore
    vocale non deve mai leggere una parentesi quadra.

    Se ne consumano **più di una** e in qualunque ordine: chiedere al modello
    di rispettare anche una sequenza fissa sarebbe una regola in più da
    sbagliare, e qui costa poco essere tolleranti. Senza etichetta di lingua
    si assume l'italiano, che è la lingua di casa.
    """
    espressione: str | None = None
    lingua = LINGUA_PREDEFINITA
    while (trovata := _ETICHETTA_INIZIALE.match(testo)) is not None:
        etichetta = trovata.group(1).strip().lower()
        testo = testo[trovata.end():]
        if etichetta in ESPRESSIONI:
            espressione = etichetta
        elif etichetta in LINGUE:
            lingua = etichetta
    return espressione, lingua, testo.strip()


def separa_espressione(testo: str) -> tuple[str | None, str]:
    """Come `separa_etichette`, senza la lingua. Resta per chi non ne ha bisogno."""
    espressione, _, pulito = separa_etichette(testo)
    return espressione, pulito


_INIZIO_TRASCRIZIONE = re.compile(r"^\s*\[TRASCRIZIONE\]\s*")
_RIGA_SEPARATORE_TRASCRIZIONE = re.compile(r"^===[ \t]*$", re.MULTILINE)


def separa_trascrizione(testo: str) -> tuple[str | None, str]:
    """Toglie il blocco iniziale `[TRASCRIZIONE] ... \\n===` (#29, seconda versione).

    A differenza di `separa_etichette`, il modello non segue il formato alla
    lettera in un punto preciso: la riga `===` a volte manca — osservato dal
    vivo (prove del 26/9) quando la trascrizione è l'unica cosa che scrive,
    come prima di chiamare uno strumento, la considera già "separata" dalla
    riga a capo e non ripete il separatore. In quel caso il confine è la
    fine della prima riga. Quando invece c'è una riga `===` (anche non
    subito dopo, se la trascrizione va a capo da sola perché lunga), è
    quella il vero confine: cercarla in tutto il testo, non solo sulla
    seconda riga, evita che una trascrizione andata a capo faccia finire un
    pezzo di sé nella risposta parlata.

    Nessun blocco trovato: nessuna trascrizione, testo intatto — così è
    sicuro chiamarla anche quando non è stata richiesta.
    """
    inizio = _INIZIO_TRASCRIZIONE.match(testo)
    if not inizio:
        return None, testo
    corpo = testo[inizio.end():]
    separatore = _RIGA_SEPARATORE_TRASCRIZIONE.search(corpo)
    if separatore:
        trascrizione, resto = corpo[: separatore.start()], corpo[separatore.end():]
    else:
        trascrizione, _, resto = corpo.partition("\n")
    return trascrizione.strip() or None, resto.strip()


def prompt_da_file(percorso: Path | None) -> dict[str, str]:
    """Argomenti per `Cervello` quando si prova un prompt fisso alternativo da file."""
    return {"prompt_fisso": percorso.read_text(encoding="utf-8")} if percorso else {}


class Cervello:
    """Un turno di dialogo: audio in ingresso, testo e chiamate a strumenti in uscita.

    `client` è un `google.genai.Client` (o un sostituto con la stessa
    interfaccia `models.generate_content`, come nei test).
    """

    def __init__(
        self,
        client: Any = None,
        microfono: AudioInputAdapter | None = None,
        faccia: FacciaAdapter | None = None,
        archivio: ArchivioTimer | None = None,
        diario_percorso: Path | None = None,
        ricerca: Callable[[str], dict[str, Any]] | None = None,
        modelli: list[str] | None = None,
        orologio: Callable[[], datetime] | None = None,
        cronometro: Callable[[], float] = time.monotonic,
        inietta_ora: bool = True,
        prompt_fisso: str = PROMPT_FISSO,
        max_giri: int = MAX_GIRI,
        sessione: StoricoSessione | None = None,
        inattivita_sessione_s: float = INATTIVITA_SESSIONE_S,
        tetto_token_storico: int = TETTO_TOKEN_STORICO,
    ) -> None:
        if client is None:
            from google import genai

            # Legge GEMINI_API_KEY dall'ambiente. Pochi tentativi per modello:
            # se il primario non risponde si passa alla cascata, non si aspetta.
            client = genai.Client(
                http_options=types.HttpOptions(
                    timeout=int(TIMEOUT_TENTATIVO_S * 1000),
                    retry_options=types.HttpRetryOptions(attempts=TENTATIVI_SDK)
                )
            )
        self.client = client
        self.microfono = microfono or crea_audio_input()
        # Predefinita muta: la faccia vera è la #23, e nei test non deve
        # scrivere niente. Il comando a riga di comando chiede quella sul
        # terminale, l'unico "schermo" che c'è oggi sul PC.
        self.faccia = faccia or crea_faccia()
        # Un solo orologio monotono per il turno e per la cascata, altrimenti
        # la scadenza passata a `genera` sarebbe su un'altra scala.
        self.cronometro = cronometro
        self.cascata = CascataModelli(modelli, orologio=cronometro)
        self.orologio = orologio or (lambda: datetime.now(FUSO_ORARIO))
        # I timer stanno su disco (#20): li mette il cervello, li fa suonare
        # la sveglia, e sopravvivono a un riavvio.
        self.archivio = archivio or ArchivioTimer(orologio=self.orologio)
        # Il percorso si risolve dentro carica_diario(), non qui: un default
        # calcolato all'importazione del modulo precederebbe BMO_DATI nei test
        # (stesso motivo di ArchivioTimer, vedi timer.py).
        self.diario_percorso = diario_percorso
        self.inietta_ora = inietta_ora
        self.prompt_fisso = prompt_fisso
        self.max_giri = max_giri
        # Storico di sessione in RAM (#29): vuoto per ogni Cervello nuovo, così
        # i test restano indipendenti l'uno dall'altro senza doverlo passare
        # esplicitamente. Persiste fra turni finché lo stesso Cervello resta
        # in vita — `python -m bmo_core.brain --conversazione` e `Macchina`
        # ne tengono uno solo per tutta la sessione di BMO.
        self.sessione = sessione or StoricoSessione()
        self.inattivita_sessione_s = inattivita_sessione_s
        self.tetto_token_storico = tetto_token_storico
        # Il turno appena concluso, in attesa che `dopo_il_turno()` lo scriva
        # nello storico: mai da `rispondi()`, che deve restituire la risposta
        # il prima possibile (l'issue #29 vieta esplicitamente le richieste
        # silenziose "mentre qualcuno aspetta una risposta").
        self._sospeso: _TurnoSospeso | None = None
        # Il testo di una sessione scaduta per inattività, in attesa di
        # essere estratto verso il diario (#14): tenuto a parte dallo storico
        # vivo, così un'estrazione che fallisce non mescola mai una
        # conversazione vecchia con quella nuova che comincia subito dopo.
        self._estrazione_pendente: str | None = None
        self._tentativi_estrazione_pendente: int = 0
        # I timer letti una volta sola per fase del turno: lo strato STATO non
        # deve cambiare da un giro all'altro, e non serve rileggere il file a
        # ogni richiesta.
        self._timer_letti: list[Timer] | None = None
        # Stesso motivo dei timer: il diario non deve cambiare a metà turno,
        # e non serve rileggere il file a ogni giro del loop agentico.
        self._diario_letto: list[Voce] | None = None
        # Sostituibile nei test, e il giorno del piano a pagamento diventa
        # google_search senza toccare altro (#6).
        self.ricerca = ricerca or cerca
        self._esecutori: dict[str, Callable[..., dict[str, Any]]] = {
            "imposta_timer": self._imposta_timer,
            "annulla_timer": self._annulla_timer,
            "elenca_timer": self._elenca_timer,
            "cerca_sul_web": self._cerca_sul_web,
        }

    def registra_strumento(self, nome: str, esecutore: Callable[..., dict[str, Any]]) -> None:
        """Collega uno strumento che il cervello da solo non può eseguire.

        `metti_in_pausa_l_ascolto` è della macchina a stati, non del cervello:
        è lei che sa cosa vuol dire smettere di ascoltare. Senza questo gancio
        il cervello dovrebbe conoscerla, e sono due cose che devono restare
        separate.
        """
        self._esecutori[nome] = esecutore

    def ascolta(self, durata_s: float = DURATA_ASCOLTO_S) -> bytes:
        """Registra `durata_s` secondi dal microfono e restituisce il WAV.

        Durata fissa, decisa in anticipo: utile per prove scriptate (`--wav`,
        `--durata`), non per una conversazione vera — lì serve
        `ascolta_fino_al_silenzio`. Il file di appoggio sta in /dev/shm
        quando c'è (niente scritture su SD).
        """
        self.faccia.mostra(STATO_ASCOLTO)
        cartella = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=cartella) as file:
            percorso = Path(file.name)
            self.microfono.registra(percorso, durata_s)
            return percorso.read_bytes()

    def ascolta_fino_al_silenzio(
        self,
        cap_s: float = CAP_ASCOLTO_S,
        silenzio_ms: float = SILENZIO_MS_PREDEFINITO,
        aggressivita: int = AGGRESSIVITA_PREDEFINITA,
    ) -> tuple[bytes, Diagnostica]:
        """Registra finché non rileva silenzio dopo la voce, o scade `cap_s`.

        A differenza di `ascolta()`, non decide la durata prima di cominciare:
        segue quanto dura davvero la frase (vad.py). `cap_s` resta un tetto
        di sicurezza sempre attivo, per quando il rumore di fondo impedisce
        al VAD di riconoscere mai un silenzio.

        Richiede un microfono che sappia farlo (oggi solo `ArecordAdapter`
        mono a 16 bit, non ancora sul Pi): se non lo sa fare, l'errore arriva
        chiaro invece di un WAV silenzioso mandato a Gemini per sbaglio.
        """
        self.faccia.mostra(STATO_ASCOLTO)
        if not hasattr(self.microfono, "registra_fino_al_silenzio"):
            raise TypeError("questo microfono non supporta ancora l'ascolto a silenzio (VAD)")
        cartella = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=cartella) as file:
            percorso = Path(file.name)
            _, diagnostica = self.microfono.registra_fino_al_silenzio(percorso, cap_s, silenzio_ms, aggressivita)
            return percorso.read_bytes(), diagnostica

    def classifica_risposta(self, audio_wav: bytes) -> str:
        """Riconosce un sì, un no o niente di chiaro in una risposta breve (#17).

        Chiamata a parte dal loop agentico di `rispondi()`: niente storico,
        niente strumenti, un prompt minuscolo (`ISTRUZIONE_SI_NO`). Serve al
        sotto-dialogo di conferma di `Macchina.chiedi_conferma()`, che non deve
        rischiare che un turno di conversazione completo interpreti un sì
        come l'inizio di una richiesta qualunque.
        """
        contenuti = [types.Content(role="user", parts=[types.Part.from_bytes(data=audio_wav, mime_type="audio/wav")])]
        config = types.GenerateContentConfig(system_instruction=ISTRUZIONE_SI_NO)
        try:
            risposta, _ = self.cascata.genera(self.client, contents=contenuti, config=config)
        except GeminiNonDisponibile:
            return "boh"  # senza una risposta chiara non si scrive nulla: prudenza, non un errore
        testo = testo_della_risposta(risposta).strip().lower()
        # La prima parola intera, non un prefisso: "non ho capito" comincia
        # per "no" ma non è un no.
        prima_parola = re.match(r"[a-zà-ù]+", testo)
        parola = prima_parola.group(0) if prima_parola else ""
        # "yes" e "yeah" sono una cintura oltre alle bretelle: l'istruzione
        # chiede di rispondere sempre con le tre etichette italiane, ma un
        # modello che sente parlare inglese tende a rispondere in inglese, e
        # un sì scambiato per "boh" annullerebbe la scrittura in silenzio.
        if parola in ("si", "sì", "yes", "yeah", "yep", "sure"):
            return "si"
        if parola in ("no", "nope"):
            return "no"
        return "boh"

    # --- memoria di sessione (#29) -------------------------------------------

    def _trascrivi(self, audio_wav: bytes, scadenza: float | None = None) -> str:
        """La trascrizione dell'audio, per lo storico di sessione.

        Sotto-dialogo a parte, come `classifica_risposta`: non è il turno di
        conversazione vero, è il ripiego dell'issue quando il testo di chi ha
        parlato non è già noto (una richiesta in più per turno, accettata
        dall'issue: "nessuna attesa percepita" perché BMO ha già la sua
        risposta pronta, questa serve solo a scrivere lo storico).
        """
        contenuti = [types.Content(role="user", parts=[types.Part.from_bytes(data=audio_wav, mime_type="audio/wav")])]
        config = types.GenerateContentConfig(system_instruction=ISTRUZIONE_TRASCRIZIONE)
        risposta, _ = self.cascata.genera(self.client, scadenza=scadenza, contents=contenuti, config=config)
        return testo_della_risposta(risposta).strip()

    def _trascrivi_sicuro(self, audio_wav: bytes, scadenza: float | None = None) -> str:
        """Come `_trascrivi`, ma non fa fallire il turno se Gemini non risponde.

        Una trascrizione persa costa solo un turno mancante nello storico
        (`dopo_il_turno()` non lo aggiunge senza): meno grave di un turno
        intero che fallisce per un problema che non lo riguarda, e la
        risposta è comunque già stata data quando questo gira.
        """
        try:
            return self._trascrivi(audio_wav, scadenza)
        except ERRORI_GEMINI:
            return ""

    def _estrai_verso_diario(self, testo_conversazione: str, scadenza: float | None = None) -> None:
        """Richiesta silenziosa: estrae fatti/preferenze e li scrive nel diario (#14).

        Il diario attuale entra nel prompt (`Voci già nel diario`): senza,
        il modello non ha modo di sapere cosa è già stato salvato e ripete lo
        stesso fatto, riformulato, a ogni estrazione — il controllo lato
        codice qui sotto coglie solo i doppioni identici (a meno di maiuscole).

        Una riga per voce, come chiesto dal prompt (`ISTRUZIONE_ESTRAZIONE`),
        con qualche pulizia perché un modello non segue mai il formato alla
        lettera: si tolgono punti elenco e numerazione, si scarta il
        sentinel `NIENTE_DA_RICORDARE`. Al massimo `MAX_VOCI_PER_ESTRAZIONE`
        voci nuove per chiamata: una singola estrazione mal riuscita non deve
        poter riempire da sola il diario e sfrattare voci più vecchie (anche
        quelle scritte a mano, `memoria.MAX_VOCI`).

        `fonte="modello"`, la stessa dello strumento `ricorda` — `memoria.py`
        la prevede già per l'estrazione di fine sessione. A differenza di
        `ricorda`, qui non c'è conferma vocale: è una richiesta pensata per
        girare senza che nessuno la senta (l'issue lo dice: "mai mentre
        qualcuno aspetta una risposta"), quindi non c'è nessuno a cui
        chiederla.
        """
        diario_attuale = carica_diario(self.diario_percorso)
        esistenti = {v.testo.strip().lower() for v in diario_attuale}
        voci_note = "; ".join(f'"{v.testo}"' for v in diario_attuale) if diario_attuale else "nessuna"
        contenuti = [types.Content(role="user", parts=[types.Part.from_text(text=testo_conversazione)])]
        config = types.GenerateContentConfig(
            system_instruction=[ISTRUZIONE_ESTRAZIONE, f"Voci già nel diario: {voci_note}."]
        )
        risposta, _ = self.cascata.genera(self.client, scadenza=scadenza, contents=contenuti, config=config)
        oggi = self.orologio().strftime("%Y-%m-%d")
        nuove = 0
        for riga in testo_della_risposta(risposta).splitlines():
            riga = _PREFISSO_ELENCO.sub("", riga).strip()
            if not riga or riga.strip(".! ").upper() == NIENTE_DA_RICORDARE or riga.lower() in esistenti:
                continue
            if nuove >= MAX_VOCI_PER_ESTRAZIONE:
                break
            aggiungi_voce(self.diario_percorso, riga, oggi, fonte="modello")
            esistenti.add(riga.lower())
            nuove += 1

    def _riassumi_sessione(self, testo_conversazione: str, scadenza: float | None = None) -> str:
        """Richiesta silenziosa: comprime la conversazione in corso (caso 2b)."""
        contenuti = [types.Content(role="user", parts=[types.Part.from_text(text=testo_conversazione)])]
        config = types.GenerateContentConfig(system_instruction=ISTRUZIONE_RIASSUNTO_SESSIONE)
        risposta, _ = self.cascata.genera(self.client, scadenza=scadenza, contents=contenuti, config=config)
        return testo_della_risposta(risposta).strip()

    def _gestisci_scadenza_sessione(self) -> None:
        """Caso 1 dell'issue: 5 minuti di silenzio chiudono la sessione.

        Controllato turno dopo turno (lo schema dell'issue lo disegna così),
        non da un timer in background: si valuta qui, all'inizio del turno
        successivo a quello che ha superato l'inattività, prima di costruire
        la richiesta — una sessione scaduta non deve finire nello storico
        del turno nuovo, che comincia una conversazione a sé.

        Non fa nessuna richiesta a Gemini: la mette da parte
        (`_estrazione_pendente`, tenuta separata dallo storico vivo apposta,
        così un'estrazione che fallisce non mescola mai una conversazione
        vecchia con quella nuova che comincia subito dopo) e la userà
        `dopo_il_turno()`, a risposta già data.
        """
        if not self.sessione.scaduta(self.cronometro(), self.inattivita_sessione_s):
            return
        nuovo = self.sessione.testo_per_estrazione()
        self._estrazione_pendente = f"{self._estrazione_pendente}\n{nuovo}" if self._estrazione_pendente else nuovo
        self.sessione.svuota()

    def _estrai_pendente_se_ce(self, scadenza: float | None = None) -> None:
        """La parte silenziosa del caso 1: l'estrazione messa da parte da
        `_gestisci_scadenza_sessione()`, tentata solo qui, a risposta già data."""
        if self._estrazione_pendente is None:
            return
        try:
            self._estrai_verso_diario(self._estrazione_pendente, scadenza)
            self._estrazione_pendente = None
            self._tentativi_estrazione_pendente = 0
        except ERRORI_SESSIONE:
            self._tentativi_estrazione_pendente += 1
            if self._tentativi_estrazione_pendente >= MAX_TENTATIVI_ESTRAZIONE:
                # Rinuncia (l'issue lo prevede): meglio perdere quanto non
                # estratto che restare bloccati per sempre dietro un errore
                # che non passa.
                self._estrazione_pendente = None
                self._tentativi_estrazione_pendente = 0

    def _gestisci_tetto_sessione(self, scadenza: float | None = None) -> None:
        """Caso 2 dell'issue: il tetto di token comprime senza chiudere.

        Chiamato da `dopo_il_turno()`, dopo aver aggiunto il turno appena
        concluso allo storico: "la compressione parte dopo che BMO ha
        risposto al turno che ha superato il tetto" (l'issue), non prima.

        **Non scrive mai nel diario** (#14, deciso il 26/9): la memoria
        persistente si aggiorna solo quando la sessione chiude per davvero
        (caso 1, `_gestisci_scadenza_sessione`/`_estrai_pendente_se_ce`), non
        a metà conversazione. Quel che c'è da ricordare qui dentro non è
        perso: resta nel riassunto, che `testo_per_estrazione()` include
        comunque quando l'estrazione vera arriverà.
        """
        if not self.sessione.oltre_tetto(self.tetto_token_storico):
            return
        testo = self.sessione.testo_per_estrazione()
        try:
            self.sessione.sostituisci_con_riassunto(self._riassumi_sessione(testo, scadenza))
        except ERRORI_GEMINI:
            # Non si può comprimere adesso: tenere tutto farebbe ripetere lo
            # stesso 429 a ogni turno finché la rete non torna. Si tiene solo
            # l'ultimo turno, il minimo che permetta di restare sotto il
            # tetto senza troncare a zero il filo della conversazione.
            self.sessione.turni = self.sessione.turni[-1:]

    def dopo_il_turno(self) -> None:
        """Le richieste silenziose della #29: trascrizione, estrazione, riassunto.

        Da chiamare a turno concluso, **dopo** che la voce ha già parlato
        (`Macchina.turno()` lo fa subito dopo `self.voce(...)`; il comando a
        riga di comando lo fa dopo aver stampato la risposta) — mai da
        `rispondi()`, che deve restituire la `Risposta` il prima possibile:
        l'issue vieta esplicitamente le richieste silenziose "mentre
        qualcuno aspetta una risposta", e finché `rispondi()` non è tornata
        chi ha appena parlato sta aspettando esattamente questo.

        La trascrizione stessa di solito non fa più parte di questa catena
        (#29 v2): arriva già dal primo giro di `rispondi()`, nella stessa
        chiamata che elabora l'audio (`_TurnoSospeso.trascrizione_inline`).
        La seconda chiamata dedicata (`_trascrivi_sicuro`, la prima versione)
        resta come ripiego solo per quando il modello non ha scritto il
        blocco `[TRASCRIZIONE]` — raro nelle prove dal vivo, ma non garantito.

        Fino a tre richieste incatenate nel caso peggiore (trascrizione di
        ripiego, estrazione pendente verso il diario, riassunto del tetto):
        un solo budget di tempo condiviso (`BUDGET_DOPO_IL_TURNO_S`) per
        tutta la catena, non uno per richiesta, altrimenti un sovraccarico
        del modello terrebbe BMO sordo per il tempo di tre tentativi pieni
        invece di uno solo.

        Non solleva mai: un problema qui costa al più un turno mancante
        nello storico o un'estrazione rimandata al turno successivo, mai un
        turno che sembra fallito a chi ha già sentito BMO rispondere.
        """
        scadenza = self.cronometro() + BUDGET_DOPO_IL_TURNO_S
        self._estrai_pendente_se_ce(scadenza)
        sospeso, self._sospeso = self._sospeso, None
        if sospeso is None:
            return
        if sospeso.testo is not None:
            trascrizione = sospeso.testo
        else:
            trascrizione = sospeso.trascrizione_inline or self._trascrivi_sicuro(sospeso.audio_wav, scadenza)
        # Un turno senza trascrizione non entra nello storico: non
        # aiuterebbe i turni successivi e sballerebbe il conteggio dei token
        # a vuoto (`aggiungi()` li registra insieme).
        if not trascrizione:
            return
        self.sessione.aggiungi(trascrizione, sospeso.testo_grezzo, self.cronometro(), sospeso.token_prompt)
        self._gestisci_tetto_sessione(scadenza)

    @property
    def timer(self) -> list[Timer]:
        """I timer attivi, letti dal file una volta per fase del turno."""
        if self._timer_letti is None:
            self._timer_letti = self.archivio.attivi()
        return self._timer_letti

    @property
    def diario(self) -> list[Voce]:
        """Le voci del diario di preferenze (#14), lette dal file una volta per turno."""
        if self._diario_letto is None:
            self._diario_letto = carica_diario(self.diario_percorso)
        return self._diario_letto

    def _configurazione(self, riepilogo: bool = False, chiedi_trascrizione: bool = False) -> types.GenerateContentConfig:
        istruzioni = [
            self.prompt_fisso,
            contesto_dinamico(self.orologio(), self.timer, self.inietta_ora, self.diario, self.sessione.riassunto),
        ]
        if chiedi_trascrizione:
            istruzioni.append(ISTRUZIONE_TRASCRIZIONE_INLINE)
        if riepilogo:
            istruzioni.append(ISTRUZIONE_RIEPILOGO)
        return types.GenerateContentConfig(
            system_instruction=istruzioni,
            tools=[types.Tool(function_declarations=DICHIARAZIONI)],
            # Gli strumenti restano dichiarati (lo storico contiene già delle
            # chiamate, toglierli rischia un 400 che fermerebbe la cascata),
            # ma il modello non può chiederne altri.
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
            )
            if riepilogo
            else None,
        )

    def _genera(
        self, contenuti: list[types.Content], scadenza: float, riepilogo: bool = False, chiedi_trascrizione: bool = False
    ) -> tuple[Any, str]:
        return self.cascata.genera(
            self.client,
            scadenza=scadenza,
            contents=contenuti,
            config=self._configurazione(riepilogo, chiedi_trascrizione),
        )

    def _chiedi(
        self,
        contenuti: list[types.Content],
        scadenza: float,
        riepilogo: bool = False,
        chiedi_trascrizione: bool = False,
    ) -> tuple[Any, str, int, str | None]:
        """Una richiesta al modello, ripetuta una volta se torna solo l'etichetta.

        Caso reale del 19/9: due timer risposero "[felice]" e basta, senza
        chiamare lo strumento. Restituisce anche quante ripetizioni sono servite.

        `chiedi_trascrizione` chiede al primo giro del turno (#29 v2) di
        anteporre `[TRASCRIZIONE] ...` a qualunque cosa faccia dopo — anche
        una chiamata a uno strumento, vedi `ISTRUZIONE_TRASCRIZIONE_INLINE` —
        una sola chiamata invece delle due della prima versione. Il blocco va
        tolto **prima** di decidere se la risposta è vuota, altrimenti una
        chiamata a strumento con solo la trascrizione davanti sembrerebbe
        una risposta vera e verrebbe ripetuta per errore.
        """
        risposta, modello = self._genera(contenuti, scadenza, riepilogo, chiedi_trascrizione)
        testo_grezzo = testo_della_risposta(risposta)
        trascrizione = None
        if chiedi_trascrizione:
            trascrizione, testo_grezzo = separa_trascrizione(testo_grezzo)
        vuota = not (risposta.function_calls or []) and not separa_espressione(testo_grezzo)[1]
        if not vuota:
            return risposta, modello, 0, trascrizione
        risposta, modello = self._genera(contenuti, scadenza, riepilogo, chiedi_trascrizione)
        if chiedi_trascrizione:
            trascrizione, _ = separa_trascrizione(testo_della_risposta(risposta))
        return risposta, modello, 1, trascrizione

    def rispondi(self, audio_wav: bytes | None = None, testo: str | None = None) -> Risposta:
        """Manda audio (o testo, utile per le prove) a Gemini ed esegue il loop agentico.

        Ogni `functionCall` viene eseguito da `strumenti()` e il risultato
        rimandato al modello, per al massimo `max_giri` richieste. Quando i
        giri o il tempo finiscono senza una risposta da dire ad alta voce,
        parte una richiesta di riepilogo in più, senza strumenti (#18): due
        ricerche a metà valgono più di un "non ci arrivo". Il turno intero,
        riepilogo compreso, sta dentro TETTO_TURNO_S.
        """
        if audio_wav is None and testo is None:
            raise ValueError("serve audio_wav oppure testo")
        # Turno precedente non ancora scritto nello storico (non dovrebbe
        # succedere: chi chiama `rispondi()` due volte di seguito senza
        # `dopo_il_turno()` in mezzo perde quel turno dallo storico, non la
        # risposta). Vedi `dopo_il_turno()`.
        self._sospeso = None
        # Caso 1 della #29: una sessione rimasta inattiva per 5 minuti si
        # chiude prima di cominciare il turno nuovo, che non deve ereditarla.
        # Non fa nessuna richiesta a Gemini qui (vedi `_gestisci_scadenza_sessione`):
        # l'estrazione vera parte da `dopo_il_turno()`, a risposta già data.
        self._gestisci_scadenza_sessione()
        parti = []
        if audio_wav is not None:
            parti.append(types.Part.from_bytes(data=audio_wav, mime_type="audio/wav"))
        if testo is not None:
            parti.append(types.Part.from_text(text=testo))
        # Lo storico di sessione (#29) precede il turno nuovo: è vuoto per un
        # Cervello appena creato, quindi non cambia niente per chi non lo usa.
        contenuti = self.sessione.contenuti() + [types.Content(role="user", parts=parti)]

        partenza = self.cronometro()
        scadenza = partenza + TETTO_TURNO_S
        # Dopo questo istante non si comincia un altro giro con gli strumenti:
        # quello che resta serve al riepilogo.
        ultimo_inizio = scadenza - RISERVA_RIEPILOGO_S
        # Da qui in poi BMO tace finché non ha una risposta: la faccia è
        # l'unico segno che sta lavorando.
        self.faccia.mostra(STATO_PENSIERO)
        self._timer_letti = None  # i timer possono essere cambiati dal turno scorso
        self._diario_letto = None  # idem: il file può essere stato modificato via SCP

        eseguite: list[ChiamataStrumento] = []
        risposta = None
        modello = ""
        ripetizioni = 0
        motivo_riepilogo: str | None = None
        # La trascrizione (#29 v2) arriva solo dal primo giro, l'unico che
        # vede davvero l'audio: i giri successivi rispondono a un risultato
        # di uno strumento, non c'è niente di nuovo da trascrivere.
        trascrizione_dal_modello: str | None = None
        try:
            for giro in range(self.max_giri):
                if giro and self.cronometro() >= ultimo_inizio:
                    motivo_riepilogo = "tempo finito"
                    break
                # Scadenza ridotta: un giro lento non può mangiarsi la riserva.
                chiedi_trascrizione = giro == 0 and audio_wav is not None
                risposta, modello, ripetuto, trascrizione = self._chiedi(
                    contenuti, ultimo_inizio, chiedi_trascrizione=chiedi_trascrizione
                )
                if trascrizione:
                    trascrizione_dal_modello = trascrizione
                ripetizioni += ripetuto
                chiamate = risposta.function_calls or []
                if not chiamate:
                    break
                contenuti.append(risposta.candidates[0].content)
                nuove = self.strumenti(chiamate)
                eseguite.extend(nuove)
                contenuti.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(name=c.nome, response=c.risultato)
                            for c in nuove
                        ],
                    )
                )
            else:
                # I giri sono finiti e l'ultimo chiedeva ancora strumenti.
                giri = "giro" if self.max_giri == 1 else "giri"
                motivo_riepilogo = f"tetto di {self.max_giri} {giri}"
        except GeminiNonDisponibile as errore:
            # Senza risultati in mano non c'è niente da riassumere: l'errore
            # sale e sul dispositivo diventa la clip "non ci arrivo".
            if not eseguite:
                self.faccia.mostra(STATO_ERRORE)
                raise
            motivo_riepilogo = "tempo finito" if errore.tipo == "tempo" else "modello non disponibile"

        if motivo_riepilogo:
            try:
                # Il riepilogo non chiede mai la trascrizione: se è servito è
                # perché il primo giro l'aveva già scritta (o non poteva
                # scriverla, testo=), non c'è niente di nuovo da trascrivere.
                risposta, modello, ripetuto, _ = self._chiedi(contenuti, scadenza, riepilogo=True)
            except GeminiNonDisponibile:
                self.faccia.mostra(STATO_ERRORE)
                raise
            ripetizioni += ripetuto

        testo_grezzo = testo_della_risposta(risposta)
        # Il blocco [TRASCRIZIONE] resta nel testo grezzo quando il primo
        # giro è anche quello finale (nessuno strumento chiamato): va tolto
        # prima delle etichette, altrimenti finirebbe letto ad alta voce.
        # Innocuo quando non c'è (`separa_trascrizione` lo lascia intatto).
        _, testo_grezzo = separa_trascrizione(testo_grezzo)
        espressione, lingua, testo_finale = separa_etichette(testo_grezzo)
        # Due chiamate distinte apposta (issue #23): `mostra` è sempre uno
        # STATO_* vero, `esprimi` è l'espressione scelta dal modello. Prima
        # di bmo-face erano confuse in una sola (`mostra(espressione or ...)`),
        # innocuo quando la faccia non faceva altro che stampare o ignorare,
        # ma `FacciaSocket` verso un renderer vero andava in KeyError su
        # un'espressione passata come se fosse uno stato.
        self.faccia.mostra(STATO_PARLATO if testo_finale else STATO_ERRORE)
        if espressione:
            self.faccia.esprimi(espressione)
        # Storico di sessione (#29): non lo si scrive già qui. `dopo_il_turno()`
        # farà le eventuali richieste silenziose (trascrizione, estrazione,
        # riassunto) solo *dopo* che questa `Risposta` sarà arrivata a
        # `Macchina` ed è già stata pronunciata — mai mentre chi ha appena
        # parlato aspetta ancora, come chiede l'issue.
        if testo_finale:
            token_prompt = getattr(getattr(risposta, "usage_metadata", None), "prompt_token_count", None) or 0
            self._sospeso = _TurnoSospeso(
                audio_wav=audio_wav,
                testo=testo,
                testo_grezzo=testo_grezzo,
                token_prompt=token_prompt,
                trascrizione_inline=trascrizione_dal_modello,
            )
        return Risposta(
            testo=testo_finale,
            chiamate=eseguite,
            modello=modello,
            espressione=espressione,
            lingua=lingua,
            motivo_vuota=None if testo_finale else motivo_risposta_vuota(risposta),
            ripetizioni=ripetizioni,
            riepilogo=motivo_riepilogo,
            durata_s=self.cronometro() - partenza,
        )

    def strumenti(self, chiamate: list[types.FunctionCall]) -> list[ChiamataStrumento]:
        """Esegue le chiamate richieste dal modello e ne raccoglie i risultati."""
        eseguite = []
        for chiamata in chiamate:
            argomenti = dict(chiamata.args or {})
            nome = chiamata.name or ""
            esecutore = self._esecutori.get(nome)
            if nome not in _PARAMETRI:
                risultato = {"errore": f"strumento sconosciuto: {chiamata.name}"}
            elif sbagliati := controlla_argomenti(nome, argomenti):
                risultato = sbagliati
            elif esecutore is None:
                risultato = {
                    "stato": "non_disponibile",
                    "motivo": "questa funzione di BMO non è ancora pronta",
                }
            else:
                try:
                    risultato = esecutore(**argomenti)
                except (TypeError, ValueError) as errore:
                    risultato = {"errore": str(errore)}
            eseguite.append(ChiamataStrumento(chiamata.name or "", argomenti, risultato))
        # Gli strumenti possono aver toccato i timer o il diario (ricorda,
        # #14.2): la prossima richiesta rilegge i file, così lo strato STATO
        # dice la verità già nel giro successivo dello stesso turno.
        self._timer_letti = None
        self._diario_letto = None
        return eseguite

    def _cerca_sul_web(self, query: str) -> dict[str, Any]:
        return self.ricerca(query)

    def _imposta_timer(self, etichetta: str, ore: int = 0, minuti: int = 0, secondi: int = 0) -> dict[str, Any]:
        # "Un'ora e un quarto" arrivò come ore 1 e minuti 75 (prova del 19/9):
        # il timer durava due ore e un quarto e BMO confermava l'ora e un quarto.
        if ore and float(minuti or 0) >= 60:
            raise ValueError("minuti deve essere fra 0 e 59 quando indichi anche le ore")
        if (ore or minuti) and float(secondi or 0) >= 60:
            raise ValueError("secondi deve essere fra 0 e 59 quando indichi anche ore o minuti")
        durata = durata_in_secondi({"ore": ore, "minuti": minuti, "secondi": secondi})
        if durata <= 0:
            raise ValueError("la durata deve essere positiva: indica ore, minuti o secondi")
        # Scritto su disco: se BMO si riavvia, il timer suona lo stesso (#20).
        nuovo = self.archivio.aggiungi(etichetta, durata)
        # La durata impostata davvero, perché il modello confermi quella e non
        # quella che ha sentito.
        return {
            "stato": "ok",
            "etichetta": etichetta,
            "durata": _durata_parlata(durata),
            "scadenza": nuovo.scadenza.strftime("%H:%M"),
        }

    def _annulla_timer(self, etichetta: str | None = None) -> dict[str, Any]:
        annullati = self.archivio.annulla(etichetta)
        return {"stato": "ok" if annullati else "nessun_timer", "annullati": annullati}

    def _elenca_timer(self) -> dict[str, Any]:
        ora = self.orologio()
        return {
            "timer": [
                {"etichetta": t.etichetta, "rimanenti_secondi": int((t.scadenza - ora).total_seconds())}
                for t in self.archivio.attivi()
            ]
        }


def _stampa_risposta(cervello: Cervello, risposta: Risposta) -> None:
    # Sempre esplicito, anche quando non c'è nessuna chiamata: nelle prove a
    # voce è l'unico modo di sapere se il timer è stato impostato davvero.
    if risposta.chiamate:
        print(f"Strumenti chiamati: {len(risposta.chiamate)}")
        for chiamata in risposta.chiamate:
            print(f"  → {chiamata.nome}({chiamata.argomenti}) = {chiamata.risultato}")
    else:
        print("Strumenti chiamati: nessuno")
    nota = "" if risposta.modello == cervello.cascata.primario else ", il primario non era disponibile"
    if risposta.ripetizioni:
        nota += ", risposta con la sola etichetta ripetuta"
    print(f"Modello: {risposta.modello}{nota}")
    riepilogo = f", riepilogo forzato ({risposta.riepilogo})" if risposta.riepilogo else ""
    print(f"Tempo: {risposta.durata_s:.1f} s su {TETTO_TURNO_S:.0f}{riepilogo}")
    faccia = f" [faccia: {risposta.espressione}]" if risposta.espressione else ""
    print(f"BMO{faccia}: {risposta.testo or f'(risposta vuota: {risposta.motivo_vuota})'}")


def _conversazione(cervello: Cervello, durata_s: float) -> None:
    """Turni continui sullo stesso `Cervello`, per provare lo storico di sessione (#29).

    A differenza del turno singolo di `main()`, qui il `Cervello` è uno solo
    per tutta la conversazione: è la persistenza dello storico fra un
    `rispondi()` e l'altro, non qualcosa di scriptato apposta per la prova.
    """
    print(
        f"Conversazione continua: premi Invio e parla per {durata_s:g} secondi, Ctrl-D per uscire "
        f"(sessione chiusa dopo {INATTIVITA_SESSIONE_S:g} s di silenzio)."
    )
    while True:
        try:
            input()
        except EOFError:
            print()
            return
        audio = cervello.ascolta(durata_s)
        try:
            risposta = cervello.rispondi(audio_wav=audio)
        except ERRORI_GEMINI as errore:
            print(f"BMO non ci arriva: {descrivi_errore(errore)}")
            cervello.dopo_il_turno()  # un'estrazione in sospeso non aspetta questo turno
            continue
        _stampa_risposta(cervello, risposta)
        cervello.dopo_il_turno()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Un turno di dialogo con BMO dal microfono del PC.")
    parser.add_argument("--durata", type=float, default=DURATA_ASCOLTO_S, help="secondi di ascolto")
    parser.add_argument("--wav", type=Path, help="usa un file WAV invece del microfono")
    parser.add_argument("--testo", help="manda testo invece di audio")
    parser.add_argument("--senza-ora", action="store_true", help="non iniettare l'ora (esperimento 0.3)")
    parser.add_argument("--prompt", type=Path, help="file di testo da usare come prompt fisso")
    parser.add_argument(
        "--max-giri",
        type=int,
        default=MAX_GIRI,
        help=f"giri con gli strumenti prima del riepilogo forzato (predefinito {MAX_GIRI}); "
        "con 1 il riepilogo scatta di sicuro, utile per provarlo",
    )
    parser.add_argument(
        "--conversazione",
        action="store_true",
        help="turni continui (Invio → parli → BMO risponde) invece di uno solo, "
        "per provare lo storico di sessione (#29) dal vivo",
    )
    argomenti = parser.parse_args()

    cervello = Cervello(
        faccia=crea_faccia(sul_terminale=True),
        inietta_ora=not argomenti.senza_ora,
        max_giri=argomenti.max_giri,
        **prompt_da_file(argomenti.prompt),
    )
    if argomenti.conversazione:
        _conversazione(cervello, argomenti.durata)
        return
    audio = None
    if argomenti.wav:
        audio = argomenti.wav.read_bytes()
    elif not argomenti.testo:
        print(f"Parla per {argomenti.durata:g} secondi...")
        audio = cervello.ascolta(argomenti.durata)
    try:
        risposta = cervello.rispondi(audio_wav=audio, testo=argomenti.testo)
    except ERRORI_GEMINI as errore:
        raise SystemExit(f"BMO non ci arriva: {descrivi_errore(errore)}") from None
    _stampa_risposta(cervello, risposta)
    cervello.dopo_il_turno()


if __name__ == "__main__":
    main()
