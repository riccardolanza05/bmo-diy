"""Quanti pixel *reali* dello schermo di sviluppo servono per mostrare la
faccia alle dimensioni fisiche vere del pannello (criterio b, issue #23).

Tutto qui è puro calcolo, testabile senza un display: `finestra.py` è l'unico
posto che lo collega a GTK e a uno schermo vero.
"""
from __future__ import annotations

import json
import shutil
import subprocess

# Preset noti dal BOM del piano (§1.3, issue #1): millimetri reali del
# pannello, non solo la diagonale in pollici — sono due numeri diversi e il
# secondo è quello che conta per questa prova. Nessun pannello più piccolo
# (il "caso peggiore" citato nella #23) è ancora nel BOM: chi lo misura passa
# --mm-larghezza/--mm-altezza a mano invece di aggiungerne uno qui a caso.
PRESET_PANNELLI: dict[str, tuple[float, float]] = {
    "2.4": (48.96, 36.72),  # Waveshare 2.4" ILI9341 240×320 ruotato (piano §1.3)
    "3.5": (73.0, 48.7),  # ILI9488 320×480 ruotato, stima da datasheet standard del formato
}


def pitch_schermo_mm(nome_monitor: str | None = None) -> tuple[float, float] | None:
    """(mm/px orizzontale, mm/px verticale) del monitor Hyprland scelto.

    `None` se `hyprctl` manca, fallisce, o non gira sotto Hyprland (un'altra
    macchina, un altro window manager): mai un'eccezione per un dato che è
    solo "non disponibile qui", come il resto del progetto tratta un file di
    configurazione mancante.
    """
    if shutil.which("hyprctl") is None:
        return None
    try:
        grezzo = subprocess.run(
            ["hyprctl", "monitors", "-j"], capture_output=True, check=True, timeout=2
        ).stdout
        monitor = json.loads(grezzo)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(monitor, list) or not monitor:
        return None
    scelto = None
    if nome_monitor:
        scelto = next((m for m in monitor if m.get("name") == nome_monitor), None)
    else:
        scelto = next((m for m in monitor if m.get("focused")), monitor[0])
    if not scelto:
        return None
    largh, alt = scelto.get("physicalWidth"), scelto.get("physicalHeight")
    px_largh, px_alt = scelto.get("width"), scelto.get("height")
    if not largh or not alt or not px_largh or not px_alt:
        return None
    return largh / px_largh, alt / px_alt


def px_per_dimensione_fisica(
    mm_larghezza: float, mm_altezza: float, pitch: tuple[float, float]
) -> tuple[int, int]:
    """Quanti pixel *dello schermo di sviluppo* occupano (mm_larghezza × mm_altezza) mm."""
    pitch_x, pitch_y = pitch
    return max(1, round(mm_larghezza / pitch_x)), max(1, round(mm_altezza / pitch_y))


def e_sottocampionato(host_px: tuple[int, int], pannello_px: tuple[int, int]) -> bool:
    """True se lo schermo di sviluppo ha un pitch più grosso del pannello target.

    In quel caso i pixel richiesti per l'ingombro fisico vero sono MENO della
    risoluzione nativa del pannello (es. meno di 320×240): la finestra deve
    ridurre l'immagine, perdendo nitidezza che il pannello vero non perderebbe
    mai (i suoi pixel sono fisicamente quella dimensione, non un'approssimazione
    su un monitor più grossolano). La prova è quindi più severa del display
    reale, mai più ottimista — un avviso, non un errore.
    """
    return host_px[0] < pannello_px[0] or host_px[1] < pannello_px[1]
