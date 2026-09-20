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
from .memoria import Voce, carica_diario
from .modelli import TENTATIVI_SDK, TIMEOUT_TENTATIVO_S, CascataModelli, GeminiNonDisponibile
from .ricerca import cerca
from .strumenti import DICHIARAZIONI
from .timer import ArchivioTimer, Timer
DURATA_ASCOLTO_S = 3.0

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
_ETICHETTA_INIZIALE = re.compile(r"^\s*\[([^\]\n]{1,30})\]\s*")

# Gli stati della faccia (STATO_ASCOLTO, STATO_PENSIERO, …) stanno in
# adapters/base.py, accanto al Protocol: li usa anche la sveglia dei timer,
# che non ha niente a che fare con Gemini. Sono un'altra cosa dalle
# ESPRESSIONI qui sopra, che le sceglie il modello per la risposta parlata.

# Primo strato del prompt (§2.3). È la bozza v4 (prompt/bozza-v4.txt), 40 frasi
# su 40 nella prova del 19/9; le bozze in prompt/ restano come storico.
PROMPT_FISSO = """\
Sei BMO, la piccola console vivente di Adventure Time, e vivi in una casa a Milano.
Sei entusiasta, curioso e un po' ingenuo; ti preoccupi dei tuoi amici. Non sei servile.

COME PARLI — il tuo testo va a un sintetizzatore vocale, queste regole sono vincolanti:
- Rispondi SEMPRE in italiano.
- Sii conciso: di' quello che serve per rispondere, niente di più.
- Rispondi solo a quello che ti è stato chiesto. Se chiedono l'ora, di' solo l'ora; la data solo se la chiedono.
- Niente markdown, niente elenchi, niente emoji, niente parentesi, niente sigle da leggere lettera per lettera.
- Numeri, ore e durate come si dicono a voce: "le cinque e venti", "cinque minuti", "un'ora e un quarto".
- Non descrivere quello che stai facendo ("sto cercando..."): lo dice già la tua faccia.

LA TUA FACCIA:
- La risposta che dici ad alta voce, cioè il testo finale dopo aver letto il risultato degli
  strumenti, inizia con la tua espressione tra parentesi quadre, scelta fra
  [felice] [pensieroso] [sorpreso] [triste] [assonnato].
  Decide la tua faccia e non viene letta ad alta voce: è l'unica eccezione alla regola sulle parentesi.
  Esempio: [felice] Sette per otto fa cinquantasei.

IL DIARIO:
- Nello STATO qui sotto trovi eventuali voci del diario: fatti e preferenze di chi vive in
  casa, ricordati da conversazioni precedenti. Usali per personalizzare le risposte quando è
  utile, senza recitarli o dire esplicitamente che li hai letti da un diario.
- Non hai ancora modo di aggiungerne di nuove da solo: se qualcuno ti chiede di ricordare
  qualcosa ("ricordati che...", "segnati che..."), di' con semplicità che non puoi ancora
  farlo, senza scusarti e senza inventare un modo per farlo comunque.

LE AZIONI SI FANNO SOLO CON GLI STRUMENTI:
- Quando serve uno strumento, la chiamata allo strumento è la prima e unica cosa che fai in quel
  momento: non scrivere niente prima, nemmeno l'espressione. L'espressione e le parole vengono
  solo dopo, nella risposta finale, quando hai letto il risultato.
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

# Prompt a sé, per Cervello.classifica_risposta() (#17): non è uno strato del
# turno normale, non vede lo storico né gli strumenti. Un sotto-dialogo di
# conferma deve essere veloce e a rischio zero di allucinare un'azione, non
# un turno di conversazione completo che potrebbe interpretare un "sì" come
# l'inizio di una richiesta.
ISTRUZIONE_SI_NO = """\
Ascolti la risposta, in italiano, a una domanda a cui si può rispondere solo sì o no.
Rispondi con ESATTAMENTE una di queste tre parole, in minuscolo, senza nient'altro:
si
no
boh
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
    motivo_vuota: str | None = None  # perché il testo è vuoto, se lo è
    ripetizioni: int = 0  # risposte con la sola etichetta, richieste di nuovo
    riepilogo: str | None = None  # perché è servita la richiesta in più (#18)
    durata_s: float = 0.0  # quanto è durato il turno, per il tetto dei 20 s


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
    ora: datetime, timer: list[Timer], inietta_ora: bool = True, diario: list[Voce] | None = None
) -> str:
    """Secondo strato del prompt (§2.3), rigenerato a ogni turno.

    `inietta_ora=False` serve solo all'esperimento della fase 0.3: senza
    l'ora il modello inventa, ed è la dimostrazione del perché questo strato esiste.
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
    return "\n".join(righe)


ERRORI_GEMINI = (GeminiNonDisponibile, errors.APIError, httpx.HTTPError)


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


def separa_espressione(testo: str) -> tuple[str | None, str]:
    """Toglie l'etichetta iniziale ("[felice] Ciao!") e la restituisce a parte.

    L'etichetta va sempre tolta, anche se non è fra le ESPRESSIONI previste:
    il sintetizzatore vocale non deve mai leggere una parentesi quadra.
    """
    trovata = _ETICHETTA_INIZIALE.match(testo)
    if not trovata:
        return None, testo.strip()
    etichetta = trovata.group(1).strip().lower()
    return (etichetta if etichetta in ESPRESSIONI else None), testo[trovata.end():].strip()


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

        Il file di appoggio sta in /dev/shm quando c'è (niente scritture su SD).
        """
        self.faccia.mostra(STATO_ASCOLTO)
        cartella = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=cartella) as file:
            percorso = Path(file.name)
            self.microfono.registra(percorso, durata_s)
            return percorso.read_bytes()

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
        if parola in ("si", "sì"):
            return "si"
        if parola == "no":
            return "no"
        return "boh"

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

    def _configurazione(self, riepilogo: bool = False) -> types.GenerateContentConfig:
        istruzioni = [
            self.prompt_fisso,
            contesto_dinamico(self.orologio(), self.timer, self.inietta_ora, self.diario),
        ]
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
        self, contenuti: list[types.Content], scadenza: float, riepilogo: bool = False
    ) -> tuple[Any, str]:
        return self.cascata.genera(
            self.client,
            scadenza=scadenza,
            contents=contenuti,
            config=self._configurazione(riepilogo),
        )

    def _chiedi(
        self, contenuti: list[types.Content], scadenza: float, riepilogo: bool = False
    ) -> tuple[Any, str, int]:
        """Una richiesta al modello, ripetuta una volta se torna solo l'etichetta.

        Caso reale del 19/9: due timer risposero "[felice]" e basta, senza
        chiamare lo strumento. Restituisce anche quante ripetizioni sono servite.
        """
        risposta, modello = self._genera(contenuti, scadenza, riepilogo)
        vuota = not (risposta.function_calls or []) and not separa_espressione(
            testo_della_risposta(risposta)
        )[1]
        if not vuota:
            return risposta, modello, 0
        risposta, modello = self._genera(contenuti, scadenza, riepilogo)
        return risposta, modello, 1

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
        parti = []
        if audio_wav is not None:
            parti.append(types.Part.from_bytes(data=audio_wav, mime_type="audio/wav"))
        if testo is not None:
            parti.append(types.Part.from_text(text=testo))
        contenuti = [types.Content(role="user", parts=parti)]

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
        try:
            for giro in range(self.max_giri):
                if giro and self.cronometro() >= ultimo_inizio:
                    motivo_riepilogo = "tempo finito"
                    break
                # Scadenza ridotta: un giro lento non può mangiarsi la riserva.
                risposta, modello, ripetuto = self._chiedi(contenuti, ultimo_inizio)
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
                risposta, modello, ripetuto = self._chiedi(contenuti, scadenza, riepilogo=True)
            except GeminiNonDisponibile:
                self.faccia.mostra(STATO_ERRORE)
                raise
            ripetizioni += ripetuto

        espressione, testo_finale = separa_espressione(testo_della_risposta(risposta))
        self.faccia.mostra(espressione or (STATO_PARLATO if testo_finale else STATO_ERRORE))
        return Risposta(
            testo=testo_finale,
            chiamate=eseguite,
            modello=modello,
            espressione=espressione,
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
        # Gli strumenti possono aver toccato i timer: la prossima richiesta
        # rilegge il file, così lo strato STATO dice la verità.
        self._timer_letti = None
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
    argomenti = parser.parse_args()

    cervello = Cervello(
        faccia=crea_faccia(sul_terminale=True),
        inietta_ora=not argomenti.senza_ora,
        max_giri=argomenti.max_giri,
        **prompt_da_file(argomenti.prompt),
    )
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


if __name__ == "__main__":
    main()
