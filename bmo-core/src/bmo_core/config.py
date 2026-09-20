"""Rilevamento dell'ambiente di esecuzione: PC di sviluppo (Linux) o Raspberry Pi.

Entrambi gli ambienti sono Linux, quindi la distinzione non si basa sul
sistema operativo ma sulla presenza del device-tree del Raspberry Pi.

Qui sta anche il fuso orario di casa e la cartella in cui BMO tiene quello
che deve sopravvivere a un riavvio (per ora i timer, issue #20).
"""
from __future__ import annotations

import os
import platform
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

FUSO_ORARIO = ZoneInfo("Europe/Rome")


class Ambiente(str, Enum):
    DEV_LINUX = "dev-linux"
    PI = "pi"


_DEVICE_TREE_MODEL = Path("/proc/device-tree/model")


def rileva_ambiente() -> Ambiente:
    """Determina l'ambiente corrente.

    Priorita': variabile d'ambiente BMO_ENV, poi rilevamento automatico
    (device-tree del Raspberry Pi -> pi, qualunque altro Linux -> dev-linux).
    """
    forzato = os.environ.get("BMO_ENV")
    if forzato:
        try:
            return Ambiente(forzato)
        except ValueError as errore:
            valori = ", ".join(a.value for a in Ambiente)
            raise ValueError(
                f"BMO_ENV={forzato!r} non valido, valori ammessi: {valori}"
            ) from errore

    if _DEVICE_TREE_MODEL.exists():
        modello = _DEVICE_TREE_MODEL.read_text(errors="ignore")
        if "Raspberry Pi" in modello:
            return Ambiente.PI

    if platform.system() == "Linux":
        return Ambiente.DEV_LINUX

    raise RuntimeError(
        "Impossibile rilevare l'ambiente automaticamente: imposta BMO_ENV=dev-linux o BMO_ENV=pi"
    )


def percorso_dati(ambiente: Ambiente | None = None) -> Path:
    """Cartella dei dati che devono sopravvivere a un riavvio.

    Sul Pi e' `/var/lib/bmo`, come il piano (§2.4), perche' li' BMO e' un
    servizio di sistema. Sul PC di sviluppo scriverci vorrebbe i permessi di
    root, quindi si usa la cartella di stato dell'utente. `BMO_DATI` ha la
    precedenza su tutto: serve ai test, che non devono mai scrivere nella
    cartella vera.
    """
    forzato = os.environ.get("BMO_DATI")
    if forzato:
        return Path(forzato)
    if (ambiente or rileva_ambiente()) is Ambiente.PI:
        return Path("/var/lib/bmo")
    stato = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(stato) / "bmo"
