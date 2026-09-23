"""Prove della sintesi vocale e della voce che la usa (#42).

`VoceTts` sta in `macchina.py` ma si prova qui: è la stessa funzione del
modulo TTS vista dall'altro capo, e tenerle insieme rende evidente quale
comportamento del ripiego dipende da quale guasto della sintesi.
"""
import wave

import pytest
from google.genai import errors

from bmo_core.adapters import catena_filtro
from bmo_core.adapters.audio_output import MpvAdapter
from bmo_core.macchina import VoceTts
from bmo_core.modelli import CascataModelli
from bmo_core.tts import (
    FREQUENZA_HZ,
    MODELLI_TTS_PREDEFINITI,
    TtsNonDisponibile,
    _chiave,
    cartella_voce,
    durata_s,
    lingua_configurata,
    modelli_configurati,
    motore_configurato,
    velocita_configurata,
    scrivi_wav,
    sintetizza,
    voce_configurata,
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
    percorso = sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini")

    assert percorso.exists()
    with wave.open(str(percorso), "rb") as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, FREQUENZA_HZ)
        assert f.readframes(f.getnframes()) == PCM
    assert durata_s(percorso) == pytest.approx(0.1, abs=0.01)


def test_chiede_audio_in_italiano_con_la_voce_configurata(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)))
    sintetizza("ciao", client=client, cartella=tmp_path, modello="m", voce="Vega", lingua="it-IT", motore="gemini")

    richiesta = client.richieste[0]
    configurazione = richiesta["config"]
    assert richiesta["model"] == "m"
    assert richiesta["contents"] == "ciao"
    assert list(configurazione.response_modalities) == ["AUDIO"]
    assert configurazione.speech_config.language_code == "it-IT"
    assert configurazione.speech_config.voice_config.prebuilt_voice_config.voice_name == "Vega"


def test_la_seconda_volta_non_chiama_la_rete(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)))
    primo = sintetizza("la stessa frase", client=client, cartella=tmp_path, motore="gemini")
    secondo = sintetizza("la stessa frase", client=client, cartella=tmp_path, motore="gemini")

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
    primo = sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini", **base)
    secondo = sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini", **{**base, **cambio})

    assert primo != secondo
    assert len(client.richieste) == 2


def test_senza_cache_risintetizza(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=PCM)), RispostaFinta(ParteFinta(dati=PCM)))
    sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini")
    sintetizza("ciao", client=client, cartella=tmp_path, usa_cache=False, motore="gemini")

    assert len(client.richieste) == 2


def test_salta_la_parte_di_testo_e_trova_l_audio(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(testo="ecco:"), ParteFinta(dati=PCM)))
    percorso = sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini")

    with wave.open(str(percorso), "rb") as f:
        assert f.readframes(f.getnframes()) == PCM


def test_audio_vuoto_e_un_guasto_non_un_file_muto(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(dati=b"")))
    with pytest.raises(TtsNonDisponibile):
        sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini")
    assert list(tmp_path.glob("*.wav")) == []


def test_audio_troncato_a_meta_campione_e_un_guasto(tmp_path):
    with pytest.raises(TtsNonDisponibile, match="troncato"):
        scrivi_wav(tmp_path / "x.wav", b"\x00\x00\x00")
    assert not (tmp_path / "x.wav").exists()


def test_risposta_senza_audio(tmp_path):
    client = ClientFinto(RispostaFinta(ParteFinta(testo="scusa, non posso")))
    with pytest.raises(TtsNonDisponibile, match="nessun audio"):
        sintetizza("ciao", client=client, cartella=tmp_path, motore="gemini")


def test_errore_dell_api_dice_dove_guardare(tmp_path):
    client = ClientFinto(RuntimeError("400 INVALID_ARGUMENT"))
    with pytest.raises(TtsNonDisponibile) as errore:
        sintetizza("ciao", client=client, cartella=tmp_path, voce="Inesistente", motore="gemini")

    messaggio = str(errore.value)
    assert "BMO_VOCE" in messaggio and "BMO_GEMINI_TTS_MODEL" in messaggio
    assert "Inesistente" in messaggio


def test_testo_vuoto(tmp_path):
    with pytest.raises(ValueError):
        sintetizza("   ", client=ClientFinto(), cartella=tmp_path, motore="gemini")


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

    def riproduci(self, sorgente, *, filtro=None):
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
    # Niente durata: leggerla da un mp3 costerebbe un ffprobe a ogni risposta.
    assert "s di audio" not in errori


# --- la cascata TTS (3 richieste al minuto per modello) ----------------------


def _quota_esaurita():
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})


def test_se_il_primario_e_a_quota_parla_il_secondo(tmp_path):
    client = ClientFinto(_quota_esaurita(), RispostaFinta(ParteFinta(dati=PCM)))
    cascata = CascataModelli(["primo", "secondo"])

    percorso = sintetizza("ciao", client=client, cartella=tmp_path, cascata=cascata, motore="gemini")

    assert [r["model"] for r in client.richieste] == ["primo", "secondo"]
    assert percorso.exists()


def test_la_chiave_porta_il_modello_che_ha_davvero_parlato(tmp_path):
    """Altrimenti il giro dopo non lo ritrova in cache e lo si paga due volte."""
    client = ClientFinto(_quota_esaurita(), RispostaFinta(ParteFinta(dati=PCM)))
    cascata = CascataModelli(["primo", "secondo"])
    percorso = sintetizza("ciao", client=client, cartella=tmp_path, cascata=cascata, motore="gemini")

    atteso = tmp_path / _chiave("ciao", "secondo", voce_configurata("gemini"), lingua_configurata())
    assert percorso == atteso


def test_la_cache_vale_per_tutti_i_modelli_della_cascata(tmp_path):
    """Un WAV gia' su disco dice la stessa frase: risintetizzarlo per 'farlo
    dire al modello giusto' spenderebbe una richiesta che non abbiamo."""
    client = ClientFinto(_quota_esaurita(), RispostaFinta(ParteFinta(dati=PCM)))
    cascata = CascataModelli(["primo", "secondo"])
    primo = sintetizza("ciao", client=client, cartella=tmp_path, cascata=cascata, motore="gemini")
    assert len(client.richieste) == 2

    # Secondo giro, cascata nuova (nessuna memoria di sospensione): il
    # primario sarebbe disponibile, ma l'audio del secondo e' gia' li'.
    secondo = sintetizza(
        "ciao", client=ClientFinto(), cartella=tmp_path,
        cascata=CascataModelli(["primo", "secondo"]), motore="gemini",
    )
    assert secondo == primo


def test_la_cascata_condivisa_ricorda_chi_e_a_quota(tmp_path, monkeypatch):
    """Ricrearla a ogni frase significherebbe sbattere ogni volta sul 429."""
    import bmo_core.tts as modulo

    monkeypatch.setattr(modulo, "_cascata", None)
    monkeypatch.setenv("BMO_GEMINI_TTS_MODELLI", "primo,secondo")
    client = ClientFinto(
        _quota_esaurita(),
        RispostaFinta(ParteFinta(dati=PCM)),
        RispostaFinta(ParteFinta(dati=PCM)),
    )

    sintetizza("una", client=client, cartella=tmp_path, usa_cache=False, motore="gemini")
    sintetizza("due", client=client, cartella=tmp_path, usa_cache=False, motore="gemini")

    # Alla seconda frase "primo" e' ancora sospeso: non lo si riprova.
    assert [r["model"] for r in client.richieste] == ["primo", "secondo", "secondo"]


def test_se_tutti_i_modelli_sono_a_quota_lo_dice(tmp_path):
    client = ClientFinto(_quota_esaurita(), _quota_esaurita())
    cascata = CascataModelli(["primo", "secondo"])

    with pytest.raises(TtsNonDisponibile, match="3 richieste al minuto"):
        sintetizza("ciao", client=client, cartella=tmp_path, cascata=cascata, motore="gemini")


def test_modello_singolo_esclude_il_ripiego(tmp_path):
    """`BMO_GEMINI_TTS_MODEL` serve a provarne uno senza rete di salvataggio."""
    client = ClientFinto(_quota_esaurita(), RispostaFinta(ParteFinta(dati=PCM)))

    with pytest.raises(TtsNonDisponibile):
        sintetizza("ciao", client=client, cartella=tmp_path, modello="solo-questo", motore="gemini")
    assert [r["model"] for r in client.richieste] == ["solo-questo"]


def test_elenco_dei_modelli_dall_ambiente(monkeypatch):
    monkeypatch.delenv("BMO_GEMINI_TTS_MODEL", raising=False)
    monkeypatch.setenv("BMO_GEMINI_TTS_MODELLI", " uno , due ,, tre ")
    assert modelli_configurati() == ["uno", "due", "tre"]

    monkeypatch.delenv("BMO_GEMINI_TTS_MODELLI")
    monkeypatch.setenv("BMO_GEMINI_TTS_MODEL", "solo-uno")
    assert modelli_configurati() == ["solo-uno"]

    monkeypatch.delenv("BMO_GEMINI_TTS_MODEL")
    assert modelli_configurati() == MODELLI_TTS_PREDEFINITI


# --- il motore edge-tts, che e' la voce vera di BMO (#42) --------------------


def test_il_motore_predefinito_e_edge(monkeypatch):
    monkeypatch.delenv("BMO_TTS_MOTORE", raising=False)
    assert motore_configurato() == "edge"


def test_ogni_motore_ha_il_suo_catalogo_di_voci(monkeypatch):
    """`it-IT-DiegoNeural` non esiste su Gemini e `Kore` non esiste su edge."""
    monkeypatch.delenv("BMO_VOCE", raising=False)
    assert voce_configurata("edge") == "it-IT-DiegoNeural"
    assert voce_configurata("gemini") == "Kore"

    monkeypatch.setenv("BMO_VOCE", "una-qualunque")
    assert voce_configurata("edge") == voce_configurata("gemini") == "una-qualunque"


def test_edge_scrive_un_mp3_e_non_chiama_gemini(tmp_path, monkeypatch):
    chiamate = []

    def finto(percorso, testo, voce, velocita):
        chiamate.append((testo, voce, velocita))
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(b"finto-mp3")

    monkeypatch.setattr("bmo_core.tts._sintetizza_edge", finto)
    client = ClientFinto()  # senza risposte: se venisse usato, esploderebbe

    percorso = sintetizza("ciao", client=client, cartella=tmp_path, motore="edge")

    assert percorso.suffix == ".mp3"
    # Legato al valore configurato, non a una costante scritta a mano: la
    # velocita' e' stata gia' regolata una volta all'ascolto e lo sara' ancora.
    assert chiamate == [("ciao", "it-IT-DiegoNeural", velocita_configurata())]
    assert client.richieste == []


def test_la_velocita_entra_nella_chiave(tmp_path, monkeypatch):
    """+20% fa parte dell'identita' di BMO: cambiarla deve rigenerare l'audio."""
    def finto(percorso, testo, voce, velocita):
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(b"finto-mp3")

    monkeypatch.setattr("bmo_core.tts._sintetizza_edge", finto)
    lento = sintetizza("ciao", cartella=tmp_path, motore="edge", velocita="+0%")
    svelto = sintetizza("ciao", cartella=tmp_path, motore="edge", velocita="+20%")

    assert lento != svelto


def test_edge_usa_la_cache(tmp_path, monkeypatch):
    chiamate = []

    def finto(percorso, testo, voce, velocita):
        chiamate.append(testo)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(b"finto-mp3")

    monkeypatch.setattr("bmo_core.tts._sintetizza_edge", finto)
    primo = sintetizza("ciao", cartella=tmp_path, motore="edge")
    secondo = sintetizza("ciao", cartella=tmp_path, motore="edge")

    assert primo == secondo
    assert chiamate == ["ciao"]


def test_durata_non_si_legge_dagli_mp3(tmp_path):
    """Leggerla costerebbe un ffprobe per frase: il criterio della #42 non la chiede."""
    wav = tmp_path / "x.wav"
    scrivi_wav(wav, PCM)
    assert durata_s(wav) == pytest.approx(0.1, abs=0.01)
    assert durata_s(tmp_path / "x.mp3") is None


# --- il trattamento robotico, applicato in riproduzione ----------------------


def test_i_preset_dei_filtri(monkeypatch):
    assert catena_filtro("naturale") is None
    assert catena_filtro(None) is None
    assert catena_filtro("nome-inventato") is None  # BMO parla lo stesso
    for nome in ("altoparlante", "console", "anello", "metallico", "bmo"):
        catena = catena_filtro(nome)
        assert catena and "loudnorm" in catena  # senza, BMO cambierebbe volume col filtro


def test_il_filtro_diventa_un_argomento_di_mpv(monkeypatch):
    lanciati = []
    monkeypatch.setattr(
        "bmo_core.adapters.audio_output.subprocess.Popen",
        lambda comando, *a, **k: lanciati.append(comando) or _ProcessoFinto(),
    )
    adapter = MpvAdapter()

    adapter.riproduci("a.mp3")
    adapter.riproduci("b.mp3", filtro="highpass=f=400")

    assert not any(x.startswith("--af") for x in lanciati[0])
    assert "--af=lavfi=[highpass=f=400]" in lanciati[1]


class _ProcessoFinto:
    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass


def test_la_voce_passa_il_suo_filtro_alla_riproduzione(tmp_path, monkeypatch):
    """E il tono della sveglia, che usa lo stesso adapter, non lo riceve."""
    percorso = tmp_path / "frase.wav"
    scrivi_wav(percorso, PCM)
    ricevuti = []

    class Altoparlante:
        def riproduci(self, sorgente, *, filtro=None):
            ricevuti.append(filtro)

        def attendi(self, timeout_s=None):
            pass

        def ferma(self):
            pass

    monkeypatch.setenv("BMO_VOCE_FILTRO", "console")
    VoceTts(altoparlante=Altoparlante(), sintetizza_fn=lambda t: percorso, diagnostica=False)("ciao")

    assert ricevuti and ricevuti[0] and "acrusher" in ricevuti[0]


def test_senza_configurazione_nessun_filtro(tmp_path, monkeypatch):
    """Il timbro di BMO e' una scelta di Riccardo, non un valore predefinito."""
    monkeypatch.delenv("BMO_VOCE_FILTRO", raising=False)
    assert VoceTts(altoparlante=AltoparlanteFinto(), diagnostica=False).filtro is None
