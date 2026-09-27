"""L'inviluppo RMS della voce sintetizzata, per la bocca di BMO (#23, §2.2).

`tts.sintetizza()` scrive un file audio prima di suonarlo (`VoceTts.__call__`,
macchina.py): questo modulo lo rilegge e calcola quanto è "forte" ogni
pezzetto da 1/25 di secondo, il numero che manda al comando socket `speak`
perché `bmo-face` sappia quanto aprire la bocca, invece di farla scorrere a
caso o restare ferma.

Passa da `ffmpeg` invece che da un decoder Python: è già una dipendenza
richiesta dal progetto (README, verifiche sul PC di sviluppo, serve anche a
`mpv`), e decodifica sia i `.wav` di Gemini sia gli `.mp3` di edge-tts (#42)
con lo stesso comando, senza dover distinguere il formato qui.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

FREQUENZA_DECODIFICA_HZ = 16000
FPS_PREDEFINITO = 25.0


def inviluppo_rms(percorso: Path, fps: float = FPS_PREDEFINITO) -> list[float]:
    """L'inviluppo RMS di `percorso`, normalizzato al proprio picco (0-1).

    Normalizzare sul picco *di questa battuta* (non su una soglia fissa)
    tiene la bocca leggibile qualunque sia il volume della sintesi: edge-tts
    e Gemini TTS non garantiscono lo stesso livello, e una soglia fissa
    lascerebbe la bocca quasi chiusa per l'una o sempre spalancata per l'altra.

    Lista vuota se `ffmpeg` manca o il file non si decodifica: una bocca
    ferma è un difetto cosmetico, non deve mai far fallire il turno che ha
    già prodotto la risposta e sta per pronunciarla.
    """
    comando = [
        "ffmpeg",
        "-v", "error",
        "-i", str(percorso),
        "-f", "s16le",
        "-ac", "1",
        "-ar", str(FREQUENZA_DECODIFICA_HZ),
        "-",
    ]
    try:
        grezzo = subprocess.run(comando, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    if len(grezzo) < 2:
        return []
    campioni = np.frombuffer(grezzo, dtype="<i2").astype(np.float64)
    per_fotogramma = max(1, round(FREQUENZA_DECODIFICA_HZ / fps))
    n_fotogrammi = len(campioni) // per_fotogramma
    if n_fotogrammi == 0:
        return []
    tagliati = campioni[: n_fotogrammi * per_fotogramma].reshape(n_fotogrammi, per_fotogramma)
    rms = np.sqrt(np.mean(tagliati**2, axis=1))
    picco = rms.max()
    if picco <= 0:
        return [0.0] * n_fotogrammi
    return (rms / picco).tolist()
