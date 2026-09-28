"""`RilevatoreLeggero` deve dare gli stessi punteggi di `openwakeword.Model` (#58)."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from bmo_core.wake_word import CAMPIONI_PER_PEZZO, RilevatoreLeggero, percorso_modello

pytest.importorskip("onnxruntime")
pytest.importorskip("openwakeword")

MODELLI = [str(Path(__file__).resolve().parents[1] / "modelli-wake-word" / f"bmo{i}.onnx") for i in (1, 2)]


def _audio_di_prova(secondi: float = 20.0) -> np.ndarray:
    """Silenzio, rumore, toni e sillabe finte: abbastanza vario da muovere i punteggi."""
    generatore = np.random.default_rng(58)
    t = np.arange(int(secondi * 16000)) / 16000
    segnale = 0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    segnale += 0.2 * np.sin(2 * np.pi * 660 * t * (1 + 0.1 * np.sin(2 * np.pi * 0.5 * t)))
    segnale += 0.05 * generatore.standard_normal(len(t))
    segnale[: 16000 * 2] = 0  # due secondi di silenzio vero all'inizio
    return (np.clip(segnale, -1, 1) * 32000).astype(np.int16)


def test_stessi_punteggi_di_openwakeword_pezzo_per_pezzo():
    from openwakeword.model import Model

    originale = Model(wakeword_model_paths=MODELLI)
    leggero = RilevatoreLeggero(MODELLI)
    audio = _audio_di_prova()
    for inizio in range(0, len(audio) - CAMPIONI_PER_PEZZO + 1, CAMPIONI_PER_PEZZO):
        pezzo = audio[inizio : inizio + CAMPIONI_PER_PEZZO]
        atteso = originale.predict(pezzo)
        ottenuto = leggero.predict(pezzo)
        assert ottenuto.keys() == atteso.keys()
        for nome in atteso:
            assert float(ottenuto[nome]) == float(atteso[nome]), (inizio, nome)


def test_reset_come_openwakeword():
    from openwakeword.model import Model

    originale = Model(wakeword_model_paths=MODELLI)
    leggero = RilevatoreLeggero(MODELLI)
    audio = _audio_di_prova(6.0)
    pezzi = [audio[i : i + CAMPIONI_PER_PEZZO] for i in range(0, len(audio) - CAMPIONI_PER_PEZZO + 1, CAMPIONI_PER_PEZZO)]
    for pezzo in pezzi[:40]:
        originale.predict(pezzo)
        leggero.predict(pezzo)
    originale.reset()
    leggero.reset()
    for pezzo in pezzi[40:]:
        atteso = originale.predict(pezzo)
        ottenuto = leggero.predict(pezzo)
        assert {k: float(v) for k, v in ottenuto.items()} == {k: float(v) for k, v in atteso.items()}


def test_non_importa_openwakeword_ne_sklearn():
    """Il punto di tutto il modulo: caricare e usare il rilevatore senza i +92 MB (#58)."""
    codice = (
        "import sys, numpy as np\n"
        "from bmo_core.wake_word import RilevatoreLeggero\n"
        f"r = RilevatoreLeggero({MODELLI!r})\n"
        "r.predict(np.zeros(1280, dtype=np.int16))\n"
        "pesanti = [m for m in ('openwakeword', 'sklearn', 'scipy') if m in sys.modules]\n"
        "print(','.join(pesanti))\n"
    )
    uscita = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True, check=True)
    assert uscita.stdout.strip() == ""


def test_pezzi_sbagliati_rifiutati():
    leggero = RilevatoreLeggero(MODELLI[:1])
    with pytest.raises(ValueError):
        leggero.predict(np.zeros(640, dtype=np.int16))
    with pytest.raises(ValueError):
        leggero.predict(np.zeros(1280, dtype=np.float32))


def test_percorso_modello():
    assert percorso_modello("/qui/bmo9.onnx") == "/qui/bmo9.onnx"
    assert percorso_modello("hey_jarvis").endswith(".onnx")
    with pytest.raises(ValueError, match="sconosciuto"):
        percorso_modello("non_esiste")
