import ast
from datetime import datetime
from pathlib import Path

from google.genai import types

import bmo_core.brain as brain_modulo
from bmo_core.brain import FUSO_ORARIO, Cervello, contesto_dinamico

ORA = datetime(2026, 9, 8, 22, 14, tzinfo=FUSO_ORARIO)


def _risposta_testo(testo):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=testo)]))]
    )


def _risposta_chiamata(nome, **argomenti):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part(function_call=types.FunctionCall(name=nome, args=argomenti))],
                )
            )
        ]
    )


class ClientFinto:
    """Sostituto di google.genai.Client: restituisce risposte preparate e registra le richieste."""

    def __init__(self, risposte):
        self._risposte = list(risposte)
        self.richieste = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.richieste.append({"model": model, "contents": list(contents), "config": config})
        return self._risposte.pop(0)


class MicrofonoFinto:
    def __init__(self):
        self.durate = []

    def registra(self, destinazione: Path, durata_s: float) -> Path:
        self.durate.append(durata_s)
        destinazione.write_bytes(b"RIFF-finto")
        return destinazione

    def flusso_pcm(self):
        yield b""


def _cervello(risposte, **opzioni):
    client = ClientFinto(risposte)
    return Cervello(client=client, microfono=MicrofonoFinto(), orologio=lambda: ORA, **opzioni), client


def test_timer_di_dieci_minuti_produce_imposta_timer():
    cervello, client = _cervello(
        [_risposta_chiamata("imposta_timer", durata_secondi=600, etichetta="timer"), _risposta_testo("Fatto!")]
    )
    risposta = cervello.rispondi(audio_wav=b"RIFF")

    assert risposta.testo == "Fatto!"
    assert [(c.nome, c.argomenti) for c in risposta.chiamate] == [
        ("imposta_timer", {"durata_secondi": 600, "etichetta": "timer"})
    ]
    assert cervello.timer[0].scadenza == datetime(2026, 9, 8, 22, 24, tzinfo=FUSO_ORARIO)
    # Il secondo giro rimanda al modello la functionResponse.
    ultima = client.richieste[1]["contents"][-1]
    assert ultima.parts[0].function_response.name == "imposta_timer"
    assert ultima.parts[0].function_response.response["stato"] == "ok"


def test_audio_inviato_come_wav():
    cervello, client = _cervello([_risposta_testo("Ciao!")])
    cervello.rispondi(audio_wav=b"RIFF")
    parte = client.richieste[0]["contents"][0].parts[0]
    assert parte.inline_data.mime_type == "audio/wav"
    assert parte.inline_data.data == b"RIFF"


def test_risposta_senza_strumenti_fa_un_solo_giro():
    cervello, client = _cervello([_risposta_testo("Una poesia.")])
    risposta = cervello.rispondi(testo="Scrivi una poesia sui dinosauri")
    assert risposta.chiamate == []
    assert len(client.richieste) == 1


def test_loop_agentico_limitato_a_quattro_giri():
    cervello, client = _cervello(
        [_risposta_chiamata("imposta_timer", durata_secondi=60, etichetta=f"t{i}") for i in range(10)]
    )
    cervello.rispondi(testo="timer infiniti")
    assert len(client.richieste) == brain_modulo.MAX_GIRI


def test_strumento_sconosciuto_e_argomenti_errati_non_sollevano():
    cervello, _ = _cervello([])
    esiti = cervello.strumenti(
        [
            types.FunctionCall(name="lancia_razzo", args={}),
            types.FunctionCall(name="imposta_timer", args={"durata_secondi": 0, "etichetta": "x"}),
            types.FunctionCall(name="imposta_timer", args={"minuti": 5}),
        ]
    )
    assert all("errore" in e.risultato for e in esiti)
    assert cervello.timer == []


def test_prompt_contiene_strato_fisso_e_dinamico():
    cervello, client = _cervello([_risposta_testo("ok")])
    cervello.rispondi(testo="ciao")
    config = client.richieste[0]["config"]
    fisso, dinamico = config.system_instruction
    assert "Sei BMO" in fisso
    assert "22:14 DI MARTEDÌ 8 SETTEMBRE 2026" in dinamico


def test_contesto_dinamico_timer_e_senza_ora():
    cervello, _ = _cervello([])
    cervello.strumenti([types.FunctionCall(name="imposta_timer", args={"durata_secondi": 252, "etichetta": "pasta"})])
    testo = contesto_dinamico(ORA, cervello.timer)
    assert '"pasta" scade fra 4 minuti e 12 secondi' in testo
    assert "22:14" not in contesto_dinamico(ORA, [], inietta_ora=False)


def test_ascolta_usa_il_microfono_iniettato():
    cervello, _ = _cervello([])
    assert cervello.ascolta(3.0) == b"RIFF-finto"
    assert cervello.microfono.durate == [3.0]


def test_modello_sovrascrivibile_da_ambiente(monkeypatch):
    monkeypatch.setenv("BMO_GEMINI_MODEL", "modello-di-prova")
    cervello, client = _cervello([_risposta_testo("ok")])
    cervello.rispondi(testo="ciao")
    assert client.richieste[0]["model"] == "modello-di-prova"


def test_brain_non_importa_adapter_concreti():
    """Il cervello deve dipendere solo da base.py e dalla factory (issue #19)."""
    sorgente = Path(brain_modulo.__file__).read_text()
    nomi = set()
    for nodo in ast.walk(ast.parse(sorgente)):
        if isinstance(nodo, ast.ImportFrom):
            nomi.update(alias.name for alias in nodo.names)
            assert not (nodo.module or "").startswith(("adapters.", "bmo_core.adapters."))
    assert nomi.isdisjoint({"ArecordAdapter", "MpvAdapter", "LibcameraAdapter", "WebcamV4L2Adapter"})


def test_tutti_gli_strumenti_della_2_4_dichiarati():
    cervello, client = _cervello([_risposta_testo("ok")])
    cervello.rispondi(testo="ciao")
    nomi = {d.name for d in client.richieste[0]["config"].tools[0].function_declarations}
    assert nomi == {
        "scatta_foto", "cerca_sul_web", "imposta_timer", "annulla_timer", "elenca_timer",
        "riproduci_musica", "controllo_riproduzione", "regola_volume", "metti_in_pausa_l_ascolto",
    }


def test_strumenti_non_ancora_pronti_rispondono_non_disponibile():
    cervello, _ = _cervello([])
    [esito] = cervello.strumenti([types.FunctionCall(name="scatta_foto", args={"motivo": "x"})])
    assert esito.risultato["stato"] == "non_disponibile"


def test_annulla_ed_elenca_timer():
    cervello, _ = _cervello([])
    for etichetta, secondi in (("pasta", 300), ("uova", 90)):
        cervello.strumenti([types.FunctionCall(name="imposta_timer", args={"durata_secondi": secondi, "etichetta": etichetta})])
    [elenco] = cervello.strumenti([types.FunctionCall(name="elenca_timer", args={})])
    assert [t["etichetta"] for t in elenco.risultato["timer"]] == ["pasta", "uova"]
    [annullato] = cervello.strumenti([types.FunctionCall(name="annulla_timer", args={"etichetta": "Pasta"})])
    assert annullato.risultato == {"stato": "ok", "annullati": 1}
    assert [t.etichetta for t in cervello.timer] == ["uova"]
    cervello.strumenti([types.FunctionCall(name="annulla_timer", args={})])
    assert cervello.timer == []


def test_prompt_fisso_sostituibile(tmp_path):
    file = tmp_path / "prompt.txt"
    file.write_text("You are BMO. Always answer in Italian.", encoding="utf-8")
    client = ClientFinto([_risposta_testo("ok")])
    cervello = Cervello(client=client, microfono=MicrofonoFinto(), orologio=lambda: ORA,
                        **brain_modulo.prompt_da_file(file))
    cervello.rispondi(testo="ciao")
    assert client.richieste[0]["config"].system_instruction[0] == "You are BMO. Always answer in Italian."


def test_descrivi_errore_senza_traceback():
    import httpx
    from google.genai import errors

    from bmo_core.brain import descrivi_errore

    sovraccarico = errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "high demand"}})
    quota = errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})
    assert "sovraccarico" in descrivi_errore(sovraccarico)
    assert "quota" in descrivi_errore(quota)
    assert "rete" in descrivi_errore(httpx.ConnectError("giù"))


def test_main_stampa_messaggio_invece_del_traceback(monkeypatch, capsys):
    import sys

    import pytest
    from google.genai import errors

    class ClientSovraccarico:
        class models:
            @staticmethod
            def generate_content(**_):
                raise errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "x"}})

    monkeypatch.setattr(brain_modulo, "Cervello", lambda **k: Cervello(client=ClientSovraccarico(), microfono=MicrofonoFinto(), **k))
    monkeypatch.setattr(sys, "argv", ["brain", "--testo", "ciao"])
    with pytest.raises(SystemExit) as uscita:
        brain_modulo.main()
    assert "BMO non ci arriva" in str(uscita.value)


def test_cervello_ripiega_sul_modello_di_riserva():
    from google.genai import errors

    class Client:
        def __init__(self):
            self.models = self
            self.modelli = []

        def generate_content(self, *, model, contents, config):
            self.modelli.append(model)
            if model == "primario":
                raise errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "x"}})
            return _risposta_testo("Eccomi!")

    client = Client()
    cervello = Cervello(client=client, microfono=MicrofonoFinto(), modelli=["primario", "riserva"])
    risposta = cervello.rispondi(testo="ciao")
    assert (risposta.testo, risposta.modello) == ("Eccomi!", "riserva")
    assert client.modelli == ["primario", "riserva"]


def test_espressione_dall_etichetta_iniziale():
    cervello, client = _cervello([_risposta_testo("[Felice] Ciao, amico!")])
    risposta = cervello.rispondi(testo="ciao")
    assert (risposta.espressione, risposta.testo) == ("felice", "Ciao, amico!")
    assert len(client.richieste) == 1  # nessun giro in più per la faccia


def test_etichetta_sconosciuta_tolta_comunque():
    assert brain_modulo.separa_espressione("[contentissimo] Evviva!") == (None, "Evviva!")
    assert brain_modulo.separa_espressione("Nessuna etichetta.") == (None, "Nessuna etichetta.")
    assert brain_modulo.separa_espressione("Ho visto [una cosa] strana") == (None, "Ho visto [una cosa] strana")


def test_testo_letto_dalle_parti_senza_avvisi(recwarn):
    risposta = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="ragionamento", thought=True),
                        types.Part(function_call=types.FunctionCall(name="elenca_timer", args={})),
                        types.Part(text="[pensieroso] Vediamo."),
                    ],
                )
            )
        ]
    )
    assert brain_modulo.testo_della_risposta(risposta) == "[pensieroso] Vediamo."
    assert brain_modulo.testo_della_risposta(types.GenerateContentResponse(candidates=[])) == ""
    assert not recwarn.list
