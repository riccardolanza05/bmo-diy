"""Adapter fotocamera: libcamera-still sul Pi, webcam V4L2 sul PC di sviluppo."""
from __future__ import annotations

import subprocess
from pathlib import Path


class LibcameraAdapter:
    """Raspberry Pi + modulo camera CSI (OV5647), via libcamera-still.

    Comando di riferimento: docs/02-piano-attuale.md, Fase 5.
    """

    def __init__(
        self,
        larghezza: int = 640,
        altezza: int = 480,
        qualita: int = 75,
        timeout_ms: int = 800,
    ) -> None:
        self.larghezza = larghezza
        self.altezza = altezza
        self.qualita = qualita
        self.timeout_ms = timeout_ms

    def scatta_foto(self, destinazione: Path) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "libcamera-still",
                "-o", str(destinazione),
                "--width", str(self.larghezza),
                "--height", str(self.altezza),
                "-q", str(self.qualita),
                "-n",
                "-t", str(self.timeout_ms),
            ],
            check=True,
        )
        return destinazione


class WebcamV4L2Adapter:
    """Webcam del PC di sviluppo (omarchy/Linux), via ffmpeg + V4L2.

    `dispositivo` va verificato sulla macchina reale con `v4l2-ctl --list-devices`
    (di solito /dev/video0, ma non è garantito se ci sono più device video).
    """

    def __init__(
        self,
        dispositivo: str = "/dev/video0",
        larghezza: int = 640,
        altezza: int = 480,
    ) -> None:
        self.dispositivo = dispositivo
        self.larghezza = larghezza
        self.altezza = altezza

    def scatta_foto(self, destinazione: Path) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "v4l2",
                "-video_size", f"{self.larghezza}x{self.altezza}",
                "-i", self.dispositivo,
                "-frames:v", "1",
                str(destinazione),
            ],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        return destinazione
