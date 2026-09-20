"""Punto unico in cui bmo-core sceglie quale implementazione di adapter usare.

Il resto del codice importa solo da qui (o dai Protocol in base.py), mai
le classi concrete direttamente: e' questo il confine che rende possibile
sviluppare sul PC (omarchy) e spostarsi sul Pi cambiando solo questo file.
"""
from __future__ import annotations

from ..config import Ambiente, rileva_ambiente
from .audio_input import ArecordAdapter
from .audio_output import MpvAdapter
from .base import AudioInputAdapter, AudioOutputAdapter, CameraAdapter, FacciaAdapter
from .camera import LibcameraAdapter, WebcamV4L2Adapter
from .faccia import FacciaMuta, FacciaTerminale


def crea_camera(ambiente: Ambiente | None = None) -> CameraAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        return LibcameraAdapter()
    return WebcamV4L2Adapter()


def crea_audio_input(ambiente: Ambiente | None = None) -> AudioInputAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        return ArecordAdapter(dispositivo="hw:0,0", formato="S32_LE")
    # Sul PC si registra gia' nel formato che va a Gemini (§2.1: WAV 16 kHz
    # mono): ~96 kB per 3 s invece di ~1,1 MB a 48 kHz stereo 32 bit.
    return ArecordAdapter(dispositivo="default", frequenza=16000, canali=1, formato="S16_LE")


def crea_faccia(ambiente: Ambiente | None = None, sul_terminale: bool = False) -> FacciaAdapter:
    """La faccia di BMO.

    Finche' la #23 non la disegna davvero non c'e' niente da accendere in
    nessuno dei due ambienti, quindi la predefinita e' muta. `sul_terminale`
    la fa scrivere sullo standard error: serve alle prove sul PC, dove
    altrimenti non si vede che BMO sta elaborando.
    """
    del ambiente  # la faccia vera non dipende ancora dall'hardware
    return FacciaTerminale() if sul_terminale else FacciaMuta()


def crea_audio_output(ambiente: Ambiente | None = None) -> AudioOutputAdapter:
    del ambiente  # mpv è identico in entrambi gli ambienti
    return MpvAdapter()
