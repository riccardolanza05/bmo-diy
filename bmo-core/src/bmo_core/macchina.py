"""La macchina a stati di BMO (§2.1 del piano, issue #20).

    ATTESA ──richiamo──► ASCOLTO ──► PENSIERO ──► PARLATO ──► ATTESA
       ▲                                  ↕                       │
       │                             CONFERMA (chiedi_conferma,   │
       │                             #17: proponi → sì/no/boh)    │
       └────────────────── PAUSA (metti_in_pausa_l_ascolto) ──────┘
       └────────────────── ERRORE (Gemini non risponde) ──────────┘

CONFERMA è un sotto-dialogo, non un giro completo: chi la chiede resta in
ascolto diretto, senza richiedere di nuovo "Hey BMO" (chiedi_conferma()).

Il punto del piano che conta piu' di tutti: **a ogni transizione cambia la
faccia**. Senza pulsanti e senza spie, la faccia e' l'unico modo di sapere
che BMO ha sentito il richiamo, che sta elaborando o che non ce l'ha fatta.
Per questo la faccia si mostra *prima* di cominciare l'azione, mai dopo: il
piano chiede che il passaggio ad ASCOLTO si veda entro 150 ms, altrimenti la
persona ripete la frase e rovina la registrazione.

Due pezzi restano isolati apposta dietro due funzioni, per ragioni ormai
diverse — uno e' provvisorio, l'altro e' una scelta:

- il **richiamo** e' Invio sulla tastiera di default; `RichiamoWakeWord`
  (#22, `richiamo.py`) ascolta «Hey BMO» coi due modelli addestrati da
  Riccardo committati nel repo (`modelli-wake-word/bmo1.onnx`, `bmo2.onnx`,
  §2.6 — non più il preaddestrato `hey_jarvis`, deciso il 26/9). Un terzo
  modello (bmo3) resta deliberatamente fuori dal repo, solo sul BMO
  personale di Riccardo. Si chiede con `--wake-word`. Resta opt-in, deciso
  il 25/9 sullo stesso schema della voce sotto: la soglia è «provvisoria»
  (l'issue lo dice nel titolo) finché non è stata sentita funzionare dal
  vivo nella stanza vera;
- la **voce** stampa il testo di default (`voce_sul_terminale`); `VoceTts`
  (#42) la sintetizza con edge-tts e la suona, e si chiede con
  `--voce-tts`. Resta opt-in finché non è stata sentita funzionare dal vivo:
  il terminale non ha bisogno di rete e di un nome di voce giusto.

Quando la rete non risponde, prima della frase suona un breve suono
d'errore (#21, `suoni.py`), sullo stesso altoparlante della voce.

**L'ascolto, una volta iniziato, non e' piu' provvisorio**: si ferma da solo
quando rileva silenzio dopo la voce (VAD, `vad.py`), non dopo una durata
fissa decisa in anticipo — richiesto da Riccardo il 20/9 provando la #14.2 a
voce, perche' nessuno sa in anticipo quanto debba durare una frase.
`usa_vad=False` torna alla durata fissa di prima, per i casi in cui il VAD
non e' disponibile o serve confrontare i due comportamenti.

**Ctrl-D non spegne qualcosa che sta ancora lavorando** (bug del 21/9: BMO
chiuso a metà lasciava la radio orfana). Il piano dice che BMO e' acceso
24/7, senza un vero interruttore software (§2.1): coerente con questo, se
la radio sta suonando o c'e' un timer attivo, `esegui()` resta acceso in
sottofondo finche' non finiscono da soli, poi esce senza dover spegnere
niente a forza. Ctrl-C (KeyboardInterrupt) resta la via per uscire subito
comunque, e in quel caso sì si spegne la radio esplicitamente (`main()`).

**Il microfono aperto sente anche la radio** (trovato il 21/9 provando dal
vivo): col volume alto il VAD non distingue più la voce dalla musica.
`turno()` e `_ascolta_e_classifica()` sospendono `sospendi_ascolto()` (di
solito `Radio.sospesa()`, agganciata in `main()`) per la durata
dell'ascolto e la riprendono subito dopo, non a fine turno.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from .adapters import (
    STATO_ASCOLTO,
    STATO_ASSONNATO,
    STATO_CONFERMA,
    STATO_ERRORE,
    STATO_IDLE,
    STATO_PARLATO,
    STATO_PENSIERO,
    AudioOutputAdapter,
    FacciaAdapter,
    catena_voce,
    crea_audio_output,
    crea_faccia,
)
from .brain import CAP_ASCOLTO_S, DURATA_ASCOLTO_S, ERRORI_GEMINI, Cervello, descrivi_errore
from .config import FUSO_ORARIO
from .inviluppo import inviluppo_rms
from .volumi import leggi_volume
from .memoria import aggiungi_voce
from .radio import Radio
from .richiamo import MODELLI_PREDEFINITI, SOGLIA_PREDEFINITA, RichiamoWakeWord
from .suoni import Suoni, SuoniMuti
from .sveglia import Sveglia
from .tts import TtsNonDisponibile, sintetizza
from .vad import AGGRESSIVITA_PREDEFINITA, SILENZIO_MS_PREDEFINITO, Diagnostica

MAX_PAUSA_MINUTI = 8 * 60  # otto ore: oltre, BMO resterebbe sordo per sbaglio

# Tetto di sicurezza per il sotto-dialogo di conferma (#17): un sì o un no si
# dicono in meno di due secondi, il VAD si ferma molto prima di arrivarci.
# Senza VAD (usa_vad=False) diventa invece la durata fissa di ascolto, come
# prima di questo cambiamento.
CAP_CONFERMA_S = 8.0

# Quanto aspettare fra un controllo e l'altro mentre BMO resta acceso in
# sottofondo dopo Ctrl-D, aspettando che radio o timer finiscano da soli.
ATTESA_SPEGNIMENTO_S = 2.0


class Stato(str, Enum):
    ATTESA = "attesa"
    ASCOLTO = "ascolto"
    PENSIERO = "pensiero"
    PARLATO = "parlato"
    PAUSA = "pausa"
    ERRORE = "errore"
    CONFERMA = "conferma"


def richiamo_da_tastiera() -> bool:
    """Il richiamo provvisorio: Invio. Restituisce False quando si vuole uscire."""
    try:
        input()
        return True
    except EOFError:
        return False


def voce_sul_terminale(testo: str, lingua: str = "it") -> None:
    """La voce di ripiego: BMO scrive quello che direbbe.

    Era la voce provvisoria in attesa del TTS (#42). Adesso che il TTS c'è
    resta come rete di sicurezza — senza rete, senza chiave o con un nome di
    voce sbagliato la risposta si legge invece di perdersi — e come voce
    predefinita finché `VoceTts` non viene chiesta esplicitamente.
    """
    # La lingua si stampa solo quando non e' quella di casa: serve a vedere a
    # colpo d'occhio se il modello l'ha dichiarata come doveva.
    marca = "" if lingua == "it" else f" [{lingua}]"
    print(f"BMO{marca}: {testo}", flush=True)


def _pausa_da_ambiente() -> float | None:
    """`BMO_VOCE_PAUSA` in secondi, o `None` per il valore predefinito.

    Un valore illeggibile non deve lasciare BMO muto: si ignora e si usa il
    predefinito, come per un nome di filtro sbagliato.
    """
    grezzo = os.environ.get("BMO_VOCE_PAUSA")
    if not grezzo:
        return None
    try:
        return float(grezzo.replace(",", "."))
    except ValueError:
        print(f"[voce: BMO_VOCE_PAUSA={grezzo!r} non e' un numero, uso il predefinito]", file=sys.stderr)
        return None


def _sintetizza_nella_lingua(testo: str, lingua: str = "it") -> Any:
    """Adattatore fra la voce e `tts.sintetizza`, che prende la lingua come
    argomento con nome. Esiste solo per tenere `VoceTts` ignara della firma."""
    return sintetizza(testo, lingua=lingua)


class VoceTts:
    """La voce vera (#42): sintetizza la risposta e la fa sentire.

    Sta qui e non in `tts.py` perché è il punto in cui tre cose separate si
    incontrano — la sintesi, l'altoparlante e il ripiego — e perché `Macchina`
    prende già una `voce` come `Callable[[str], None]`: questa classe è
    chiamabile, quindi si innesta lì senza toccare altro. `tts.py` resta
    ignaro di tutto e riutilizzabile dalla #21 per generare le clip offline.

    **Il ripiego è largo di proposito.** Qualunque cosa vada storta nella
    sintesi o nella riproduzione, la risposta finisce sul terminale: una
    risposta letta è molto meglio di una risposta persa, e questo è il
    comportamento che la #42 promette.

    **Aspetta la fine della frase** (`altoparlante.attendi()`). Senza, la
    macchina a stati tirerebbe dritto e la riproduzione successiva —
    `riproduci` comincia con `ferma()` — taglierebbe BMO a metà parola.
    """

    def __init__(
        self,
        altoparlante: AudioOutputAdapter | None = None,
        ripiego: Callable[..., None] = voce_sul_terminale,
        sintetizza_fn: Callable[..., Any] = _sintetizza_nella_lingua,
        filtro: str | None = None,
        pausa_max_s: float | None = None,
        diagnostica: bool = True,
        cronometro: Callable[[], float] = time.monotonic,
        faccia: FacciaAdapter | None = None,
        inviluppo_fn: Callable[..., list[float]] = inviluppo_rms,
    ) -> None:
        self.altoparlante = altoparlante or crea_audio_output()
        self.ripiego = ripiego
        self.sintetizza_fn = sintetizza_fn
        # Bocca guidata dall'inviluppo RMS della voce vera (§2.2, issue #23):
        # facoltativa, `None` di default, così chi non ha bmo-face acceso non
        # paga il costo di `ffmpeg` per ogni battuta.
        self.faccia = faccia
        self.inviluppo_fn = inviluppo_fn
        # La catena della voce (#42): timbro da `BMO_VOCE_FILTRO` (predefinito
        # "radiolina", scelto all'ascolto) e accorciamento delle pause da
        # `BMO_VOCE_PAUSA`, in secondi — "0" lo disattiva.
        self.filtro = catena_voce(
            filtro if filtro is not None else os.environ.get("BMO_VOCE_FILTRO"),
            pausa_max_s if pausa_max_s is not None else _pausa_da_ambiente(),
        )
        self.diagnostica = diagnostica
        self.cronometro = cronometro

    def __call__(self, testo: str, lingua: str = "it") -> None:
        inizio = self.cronometro()
        try:
            percorso = self.sintetizza_fn(testo, lingua)
        except (TtsNonDisponibile, ValueError) as errore:
            print(f"[voce: sintesi non riuscita, leggo il testo — {errore}]", file=sys.stderr)
            self.ripiego(testo, lingua)
            return
        sintesi = self.cronometro()
        if self.faccia is not None:
            # In un thread a parte, apposta: `_stampa_tempi` protegge già
            # (#42) i due numeri di latenza che contano da qualunque lavoro
            # in più per singola risposta, e decodificare con ffmpeg è
            # esattamente il costo che quella scelta aveva evitato. Qui
            # arriva comunque, ma senza aggiungersi alla latenza percepita:
            # la bocca può restare ferma per i primi fotogrammi di una
            # battuta, mai far aspettare l'inizio del suono.
            threading.Thread(target=self._manda_inviluppo, args=(percorso,), daemon=True).start()
        try:
            # Il volume si rilegge a ogni battuta, non una volta sola
            # all'avvio: "abbassa la tua voce" deve valere dalla prossima
            # frase (volumi.py — il canale "voce" del volume indipendente).
            self.altoparlante.riproduci(percorso, filtro=self.filtro, volume=leggi_volume("voce"))
        except OSError as errore:  # mpv non installato, dispositivo audio occupato
            print(f"[voce: riproduzione non riuscita, leggo il testo — {errore}]", file=sys.stderr)
            self.ripiego(testo, lingua)
            return
        partenza = self.cronometro()
        if self.diagnostica:
            self._stampa_tempi(sintesi - inizio, partenza - sintesi)
        self.altoparlante.attendi()

    def _manda_inviluppo(self, percorso: Any) -> None:
        """La parte in background di `__call__`: mai far fallire la voce (#23)."""
        try:
            inviluppo = self.inviluppo_fn(percorso)
        except Exception:  # difensivo apposta: un thread in background non deve mai propagare
            return
        if inviluppo:
            self.faccia.parla(inviluppo)

    def _stampa_tempi(self, sintesi_s: float, avvio_s: float) -> None:
        """I due tempi separati, non la somma (criterio di uscita della #42).

        Il primo è l'attesa di rete, il secondo è il tempo di far partire
        mpv: si curerebbero in modi diversi, e sommati non si distinguono
        piu'. Sullo stderr come la diagnostica del VAD, per non
        sporcare lo stdout dei comandi di prova.

        **Niente durata dell'audio**: leggerla da un mp3 vorrebbe dire
        decodificarlo o lanciare `ffprobe` a ogni singola risposta, ed e'
        proprio il costo per frase che i filtri di mpv ci hanno permesso di
        evitare. Il criterio della #42 chiede questi due numeri, non quello.
        """
        print(
            f"[voce: sintesi {sintesi_s:.2f} s, primo suono +{avvio_s:.2f} s]",
            file=sys.stderr,
        )


class Macchina:
    """Un BMO acceso: aspetta di essere chiamato, risponde, torna ad aspettare."""

    def __init__(
        self,
        cervello: Cervello,
        faccia: FacciaAdapter | None = None,
        richiamo: Callable[[], bool] = richiamo_da_tastiera,
        voce: Callable[..., None] = voce_sul_terminale,
        durata_ascolto_s: float = DURATA_ASCOLTO_S,
        cap_ascolto_s: float = CAP_ASCOLTO_S,
        cap_conferma_s: float = CAP_CONFERMA_S,
        usa_vad: bool = True,
        silenzio_ms: float = SILENZIO_MS_PREDEFINITO,
        aggressivita_vad: int = AGGRESSIVITA_PREDEFINITA,
        orologio: Callable[[], datetime] | None = None,
        qualcosa_attivo: Callable[[], bool] | None = None,
        attesa_spegnimento_s: float = ATTESA_SPEGNIMENTO_S,
        dormi: Callable[[float], None] = time.sleep,
        sospendi_ascolto: Callable[[], AbstractContextManager[None]] | None = None,
        suoni: Suoni | SuoniMuti | None = None,
    ) -> None:
        self.cervello = cervello
        # Muti se non collegati: i test e prova_frasi non lanciano mpv.
        self.suoni = suoni or SuoniMuti()
        self.faccia = faccia or crea_faccia()
        self.richiamo = richiamo
        self.voce = voce
        # durata_ascolto_s/cap_conferma_s contano solo con usa_vad=False: col
        # VAD acceso è cap_ascolto_s/cap_conferma_s a fare da tetto, e ci si
        # ferma molto prima per silenzio.
        self.durata_ascolto_s = durata_ascolto_s
        self.cap_ascolto_s = cap_ascolto_s
        self.cap_conferma_s = cap_conferma_s
        self.usa_vad = usa_vad
        self.silenzio_ms = silenzio_ms
        self.aggressivita_vad = aggressivita_vad
        self.orologio = orologio or (lambda: datetime.now(FUSO_ORARIO))
        # Cosa impedisce l'uscita dopo Ctrl-D: radio e timer sono cose che
        # Macchina non conosce direttamente, chi la costruisce (main()) dice
        # come controllarle. Senza niente di collegato, esce sempre subito.
        self.qualcosa_attivo = qualcosa_attivo or (lambda: False)
        self.attesa_spegnimento_s = attesa_spegnimento_s
        self.dormi = dormi
        # Cosa mettere in pausa mentre il microfono è aperto (di solito
        # Radio.sospesa()): senza niente di collegato non sospende nulla.
        self.sospendi_ascolto = sospendi_ascolto or (lambda: nullcontext())
        self.stato = Stato.ATTESA
        self.pausa_fino_a: datetime | None = None
        # La pausa la sa solo la macchina: il cervello si limita a chiamare
        # lo strumento quando il modello lo chiede.
        cervello.registra_strumento("metti_in_pausa_l_ascolto", self.metti_in_pausa)
        # Idem per la scrittura del diario (#14.2): serve chiedi_conferma, che
        # è della macchina, non del cervello.
        cervello.registra_strumento("ricorda", self._ricorda)

    # --- strumento della §2.4 ------------------------------------------------

    def metti_in_pausa(self, minuti: int) -> dict[str, Any]:
        minuti = int(minuti)
        if minuti <= 0:
            raise ValueError("minuti deve essere un numero positivo")
        if minuti > MAX_PAUSA_MINUTI:
            raise ValueError(f"al massimo {MAX_PAUSA_MINUTI} minuti")
        self.pausa_fino_a = self.orologio() + timedelta(minutes=minuti)
        # La faccia cambia quando la pausa comincia davvero, cioè quando BMO
        # ha finito di rispondere: qui sta ancora parlando.
        return {"stato": "ok", "minuti": minuti, "fino_a": self.pausa_fino_a.strftime("%H:%M")}

    @property
    def in_pausa(self) -> bool:
        if self.pausa_fino_a is None:
            return False
        if self.orologio() >= self.pausa_fino_a:
            self.pausa_fino_a = None
            return False
        return True

    def _ricorda(self, testo: str) -> dict[str, Any]:
        """Lo strumento `ricorda` (#14.2): propone, chiede conferma, scrive.

        Nessuna scrittura silenziosa (#14): il diario si tocca solo dopo un
        sì esplicito da `chiedi_conferma`. Un "no" o un "non ho capito" non
        sono errori — il modello deve poterli distinguere per dire la cosa
        giusta — quindi tornano come `stato: annullato` con un `motivo`, non
        come eccezione.

        Nota per chi tocca il tetto del turno (#18, TETTO_TURNO_S): questa
        chiamata può bloccare dentro un giro del loop agentico per un tempo
        che il cronometro del turno non scorpora. Col VAD il caso comune è
        breve (un sì o un no più il silenzio che segue, sotto i 2 s); il
        caso peggiore resta comunque fino a 2×cap_conferma_s se il VAD non
        sente mai voce. È accettato per ora: chi sta aspettando una conferma
        sta parlando con BMO, non aspettando in silenzio, e il caso serio
        (rete giù durante la conferma) lo gestisce già `classifica_risposta`
        restituendo "boh". Se in pratica il tetto dei 20 s salta spesso per
        questo, va rivisto.
        """
        testo = (testo or "").strip()
        if not testo:
            raise ValueError("testo non può essere vuoto")
        confermato = self.chiedi_conferma(f"Vuoi che mi ricordi che {testo}?")
        if confermato is True:
            aggiungi_voce(
                self.cervello.diario_percorso, testo, self.orologio().strftime("%Y-%m-%d"), fonte="modello"
            )
            return {"stato": "ok"}
        if confermato is False:
            return {"stato": "annullato", "motivo": "rifiutato"}
        return {"stato": "annullato", "motivo": "non ho capito la conferma"}

    # --- sotto-dialogo di conferma (#17) --------------------------------------

    def chiedi_conferma(self, domanda: str) -> bool | None:
        """Proponi/conferma a voce, senza richiedere di nuovo il richiamo.

        Nato dalla #14 (memoria persistente): nessuna scrittura deve avvenire
        in silenzio — `_ricorda` (#14.2) è il primo chiamante. Pensato per
        essere riusabile per qualunque altra azione che meriti una conferma
        esplicita, come chiede l'issue #17.

        Restituisce True se confermato, False se rifiutato esplicitamente,
        None se non è arrivata una risposta chiara: silenzio, rumore, o
        un'ambiguità che resiste anche dopo un solo chiarimento. Non c'è un
        secondo tentativo dopo quello: un loop di richieste sarebbe peggio di
        annullare (l'issue lo dice esplicitamente). Chi chiama decide se dire
        qualcosa di diverso per "no" esplicito rispetto a "non ho capito".
        """
        self.voce(domanda)
        esito = self._ascolta_e_classifica()
        if esito == "boh":
            self.voce("Non ho capito, dimmi solo sì o no.")
            esito = self._ascolta_e_classifica()
        # Si torna a "pensiero": chi ha chiesto la conferma è ancora dentro
        # un turno di Cervello.rispondi(), non è la faccia finale del turno.
        self._vai(Stato.PENSIERO, STATO_PENSIERO)
        return {"si": True, "no": False}.get(esito)

    def _ascolta_e_classifica(self) -> str:
        self._vai(Stato.CONFERMA, STATO_CONFERMA)
        with self.sospendi_ascolto():
            audio = self._ascolta(self.cap_conferma_s)
        return self.cervello.classifica_risposta(audio)

    # --- gli stati -----------------------------------------------------------

    def _vai(self, stato: Stato, faccia: str) -> None:
        # Prima la faccia, poi l'azione: il piano chiede che il passaggio si
        # veda entro 150 ms, e un'azione lenta non deve ritardarlo.
        self.stato = stato
        self.faccia.mostra(faccia)

    def _ascolta(self, cap_s: float) -> bytes:
        """Un ascolto, con o senza VAD secondo `usa_vad`.

        `cap_s` è la durata fissa quando `usa_vad` è spento, il tetto di
        sicurezza quando è acceso: stesso numero, ruolo diverso.
        """
        if not self.usa_vad:
            return self.cervello.ascolta(cap_s)
        audio, diagnostica = self.cervello.ascolta_fino_al_silenzio(cap_s, self.silenzio_ms, self.aggressivita_vad)
        self._stampa_diagnostica(diagnostica)
        return audio

    def _stampa_diagnostica(self, diagnostica: Diagnostica) -> None:
        # Sullo stderr, come la faccia sul terminale: non deve sporcare
        # l'eventuale uso di stdout dei comandi di prova.
        print(
            f"[ascolto: {diagnostica.durata_totale_s:.1f} s, "
            f"voce rilevata: {'sì' if diagnostica.voce_rilevata else 'no'}, "
            f"fine per: {diagnostica.motivo_fine}]",
            file=sys.stderr,
        )

    def turno(self) -> None:
        """Un giro completo: ascolta, pensa, risponde."""
        self._vai(Stato.ASCOLTO, STATO_ASCOLTO)
        with self.sospendi_ascolto():
            audio = self._ascolta(self.cap_ascolto_s if self.usa_vad else self.durata_ascolto_s)
        try:
            # Il cervello mostra da sé "pensiero" e l'espressione finale.
            self.stato = Stato.PENSIERO
            risposta = self.cervello.rispondi(audio_wav=audio)
        except ERRORI_GEMINI as errore:
            self.stato = Stato.ERRORE
            self.faccia.mostra(STATO_ERRORE)
            # Prima il suono, per intero: senza rete la frase che segue
            # finisce sul terminale, e il suono è tutto quello che si sente.
            self.suoni.errore()
            self.voce(f"Non ci arrivo: {descrivi_errore(errore)}")
            # Un'eventuale estrazione di sessione in sospeso (#29) non deve
            # aspettare che questo turno vada a buon fine: non lo riguarda.
            self.cervello.dopo_il_turno()
            return
        self.stato = Stato.PARLATO
        if risposta.testo:
            # La lingua la dichiara il modello nella risposta (#42): decide
            # quale voce parla, non la si indovina dal testo.
            self.voce(risposta.testo, risposta.lingua)
        else:
            # Il riepilogo non ha prodotto niente (#18): meglio dirlo che tacere.
            self.faccia.mostra(STATO_ERRORE)
            self.voce("Non sono riuscito a rispondere.")
        # Le richieste silenziose della #29 (trascrizione, estrazione,
        # riassunto) girano solo adesso: la voce ha già finito di parlare
        # (`self.voce` aspetta la fine della sintesi, vedi `VoceTts.__call__`),
        # non prima e non durante.
        self.cervello.dopo_il_turno()

    def esegui(self, giri: int | None = None) -> None:
        """Aspetta di essere chiamato, finché non si esce (`giri` serve ai test).

        Quando il richiamo dice di uscire (Ctrl-D), non si esce subito se
        `qualcosa_attivo()` dice che radio o timer stanno ancora lavorando:
        BMO non ha un vero interruttore (§2.1), quindi resta acceso in
        sottofondo finché non finiscono da soli, controllando ogni
        `attesa_spegnimento_s` secondi.
        """
        fatti = 0
        avvisato = False
        while giri is None or fatti < giri:
            if self.in_pausa:
                self._vai(Stato.PAUSA, STATO_ASSONNATO)
            else:
                self._vai(Stato.ATTESA, STATO_IDLE)
            if self.richiamo():
                fatti += 1
                if self.in_pausa:
                    # Chiamato mentre dorme: non registra, e la faccia lo dice.
                    self.faccia.mostra(STATO_ASSONNATO)
                    continue
                self.turno()
                continue
            if not self.qualcosa_attivo():
                return
            if not avvisato:
                self.voce("Radio o timer sono ancora attivi: resto acceso finché non finiscono da soli.")
                avvisato = True
            self.dormi(self.attesa_spegnimento_s)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="BMO acceso: premi Invio per parlargli (--wake-word per «Hey BMO» invece di Invio)."
    )
    parser.add_argument(
        "--senza-vad", action="store_true",
        help="registra per una durata fissa (--durata) invece di fermarsi da solo al silenzio",
    )
    parser.add_argument("--durata", type=float, default=DURATA_ASCOLTO_S, help="secondi di ascolto con --senza-vad")
    parser.add_argument("--cap-ascolto", type=float, default=CAP_ASCOLTO_S, help="tetto massimo di ascolto col VAD")
    parser.add_argument(
        "--silenzio-ms", type=float, default=SILENZIO_MS_PREDEFINITO,
        help="quanto silenzio dopo la voce prima di fermarsi (col VAD)",
    )
    parser.add_argument(
        "--aggressivita", type=int, default=AGGRESSIVITA_PREDEFINITA, choices=[0, 1, 2, 3],
        help="aggressività del VAD: 0 permissivo, 3 aggressivo (con la TV accesa serve più alta)",
    )
    parser.add_argument("--senza-timer", action="store_true", help="non far partire la sveglia dei timer")
    parser.add_argument("--senza-radio", action="store_true", help="non collegare radio e volume")
    parser.add_argument(
        "--voce-tts", action="store_true",
        help="parla con edge-tts (#42) invece di scrivere sul terminale; serve la rete",
    )
    parser.add_argument("--senza-suoni", action="store_true", help="niente suono d'errore (#21)")
    parser.add_argument(
        "--wake-word", action="store_true",
        help="richiamo a voce «Hey BMO» (#22, soglia provvisoria) invece di Invio; serve un microfono",
    )
    parser.add_argument(
        "--modello-wake-word", action="append", default=None,
        help="nome fra i preaddestrati di openWakeWord, o un file .onnx (con --wake-word); "
        "ripetibile per caricarne più di uno insieme",
    )
    parser.add_argument(
        "--soglia-wake-word", type=float, default=SOGLIA_PREDEFINITA,
        help="soglia di rilevamento, 0-1: da tarare nella stanza vera (con --wake-word)",
    )
    argomenti = parser.parse_args()

    faccia = crea_faccia(sul_terminale=True)
    cervello = Cervello(faccia=faccia)
    radio = None
    if not argomenti.senza_radio:
        radio = Radio()
        radio.registra(cervello)
        print(f"Radio: {len(radio.preferite)} stazioni salvate in {radio.percorso}", flush=True)
    # Opt-in: il terminale resta la voce predefinita finché il TTS non è
    # stato sentito funzionare dal vivo. Così prova_frasi e i test non
    # cominciano di colpo a dipendere da una chiamata di rete.
    # Un altoparlante solo per voce e suoni: `riproduci` ferma quello che sta
    # suonando, quindi non ci sono mai due mpv che si parlano sopra.
    altoparlante = crea_audio_output()
    # Stessa `faccia` di Cervello: un solo FacciaSocket, una sola connessione
    # persistente verso bmo-face, non due che si rincorrono (#23).
    voce = VoceTts(altoparlante=altoparlante, faccia=faccia) if argomenti.voce_tts else voce_sul_terminale
    # Uno solo, condiviso col richiamo qui sotto: stesso altoparlante di voce
    # ed errore, così due mpv non suonano mai uno sopra l'altro.
    suoni_bmo = None if argomenti.senza_suoni else Suoni(altoparlante)
    # Opt-in come la voce sopra: Invio resta il richiamo predefinito finché
    # la soglia non è stata sentita funzionare dal vivo nella stanza vera
    # (#22, §2.6 — la soglia qui è dichiaratamente provvisoria).
    if argomenti.wake_word:
        modelli_wake_word = argomenti.modello_wake_word or MODELLI_PREDEFINITI
        rilevatore_vocale = RichiamoWakeWord(modello=modelli_wake_word, soglia=argomenti.soglia_wake_word)

        def richiamo() -> bool:
            # Segnale esplicito dello scatto, distinto dal generico
            # "[faccia: ascolto]" che segue subito dopo (uguale per Invio):
            # utile per una prova dal vivo, per vedere a colpo d'occhio che
            # è stata la wake word e non un richiamo da tastiera. Il suono
            # (stile Google Home/Alexa, ancora il tono di ripiego: non è
            # stato scelto un file vero come per errore/timer, #21) suona
            # per intero prima di continuare, come errore().
            rilevata = rilevatore_vocale()
            if rilevata:
                print("(bmo ascolta)", flush=True)
                if suoni_bmo is not None:
                    suoni_bmo.ascolto()
            return rilevata

        print(
            f"Wake word: {modelli_wake_word}, soglia {argomenti.soglia_wake_word} (provvisoria)",
            flush=True,
        )
    else:
        richiamo = richiamo_da_tastiera
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=richiamo,
        voce=voce,
        durata_ascolto_s=argomenti.durata,
        cap_ascolto_s=argomenti.cap_ascolto,
        usa_vad=not argomenti.senza_vad,
        silenzio_ms=argomenti.silenzio_ms,
        aggressivita_vad=argomenti.aggressivita,
        # Ctrl-D non spegne BMO se radio o timer stanno ancora lavorando
        # (§2.1: acceso 24/7, senza un vero interruttore software) — vedi
        # Macchina.esegui(). I timer sono sempre disponibili via l'archivio
        # del cervello; la radio solo se collegata.
        qualcosa_attivo=lambda: (radio is not None and radio.lettore.in_riproduzione())
        or bool(cervello.archivio.attivi()),
        # Il microfono aperto sente la radio come voce (trovato il 21/9): la
        # si sospende per la durata dell'ascolto e la si riprende subito
        # dopo. Radio.sospesa() non fa nulla se non sta suonando.
        sospendi_ascolto=radio.sospesa if radio is not None else None,
        suoni=suoni_bmo,
    )
    if not argomenti.senza_timer:
        # Nello stesso processo, in un thread: un timer deve suonare anche
        # mentre BMO sta ascoltando o pensando.
        sveglia = Sveglia(archivio=macchina.cervello.archivio, faccia=faccia)
        threading.Thread(target=sveglia.esegui, daemon=True).start()
    if argomenti.wake_word:
        # Niente Invio da premere, quindi niente Ctrl-D per uscire: con la
        # tastiera fuori dal giro l'unica uscita resta Ctrl-C. Il testo non
        # presume più "Hey Jarvis": con --modello-wake-word personalizzati
        # sarebbe stato fuorviante durante una prova dal vivo.
        print(f"BMO è sveglio. Di' una delle wake word configurate ({modelli_wake_word}); Ctrl-C per spegnerlo.", flush=True)
    else:
        print(
            "BMO è sveglio. Premi Invio e parla; Ctrl-D per spegnerlo "
            "(se radio o timer sono attivi resta acceso finché non finiscono da soli; Ctrl-C spegne comunque subito).",
            flush=True,
        )
    try:
        macchina.esegui()
    except KeyboardInterrupt:
        pass
    finally:
        # Sempre, qualunque sia stata l'uscita: mpv resta acceso "idle" (§2.4)
        # anche quando non sta più suonando niente, ed è questo comando, non
        # l'assenza di riproduzione, a spegnerlo per davvero. spegni() non fa
        # niente se la radio non è mai partita.
        if radio is not None:
            radio.lettore.spegni()
    print("\nBuonanotte.", flush=True)


if __name__ == "__main__":
    main()
