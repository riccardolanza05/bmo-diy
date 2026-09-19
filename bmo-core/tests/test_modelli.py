import httpx
import pytest
from google.genai import errors

from bmo_core.modelli import (
    SOSPENSIONE_SOVRACCARICO_S,
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
        self.models = self

    def generate_content(self, *, model, **_):
        self.chiamati.append(model)
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
