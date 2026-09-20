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
"""
from __future__ import annotations

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
from .brain import ERRORI_GEMINI, DURATA_ASCOLTO_S, Cervello, descrivi_errore
from .config import FUSO_ORARIO
from .radio import Radio
from .sveglia import Sveglia

MAX_PAUSA_MINUTI = 8 * 60  # otto ore: oltre, BMO resterebbe sordo per sbaglio

# Un sì o un no si dicono in meno di due secondi: otto bastano e avanzano
# anche a chi esita (#17). Non c'è un VAD reale a tagliare corto: si registra
# per tutta la durata e si classifica dopo.
DURATA_ASCOLTO_CONFERMA_S = 8.0


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
        orologio: Callable[[], datetime] | None = None,
    ) -> None:
        self.cervello = cervello
        self.faccia = faccia or crea_faccia()
        self.richiamo = richiamo
        self.voce = voce
        self.durata_ascolto_s = durata_ascolto_s
        self.orologio = orologio or (lambda: datetime.now(FUSO_ORARIO))
        self.stato = Stato.ATTESA
        self.pausa_fino_a: datetime | None = None
        # La pausa la sa solo la macchina: il cervello si limita a chiamare
        # lo strumento quando il modello lo chiede.
        cervello.registra_strumento("metti_in_pausa_l_ascolto", self.metti_in_pausa)

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

    # --- sotto-dialogo di conferma (#17) --------------------------------------

    def chiedi_conferma(self, domanda: str) -> bool | None:
        """Proponi/conferma a voce, senza richiedere di nuovo il richiamo.

        Nato dalla #14 (memoria persistente): nessuna scrittura deve avvenire
        in silenzio. Oggi non ha ancora un chiamante concreto — arriverà con
        la #14.2 — ma è pensato per essere riusabile per qualunque azione che
        meriti una conferma esplicita, come chiede l'issue #17.

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
        audio = self.cervello.ascolta(DURATA_ASCOLTO_CONFERMA_S)
        return self.cervello.classifica_risposta(audio)

    # --- gli stati -----------------------------------------------------------

    def _vai(self, stato: Stato, faccia: str) -> None:
        # Prima la faccia, poi l'azione: il piano chiede che il passaggio si
        # veda entro 150 ms, e un'azione lenta non deve ritardarlo.
        self.stato = stato
        self.faccia.mostra(faccia)

    def turno(self) -> None:
        """Un giro completo: ascolta, pensa, risponde."""
        self._vai(Stato.ASCOLTO, STATO_ASCOLTO)
        audio = self.cervello.ascolta(self.durata_ascolto_s)
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
    parser.add_argument("--durata", type=float, default=DURATA_ASCOLTO_S, help="secondi di ascolto")
    parser.add_argument("--senza-timer", action="store_true", help="non far partire la sveglia dei timer")
    parser.add_argument("--senza-radio", action="store_true", help="non collegare radio e volume")
    argomenti = parser.parse_args()

    faccia = crea_faccia(sul_terminale=True)
    cervello = Cervello(faccia=faccia)
    macchina = Macchina(cervello=cervello, faccia=faccia, durata_ascolto_s=argomenti.durata)
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
