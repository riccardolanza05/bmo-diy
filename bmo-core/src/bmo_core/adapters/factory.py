"""Punto unico in cui bmo-core sceglie quale implementazione di adapter usare.

Il resto del codice importa solo da qui (o dai Protocol in base.py), mai
le classi concrete direttamente: e' questo il confine che rende possibile
sviluppare sul PC (omarchy) e spostarsi sul Pi cambiando solo questo file.
"""
from __future__ import annotations

from ..config import Ambiente, rileva_ambiente
from .audio_input import ArecordAdapter
from .audio_output import MpvAdapter
from .base import AudioInputAdapter, AudioOutputAdapter, CameraAdapter
from .camera import LibcameraAdapter, WebcamV4L2Adapter


def crea_camera(ambiente: Ambiente | None = None) -> CameraAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        return LibcameraAdapter()
    return WebcamV4L2Adapter()


def crea_audio_input(ambiente: Ambiente | None = None) -> AudioInputAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        return ArecordAdapter(dispositivo="hw:0,0", formato="S32_LE")
    return ArecordAdapter(dispositivo="default")


def crea_audio_output(ambiente: Ambiente | None = None) -> AudioOutputAdapter:
    del ambiente  # mpv è identico in entrambi gli ambienti
    return MpvAdapter()
