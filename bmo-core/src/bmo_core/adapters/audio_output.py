"""Adapter uscita audio: mpv, identico su PC di sviluppo e su Pi."""
from __future__ import annotations

import subprocess
from pathlib import Path


class MpvAdapter:
    """Riproduzione via mpv.

    Nessuna differenza hardware da astrarre qui: mpv gira nativo e
    identico sia sul PC di sviluppo (omarchy/Linux) sia sul Pi.
    """

    def __init__(self) -> None:
        self._processo: subprocess.Popen | None = None

    def riproduci(self, sorgente: Path | str) -> None:
        self.ferma()
        self._processo = subprocess.Popen(
            ["mpv", "--no-video", "--really-quiet", str(sorgente)],
        )

    def attendi(self, timeout_s: float | None = None) -> None:
        """Aspetta che la riproduzione finisca da sola.

        `riproduci` non blocca: lancia mpv e torna subito, che è giusto per un
        tono o una clip che parte e si dimentica. Per la **voce** (#42) serve
        l'opposto: se chi parla non aspetta, la riga dopo della macchina a
        stati fa ripartire l'ascolto o suona qualcos'altro, e `riproduci`
        comincia uccidendo il processo precedente — cioè taglia BMO a
        metà frase.

        Senza `timeout_s` aspetta quanto serve. Con un timeout scaduto non
        solleva: torna e basta, lasciando mpv a finire per conto suo, perché
        un'attesa troppo lunga non deve diventare un BMO bloccato.
        """
        if self._processo is None:
            return
        try:
            self._processo.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass

    def ferma(self) -> None:
        if self._processo is not None and self._processo.poll() is None:
            self._processo.terminate()
            self._processo.wait(timeout=5)
        self._processo = None
