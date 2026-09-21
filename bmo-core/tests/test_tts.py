"""Prove della sintesi vocale e della voce che la usa (#42).

`VoceTts` sta in `macchina.py` ma si prova qui: è la stessa funzione del
modulo TTS vista dall'altro capo, e tenerle insieme rende evidente quale
comportamento del ripiego dipende da quale guasto della sintesi.
"""
import wave

import pytest

from bmo_core.macchina import VoceTts
from bmo_core.tts import (
    FREQUENZA_HZ,
    TtsNonDisponibile,
    cartella_voce,
    durata_s,
    scrivi_wav,
    sintetizza,
)

# Un decimo di secondo di silenzio: campioni interi a 16 bit, mono.
PCM = b"\x00\x00" * (FREQUENZA_HZ // 10)


class ParteFinta:
    def __init__(self, dati=None, testo=None):
        self.inline_data = type("Inline", (), {"data": dati})() if dati is not None else None
        self.text = testo


class RispostaFinta:
    def __init__(self, *parti):
        contenuto = type("Contenuto", (), {"parts": list(parti)})()
        self.candidates = [type("Candidato", (), {"content": contenuto})()]


class ClientFinto:
    """Sostituto di google.genai.Client per il solo TTS.

    Non riusa quello di test_brain.py: là `contents` è una lista di Content,
    qui è una stringa, e farla passare da `list()` la spezzerebbe in caratteri.
    """

    def __init__(self, *risposte):
        self._risposte = list(risposte)
        self.richieste = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.richieste.append({"model": model, "contents": contents, "config": config})
        risposta = self._risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta


def test_scrive_un_wav_vero_col_formato_dell_api(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)))
    percorso = sintetizza("ciao", client=client, cartella=tmp_path)

    assert percorso.exists()
    with wave.open(str(percorso), "rb") as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, FREQUENZA_HZ)
        assert f.readframes(f.getnframes()) == PCM
    assert durata_s(percorso) == pytest.approx(0.1, abs=0.01)


def test_chiede_audio_in_italiano_con_la_voce_configurata(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)))
    sintetizza("ciao", client=client, cartella=tmp_path, modello="m", voce="Vega", lingua="it-IT")

    richiesta = client.richieste[0]
    configurazione = richiesta["config"]
    assert richiesta["model"] == "m"
    assert richiesta["contents"] == "ciao"
    assert list(configurazione.response_modalities) == ["AUDIO"]
    assert configurazione.speech_config.language_code == "it-IT"
    assert configurazione.speech_config.voice_config.prebuilt_voice_config.voice_name == "Vega"


def test_la_seconda_volta_non_chiama_la_rete(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)))
    primo = sintetizza("la stessa frase", client=client, cartella=tmp_path)
    secondo = sintetizza("la stessa frase", client=client, cartella=tmp_path)

    assert primo == secondo
    assert len(client.richieste) == 1  # la cache è il conto, non un'ottimizzazione (§2.5)


@pytest.mark.parametrize(
    "cambio",
    [{"voce": "Altra"}, {"modello": "altro-modello"}, {"lingua": "en-US"}],
    ids=["voce", "modello", "lingua"],
)
def test_cambiare_voce_modello_o_lingua_non_serve_l_audio_vecchio(tmp_path, cambio):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)), RispostaFinta(ParteFinta(dati=PCM)))
    base = {"modello": "m", "voce": "Uno", "lingua": "it-IT"}
    primo = sintetizza("ciao", client=client, cartella=tmp_path, **base)
    secondo = sintetizza("ciao", client=client, cartella=tmp_path, **{**base, **cambio})

    assert primo != secondo
    assert len(client.richieste) == 2


def test_senza_cache_risintetizza(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)), RispostaFinta(ParteFinta(dati=PCM)))
    sintetizza("ciao", client=client, cartella=tmp_path)
    sintetizza("ciao", client=client, cartella=tmp_path, usa_cache=False)

    assert len(client.richieste) == 2


def test_salta_la_parte_di_testo_e_trova_l_audio(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(testo="ecco:"), ParteFinta(dati=PCM)))
    percorso = sintetizza("ciao", client=client, cartella=tmp_path)

    with wave.open(str(percorso), "rb") as f:
        assert f.readframes(f.getnframes()) == PCM


def test_audio_vuoto_e_un_guasto_non_un_file_muto(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=b"")))
    with pytest.raises(TtsNonDisponibile):
        sintetizza("ciao", client=client, cartella=tmp_path)
    assert list(tmp_path.glob("*.wav")) == []


def test_audio_troncato_a_meta_campione_e_un_guasto(tmp_path):
    with pytest.raises(TtsNonDisponibile, match="troncato"):
        scrivi_wav(tmp_path / "x.wav", b"\x00\x00\x00")
    assert not (tmp_path / "x.wav").exists()


def test_risposta_senza_audio(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(testo="scusa, non posso")))
    with pytest.raises(TtsNonDisponibile, match="nessun audio"):
        sintetizza("ciao", client=client, cartella=tmp_path)


def test_errore_dell_api_dice_dove_guardare(tmp_path):
    client = ClientFinto(RuntimeError("400 INVALID_ARGUMENT"))
    with pytest.raises(TtsNonDisponibile) as errore:
        sintetizza("ciao", client=client, cartella=tmp_path, voce="Inesistente")

    messaggio = str(errore.value)
    assert "BMO_VOCE" in messaggio and "BMO_GEMINI_TTS_MODEL" in messaggio
    assert "Inesistente" in messaggio


def test_testo_vuoto(tmp_path):
    with pytest.raises(ValueError):
        sintetizza("   ", client=ClientFinto(), cartella=tmp_path)


def test_la_cartella_predefinita_segue_bmo_dati(tmp_path, monkeypatch):
    # La fixture di conftest punta già BMO_DATI su una cartella usa e getta:
    # qui si verifica che la voce ci finisca dentro e non nella cartella vera.
    monkeypatch.setenv("BMO_DATI", str(tmp_path / "dati"))
    assert cartella_voce() == tmp_path / "dati" / "voce"


# --- la voce che usa la sintesi (VoceTts) ------------------------------------


class AltoparlanteFinto:
    def __init__(self, errore_alla_riproduzione=None):
        self.eventi = []
        self._errore = errore_alla_riproduzione

    def riproduci(self, sorgente):
        if self._errore is not None:
            raise self._errore
        self.eventi.append(("riproduci", sorgente))

    def attendi(self, timeout_s=None):
        self.eventi.append(("attendi", timeout_s))

    def ferma(self):
        self.eventi.append(("ferma", None))


def test_la_voce_suona_e_aspetta_la_fine_della_frase(tmp_path):
    percorso = tmp_path / "frase.wav"
    scrivi_wav(percorso, PCM)
    altoparlante = AltoparlanteFinto()
    detto = []
    voce = VoceTts(
        altoparlante=altoparlante,
        ripiego=detto.append,
        sintetizza_fn=lambda testo: percorso,
        diagnostica=False,
    )

    voce("ciao")

    # L'ordine conta: senza l'attesa la riproduzione successiva comincia con
    # ferma() e taglierebbe BMO a metà parola.
    assert altoparlante.eventi == [("riproduci", percorso), ("attendi", None)]
    assert detto == []


def test_se_la_sintesi_fallisce_la_risposta_si_legge(tmp_path):
    altoparlante = AltoparlanteFinto()
    detto = []

    def esplode(testo):
        raise TtsNonDisponibile("niente rete")

    VoceTts(altoparlante=altoparlante, ripiego=detto.append, sintetizza_fn=esplode, diagnostica=False)("ciao")

    assert detto == ["ciao"]  # una risposta letta è meglio di una risposta persa
    assert altoparlante.eventi == []


def test_se_mpv_manca_la_risposta_si_legge(tmp_path):
    percorso = tmp_path / "frase.wav"
    scrivi_wav(percorso, PCM)
    detto = []
    voce = VoceTts(
        altoparlante=AltoparlanteFinto(errore_alla_riproduzione=FileNotFoundError("mpv")),
        ripiego=detto.append,
        sintetizza_fn=lambda testo: percorso,
        diagnostica=False,
    )

    voce("ciao")

    assert detto == ["ciao"]


def test_i_due_tempi_si_stampano_separati(tmp_path, capsys):
    """Criterio di uscita della #42: il numero che serve a dimensionare la #21.

    Separati e non sommati: l'attesa di rete si cura con una clip, l'avvio di
    mpv no.
    """
    percorso = tmp_path / "frase.wav"
    scrivi_wav(percorso, PCM)

    class Cronometro:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            self.t += 1.5  # inizio=1.5, dopo sintesi=3.0, dopo riproduci=4.5
            return self.t

    VoceTts(
        altoparlante=AltoparlanteFinto(),
        sintetizza_fn=lambda testo: percorso,
        cronometro=Cronometro(),
    )("ciao")

    errori = capsys.readouterr().err
    assert "sintesi 1.50 s" in errori
    assert "primo suono +1.50 s" in errori
    assert "0.1 s di audio" in errori
