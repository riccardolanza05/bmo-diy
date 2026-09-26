"""Storico di conversazione a breve termine, in RAM (issue #29).

Oggi ogni turno di `Cervello.rispondi()` parte da zero: qui c'è solo lo stato
— i turni recenti, quando è stato l'ultimo, quanti token ha usato l'ultima
richiesta — e la logica pura per decidere quando la sessione è scaduta o ha
superato il tetto. Le chiamate a Gemini (trascrizione, estrazione verso il
diario della #14, riassunto) restano in `brain.Cervello`, che è già il solo
posto che conosce client e cascata — e girano tutte da `Cervello.dopo_il_turno()`,
mai da `rispondi()`: l'issue lo chiede esplicitamente ("mai mentre qualcuno
aspetta una risposta"), e `rispondi()` è ancora in corso finché non è tornata
la `Risposta` che `Macchina` userà per parlare.

Le due soglie sono quelle decise nell'issue: **5 minuti di inattività**
chiudono la sessione, un tetto di **60k token** in ingresso la comprime senza
interromperla. Il controllo è "turno dopo turno" (vedi lo schema
dell'issue), non un timer in background: si valuta all'inizio del turno
successivo, non mentre non sta succedendo niente. È una scelta deliberata,
coerente con "il file della #14 resta leggibile via SCP" e con il limite già
accettato dall'issue ("se il processo si riavvia, una conversazione aperta
si perde"): un ritardo di qualche minuto nel chiudere una sessione silenziosa
non cambia niente in pratica, e non serve un thread in più che tocchi lo
stesso stato di `Cervello` in concorrenza con un turno vero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from google.genai import types

# Sessione chiusa dopo tanti secondi di silenzio (issue #29: 5 minuti,
# inattività non durata totale — una conversazione lunga non viene tagliata).
INATTIVITA_SESSIONE_S = 5 * 60.0

# Tetto di token in ingresso per richiesta, letto da
# usage_metadata.prompt_token_count dell'ultima risposta (nessuna chiamata in
# più solo per contare). Con 60k anche un turno a 4 giri di loop agentico
# resta sotto il limite di 250k token/minuto del free tier.
TETTO_TOKEN_STORICO = 60_000

# Se l'estrazione verso il diario (#14) fallisce (rete giù, quota), il testo
# in attesa di essere estratto resta in `Cervello._estrazione_pendente` e si
# ritenta al turno successivo: oltre questo numero di tentativi si rinuncia e
# lo si scarta comunque, per non restare bloccati per sempre dietro un
# errore che non passa.
MAX_TENTATIVI_ESTRAZIONE = 3

# Tetto di tempo per l'intera catena di richieste silenziose di un
# `dopo_il_turno()` (trascrizione, estrazione pendente, estrazione e
# riassunto del tetto): un solo budget condiviso, non uno per chiamata,
# altrimenti un sovraccarico del modello fa restare BMO sordo fino a
# TENTATIVI_SDK × TIMEOUT_TENTATIVO_S per ciascuna delle richieste
# incatenate (fino a 4). Se il budget finisce a metà catena, le richieste
# successive falliscono con GeminiNonDisponibile("tempo", ...) e i loro
# `except` già previsti si comportano come per qualunque altro errore.
BUDGET_DOPO_IL_TURNO_S = 8.0

# Al massimo tante voci nuove per estrazione: un'unica richiesta di
# estrazione mal riuscita (o un modello che elenca ogni dettaglio invece dei
# fatti degni di nota) non deve poter riempire da sola il diario e sfrattare
# le voci più vecchie, comprese quelle scritte a mano (`memoria.MAX_VOCI`).
MAX_VOCI_PER_ESTRAZIONE = 3

# Il modello risponde con questa parola sola quando non c'è niente da
# ricordare: più facile da riconoscere ed escludere di una riga vuota, che
# in pratica arriva spesso circondata da altro testo ("Nessuna informazione
# degna di nota.", frasi intere invece del solo sentinel).
NIENTE_DA_RICORDARE = "NIENTE"

# Prompt per le tre richieste silenziose della #29: mai visti da chi parla
# con BMO, non condividono niente col prompt di sistema di brain.py perché
# non sono un turno di conversazione — più vicini a ISTRUZIONE_SI_NO di
# brain.py (classifica_risposta) che al prompt fisso.
ISTRUZIONE_TRASCRIZIONE = """\
Trascrivi esattamente quello che dice l'audio, in italiano o in inglese a seconda
della lingua parlata. Scrivi solo la trascrizione: non rispondere, non commentare,
non correggere quello che è stato detto.
Se l'audio è silenzio o rumore senza parole comprensibili, rispondi con una
riga vuota.
"""

ISTRUZIONE_ESTRAZIONE = f"""\
Rileggi questa conversazione fra una persona di casa e BMO. Estrai SOLO i fatti o
le preferenze utili da ricordare per il futuro — gusti, abitudini, programmi,
nomi ricorrenti — non il contenuto occasionale della chiacchierata.
Al massimo {MAX_VOCI_PER_ESTRAZIONE} fatti, un fatto per riga, in italiano, in
prosa, senza numerarli, senza punti elenco e senza altro testo intorno.
Non scrivere informazioni personali delicate: salute, soldi, password o dati
di accesso.
Il diario ha già queste voci: non ripeterle, nemmeno riformulate. Se non c'è
niente di nuovo e degno di essere ricordato, rispondi con la sola parola
{NIENTE_DA_RICORDARE}.
"""

ISTRUZIONE_RIASSUNTO_SESSIONE = """\
Riassumi questa conversazione fra una persona di casa e BMO in poche righe,
tenendo le informazioni utili per proseguirla: di cosa si stava parlando, cosa
è stato deciso o chiesto. Scrivi in italiano, in prosa, senza etichette né
elenchi puntati.
"""


@dataclass
class Turno:
    """Un turno passato: la trascrizione di chi ha parlato e la risposta di BMO.

    `bmo` è il testo *con* le etichette iniziali di lingua/espressione
    (`brain.testo_della_risposta`, non `separa_etichette`): senza, dal
    secondo turno in poi il modello vedrebbe solo le proprie risposte già
    spogliate nello storico e smetterebbe di scriverle, imitando quello che
    si vede scrivere (§2.3 le rende obbligatorie).
    """

    utente: str
    bmo: str


@dataclass
class StoricoSessione:
    """Lo storico letterale dei turni recenti, tenuto in RAM per un `Cervello`.

    `riassunto` è quanto resta di una compressione precedente (caso 2 della
    #29): a differenza dei turni letterali non entra nei `contents` mandati a
    Gemini (due `Content` di seguito con `role="user"` non è una forma
    garantita dall'API multi-turno), ma nello strato STATO del prompt
    (`brain.contesto_dinamico`), accanto a Diario e Timer.
    """

    turni: list[Turno] = field(default_factory=list)
    riassunto: str | None = None
    ultimo_turno: float | None = None  # istante del cronometro del Cervello
    token_prompt: int = 0  # prompt_token_count dell'ultima risposta

    @property
    def attiva(self) -> bool:
        """Una sessione senza niente da ricordare non può essere né scaduta né estratta."""
        return bool(self.turni) or self.riassunto is not None

    def aggiungi(self, utente: str, bmo: str, adesso: float, token_prompt: int) -> None:
        self.turni.append(Turno(utente, bmo))
        self.ultimo_turno = adesso
        self.token_prompt = token_prompt

    def scaduta(self, adesso: float, inattivita_s: float = INATTIVITA_SESSIONE_S) -> bool:
        return self.attiva and self.ultimo_turno is not None and (adesso - self.ultimo_turno) >= inattivita_s

    def oltre_tetto(self, tetto: int = TETTO_TOKEN_STORICO) -> bool:
        return self.token_prompt >= tetto

    def svuota(self) -> None:
        self.turni = []
        self.riassunto = None
        self.ultimo_turno = None
        self.token_prompt = 0

    def sostituisci_con_riassunto(self, riassunto: str) -> None:
        """Caso 2b: i turni letterali lasciano il posto a un solo riassunto.

        La sessione resta attiva (`ultimo_turno` non cambia): non è una
        chiusura, è una compressione a metà conversazione.
        """
        self.turni = []
        self.riassunto = riassunto.strip() or None

    def testo_per_estrazione(self) -> str:
        """La conversazione come testo semplice, per i prompt di estrazione e riassunto.

        Testo semplice e non le `Content` originali (niente parti audio né
        `thought_signature`): resta leggibile anche se la cascata ha
        cambiato modello a metà conversazione (§2.9).
        """
        righe = []
        if self.riassunto:
            righe.append(f"[Riassunto di prima] {self.riassunto}")
        for turno in self.turni:
            righe.append(f"Persona: {turno.utente}")
            righe.append(f"BMO: {turno.bmo}")
        return "\n".join(righe)

    def contenuti(self) -> list[types.Content]:
        """Lo storico letterale da anteporre al turno nuovo nella richiesta a Gemini.

        Solo i turni, mai il riassunto (vedi la docstring della classe): chi
        chiama inietta quello nello strato STATO, non qui.
        """
        contenuti = []
        for turno in self.turni:
            if turno.utente:
                contenuti.append(types.Content(role="user", parts=[types.Part.from_text(text=turno.utente)]))
            contenuti.append(types.Content(role="model", parts=[types.Part.from_text(text=turno.bmo)]))
        return contenuti
