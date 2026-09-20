import ast
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from google.genai import types

import bmo_core.brain as brain_modulo
from bmo_core.brain import FUSO_ORARIO, Cervello, contesto_dinamico
from bmo_core.modelli import TIMEOUT_TENTATIVO_S, GeminiNonDisponibile

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
