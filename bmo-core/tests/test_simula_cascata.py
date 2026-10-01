import io
import random
import wave

from google.genai import errors

from bmo_core.misura_modelli import esito_errore, wav_da_pcm
from bmo_core.simula_cascata import (
    COMUNE,
    L31,
    L35,
    PROFILI,
    CascataSimulata,
    ProfiloModello,
    Mondo,
    conversazione,
    riassunto,
)


def _prova(modelli, seme=3, turni=60, prove=40, **opzioni):
    tutti = []
    for i in range(prove):
        rng = random.Random(seme + i)
        tutti += conversazione(
            PROFILI, lambda mondo: CascataSimulata(mondo, modelli, **opzioni), turni, rng, comune=COMUNE
        )
    return riassunto(tutti)


def test_il_simulatore_e_riproducibile_con_lo_stesso_seme():
    assert _prova([L35, L31]) == _prova([L35, L31])


def test_modelli_in_coda_non_peggiorano_i_turni_falliti():
    attuale = _prova([L35, L31])
    con_coda = _prova([L35, L31, "gemini-3.6-flash", "gemini-3.5-flash"])
    assert con_coda["falliti_%"] <= attuale["falliti_%"]


def test_un_429_al_limite_costa_una_frazione_di_secondo():
    profili = {"a": ProfiloModello(1.0, p_guasto=0.0, rpm=1), "b": ProfiloModello(1.0, p_guasto=0.0)}
    mondo = Mondo(profili, random.Random(1))
    cascata = CascataSimulata(mondo, ["a", "b"])
    conteggio = {}
    cascata.richiesta(mondo.t + 20, conteggio)  # esaurisce la finestra di "a"
    cascata._sospesi.clear()
    partenza = mondo.t
    cascata.richiesta(mondo.t + 20, conteggio)
    assert mondo.t - partenza < 3.0
    assert conteggio["b"] == 1


def test_wav_da_pcm_produce_un_wav_valido():
    wav = wav_da_pcm(b"\x00\x00" * 1600)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)


def test_esito_errore_riporta_codice_e_attesa_suggerita():
    corpo = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "m",
                       "details": [{"retryDelay": "8s"}]}}
    assert esito_errore(errors.ClientError(429, corpo)) == "429 RESOURCE_EXHAUSTED retryDelay=8s"
    assert esito_errore(ValueError("x")) == "ValueError"
