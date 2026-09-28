"""issue #64: conversione del microfono del Pi (S32_LE stereo 48 kHz ->
S16_LE mono 16 kHz), con dati sintetici — l'hardware vero (HAT WM8960) non
c'è ancora, la prova con un microfono reale resta alla fase 4.1/4.3."""
import struct

import numpy as np
import pytest

from bmo_core.adapters.audio_input import ArecordConvertitoreAdapter, _converti_s32_stereo_a_s16_mono


def _s32_stereo(valori_canale_sinistro, valori_canale_destro=None):
    """Byte S32_LE stereo da una lista di interi, un frame per valore."""
    destro = valori_canale_destro or valori_canale_sinistro
    interlacciati = []
    for sx, dx in zip(valori_canale_sinistro, destro):
        interlacciati += [sx, dx]
    return struct.pack(f"<{len(interlacciati)}i", *interlacciati)


def test_converti_downmix_e_decima_un_gruppo_intero():
    valore = 100 * 65536  # >>16 == 100 esatto, nessun arrotondamento da verificare a mano
    grezzo = _s32_stereo([valore, valore, valore])  # 3 frame stereo identici, fattore 3
    convertito, avanzo = _converti_s32_stereo_a_s16_mono(grezzo, np.empty(0, dtype=np.int32), fattore_decimazione=3)
    assert convertito == struct.pack("<h", 100)
    assert avanzo.size == 0


def test_converti_media_i_due_canali():
    # sinistro 200*65536, destro 0 -> media 100*65536 -> >>16 == 100
    grezzo = _s32_stereo([200 * 65536] * 3, [0] * 3)
    convertito, _ = _converti_s32_stereo_a_s16_mono(grezzo, np.empty(0, dtype=np.int32), fattore_decimazione=3)
    assert convertito == struct.pack("<h", 100)


def test_converti_nessun_avanzo_produce_zero_byte():
    grezzo = _s32_stereo([65536, 65536])  # 2 frame, ne servono 3: niente in uscita, tutto in avanzo
    convertito, avanzo = _converti_s32_stereo_a_s16_mono(grezzo, np.empty(0, dtype=np.int32), fattore_decimazione=3)
    assert convertito == b""
    assert list(avanzo) == [65536, 65536]


def test_l_avanzo_attraversa_il_confine_fra_due_pezzi_senza_perdere_campioni():
    """4096 byte (CHUNK_BYTES) non sono in generale un multiplo di 3 frame
    stereo: l'avanzo del primo pezzo deve confluire nel secondo, non sparire
    né duplicarsi. Confronto con la conversione dell'intero blocco in un
    colpo solo, che è la definizione di "corretto" qui."""
    valori = [(i * 1000) * 65536 for i in range(1, 10)]  # 9 frame, divisibile per 3 da solo
    tutto_insieme = _s32_stereo(valori)
    atteso, _ = _converti_s32_stereo_a_s16_mono(tutto_insieme, np.empty(0, dtype=np.int32), fattore_decimazione=3)

    primo = _s32_stereo(valori[:4])  # 4 frame: 1 gruppo di 3 convertito, 1 in avanzo
    secondo = _s32_stereo(valori[4:])  # 5 frame + 1 in avanzo = 6, tutti convertibili
    out1, avanzo = _converti_s32_stereo_a_s16_mono(primo, np.empty(0, dtype=np.int32), fattore_decimazione=3)
    out2, avanzo_finale = _converti_s32_stereo_a_s16_mono(secondo, avanzo, fattore_decimazione=3)

    assert out1 + out2 == atteso
    assert avanzo_finale.size == 0


def test_flusso_pcm_converte_e_porta_avanti_l_avanzo_fra_le_letture(monkeypatch):
    valori = [(i * 500) * 65536 for i in range(1, 10)]
    tutto_insieme = _s32_stereo(valori)
    atteso, _ = _converti_s32_stereo_a_s16_mono(tutto_insieme, np.empty(0, dtype=np.int32), fattore_decimazione=3)

    pezzi_grezzi = [_s32_stereo(valori[:4]), _s32_stereo(valori[4:])]

    def flusso_nativo_finto():
        yield from pezzi_grezzi

    adapter = ArecordConvertitoreAdapter()
    monkeypatch.setattr(adapter._nativo, "flusso_pcm", flusso_nativo_finto)
    ricevuto = b"".join(adapter.flusso_pcm())
    assert ricevuto == atteso


def test_registra_scrive_un_wav_alla_durata_richiesta(tmp_path, monkeypatch):
    campione = struct.pack("<h", 1234)

    def flusso_finto():
        for _ in range(200):  # più dei 160 campioni richiesti: deve fermarsi da sé
            yield campione

    adapter = ArecordConvertitoreAdapter()
    monkeypatch.setattr(adapter, "flusso_pcm", flusso_finto)
    destinazione = adapter.registra(tmp_path / "prova.wav", durata_s=0.01)  # 160 campioni a 16 kHz

    import wave

    with wave.open(str(destinazione), "rb") as lettore:
        assert lettore.getnchannels() == 1
        assert lettore.getsampwidth() == 2
        assert lettore.getframerate() == 16000
        assert lettore.getnframes() == round(0.01 * 16000)


def test_registra_fino_al_silenzio_non_solleva_piu_valueerror(tmp_path, monkeypatch):
    """Il bug dell'issue #64: prima `registra_fino_al_silenzio` sollevava
    `ValueError` per qualunque adapter non già mono/S16 — cioè sempre, sul
    Pi. Silenzio puro (campioni a zero) deve solo fermarsi da sé (tetto
    dell'ascolto), non sollevare."""

    def flusso_di_silenzio():
        frame_silenzio = b"\x00\x00" * 480  # 30 ms a 16 kHz mono
        for _ in range(20):
            yield frame_silenzio

    adapter = ArecordConvertitoreAdapter()
    monkeypatch.setattr(adapter, "flusso_pcm", flusso_di_silenzio)
    destinazione, diagnostica = adapter.registra_fino_al_silenzio(tmp_path / "silenzio.wav", cap_s=0.1)
    assert destinazione.exists()
    assert diagnostica.motivo_fine == "mai_iniziato"
    assert diagnostica.voce_rilevata is False


def test_formato_nativo_non_supportato_solleva_subito():
    with pytest.raises(ValueError):
        ArecordConvertitoreAdapter(formato_nativo="S16_LE")


def test_frequenza_non_multipla_solleva_subito():
    with pytest.raises(ValueError):
        ArecordConvertitoreAdapter(frequenza_nativa=44100, frequenza=16000)
