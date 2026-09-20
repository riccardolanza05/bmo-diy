"""Timer che sopravvivono al riavvio (issue #20).

Il piano (§2.4) chiama i timer «la funzione col costo di errore piu' alto» e
detta tre regole, che sono i tre motivi per cui questo modulo esiste:

1. si salva la **scadenza assoluta**, mai i secondi rimanenti: un timer di
   dieci minuti messo alle 20:00 scade alle 20:10 anche se BMO nel frattempo
   e' stato spento cinque minuti;
2. il file si riscrive con un temporaneo piu' `rename`, che e' atomico: se
   manca la corrente a meta' scrittura si ritrova il file vecchio, intero, e
   non mezzo file illeggibile;
3. un timer scaduto mentre BMO era spento suona lo stesso, con un messaggio
   diverso (quello lo fa `sveglia.py`).

Ci sono due processi che toccano lo stesso file: il cervello che aggiunge e
annulla, e la sveglia che toglie quelli scaduti. Senza un lock si perdono
timer in silenzio — la sveglia legge la lista, il cervello ne aggiunge uno,
la sveglia riscrive la lista che aveva letto e il timer nuovo sparisce. Ogni
operazione qui dentro prende quindi un lock esclusivo (`flock`) su un file
affiancato, e il difetto peggiore possibile — un timer che non suona — non
puo' capitare.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator

from .config import FUSO_ORARIO, percorso_dati

NOME_FILE = "timers.json"


@dataclass
class Timer:
    etichetta: str
    scadenza: datetime


class ArchivioTimer:
    """I timer su disco. Ogni operazione legge, modifica e riscrive sotto lock."""

    def __init__(
        self,
        percorso: Path | None = None,
        orologio: Callable[[], datetime] | None = None,
    ) -> None:
        # Il percorso si risolve qui e non nella firma: un valore predefinito
        # nella firma verrebbe calcolato all'importazione del modulo, prima
        # che i test possano spostare la cartella con BMO_DATI.
        self.percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
        self.orologio = orologio or (lambda: datetime.now(FUSO_ORARIO))

    # --- lettura e scrittura -------------------------------------------------

    @contextmanager
    def _in_esclusiva(self) -> Iterator[None]:
        """Sezione critica fra processi diversi.

        Il lock sta su un file affiancato e non su `timers.json`, perche'
        quello viene sostituito da `rename` a ogni scrittura: un lock preso
        sul file sostituito non fermerebbe piu' nessuno.
        """
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        with open(self.percorso.with_suffix(".lock"), "w") as guardia:
            fcntl.flock(guardia, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(guardia, fcntl.LOCK_UN)

    def _leggi(self) -> list[Timer]:
        try:
            righe = json.loads(self.percorso.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Meglio senza timer che morto: il file rotto si mette da parte
            # (resta li' da guardare) e si riparte da una lista vuota.
            rotto = self.percorso.with_suffix(".rotto")
            self.percorso.replace(rotto)
            print(f"timers.json illeggibile, spostato in {rotto}", file=sys.stderr)
            return []
        timer = []
        for riga in righe if isinstance(righe, list) else []:
            try:
                timer.append(Timer(str(riga["etichetta"]), datetime.fromisoformat(riga["scadenza"])))
            except (TypeError, KeyError, ValueError):
                continue  # una riga sola malformata non butta via le altre
        return timer

    def _scrivi(self, timer: list[Timer]) -> None:
        righe = [{"etichetta": t.etichetta, "scadenza": t.scadenza.isoformat()} for t in timer]
        # Il temporaneo sta nella stessa cartella, altrimenti `rename` non e'
        # atomico: fra due filesystem diventa una copia.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.percorso.parent, prefix=".timers-", delete=False
        ) as file:
            json.dump(righe, file, ensure_ascii=False, indent=1)
            file.flush()
            os.fsync(file.fileno())
            temporaneo = Path(file.name)
        temporaneo.replace(self.percorso)

    # --- operazioni ----------------------------------------------------------

    def tutti(self) -> list[Timer]:
        with self._in_esclusiva():
            return self._leggi()

    def attivi(self) -> list[Timer]:
        """Quelli che devono ancora scadere, dal primo che suona."""
        adesso = self.orologio()
        return sorted((t for t in self.tutti() if t.scadenza > adesso), key=lambda t: t.scadenza)

    def aggiungi(self, etichetta: str, durata_s: float) -> Timer:
        nuovo = Timer(etichetta, self.orologio() + timedelta(seconds=durata_s))
        with self._in_esclusiva():
            timer = self._leggi()
            timer.append(nuovo)
            self._scrivi(timer)
        return nuovo

    def annulla(self, etichetta: str | None = None) -> int:
        """Toglie i timer con quell'etichetta, o tutti se non e' indicata."""
        with self._in_esclusiva():
            timer = self._leggi()
            if etichetta:
                restano = [t for t in timer if t.etichetta.lower() != etichetta.lower()]
            else:
                restano = []
            if len(restano) != len(timer):
                self._scrivi(restano)
            return len(timer) - len(restano)

    def preleva_scaduti(self) -> list[Timer]:
        """Restituisce i timer scaduti e li toglie dal file, in un colpo solo.

        Prelevare e togliere devono stare nello stesso lock: se un timer
        restasse nel file dopo essere suonato, suonerebbe di nuovo al giro
        dopo, e non c'e' niente di peggio di un timer che non smette.
        """
        adesso = self.orologio()
        with self._in_esclusiva():
            timer = self._leggi()
            scaduti = [t for t in timer if t.scadenza <= adesso]
            if scaduti:
                self._scrivi([t for t in timer if t.scadenza > adesso])
        return sorted(scaduti, key=lambda t: t.scadenza)

    def sostituisci(self, timer: list[Timer]) -> None:
        """Riscrive tutto l'elenco: serve a preparare uno stato noto nelle prove."""
        with self._in_esclusiva():
            self._scrivi(list(timer))
