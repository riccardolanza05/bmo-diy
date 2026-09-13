"""Adapter ingresso microfono: ALSA (arecord) su entrambi gli ambienti.

Sia il Pi (HAT WM8960) sia il PC di sviluppo (omarchy/Linux, ALSA o
PipeWire con compatibilita' ALSA) espongono `arecord`: cambia solo il
device. Va verificato sulla macchina reale con `arecord -l`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

CHUNK_BYTES = 4096


class ArecordAdapter:
    """Cattura microfono via `arecord`.

    Parametri di riferimento per il Pi: docs/02-piano-attuale.md §2.3
    (S32_LE, 48kHz, stereo, device hw:0,0).
    """

    def __init__(
        self,
        dispositivo: str = "default",
        frequenza: int = 48000,
        canali: int = 2,
        formato: str = "S32_LE",
    ) -> None:
        self.dispositivo = dispositivo
        self.frequenza = frequenza
        self.canali = canali
        self.formato = formato

    def _comando_base(self) -> list[str]:
        return [
            "arecord",
            "-D", self.dispositivo,
            "-f", self.formato,
            "-r", str(self.frequenza),
            "-c", str(self.canali),
        ]

    def flusso_pcm(self) -> Iterator[bytes]:
        processo = subprocess.Popen(
            self._comando_base() + ["-t", "raw", "-"],
            stdout=subprocess.PIPE,
        )
        assert processo.stdout is not None
        try:
            while True:
                dati = processo.stdout.read(CHUNK_BYTES)
                if not dati:
                    break
                yield dati
        finally:
            processo.terminate()

    def registra(self, destinazione: Path, durata_s: float) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            self._comando_base() + ["-d", str(durata_s), str(destinazione)],
            check=True,
        )
        return destinazione
