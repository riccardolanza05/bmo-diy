"""Il volume dell'altoparlante.

Non e' il volume del lettore musicale: riguarda tutto quello che BMO emette,
voce e clip comprese, perche' "abbassa il volume" detto a un BMO che parla
troppo forte non riguarda la musica. Due implementazioni, come per gli altri
adapter: PipeWire sul PC di sviluppo, ALSA sul Pi, dove non c'e' un server
audio ma la scheda del HAT.
"""
from __future__ import annotations

import re
import subprocess

_USCITA_PREDEFINITA = "@DEFAULT_AUDIO_SINK@"


def _esegui(comando: list[str]) -> str | None:
    try:
        finito = subprocess.run(comando, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return finito.stdout if finito.returncode == 0 else None


class VolumePipeWire:
    """`wpctl`, il controllo di PipeWire: e' quello che gira su omarchy."""

    def imposta(self, percentuale: int) -> None:
        _esegui(["wpctl", "set-volume", _USCITA_PREDEFINITA, f"{int(percentuale)}%"])

    def leggi(self) -> int | None:
        uscita = _esegui(["wpctl", "get-volume", _USCITA_PREDEFINITA])
        # "Volume: 0.60" oppure "Volume: 0.60 [MUTED]"
        trovato = re.search(r"([\d.]+)", uscita or "")
        return round(float(trovato.group(1)) * 100) if trovato else None


class VolumeAlsa:
    """`amixer`, per il Pi con la scheda del HAT e senza server audio."""

    def __init__(self, controllo: str = "Master") -> None:
        self.controllo = controllo

    def imposta(self, percentuale: int) -> None:
        _esegui(["amixer", "-q", "sset", self.controllo, f"{int(percentuale)}%"])

    def leggi(self) -> int | None:
        uscita = _esegui(["amixer", "sget", self.controllo])
        trovato = re.search(r"\[(\d+)%\]", uscita or "")
        return int(trovato.group(1)) if trovato else None
