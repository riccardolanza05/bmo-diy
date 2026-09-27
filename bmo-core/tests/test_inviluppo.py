"""Prove di `inviluppo_rms` (#23): usa `ffmpeg` vero, già richiesto dal
progetto (README, verifiche sul PC di sviluppo) — niente da simulare."""
import math
import shutil
import struct
import wave

import pytest

from bmo_core.inviluppo import FREQUENZA_DECODIFICA_HZ, inviluppo_rms

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg non installato")


def _scrivi_wav_tono(percorso, frequenza_hz=16000, durata_s=1.0, ampiezza=10000):
    n = int(frequenza_hz * durata_s)
    campioni = [int(ampiezza * math.sin(2 * math.pi * 440 * i / frequenza_hz)) for i in range(n)]
    with wave.open(str(percorso), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(frequenza_hz)
        f.writeframes(struct.pack(f"<{n}h", *campioni))


def _scrivi_wav_silenzio(percorso, frequenza_hz=16000, durata_s=1.0):
    n = int(frequenza_hz * durata_s)
    with wave.open(str(percorso), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(frequenza_hz)
        f.writeframes(b"\x00\x00" * n)


def test_un_tono_produce_un_inviluppo_non_vuoto(tmp_path):
    percorso = tmp_path / "tono.wav"
    _scrivi_wav_tono(percorso)
    inviluppo = inviluppo_rms(percorso)
    assert len(inviluppo) > 0
    assert all(0.0 <= v <= 1.0 for v in inviluppo)
    assert max(inviluppo) > 0.5  # normalizzato al picco: il massimo deve avvicinarsi a 1


def test_il_silenzio_da_un_inviluppo_tutto_a_zero(tmp_path):
    percorso = tmp_path / "silenzio.wav"
    _scrivi_wav_silenzio(percorso)
    inviluppo = inviluppo_rms(percorso)
    assert len(inviluppo) > 0
    assert all(v == 0.0 for v in inviluppo)


def test_il_numero_di_campioni_segue_la_durata_e_gli_fps(tmp_path):
    percorso = tmp_path / "tono.wav"
    _scrivi_wav_tono(percorso, durata_s=2.0)
    inviluppo = inviluppo_rms(percorso, fps=25.0)
    # ~2 s * 25 fps = ~50 campioni, con un margine per l'arrotondamento a
    # blocchi interi di FREQUENZA_DECODIFICA_HZ/fps.
    assert 45 <= len(inviluppo) <= 51


def test_file_inesistente_da_lista_vuota(tmp_path):
    assert inviluppo_rms(tmp_path / "non-esiste.wav") == []


def test_file_non_audio_da_lista_vuota(tmp_path):
    percorso = tmp_path / "non-audio.wav"
    percorso.write_text("questo non è audio")
    assert inviluppo_rms(percorso) == []


def test_frequenza_di_decodifica_dichiarata():
    assert FREQUENZA_DECODIFICA_HZ == 16000
