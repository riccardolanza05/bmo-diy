"""Interfacce (Protocol) che ogni adapter hardware deve rispettare.

bmo-core parla solo con queste interfacce: la scelta dell'implementazione
concreta (PC di sviluppo vs Raspberry Pi) avviene in un unico punto
(factory.py), cosi' il resto del codice non sa mai su quale hardware gira.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Protocol


class CameraAdapter(Protocol):
    """Cattura una singola foto e la scrive su disco come JPEG."""

    def scatta_foto(self, destinazione: Path) -> Path: ...


class AudioInputAdapter(Protocol):
    """Ingresso microfono.

    flusso_pcm() serve alla wake word (ascolto continuo); registra() serve
    alla cattura del comando vocale a durata fissa dopo il risveglio.
    """

    def flusso_pcm(self) -> Iterator[bytes]: ...

    def registra(self, destinazione: Path, durata_s: float) -> Path: ...


class AudioOutputAdapter(Protocol):
    """Riproduzione audio (voce TTS e musica)."""

    def riproduci(self, sorgente: Path | str) -> None: ...

    def ferma(self) -> None: ...
