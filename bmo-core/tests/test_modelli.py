import httpx
import pytest
from google.genai import errors, types

from bmo_core.modelli import (
    MODELLI_PREDEFINITI,
    SOSPENSIONE_SOVRACCARICO_S,
    TENTATIVI_SDK,
    MINIMO_TIMEOUT_SERVER_S,
    TIMEOUT_TENTATIVO_S,
    CascataModelli,
    GeminiNonDisponibile,
    modelli_da_ambiente,
)


def _errore(codice, ritardo=None):
    corpo = {"error": {"code": codice, "status": "X", "message": "m"}}
    if ritardo:
        corpo["error"]["details"] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": ritardo}
        ]
    classe = errors.ClientError if codice < 500 else errors.ServerError
    return classe(codice, corpo)


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ClientProgrammato:
    """Per ogni modello, una lista di esiti: un'eccezione da sollevare o una risposta."""

    def __init__(self, esiti):
        self.esiti = {m: list(e) for m, e in esiti.items()}
        self.chiamati = []
        self.configurazioni = []
        self.models = self

    def generate_content(self, *, model, config=None, **_):
        self.chiamati.append(model)
        self.configurazioni.append(config)
        esito = self.esiti[model].pop(0)
        if isinstance(esito, Exception):
            raise esito
        return esito


def test_cascata_da_ambiente(monkeypatch):
    monkeypatch.setenv("BMO_GEMINI_MODELLI", " primario , riserva ,")
    assert modelli_da_ambiente() == ["primario", "riserva"]
    monkeypatch.delenv("BMO_GEMINI_MODELLI")
    monkeypatch.setenv("BMO_GEMINI_MODEL", "solo")
    assert modelli_da_ambiente() == ["solo"]
    monkeypatch.delenv("BMO_GEMINI_MODEL")
    assert modelli_da_ambiente() == MODELLI_PREDEFINITI


def test_predefinita_ha_i_lite_in_testa_e_i_flash_solo_in_coda():
    """#73: l'ordine lo decide l'affidabilità misurata; i modelli con pochi
    richieste al giorno non devono mai passare davanti ai due lite."""
    assert MODELLI_PREDEFINITI[:2] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    assert len(set(MODELLI_PREDEFINITI)) == len(MODELLI_PREDEFINITI)
    # Esclusi dalle misure: 503/504 quasi sempre, niente audio, o 404.
    for escluso in ("gemini-3.7-flash", "gemini-3.8-flash", "gemma-4-26b-a4b-it", "gemini-2.5-flash"):
        assert escluso not in MODELLI_PREDEFINITI


def test_nel_traffico_normale_la_coda_non_viene_chiamata():
    client = ClientProgrammato({m: ["ok", "ok"] for m in MODELLI_PREDEFINITI})
    cascata = CascataModelli(orologio=Orologio())
    cascata.genera(client, contents=[])
    cascata.genera(client, contents=[])
    assert client.chiamati == ["gemini-3.5-flash-lite"] * 2


def test_se_cadono_i_lite_risponde_la_coda_e_poi_i_lite_tornano():
    orologio = Orologio()
    client = ClientProgrammato({
        "gemini-3.5-flash-lite": [_errore(503), "di nuovo io"],
        "gemini-3.1-flash-lite": [_errore(429, "20s"), "anche io"],
        "gemini-3.6-flash": ["coda"],
        "gemini-3.5-flash": [],
    })
    cascata = CascataModelli(orologio=orologio)
    assert cascata.genera(client, contents=[]) == ("coda", "gemini-3.6-flash")
    assert client.chiamati == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"]
    orologio.t += SOSPENSIONE_SOVRACCARICO_S + 1  # il 429 da 20 s è già scaduto
    assert cascata.genera(client, contents=[])[1] == "gemini-3.5-flash-lite"


def test_quota_giornaliera_della_coda_esaurita_costa_solo_un_429_veloce():
    """Misura del 1/10: a quota giornaliera finita Google risponde 429 con
    retryDelay di pochi secondi. Il modello viene saltato per quel tempo e
    la cascata passa oltre senza aspettare."""
    orologio = Orologio()
    client = ClientProgrammato({
        "gemini-3.5-flash-lite": [_errore(503), _errore(503)],
        "gemini-3.1-flash-lite": [_errore(503), "ok"],
        "gemini-3.6-flash": [_errore(429, "8s")],
        "gemini-3.5-flash": ["ultima"],
    })
    cascata = CascataModelli(orologio=orologio)
    assert cascata.genera(client, contents=[]) == ("ultima", "gemini-3.5-flash")
    assert cascata.disponibili() == ["gemini-3.5-flash"]  # gli altri tre sono sospesi
    orologio.t += 9
    assert "gemini-3.6-flash" in cascata.disponibili()


def test_tutta_la_cascata_predefinita_fallita_dice_quota_se_c_e_un_429():
    client = ClientProgrammato({
        "gemini-3.5-flash-lite": [_errore(503)],
        "gemini-3.1-flash-lite": [_errore(503)],
        "gemini-3.6-flash": [_errore(429, "8s")],
        "gemini-3.5-flash": [_errore(503)],
    })
    with pytest.raises(GeminiNonDisponibile) as errore:
        CascataModelli(orologio=Orologio()).genera(client, contents=[])
    assert errore.value.tipo == "quota"
    assert list(errore.value.errori) == MODELLI_PREDEFINITI


def test_503_passa_al_modello_di_riserva():
    client = ClientProgrammato({"primario": [_errore(503)], "riserva": ["ok"]})
    cascata = CascataModelli(["primario", "riserva"], orologio=Orologio())
    assert cascata.genera(client, contents=[]) == ("ok", "riserva")
    assert client.chiamati == ["primario", "riserva"]


def test_429_usa_retry_delay_poi_torna_al_primario():
    orologio = Orologio()
    client = ClientProgrammato({"primario": [_errore(429, "37s"), "di nuovo io"], "riserva": ["ok", "ok"]})
    cascata = CascataModelli(["primario", "riserva"], orologio=orologio)

    assert cascata.genera(client, contents=[])[1] == "riserva"
    orologio.t += 36
    assert cascata.genera(client, contents=[])[1] == "riserva"  # ancora sospeso
    orologio.t += 2
    assert cascata.genera(client, contents=[]) == ("di nuovo io", "primario")


def test_sovraccarico_sospende_per_trenta_secondi():
    orologio = Orologio()
    cascata = CascataModelli(["primario", "riserva"], orologio=orologio)
    cascata.genera(ClientProgrammato({"primario": [_errore(503)], "riserva": ["ok"]}), contents=[])
    assert cascata.disponibili() == ["riserva"]
    orologio.t += SOSPENSIONE_SOVRACCARICO_S
    assert cascata.disponibili() == ["primario", "riserva"]


def test_tutti_esauriti_solleva_con_tipo_quota():
    client = ClientProgrammato({"primario": [_errore(429)], "riserva": [_errore(503)]})
    cascata = CascataModelli(["primario", "riserva"], orologio=Orologio())
    with pytest.raises(GeminiNonDisponibile) as errore:
        cascata.genera(client, contents=[])
    assert errore.value.tipo == "quota"
    assert set(errore.value.errori) == {"primario", "riserva"}


def test_tutti_sospesi_riprova_comunque_il_primario():
    client = ClientProgrammato({"primario": [_errore(503), "ripreso"], "riserva": [_errore(503)]})
    cascata = CascataModelli(["primario", "riserva"], orologio=Orologio())
    with pytest.raises(GeminiNonDisponibile) as errore:
        cascata.genera(client, contents=[])
    assert errore.value.tipo == "sovraccarico"
    assert cascata.genera(client, contents=[]) == ("ripreso", "primario")


def test_modello_inesistente_saltato():
    client = ClientProgrammato({"sbagliato": [_errore(404)], "riserva": ["ok", "ok"]})
    cascata = CascataModelli(["sbagliato", "riserva"], orologio=Orologio())
    cascata.genera(client, contents=[])
    cascata.genera(client, contents=[])
    assert client.chiamati == ["sbagliato", "riserva", "riserva"]


def test_errori_non_di_disponibilita_salgono_subito():
    client = ClientProgrammato({"primario": [_errore(400)], "riserva": ["ok"]})
    with pytest.raises(errors.ClientError):
        CascataModelli(["primario", "riserva"], orologio=Orologio()).genera(client, contents=[])
    assert client.chiamati == ["primario"]


def test_rete_giu_non_prova_gli_altri_modelli():
    client = ClientProgrammato({"primario": [httpx.ConnectError("giù")], "riserva": ["ok"]})
    with pytest.raises(GeminiNonDisponibile) as errore:
        CascataModelli(["primario", "riserva"], orologio=Orologio()).genera(client, contents=[])
    assert errore.value.tipo == "rete"
    assert client.chiamati == ["primario"]


def test_richiesta_scaduta_passa_al_modello_di_riserva():
    """Caso reale del 19/9: richiesta accettata ma mai servita, BMO restava in attesa."""
    client = ClientProgrammato({"primario": [httpx.ReadTimeout("scaduta")], "riserva": ["ok"]})
    cascata = CascataModelli(["primario", "riserva"], orologio=Orologio())
    assert cascata.genera(client, contents=[]) == ("ok", "riserva")
    assert cascata.disponibili() == ["riserva"]


def test_scadenza_accorcia_il_timeout_della_richiesta():
    """Il tetto del turno (#18) vale sulla singola richiesta, non solo fra un giro e l'altro."""
    orologio = Orologio()
    client = ClientProgrammato({"primario": ["ok"]})
    cascata = CascataModelli(["primario"], orologio=orologio)
    cascata.genera(client, scadenza=orologio() + 12.0, contents=[], config=types.GenerateContentConfig())
    opzioni = client.configurazioni[0].http_options
    assert opzioni.timeout == 12000
    # In dodici secondi non ci stanno due tentativi da quindici.
    assert opzioni.retry_options.attempts == 1


def test_il_timeout_non_scende_sotto_il_minimo_di_gemini():
    """Gemini rifiuta con 400 le scadenze sotto i 10 s (visto dal vivo il 28/9):
    con 4 s rimasti si chiede comunque 10, invece di un errore sicuro."""
    orologio = Orologio()
    client = ClientProgrammato({"primario": ["ok"]})
    cascata = CascataModelli(["primario"], orologio=orologio)
    cascata.genera(client, scadenza=orologio() + 4.0, contents=[], config=types.GenerateContentConfig())
    opzioni = client.configurazioni[0].http_options
    assert opzioni.timeout == MINIMO_TIMEOUT_SERVER_S * 1000
    assert opzioni.retry_options.attempts == 1


def test_con_tempo_abbondante_restano_i_tentativi_normali():
    orologio = Orologio()
    client = ClientProgrammato({"primario": ["ok"]})
    cascata = CascataModelli(["primario"], orologio=orologio)
    cascata.genera(client, scadenza=orologio() + 300.0, contents=[], config=types.GenerateContentConfig())
    opzioni = client.configurazioni[0].http_options
    assert opzioni.timeout == TIMEOUT_TENTATIVO_S * 1000
    assert opzioni.retry_options.attempts == TENTATIVI_SDK


def test_senza_tempo_rimasto_non_si_chiama_nessun_modello():
    orologio = Orologio()
    client = ClientProgrammato({"primario": ["ok"], "riserva": ["ok"]})
    cascata = CascataModelli(["primario", "riserva"], orologio=orologio)
    with pytest.raises(GeminiNonDisponibile) as errore:
        cascata.genera(client, scadenza=orologio(), contents=[], config=types.GenerateContentConfig())
    assert errore.value.tipo == "tempo"
    assert client.chiamati == []
