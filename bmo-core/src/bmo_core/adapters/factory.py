"""Punto unico in cui bmo-core sceglie quale implementazione di adapter usare.

Il resto del codice importa solo da qui (o dai Protocol in base.py), mai
le classi concrete direttamente: e' questo il confine che rende possibile
sviluppare sul PC (omarchy) e spostarsi sul Pi cambiando solo questo file.
"""
from __future__ import annotations

import os

from ..config import Ambiente, percorso_socket, rileva_ambiente
from .audio_input import ArecordAdapter, ArecordConvertitoreAdapter
from .audio_output import MpvAdapter
from .base import (
    AudioInputAdapter,
    AudioOutputAdapter,
    CameraAdapter,
    FacciaAdapter,
    LettoreAdapter,
    PulsanteAdapter,
    VolumeAdapter,
)
from .camera import LibcameraAdapter, WebcamV4L2Adapter
from .faccia import FacciaMuta, FacciaSocket, FacciaTerminale
from .lettore import LettoreMpv
from .pulsante import PulsanteAssente, PulsanteGpio
from .volume import VolumeAlsa, VolumePipeWire


def crea_camera(ambiente: Ambiente | None = None) -> CameraAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        return LibcameraAdapter()
    return WebcamV4L2Adapter()


def crea_audio_input(ambiente: Ambiente | None = None) -> AudioInputAdapter:
    ambiente = ambiente or rileva_ambiente()
    if ambiente is Ambiente.PI:
        # Il microfono del Pi (jack o HAT WM8960) registra nativamente a
        # S32_LE stereo 48 kHz; VAD e wake word vogliono S16_LE mono 16 kHz
        # (issue #64) — ArecordConvertitoreAdapter converte al volo.
        # `BMO_AUDIO_DISPOSITIVO` per cambiare device senza toccare il
        # codice (es. quando arriva il HAT e non è più hw:0,0).
        dispositivo = os.environ.get("BMO_AUDIO_DISPOSITIVO", "hw:0,0")
        return ArecordConvertitoreAdapter(dispositivo=dispositivo)
    # Sul PC si registra gia' nel formato che va a Gemini (§2.1: WAV 16 kHz
    # mono): ~96 kB per 3 s invece di ~1,1 MB a 48 kHz stereo 32 bit.
    return ArecordAdapter(dispositivo="default", frequenza=16000, canali=1, formato="S16_LE")


def crea_faccia(ambiente: Ambiente | None = None, sul_terminale: bool = False) -> FacciaAdapter:
    """La faccia di BMO.

    `BMO_FACCIA=socket` la collega a `bmo-face` (issue #23) sul socket Unix
    di `percorso_socket()`: e' un opt-in esplicito, non la predefinita,
    perche' bmo-face e' un processo a parte che deve essere avviato a mano
    (`python -m bmo_face.finestra`, §2.2) — senza, `FacciaSocket` scriverebbe
    a vuoto in silenzio (fallisce in silenzio di proposito, vedi la classe).
    Senza quella variabile, `sul_terminale` sceglie fra le due implementazioni
    provvisorie di prima: muta, o sullo standard error per le prove sul PC.
    """
    if os.environ.get("BMO_FACCIA") == "socket":
        return FacciaSocket(percorso_socket(ambiente))
    del ambiente  # le due implementazioni provvisorie non dipendono dall'hardware
    return FacciaTerminale() if sul_terminale else FacciaMuta()


def crea_audio_output(ambiente: Ambiente | None = None) -> AudioOutputAdapter:
    del ambiente  # mpv è identico in entrambi gli ambienti
    return MpvAdapter()


def crea_lettore(ambiente: Ambiente | None = None) -> LettoreAdapter:
    del ambiente  # anche qui mpv è lo stesso: cambia solo dove sta il socket
    return LettoreMpv()


def crea_volume(ambiente: Ambiente | None = None) -> VolumeAdapter:
    """Sul PC c'è PipeWire, sul Pi la scheda del HAT senza server audio."""
    ambiente = ambiente or rileva_ambiente()
    return VolumeAlsa() if ambiente is Ambiente.PI else VolumePipeWire()


def crea_pulsante(ambiente: Ambiente | None = None) -> PulsanteAdapter:
    """Il pulsante extra del HAT audio (issue #70), o nessun pulsante.

    `BMO_PULSANTE_PIN` sceglie il pin BCM senza toccare il codice, come
    `BMO_AUDIO_DISPOSITIVO` per il microfono. **Senza quella variabile
    resta `PulsanteAssente` anche sul Pi**: il pin del bottone extra non è
    ancora stato tracciato (scheda comprata usata, cablaggio non di
    serie), e indovinarne uno a caso rischierebbe di leggere un pin già
    usato per altro.
    """
    ambiente = ambiente or rileva_ambiente()
    pin = os.environ.get("BMO_PULSANTE_PIN")
    if ambiente is Ambiente.PI and pin is not None:
        return PulsanteGpio(int(pin))
    return PulsanteAssente()
