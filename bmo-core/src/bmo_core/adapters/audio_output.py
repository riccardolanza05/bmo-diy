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

    def ferma(self) -> None:
        if self._processo is not None and self._processo.poll() is None:
            self._processo.terminate()
            self._processo.wait(timeout=5)
        self._processo = None
