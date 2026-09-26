import ast
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from google.genai import types

import bmo_core.brain as brain_modulo
from bmo_core.brain import FUSO_ORARIO, Cervello, contesto_dinamico
from bmo_core.memoria import aggiungi_voce, carica_diario
from bmo_core.modelli import TIMEOUT_TENTATIVO_S, GeminiNonDisponibile

ORA = datetime(2026, 9, 8, 22, 14, tzinfo=FUSO_ORARIO)


def _risposta_testo(testo):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=testo)]))]
    )


def _risposta_testo_con_uso(testo, prompt_token_count):
    """Come `_risposta_testo`, con `usage_metadata` (il tetto della #29 lo legge da lì)."""
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=testo)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=prompt_token_count),
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


class CronometroFinto:
    """Orologio monotono finto, così il tetto del turno (#18) si prova senza aspettare."""

    def __init__(self):
        self.adesso = 0.0

    def __call__(self) -> float:
        return self.adesso


class ClientFinto:
    """Sostituto di google.genai.Client: restituisce risposte preparate e registra le richieste.

    Un elemento di `risposte` che è un'eccezione viene sollevato, e `costo_s`
    fa avanzare il cronometro come farebbe una richiesta vera.
    """

    def __init__(self, risposte, cronometro=None, costo_s=0.0):
        self._risposte = list(risposte)
        self.richieste = []
        self.models = self
        self.cronometro = cronometro
        self.costo_s = costo_s

    def generate_content(self, *, model, contents, config):
        self.richieste.append({"model": model, "contents": list(contents), "config": config})
        if self.cronometro is not None:
            self.cronometro.adesso += self.costo_s
        risposta = self._risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta


class MicrofonoFinto:
    def __init__(self):
        self.durate = []

    def registra(self, destinazione: Path, durata_s: float) -> Path:
        self.durate.append(durata_s)
        destinazione.write_bytes(b"RIFF-finto")
        return destinazione

    def flusso_pcm(self):
        yield b""


class FacciaFinta:
    """Registra gli stati che il cervello le chiede di mostrare."""

    def __init__(self):
        self.stati = []

    def mostra(self, stato: str) -> None:
        self.stati.append(stato)


def _ricerca_finta(query):
    """Nessun test deve andare su internet: sarebbe lento e dipenderebbe dalla rete."""
    return {"stato": "non_disponibile", "motivo": "ricerca finta"}


def _cervello(risposte, costo_s=0.0, **opzioni):
    cronometro = CronometroFinto()
    client = ClientFinto(risposte, cronometro, costo_s)
    cervello = Cervello(
        client=client,
        microfono=MicrofonoFinto(),
        ricerca=opzioni.pop("ricerca", _ricerca_finta),
        faccia=opzioni.pop("faccia", FacciaFinta()),
        orologio=lambda: ORA,
        cronometro=cronometro,
        **opzioni,
    )
    return cervello, client


def test_timer_di_dieci_minuti_produce_imposta_timer():
    cervello, client = _cervello(
        [_risposta_chiamata("imposta_timer", minuti=10, etichetta="timer"), _risposta_testo("Fatto!")]
    )
    risposta = cervello.rispondi(audio_wav=b"RIFF")

    assert risposta.testo == "Fatto!"
    assert [(c.nome, c.argomenti) for c in risposta.chiamate] == [
        ("imposta_timer", {"minuti": 10, "etichetta": "timer"})
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


def test_quattro_giri_con_strumenti_poi_riepilogo_forzato():
    """Issue #18: i 4 giri sono tutti utilizzabili, il riepilogo è una richiesta in più."""
    cervello, client = _cervello(
        [_risposta_chiamata("imposta_timer", minuti=1, etichetta=f"t{i}") for i in range(4)]
        + [_risposta_testo("[felice] Ho messo i timer.")]
    )
    risposta = cervello.rispondi(testo="timer infiniti")
    assert len(client.richieste) == brain_modulo.MAX_GIRI + 1
    # Anche la chiamata del quarto giro viene eseguita, non buttata via.
    assert len(risposta.chiamate) == brain_modulo.MAX_GIRI
    assert risposta.riepilogo == "tetto di 4 giri"
    assert risposta.testo == "Ho messo i timer."
    # Solo il riepilogo vieta nuove chiamate e porta l'istruzione in più.
    modi = [r["config"].tool_config for r in client.richieste]
    assert modi[:-1] == [None] * brain_modulo.MAX_GIRI
    assert modi[-1].function_calling_config.mode == types.FunctionCallingConfigMode.NONE
    istruzioni = client.richieste[-1]["config"].system_instruction
    assert len(istruzioni) == 3 and istruzioni[-1] == brain_modulo.ISTRUZIONE_RIEPILOGO
    assert len(client.richieste[0]["config"].system_instruction) == 2


def test_riepilogo_quando_finisce_il_tempo():
    """Con richieste da 8 s la riserva per il riepilogo è intaccata al terzo giro."""
    cervello, client = _cervello(
        [
            _risposta_chiamata("cerca_sul_web", query="meteo Torino domani"),
            _risposta_chiamata("cerca_sul_web", query="previsioni Torino sera"),
            _risposta_testo("[pensieroso] Non sono riuscito a sapere che tempo farà."),
        ],
        costo_s=8.0,
    )
    risposta = cervello.rispondi(testo="Che tempo farà a Torino domani alle otto di sera?")
    assert len(client.richieste) == 3  # due giri e il riepilogo, non quattro giri
    assert risposta.riepilogo == "tempo finito"
    assert risposta.testo.startswith("Non sono riuscito")
    # Il riepilogo ha un timeout pari al tempo che resta: il tetto lo comprende.
    rimasto_ms = client.richieste[-1]["config"].http_options.timeout
    assert 0 < rimasto_ms <= (brain_modulo.TETTO_TURNO_S - 16) * 1000


def test_giri_con_strumenti_non_intaccano_la_riserva():
    cervello, client = _cervello(
        [_risposta_chiamata("cerca_sul_web", query="meteo"), _risposta_testo("[pensieroso] Non lo so.")],
        max_giri=1,
    )
    cervello.rispondi(testo="Che tempo fa?")
    # Il giro con gli strumenti non può andare oltre l'inizio della riserva...
    atteso = brain_modulo.TETTO_TURNO_S - brain_modulo.RISERVA_RIEPILOGO_S
    assert client.richieste[0]["config"].http_options.timeout == atteso * 1000
    # ...e il riepilogo ha tutto il tempo che resta (qui il cronometro è fermo
    # a zero, quindi si ferma prima il timeout del singolo tentativo).
    assert client.richieste[1]["config"].http_options.timeout == TIMEOUT_TENTATIVO_S * 1000
    # Dentro un tetto di 20 s non c'è spazio per due tentativi da 15: se il
    # primo non risponde si passa al modello di riserva, non si insiste.
    assert client.richieste[0]["config"].http_options.retry_options.attempts == 1


def test_rete_giu_a_meta_loop_prova_comunque_il_riepilogo():
    """Due ricerche a metà valgono più di un "non ci arrivo" (#18)."""
    cervello, client = _cervello(
        [
            _risposta_chiamata("cerca_sul_web", query="meteo Torino"),
            httpx.ConnectError("rete giù"),
            _risposta_testo("[pensieroso] Non riesco a sapere il meteo di domani."),
        ]
    )
    risposta = cervello.rispondi(testo="Che tempo farà a Torino domani sera?")
    assert risposta.riepilogo == "modello non disponibile"
    assert risposta.testo.startswith("Non riesco")

    # Senza niente in mano non c'è niente da riassumere: l'errore sale e sul
    # dispositivo diventa la clip "non ci arrivo".
    cervello, client = _cervello([httpx.ConnectError("rete giù")])
    with pytest.raises(GeminiNonDisponibile):
        cervello.rispondi(testo="ciao")
    assert len(client.richieste) == 1


def test_max_giri_riducibile_per_le_prove():
    cervello, client = _cervello(
        [_risposta_chiamata("cerca_sul_web", query="meteo"), _risposta_testo("[pensieroso] Non lo so.")],
        max_giri=1,
    )
    risposta = cervello.rispondi(testo="Che tempo farà domani?")
    assert len(client.richieste) == 2
    assert risposta.riepilogo == "tetto di 1 giro"


def test_solo_etichetta_senza_chiamata_riprovata_una_volta():
    """Caso reale del 19/9: «Fra quaranta secondi…» → solo "[felice]", nessuno strumento."""
    cervello, client = _cervello(
        [
            _risposta_testo("[felice]"),
            _risposta_chiamata("imposta_timer", secondi=40, etichetta="frittata"),
            _risposta_testo("[felice] Fra quaranta secondi ti avviso."),
        ]
    )
    risposta = cervello.rispondi(testo="Fra quaranta secondi dimmi di girare la frittata")
    assert risposta.testo == "Fra quaranta secondi ti avviso."
    assert [c.nome for c in risposta.chiamate] == ["imposta_timer"]
    assert len(client.richieste) == 3
    assert risposta.ripetizioni == 1


def test_strumento_sconosciuto_e_argomenti_errati_non_sollevano():
    cervello, _ = _cervello([])
    esiti = cervello.strumenti(
        [
            types.FunctionCall(name="lancia_razzo", args={}),
            types.FunctionCall(name="imposta_timer", args={"secondi": 0, "etichetta": "x"}),
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
    cervello.strumenti([types.FunctionCall(name="imposta_timer", args={"minuti": 4, "secondi": 12, "etichetta": "pasta"})])
    testo = contesto_dinamico(ORA, cervello.timer)
    assert '"pasta" scade fra 4 minuti e 12 secondi' in testo
    assert "22:14" not in contesto_dinamico(ORA, [], inietta_ora=False)


def test_contesto_dinamico_senza_diario_lo_dice_esplicitamente():
    assert "Diario: nessuna voce." in contesto_dinamico(ORA, [])


def test_contesto_dinamico_elenca_le_voci_del_diario():
    from bmo_core.memoria import Voce

    diario = [Voce("non gli piacciono i funghi", "2026-09-14"), Voce("ceno alle 20", "2026-09-15")]
    testo = contesto_dinamico(ORA, [], diario=diario)
    assert 'Diario: "non gli piacciono i funghi"; "ceno alle 20".' in testo


def test_cervello_inietta_il_diario_letto_dal_file(tmp_path):
    import json

    percorso = tmp_path / "memoria.json"
    percorso.write_text(
        json.dumps([{"testo": "non gli piacciono i funghi", "aggiunta_il": "2026-09-14"}]),
        encoding="utf-8",
    )
    cervello, client = _cervello([_risposta_testo("ok")], diario_percorso=percorso)
    cervello.rispondi(testo="ciao")
    dinamico = client.richieste[0]["config"].system_instruction[1]
    assert '"non gli piacciono i funghi"' in dinamico


def test_diario_riletto_a_ogni_turno_non_a_ogni_giro(tmp_path):
    import json

    percorso = tmp_path / "memoria.json"
    cervello, client = _cervello(
        [_risposta_chiamata("elenca_timer"), _risposta_testo("ok")], diario_percorso=percorso
    )
    percorso.write_text(json.dumps([{"testo": "ceno alle 20", "aggiunta_il": "2026-09-20"}]), encoding="utf-8")
    cervello.rispondi(testo="ciao")
    # Il file esiste già dal primo giro: la lettura è per turno, non a ogni
    # richiesta, ma entrambi i giri di questo turno la vedono.
    for richiesta in client.richieste:
        assert '"ceno alle 20"' in richiesta["config"].system_instruction[1]


@pytest.mark.parametrize(
    "testo_modello,atteso",
    [("si", "si"), ("Sì.", "si"), ("no", "no"), ("No, grazie.", "no"), ("boh", "boh"), ("non ho capito", "boh")],
)
def test_classifica_risposta_riconosce_si_no_boh(testo_modello, atteso):
    cervello, client = _cervello([_risposta_testo(testo_modello)])
    assert cervello.classifica_risposta(b"RIFF-si-o-no") == atteso
    # Chiamata a sé, fuori dal loop agentico: niente strumenti dichiarati.
    assert client.richieste[0]["config"].tools is None


def test_classifica_risposta_senza_gemini_e_boh_non_un_errore():
    cervello, _ = _cervello([httpx.ConnectError("rete giù")])
    assert cervello.classifica_risposta(b"RIFF") == "boh"


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
    assert nomi.isdisjoint(
        {"ArecordAdapter", "MpvAdapter", "LibcameraAdapter", "WebcamV4L2Adapter", "FacciaMuta", "FacciaTerminale"}
    )


def test_la_faccia_dice_cosa_sta_facendo_bmo():
    """BMO tace mentre elabora: la faccia è l'unico segno che non è bloccato."""
    faccia = FacciaFinta()
    cervello, _ = _cervello([_risposta_testo("[felice] Ciao!")], faccia=faccia)
    cervello.ascolta(3.0)
    cervello.rispondi(testo="ciao")
    assert faccia.stati == [
        brain_modulo.STATO_ASCOLTO,
        brain_modulo.STATO_PENSIERO,
        "felice",
    ]


def test_la_faccia_resta_in_pensiero_per_tutto_il_loop():
    faccia = FacciaFinta()
    cervello, _ = _cervello(
        [_risposta_chiamata("imposta_timer", minuti=1, etichetta="pasta"), _risposta_testo("Fatto.")],
        faccia=faccia,
    )
    cervello.rispondi(testo="Metti un timer di un minuto")
    # Un solo passaggio a "pensiero", poi lo stato di chi parla: senza
    # etichetta la faccia non resta indietro.
    assert faccia.stati == [brain_modulo.STATO_PENSIERO, brain_modulo.STATO_PARLATO]


def test_la_faccia_segnala_il_turno_finito_senza_risposta():
    faccia = FacciaFinta()
    vuota = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[]), finish_reason="STOP")]
    )
    cervello, _ = _cervello([vuota, vuota], faccia=faccia)
    cervello.rispondi(testo="ciao")
    assert faccia.stati[-1] == brain_modulo.STATO_ERRORE

    faccia = FacciaFinta()
    cervello, _ = _cervello([httpx.ConnectError("rete giù")], faccia=faccia)
    with pytest.raises(GeminiNonDisponibile):
        cervello.rispondi(testo="ciao")
    assert faccia.stati[-1] == brain_modulo.STATO_ERRORE


def test_tutti_gli_strumenti_della_2_4_dichiarati():
    cervello, client = _cervello([_risposta_testo("ok")])
    cervello.rispondi(testo="ciao")
    nomi = {d.name for d in client.richieste[0]["config"].tools[0].function_declarations}
    assert nomi == {
        "scatta_foto", "cerca_sul_web", "imposta_timer", "annulla_timer", "elenca_timer",
        "riproduci_musica", "controllo_riproduzione", "regola_volume", "metti_in_pausa_l_ascolto",
        # La radio si scorre e si salva (#20): due strumenti in più della §2.4.
        "salva_stazione", "elenca_stazioni",
        # Il diario si scrive con conferma (#14.2): un altro strumento in più.
        "ricorda",
    }


def test_strumenti_non_ancora_pronti_rispondono_non_disponibile():
    cervello, _ = _cervello([])
    [esito] = cervello.strumenti([types.FunctionCall(name="scatta_foto", args={"motivo": "x"})])
    assert esito.risultato["stato"] == "non_disponibile"


def test_annulla_ed_elenca_timer():
    cervello, _ = _cervello([])
    for etichetta, secondi in (("pasta", 300), ("uova", 90)):
        cervello.strumenti([types.FunctionCall(name="imposta_timer", args={"secondi": secondi, "etichetta": etichetta})])
    [elenco] = cervello.strumenti([types.FunctionCall(name="elenca_timer", args={})])
    # In ordine di scadenza, non di inserimento: il primo che suona per primo.
    assert [t["etichetta"] for t in elenco.risultato["timer"]] == ["uova", "pasta"]
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


def test_main_dice_sempre_se_ha_chiamato_strumenti(monkeypatch, capsys):
    import sys

    for risposte, attesa in (
        ([_risposta_testo("[felice] Ciao!")], "Strumenti chiamati: nessuno"),
        (
            [_risposta_chiamata("imposta_timer", minuti=2, etichetta="timer"), _risposta_testo("[felice] Due minuti.")],
            "Strumenti chiamati: 1\n  → imposta_timer(",
        ),
    ):
        client = ClientFinto(risposte)
        monkeypatch.setattr(
            brain_modulo, "Cervello",
            lambda client=client, **k: Cervello(client=client, microfono=MicrofonoFinto(), modelli=["m"], **k),
        )
        monkeypatch.setattr(sys, "argv", ["brain", "--testo", "ciao"])
        brain_modulo.main()
        uscita = capsys.readouterr().out
        assert attesa in uscita
        assert "Modello: m" in uscita


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


def test_parametro_sbagliato_indica_i_nomi_validi():
    """Caso reale delle prove del 19/9: durata_sec invece del parametro giusto."""
    cervello, _ = _cervello([])
    [esito] = cervello.strumenti(
        [types.FunctionCall(name="imposta_timer", args={"durata_sec": 180, "etichetta": "te"})]
    )
    assert esito.risultato["errore"] == "parametri sconosciuti: durata_sec"
    assert esito.risultato["parametri_validi"] == ["etichetta", "ore", "minuti", "secondi"]
    [senza_etichetta] = cervello.strumenti([types.FunctionCall(name="imposta_timer", args={"minuti": 3})])
    assert "obbligatori mancanti: etichetta" in senza_etichetta.risultato["errore"]
    [foto] = cervello.strumenti([types.FunctionCall(name="scatta_foto", args={"zoom": 2})])
    assert "errore" in foto.risultato
    assert cervello.timer == []


def test_durata_del_timer_da_ore_minuti_e_secondi():
    cervello, _ = _cervello([])
    [esito] = cervello.strumenti(
        [types.FunctionCall(name="imposta_timer", args={"ore": 1, "minuti": 15, "etichetta": "arrosto"})]
    )
    assert esito.risultato["stato"] == "ok"
    assert cervello.timer[0].scadenza == datetime(2026, 9, 8, 23, 29, tzinfo=FUSO_ORARIO)
    assert esito.risultato["durata"] == "1 ora e 15 minuti"
    assert esito.risultato["etichetta"] == "arrosto"
    assert brain_modulo.durata_in_secondi({"minuti": 1, "secondi": 30}) == 90
    assert brain_modulo.durata_in_secondi({"minuti": 1.5}) == 90


def test_durata_ambigua_rifiutata():
    """Caso reale del 19/9: «un'ora e un quarto» arrivò come ore 1 e minuti 75."""
    cervello, _ = _cervello([])
    esiti = cervello.strumenti(
        [
            types.FunctionCall(name="imposta_timer", args={"ore": 1, "minuti": 75, "etichetta": "arrosto"}),
            types.FunctionCall(name="imposta_timer", args={"minuti": 1, "secondi": 90, "etichetta": "uova"}),
        ]
    )
    assert "fra 0 e 59" in esiti[0].risultato["errore"]
    assert "fra 0 e 59" in esiti[1].risultato["errore"]
    assert cervello.timer == []
    [solo_minuti] = cervello.strumenti(
        [types.FunctionCall(name="imposta_timer", args={"minuti": 75, "etichetta": "arrosto"})]
    )
    assert solo_minuti.risultato["durata"] == "1 ora e 15 minuti"


def test_durata_parlata_con_le_ore():
    assert brain_modulo._durata_parlata(40) == "40 secondi"
    assert brain_modulo._durata_parlata(3600) == "1 ora"
    assert brain_modulo._durata_parlata(2 * 3600 + 61) == "2 ore, 1 minuto e 1 secondo"


def test_riepilogo_senza_testo_ne_dice_il_motivo():
    """Se fallisce anche il riepilogo il turno resta senza testo, ma spiegato (#18)."""
    vuota = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[]), finish_reason="STOP")]
    )
    cervello, client = _cervello(
        [_risposta_chiamata("cerca_sul_web", query="meteo") for _ in range(4)] + [vuota, vuota]
    )
    risposta = cervello.rispondi(testo="Che tempo fa a Torino?")
    assert risposta.testo == ""
    assert risposta.riepilogo == "tetto di 4 giri"
    assert risposta.motivo_vuota == "finish_reason STOP"
    # Il riepilogo vuoto viene riprovato una volta, come ogni risposta senza testo.
    assert len(client.richieste) == brain_modulo.MAX_GIRI + 2
    assert risposta.ripetizioni == 1


def test_risposta_vuota_ne_dice_il_motivo():
    vuota = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[]), finish_reason="STOP")]
    )
    cervello, client = _cervello([vuota, vuota])
    assert cervello.rispondi(testo="ciao").motivo_vuota == "finish_reason STOP"
    assert len(client.richieste) == 2  # riprovata una volta

    cervello, _ = _cervello([_risposta_testo("[felice] Ciao!")])
    assert cervello.rispondi(testo="ciao").motivo_vuota is None


def test_separa_etichette_prende_lingua_ed_espressione():
    """Le etichette restano italiane anche quando la risposta e' in inglese:
    sono un codice, non parole di BMO."""
    assert brain_modulo.separa_etichette("[it][felice] Ciao!") == ("felice", "it", "Ciao!")
    assert brain_modulo.separa_etichette("[en][sorpreso] Hi there!") == ("sorpreso", "en", "Hi there!")
    # In qualunque ordine: una regola in meno da far sbagliare al modello.
    assert brain_modulo.separa_etichette("[felice][en] Hi!") == ("felice", "en", "Hi!")
    # Senza etichetta di lingua si assume l'italiano, la lingua di casa.
    assert brain_modulo.separa_etichette("[felice] Ciao") == ("felice", "it", "Ciao")
    assert brain_modulo.separa_etichette("Niente") == (None, "it", "Niente")
    # Un'etichetta sconosciuta si toglie comunque: il TTS non deve mai
    # leggere una parentesi quadra.
    assert brain_modulo.separa_etichette("[surprised] Hi") == (None, "it", "Hi")



# --- memoria di sessione (#29) ------------------------------------------------
#
# Le richieste silenziose (trascrizione, estrazione, riassunto) girano solo
# da `Cervello.dopo_il_turno()`, mai da `rispondi()`: nei test si chiama a
# mano, come farebbe `Macchina.turno()` subito dopo aver parlato.


def test_il_turno_successivo_riceve_lo_storico_del_precedente():
    """Il criterio di uscita dell'issue: un riferimento al turno precedente."""
    cervello, client = _cervello(
        [
            _risposta_testo("Va bene, dieci minuti."),
            _risposta_testo("Ho capito, venti minuti."),
        ]
    )
    cervello.rispondi(testo="Metti un timer di dieci minuti")
    cervello.dopo_il_turno()
    cervello.rispondi(testo="Mettilo a venti invece")

    contenuti_secondo_turno = client.richieste[1]["contents"]
    assert contenuti_secondo_turno[0] == types.Content(
        role="user", parts=[types.Part.from_text(text="Metti un timer di dieci minuti")]
    )
    assert contenuti_secondo_turno[1] == types.Content(
        role="model", parts=[types.Part.from_text(text="Va bene, dieci minuti.")]
    )
    assert contenuti_secondo_turno[2] == types.Content(
        role="user", parts=[types.Part.from_text(text="Mettilo a venti invece")]
    )


def test_lo_storico_tiene_le_etichette_della_risposta():
    """Senza, dal secondo turno il modello vedrebbe solo risposte già
    spogliate delle etichette e smetterebbe di scriverle, imitando quello
    che si vede scrivere nello storico (§2.3 le rende obbligatorie)."""
    cervello, client = _cervello([_risposta_testo("[it][felice] Ciao!"), _risposta_testo("Bene.")])
    cervello.rispondi(testo="Ciao BMO")
    cervello.dopo_il_turno()
    assert cervello.sessione.turni[0].bmo == "[it][felice] Ciao!"


def test_un_turno_senza_risposta_non_entra_nello_storico():
    """Un riepilogo vuoto (motivo_vuota) non aiuterebbe i turni successivi."""
    vuota = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[]), finish_reason="STOP")]
    )
    cervello, client = _cervello(
        [_risposta_chiamata("cerca_sul_web", query="meteo"), vuota, vuota],
        max_giri=1,
    )
    risposta = cervello.rispondi(testo="Che tempo fa?")
    assert risposta.testo == ""
    cervello.dopo_il_turno()
    assert cervello.sessione.turni == []


def test_dopo_il_turno_senza_niente_in_sospeso_non_fa_niente():
    cervello, client = _cervello([])
    cervello.dopo_il_turno()  # non solleva, non consuma risposte
    assert client.richieste == []


def test_sessione_scaduta_per_inattivita_estrae_e_svuota_lo_storico(tmp_path):
    diario = tmp_path / "memoria.json"
    cervello, client = _cervello(
        [
            _risposta_testo("Ciao!"),  # turno 1
            _risposta_testo("Certo!"),  # turno 2, su una sessione già svuotata
            _risposta_testo("Piace la pizza margherita"),  # estrazione, in dopo_il_turno() del turno 2
        ],
        diario_percorso=diario,
    )
    cervello.rispondi(testo="Mi piace la pizza margherita, ricordatelo")
    cervello.dopo_il_turno()
    assert len(cervello.sessione.turni) == 1

    cervello.cronometro.adesso += brain_modulo.INATTIVITA_SESSIONE_S
    cervello.rispondi(testo="Ciao di nuovo")
    # Il turno nuovo non eredita quello vecchio: la sessione era già stata
    # svuotata all'inizio di rispondi(), prima di costruire la richiesta.
    assert client.richieste[-1]["contents"][0] == types.Content(
        role="user", parts=[types.Part.from_text(text="Ciao di nuovo")]
    )
    cervello.dopo_il_turno()

    voci = carica_diario(diario)
    assert [v.testo for v in voci] == ["Piace la pizza margherita"]
    assert voci[0].fonte == "modello"
    assert len(cervello.sessione.turni) == 1  # solo il turno nuovo


def test_estrazione_fallita_non_perde_niente_e_ritenta(tmp_path):
    diario = tmp_path / "memoria.json"
    cervello, client = _cervello(
        [
            _risposta_testo("Ciao!"),  # turno 1
            _risposta_testo("Certo!"),  # turno 2
            httpx.ConnectError("rete giù"),  # 1° tentativo di estrazione: fallisce
        ],
        diario_percorso=diario,
    )
    cervello.rispondi(testo="Ricordati che amo il calcio")
    cervello.dopo_il_turno()

    cervello.cronometro.adesso += brain_modulo.INATTIVITA_SESSIONE_S
    cervello.rispondi(testo="Altra cosa")
    cervello.dopo_il_turno()

    # Il turno nuovo è comunque nello storico: l'estrazione fallita non lo blocca.
    assert len(cervello.sessione.turni) == 1
    assert cervello._estrazione_pendente is not None
    assert cervello._tentativi_estrazione_pendente == 1
    assert carica_diario(diario) == []


def test_estrazione_fallita_troppe_volte_rinuncia(tmp_path):
    diario = tmp_path / "memoria.json"
    risposte = [_risposta_testo("Ciao!")]
    for i in range(brain_modulo.MAX_TENTATIVI_ESTRAZIONE):
        risposte.append(_risposta_testo(f"Turno {i}"))
        risposte.append(httpx.ConnectError("rete giù"))
    cervello, client = _cervello(risposte, diario_percorso=diario)

    cervello.rispondi(testo="Primo turno")
    cervello.dopo_il_turno()
    for _ in range(brain_modulo.MAX_TENTATIVI_ESTRAZIONE):
        cervello.cronometro.adesso += brain_modulo.INATTIVITA_SESSIONE_S
        cervello.rispondi(testo="altro turno")
        cervello.dopo_il_turno()

    # Dopo il tetto di tentativi si rinuncia.
    assert cervello._estrazione_pendente is None
    assert cervello._tentativi_estrazione_pendente == 0
    assert len(cervello.sessione.turni) == 1  # solo l'ultimo turno
    assert carica_diario(diario) == []


def test_tetto_di_token_comprime_lo_storico_in_un_riassunto(tmp_path):
    diario = tmp_path / "memoria.json"
    cervello, client = _cervello(
        [
            _risposta_testo_con_uso("Fatto!", brain_modulo.TETTO_TOKEN_STORICO),
            _risposta_testo("Piace il calcio"),  # estrazione (caso 2a)
            _risposta_testo("  Si parlava di sport.  "),  # riassunto (caso 2b)
            _risposta_testo("Certo."),
        ],
        diario_percorso=diario,
    )
    cervello.rispondi(testo="Ricordati che mi piace il calcio")
    cervello.dopo_il_turno()

    assert cervello.sessione.riassunto == "Si parlava di sport."
    assert cervello.sessione.turni == []
    assert [v.testo for v in carica_diario(diario)] == ["Piace il calcio"]

    cervello.rispondi(testo="Altra domanda")
    # Il riassunto non è un `Content`: due `user` di seguito (il riassunto,
    # poi il turno nuovo, senza ancora turni letterali in mezzo) non è una
    # forma garantita dall'API multi-turno.
    contenuti = client.richieste[-1]["contents"]
    assert contenuti == [types.Content(role="user", parts=[types.Part.from_text(text="Altra domanda")])]
    istruzioni = client.richieste[-1]["config"].system_instruction
    assert any("Si parlava di sport." in strato for strato in istruzioni)


def test_estrazione_scarta_sentinel_punti_elenco_e_doppioni(tmp_path):
    diario = tmp_path / "memoria.json"
    aggiungi_voce(diario, "Piace la pizza", "2026-09-01", fonte="manuale")
    cervello, client = _cervello(
        [
            _risposta_testo("Certo."),
            _risposta_testo("- Piace la pizza\n* Piace il calcio\nNIENTE\n1. Piace il jazz"),
        ],
        diario_percorso=diario,
    )
    cervello.rispondi(testo="Ricordati alcune cose")
    cervello.dopo_il_turno()
    cervello._estrai_verso_diario(cervello.sessione.testo_per_estrazione())
    voci = [v.testo for v in carica_diario(diario)]
    # La voce già presente non si ripete, il sentinel e i punti elenco non ci finiscono dentro.
    assert voci == ["Piace la pizza", "Piace il calcio", "Piace il jazz"]


def test_estrazione_al_massimo_un_tetto_di_voci_nuove(tmp_path):
    diario = tmp_path / "memoria.json"
    cervello, client = _cervello(
        [_risposta_testo("Certo."), _risposta_testo("Fatto uno\nFatto due\nFatto tre\nFatto quattro")],
        diario_percorso=diario,
    )
    cervello.rispondi(testo="Ricordati tante cose")
    cervello.dopo_il_turno()
    cervello._estrai_verso_diario(cervello.sessione.testo_per_estrazione())
    assert len(carica_diario(diario)) == brain_modulo.MAX_VOCI_PER_ESTRAZIONE


def test_dopo_il_turno_trascrive_laudio_con_una_richiesta_dedicata():
    cervello, client = _cervello([_risposta_testo("Fatto!"), _risposta_testo("Metti un timer di dieci minuti")])
    cervello.rispondi(audio_wav=b"RIFF")
    assert len(client.richieste) == 1  # la trascrizione non è ancora partita

    cervello.dopo_il_turno()
    assert len(client.richieste) == 2
    assert client.richieste[1]["config"].system_instruction == brain_modulo.ISTRUZIONE_TRASCRIZIONE
    assert client.richieste[1]["contents"][0].parts[0].inline_data.data == b"RIFF"
    assert cervello.sessione.turni[0].utente == "Metti un timer di dieci minuti"
    assert cervello.sessione.turni[0].bmo == "Fatto!"


def test_trascrizione_fallita_non_solleva_e_non_scrive_il_turno():
    cervello, client = _cervello([_risposta_testo("Fatto!"), httpx.ConnectError("rete giù")])
    cervello.rispondi(audio_wav=b"RIFF")
    cervello.dopo_il_turno()  # non deve sollevare
    assert cervello.sessione.turni == []


def test_estrazione_manda_le_voci_gia_note_del_diario(tmp_path):
    diario = tmp_path / "memoria.json"
    aggiungi_voce(diario, "Piace la pizza", "2026-09-01", fonte="manuale")
    cervello, client = _cervello(
        [_risposta_testo("Certo."), _risposta_testo("Piace il calcio")], diario_percorso=diario
    )
    cervello.rispondi(testo="Ricordati altre cose")
    cervello.dopo_il_turno()
    cervello._estrai_verso_diario(cervello.sessione.testo_per_estrazione())
    istruzioni = client.richieste[-1]["config"].system_instruction
    assert any("Piace la pizza" in strato for strato in istruzioni)
