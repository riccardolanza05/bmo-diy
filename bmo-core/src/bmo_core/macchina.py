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

Due pezzi sono ancora provvisori, e sono isolati apposta in due funzioni:

- il **richiamo** e' Invio sulla tastiera; la wake word «Hey BMO» e' la #22 e
  prendera' il posto di `richiamo_da_tastiera` senza toccare il resto;
- la **voce** stampa il testo; il TTS e le clip sono la #21 e seguenti.

**L'ascolto, una volta iniziato, non e' piu' provvisorio**: si ferma da solo
quando rileva silenzio dopo la voce (VAD, `vad.py`), non dopo una durata
fissa decisa in anticipo — richiesto da Riccardo il 20/9 provando la #14.2 a
voce, perche' nessuno sa in anticipo quanto debba durare una frase.
`usa_vad=False` torna alla durata fissa di prima, per i casi in cui il VAD
non e' disponibile o serve confrontare i due comportamenti.
"""
from __future__ import annotations

import sys
import threading
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
    FacciaAdapter,
    crea_faccia,
)
from .brain import CAP_ASCOLTO_S, DURATA_ASCOLTO_S, ERRORI_GEMINI, Cervello, descrivi_errore
from .config import FUSO_ORARIO
from .memoria import aggiungi_voce
from .radio import Radio
from .sveglia import Sveglia
from .vad import AGGRESSIVITA_PREDEFINITA, SILENZIO_MS_PREDEFINITO, Diagnostica

MAX_PAUSA_MINUTI = 8 * 60  # otto ore: oltre, BMO resterebbe sordo per sbaglio

# Tetto di sicurezza per il sotto-dialogo di conferma (#17): un sì o un no si
# dicono in meno di due secondi, il VAD si ferma molto prima di arrivarci.
# Senza VAD (usa_vad=False) diventa invece la durata fissa di ascolto, come
# prima di questo cambiamento.
CAP_CONFERMA_S = 8.0


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


def voce_sul_terminale(testo: str) -> None:
    """La voce provvisoria: BMO scrive quello che direbbe."""
    print(f"BMO: {testo}", flush=True)


class Macchina:
    """Un BMO acceso: aspetta di essere chiamato, risponde, torna ad aspettare."""

    def __init__(
        self,
        cervello: Cervello,
        faccia: FacciaAdapter | None = None,
        richiamo: Callable[[], bool] = richiamo_da_tastiera,
        voce: Callable[[str], None] = voce_sul_terminale,
        durata_ascolto_s: float = DURATA_ASCOLTO_S,
        cap_ascolto_s: float = CAP_ASCOLTO_S,
        cap_conferma_s: float = CAP_CONFERMA_S,
        usa_vad: bool = True,
        silenzio_ms: float = SILENZIO_MS_PREDEFINITO,
        aggressivita_vad: int = AGGRESSIVITA_PREDEFINITA,
        orologio: Callable[[], datetime] | None = None,
    ) -> None:
        self.cervello = cervello
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
        audio = self._ascolta(self.cap_ascolto_s if self.usa_vad else self.durata_ascolto_s)
        try:
            # Il cervello mostra da sé "pensiero" e l'espressione finale.
            self.stato = Stato.PENSIERO
            risposta = self.cervello.rispondi(audio_wav=audio)
        except ERRORI_GEMINI as errore:
            self.stato = Stato.ERRORE
            self.faccia.mostra(STATO_ERRORE)
            self.voce(f"Non ci arrivo: {descrivi_errore(errore)}")
            return
        self.stato = Stato.PARLATO
        if risposta.testo:
            self.voce(risposta.testo)
        else:
            # Il riepilogo non ha prodotto niente (#18): meglio dirlo che tacere.
            self.faccia.mostra(STATO_ERRORE)
            self.voce("Non sono riuscito a rispondere.")

    def esegui(self, giri: int | None = None) -> None:
        """Aspetta di essere chiamato, finché non si esce (`giri` serve ai test)."""
        fatti = 0
        while giri is None or fatti < giri:
            if self.in_pausa:
                self._vai(Stato.PAUSA, STATO_ASSONNATO)
            else:
                self._vai(Stato.ATTESA, STATO_IDLE)
            if not self.richiamo():
                return
            fatti += 1
            if self.in_pausa:
                # Chiamato mentre dorme: non registra, e la faccia lo dice.
                self.faccia.mostra(STATO_ASSONNATO)
                continue
            self.turno()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BMO acceso: premi Invio per parlargli.")
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
    argomenti = parser.parse_args()

    faccia = crea_faccia(sul_terminale=True)
    cervello = Cervello(faccia=faccia)
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        durata_ascolto_s=argomenti.durata,
        cap_ascolto_s=argomenti.cap_ascolto,
        usa_vad=not argomenti.senza_vad,
        silenzio_ms=argomenti.silenzio_ms,
        aggressivita_vad=argomenti.aggressivita,
    )
    if not argomenti.senza_radio:
        radio = Radio()
        radio.registra(cervello)
        print(f"Radio: {len(radio.preferite)} stazioni salvate in {radio.percorso}", flush=True)
    if not argomenti.senza_timer:
        # Nello stesso processo, in un thread: un timer deve suonare anche
        # mentre BMO sta ascoltando o pensando.
        sveglia = Sveglia(archivio=macchina.cervello.archivio, faccia=faccia)
        threading.Thread(target=sveglia.esegui, daemon=True).start()
    print("BMO è sveglio. Premi Invio e parla; Ctrl-D per spegnerlo.", flush=True)
    try:
        macchina.esegui()
    except KeyboardInterrupt:
        pass
    print("\nBuonanotte.", flush=True)


if __name__ == "__main__":
    main()
