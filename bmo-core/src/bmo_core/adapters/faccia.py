"""Facce provvisorie, e la faccia vera come processo a parte (issue #23).

Il disegno della faccia (occhi, bocca, animazioni) gira in `bmo-face`, un
pacchetto a se' (isolamento dei guasti, §2.2: se bmo-core va in eccezione,
la faccia continua a sbattere le palpebre). Qui ci sono le implementazioni
che bmo-core usa per parlarci: una muta, per i test e per chi non ha uno
schermo, una che scrive lo stato sul terminale per le prove a voce, e
`FacciaSocket`, il client vero del socket Unix (§2.2) verso `bmo-face`.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import TextIO


class FacciaMuta:
    """Non mostra niente. E' la predefinita: nessuno schermo, nessun rumore nei test."""

    def mostra(self, stato: str) -> None:
        del stato

    def esprimi(self, espressione: str, ttl: float = 3.0) -> None:
        del espressione, ttl

    def livello(self, valore: float) -> None:
        del valore

    def parla(self, inviluppo: list[float], fps: float = 25.0) -> None:
        del inviluppo, fps

    def timer(self, rimanente: int, etichetta: str | None = None) -> None:
        del rimanente, etichetta


class FacciaTerminale:
    """Scrive lo stato sul terminale, l'unico "schermo" che c'e' oggi sul PC
    quando non gira anche `bmo-face` (vedi `FacciaSocket` per quello).

    Va sullo standard error per non sporcare la risposta di BMO, che e'
    l'uscita utile dei comandi `brain` e `prova_frasi`.
    """

    def __init__(self, uscita: TextIO | None = None) -> None:
        self.uscita = uscita if uscita is not None else sys.stderr

    def mostra(self, stato: str) -> None:
        print(f"[faccia: {stato}]", file=self.uscita, flush=True)

    def esprimi(self, espressione: str, ttl: float = 3.0) -> None:
        print(f"[faccia: espressione {espressione} per {ttl:g}s]", file=self.uscita, flush=True)

    def livello(self, valore: float) -> None:
        del valore  # troppo frequente per il terminale: sporcherebbe l'uscita a ogni fotogramma

    def parla(self, inviluppo: list[float], fps: float = 25.0) -> None:
        print(f"[faccia: parla, {len(inviluppo)} campioni a {fps:g} fps]", file=self.uscita, flush=True)

    def timer(self, rimanente: int, etichetta: str | None = None) -> None:
        del rimanente, etichetta  # idem: la sveglia (timer.py) lo stampa gia' per conto suo


class FacciaSocket:
    """Il client vero del socket Unix verso `bmo-face` (§2.2, issue #23).

    Una sola connessione persistente, riaperta se cade: bmo-face puo' essere
    riavviato mentre bmo-core resta acceso (isolamento dei guasti), quindi
    ogni scrittura che fallisce prova a riconnettersi una volta prima di
    arrendersi in silenzio — una faccia muta perche' bmo-face non gira ancora
    non deve mai far fallire il turno di conversazione.
    """

    def __init__(self, percorso: Path) -> None:
        self.percorso = percorso
        self._socket: socket.socket | None = None

    def _connetti(self) -> socket.socket | None:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(str(self.percorso))
            return s
        except OSError:
            return None

    def _manda(self, messaggio: dict) -> None:
        riga = (json.dumps(messaggio) + "\n").encode("utf-8")
        if self._socket is None:
            self._socket = self._connetti()
        if self._socket is None:
            return
        try:
            self._socket.sendall(riga)
        except OSError:
            self._socket = None
            nuovo = self._connetti()
            if nuovo is None:
                return
            try:
                nuovo.sendall(riga)
                self._socket = nuovo
            except OSError:
                pass

    def mostra(self, stato: str) -> None:
        self._manda({"cmd": "state", "value": stato})

    def esprimi(self, espressione: str, ttl: float = 3.0) -> None:
        self._manda({"cmd": "expression", "value": espressione, "ttl": ttl})

    def livello(self, valore: float) -> None:
        self._manda({"cmd": "level", "value": valore})

    def parla(self, inviluppo: list[float], fps: float = 25.0) -> None:
        self._manda({"cmd": "speak", "envelope": inviluppo, "fps": fps})

    def timer(self, rimanente: int, etichetta: str | None = None) -> None:
        self._manda({"cmd": "timer", "remaining": rimanente, "label": etichetta})
