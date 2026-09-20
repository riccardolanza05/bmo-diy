"""Facce provvisorie, finche' non c'e' quella vera.

Il disegno della faccia (occhi, bocca, animazioni) e' l'issue #23 e girera'
in un processo a parte, `bmo-face`. Qui ci sono solo le due implementazioni
che servono adesso: una muta, per i test e per chi non ha uno schermo, e una
che scrive lo stato sul terminale, cosi' durante le prove a voce si vede
quando BMO sta elaborando invece di restare in un silenzio indistinguibile
da un blocco.
"""
from __future__ import annotations

import sys
from typing import TextIO


class FacciaMuta:
    """Non mostra niente. E' la predefinita: nessuno schermo, nessun rumore nei test."""

    def mostra(self, stato: str) -> None:
        del stato  # la faccia vera (#23) non c'e' ancora: non c'e' niente da mostrare


class FacciaTerminale:
    """Scrive lo stato sul terminale, l'unico "schermo" che c'e' oggi sul PC.

    Va sullo standard error per non sporcare la risposta di BMO, che e'
    l'uscita utile dei comandi `brain` e `prova_frasi`.
    """

    def __init__(self, uscita: TextIO | None = None) -> None:
        self.uscita = uscita if uscita is not None else sys.stderr

    def mostra(self, stato: str) -> None:
        print(f"[faccia: {stato}]", file=self.uscita, flush=True)
