from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from google.genai import types

from bmo_core.adapters import (
    STATO_ASCOLTO,
    STATO_ASSONNATO,
    STATO_CONFERMA,
    STATO_ERRORE,
    STATO_IDLE,
    STATO_PENSIERO,
)
from bmo_core.brain import Cervello, Risposta
from bmo_core.config import FUSO_ORARIO
from bmo_core.macchina import Macchina, Stato
from bmo_core.memoria import carica_diario
from bmo_core.modelli import GeminiNonDisponibile
from bmo_core.vad import Diagnostica

ORA = datetime(2026, 9, 20, 21, 0, tzinfo=FUSO_ORARIO)


class OrologioFinto:
    def __init__(self):
        self.adesso = ORA

    def __call__(self):
        return self.adesso

    def avanza(self, minuti):
        self.adesso += timedelta(minutes=minuti)


class FacciaFinta:
    def __init__(self):
        self.stati = []

    def mostra(self, stato):
        self.stati.append(stato)


class ArchivioFinto:
    """Basta a soddisfare cervello.archivio.attivi(), usato da main() per Ctrl-D."""

    def attivi(self):
        return []


class CervelloFinto:
    """Sostituto di Cervello: la macchina lo usa solo per ascoltare e rispondere."""

    def __init__(self, risposte, faccia=None, classificazioni=None, diagnostiche=None):
        self._risposte = list(risposte)
        self.faccia = faccia
        self.ascolti = []
        self.ascolti_vad = []
        self.strumenti_registrati = {}
        self._classificazioni = list(classificazioni or [])
        self._diagnostiche = list(diagnostiche or [])
        self.audio_classificati = []
        self.diario_percorso = None
        self.archivio = ArchivioFinto()

    def registra_strumento(self, nome, esecutore):
        self.strumenti_registrati[nome] = esecutore

    def ascolta(self, durata_s):
        # Serve a controllare che la faccia cambi PRIMA di registrare.
        self.ascolti.append((durata_s, list(self.faccia.stati) if self.faccia else []))
        return b"RIFF"

    def ascolta_fino_al_silenzio(self, cap_s, silenzio_ms, aggressivita):
        self.ascolti_vad.append((cap_s, silenzio_ms, aggressivita, list(self.faccia.stati) if self.faccia else []))
        diagnostica = self._diagnostiche.pop(0) if self._diagnostiche else Diagnostica(1.0, True, 0, "silenzio")
        return b"RIFF", diagnostica

    def rispondi(self, audio_wav=None, testo=None):
        risposta = self._risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta

    def classifica_risposta(self, audio_wav):
        self.audio_classificati.append(audio_wav)
        return self._classificazioni.pop(0)


def _macchina(risposte, orologio=None, richiami=1, classificazioni=None, diagnostiche=None, **opzioni):
    faccia = FacciaFinta()
    cervello = CervelloFinto(risposte, faccia, classificazioni=classificazioni, diagnostiche=diagnostiche)
    dette = []
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=lambda: True,
        voce=dette.append,
        orologio=orologio or OrologioFinto(),
        # Il VAD (aggiunto il 20/9) vive nel microfono vero: CervelloFinto non
        # lo implementa, perché questi test riguardano gli stati e il
        # dialogo, non l'ascolto. usa_vad=True si prova a parte, sotto.
        usa_vad=opzioni.pop("usa_vad", False),
        **opzioni,
    )
    return macchina, faccia, cervello, dette


def test_un_turno_passa_per_gli_stati_giusti():
    macchina, faccia, cervello, dette = _macchina([Risposta(testo="Ciao!", espressione="felice")])
    macchina.esegui(giri=1)
    assert faccia.stati[:2] == [STATO_IDLE, STATO_ASCOLTO]
    assert dette == ["Ciao!"]
    assert macchina.stato is Stato.PARLATO


def test_la_faccia_cambia_prima_di_registrare():
    """§2.1: il passaggio ad ASCOLTO deve vedersi entro 150 ms.

    Se la faccia si aggiornasse dopo la registrazione, la persona non saprebbe
    di essere stata sentita, ripeterebbe la frase e rovinerebbe la cattura.
    """
    macchina, _, cervello, _ = _macchina([Risposta(testo="Ciao!")])
    macchina.esegui(giri=1)
    [(_, facce_al_momento_di_registrare)] = cervello.ascolti
    assert facce_al_momento_di_registrare[-1] == STATO_ASCOLTO


def test_turno_sospende_l_ascolto_e_lo_riprende_subito_dopo():
    """La radio va sospesa solo per la registrazione, non per tutto il turno.

    Trovato il 21/9 provando dal vivo: col volume alto, il microfono aperto
    sente la radio come voce e il VAD non distingue più niente.
    """
    macchina, faccia, cervello, dette = _macchina([Risposta(testo="Ciao!")])
    eventi = []

    @contextmanager
    def sospensione():
        eventi.append(("entra", len(cervello.ascolti)))
        yield
        eventi.append(("esce", len(cervello.ascolti)))

    macchina.sospendi_ascolto = sospensione
    macchina.esegui(giri=1)
    assert eventi == [("entra", 0), ("esce", 1)]


def test_in_pausa_non_ascolta_ma_lo_fa_vedere():
    orologio = OrologioFinto()
    macchina, faccia, cervello, _ = _macchina([Risposta(testo="Ciao!")], orologio)
    assert macchina.metti_in_pausa(10)["stato"] == "ok"

    macchina.esegui(giri=1)
    assert cervello.ascolti == []  # chiamato, ma non registra
    assert faccia.stati == [STATO_ASSONNATO, STATO_ASSONNATO]
    assert macchina.stato is Stato.PAUSA

    orologio.avanza(11)
    macchina.esegui(giri=1)
    assert len(cervello.ascolti) == 1
    assert faccia.stati[2] == STATO_IDLE


def test_la_pausa_si_chiede_con_lo_strumento():
    """Lo strumento è della macchina, non del cervello: arriva con registra_strumento."""
    cervello = Cervello(
        client=object(),
        microfono=object(),
        faccia=FacciaFinta(),
        orologio=lambda: ORA,
    )
    macchina = Macchina(cervello=cervello, faccia=FacciaFinta(), orologio=lambda: ORA)
    [esito] = cervello.strumenti(
        [types.FunctionCall(name="metti_in_pausa_l_ascolto", args={"minuti": 30})]
    )
    assert esito.risultato == {"stato": "ok", "minuti": 30, "fino_a": "21:30"}
    assert macchina.in_pausa

    # Una pausa assurda non fa morire BMO: diventa un errore da rimandare al modello.
    [sbagliata] = cervello.strumenti(
        [types.FunctionCall(name="metti_in_pausa_l_ascolto", args={"minuti": 10000})]
    )
    assert "errore" in sbagliata.risultato


def test_gemini_giu_lo_dice_e_torna_in_attesa():
    macchina, faccia, _, dette = _macchina([GeminiNonDisponibile("rete", {})])
    macchina.esegui(giri=1)
    assert faccia.stati[-1] == STATO_ERRORE
    assert dette and dette[0].startswith("Non ci arrivo")
    assert macchina.stato is Stato.ERRORE


def test_risposta_vuota_non_lascia_bmo_muto():
    macchina, faccia, _, dette = _macchina([Risposta(testo="", motivo_vuota="finish_reason STOP")])
    macchina.esegui(giri=1)
    assert dette == ["Non sono riuscito a rispondere."]
    assert faccia.stati[-1] == STATO_ERRORE


def test_si_spegne_quando_il_richiamo_finisce():
    faccia = FacciaFinta()
    cervello = CervelloFinto([], faccia)
    macchina = Macchina(cervello=cervello, faccia=faccia, richiamo=lambda: False, voce=lambda t: None)
    macchina.esegui()  # senza giri: esce perché il richiamo dice di smettere
    assert cervello.ascolti == []


def test_minuti_di_pausa_non_validi():
    macchina, _, _, _ = _macchina([])
    with pytest.raises(ValueError):
        macchina.metti_in_pausa(0)
    with pytest.raises(ValueError):
        macchina.metti_in_pausa(-5)


def test_chiedi_conferma_si_al_primo_colpo():
    macchina, faccia, cervello, dette = _macchina([], classificazioni=["si"])
    assert macchina.chiedi_conferma("Vuoi che lo ricordi?") is True
    assert dette == ["Vuoi che lo ricordi?"]
    assert len(cervello.ascolti) == 1
    assert cervello.ascolti[0][0] == 8.0  # CAP_CONFERMA_S
    assert faccia.stati[-2:] == [STATO_CONFERMA, STATO_PENSIERO]


def test_chiedi_conferma_no_esplicito():
    macchina, _, _, dette = _macchina([], classificazioni=["no"])
    assert macchina.chiedi_conferma("Vuoi che lo ricordi?") is False
    assert dette == ["Vuoi che lo ricordi?"]  # nessun messaggio in più per un "no" chiaro


def test_chiedi_conferma_boh_poi_si_chiede_un_solo_chiarimento():
    macchina, _, cervello, dette = _macchina([], classificazioni=["boh", "si"])
    assert macchina.chiedi_conferma("Vuoi che lo ricordi?") is True
    assert dette == ["Vuoi che lo ricordi?", "Non ho capito, dimmi solo sì o no."]
    assert len(cervello.ascolti) == 2


def test_chiedi_conferma_sospende_l_ascolto():
    macchina, _, cervello, _ = _macchina([], classificazioni=["si"])
    eventi = []

    @contextmanager
    def sospensione():
        eventi.append("entra")
        yield
        eventi.append("esce")

    macchina.sospendi_ascolto = sospensione
    macchina.chiedi_conferma("Vuoi che lo ricordi?")
    assert eventi == ["entra", "esce"]


def test_chiedi_conferma_ambigua_non_fa_un_loop():
    """L'issue #17 lo dice esplicitamente: niente loop, un solo chiarimento."""
    macchina, _, cervello, dette = _macchina([], classificazioni=["boh", "boh"])
    assert macchina.chiedi_conferma("Vuoi che lo ricordi?") is None
    assert len(dette) == 2  # la domanda e il chiarimento, non un terzo tentativo
    assert len(cervello.ascolti) == 2  # non tre


def test_ricorda_scrive_dopo_conferma_esplicita(tmp_path):
    """#14.2: nessuna scrittura silenziosa, ma un sì esplicito scrive davvero."""
    percorso = tmp_path / "memoria.json"
    macchina, _, cervello, dette = _macchina([], classificazioni=["si"])
    cervello.diario_percorso = percorso
    esito = macchina._ricorda("non gli piacciono i funghi")
    assert esito == {"stato": "ok"}
    assert dette[0] == "Vuoi che mi ricordi che non gli piacciono i funghi?"
    [voce] = carica_diario(percorso)
    assert (voce.testo, voce.fonte, voce.aggiunta_il) == ("non gli piacciono i funghi", "modello", "2026-09-20")


def test_ricorda_rifiutato_non_scrive_nulla(tmp_path):
    percorso = tmp_path / "memoria.json"
    macchina, _, cervello, _ = _macchina([], classificazioni=["no"])
    cervello.diario_percorso = percorso
    assert macchina._ricorda("ceno alle 20") == {"stato": "annullato", "motivo": "rifiutato"}
    assert not percorso.exists()


def test_ricorda_ambiguo_non_scrive_nulla(tmp_path):
    percorso = tmp_path / "memoria.json"
    macchina, _, cervello, _ = _macchina([], classificazioni=["boh", "boh"])
    cervello.diario_percorso = percorso
    esito = macchina._ricorda("ceno alle 20")
    assert esito == {"stato": "annullato", "motivo": "non ho capito la conferma"}
    assert not percorso.exists()


def test_ricorda_testo_vuoto_rifiutato():
    macchina, _, _, _ = _macchina([])
    with pytest.raises(ValueError):
        macchina._ricorda("   ")


def test_ricorda_registrato_come_strumento():
    macchina, _, cervello, _ = _macchina([])
    assert cervello.strumenti_registrati["ricorda"] == macchina._ricorda


def test_turno_con_vad_usa_ascolta_fino_al_silenzio_e_il_cap_giusto():
    macchina, _, cervello, dette = _macchina(
        [Risposta(testo="Ciao!")], usa_vad=True, diagnostiche=[Diagnostica(1.2, True, 3, "silenzio")]
    )
    macchina.esegui(giri=1)
    assert dette == ["Ciao!"]
    assert cervello.ascolti == []  # non l'ascolto a durata fissa
    [(cap, _silenzio_ms, _aggressivita, _)] = cervello.ascolti_vad
    assert cap == macchina.cap_ascolto_s


def test_turno_con_vad_stampa_la_diagnostica_su_stderr(capsys):
    macchina, _, _, _ = _macchina(
        [Risposta(testo="Ciao!")], usa_vad=True, diagnostiche=[Diagnostica(1.2, True, 3, "silenzio")]
    )
    macchina.esegui(giri=1)
    errore = capsys.readouterr().err
    assert "1.2 s" in errore and "silenzio" in errore


def test_chiedi_conferma_con_vad_usa_il_cap_conferma():
    macchina, _, cervello, _ = _macchina(
        [], usa_vad=True, classificazioni=["si"], diagnostiche=[Diagnostica(0.9, True, 0, "silenzio")]
    )
    assert macchina.chiedi_conferma("Confermi?") is True
    [(cap, _silenzio_ms, _aggressivita, _)] = cervello.ascolti_vad
    assert cap == macchina.cap_conferma_s


def test_senza_vad_non_chiama_mai_ascolta_fino_al_silenzio():
    """usa_vad=False deve restare un vero ripiego, non un'etichetta senza effetto."""
    macchina, _, cervello, _ = _macchina([Risposta(testo="Ciao!")], usa_vad=False)
    macchina.esegui(giri=1)
    assert cervello.ascolti_vad == []
    assert len(cervello.ascolti) == 1


def test_main_spegne_la_radio_all_uscita(monkeypatch, tmp_path):
    """Bug del 21/9: BMO chiuso senza spegnere la radio la lasciava orfana."""
    import sys

    from bmo_core import macchina as macchina_modulo
    from bmo_core.radio import Radio

    class LettoreFinto:
        def __init__(self):
            self.spento = False

        def riproduci(self, tracce):
            pass

        def pausa(self):
            pass

        def riprendi(self):
            pass

        def stop(self):
            pass

        def successivo(self):
            pass

        def in_riproduzione(self):
            return False

        def spegni(self):
            self.spento = True

    lettore = LettoreFinto()
    cervello_finto = CervelloFinto([], FacciaFinta())
    monkeypatch.setattr(macchina_modulo, "Cervello", lambda **_: cervello_finto)
    monkeypatch.setattr(macchina_modulo, "Radio", lambda: Radio(lettore=lettore, percorso=tmp_path / "radio.json"))

    def _eof():
        raise EOFError

    monkeypatch.setattr("builtins.input", lambda: _eof())
    monkeypatch.setattr(sys, "argv", ["macchina", "--senza-timer"])
    macchina_modulo.main()
    assert lettore.spento is True


def test_esegui_resta_acceso_finche_la_radio_non_finisce_da_sola():
    """Chiesto il 21/9: Ctrl-D non deve spegnere qualcosa che sta ancora lavorando."""
    faccia = FacciaFinta()
    cervello = CervelloFinto([], faccia)
    stato_radio = iter([True, True, False])  # suona, suona, poi si è fermata da sola
    dormite = []
    dette = []
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=lambda: False,  # Ctrl-D subito
        voce=dette.append,
        qualcosa_attivo=lambda: next(stato_radio),
        dormi=dormite.append,
    )
    macchina.esegui()
    assert dormite == [macchina.attesa_spegnimento_s, macchina.attesa_spegnimento_s]
    assert dette == ["Radio o timer sono ancora attivi: resto acceso finché non finiscono da soli."]


def test_esegui_esce_subito_se_niente_e_attivo():
    faccia = FacciaFinta()
    cervello = CervelloFinto([], faccia)
    dormite = []
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=lambda: False,
        voce=lambda t: None,
        qualcosa_attivo=lambda: False,
        dormi=dormite.append,
    )
    macchina.esegui()
    assert dormite == []
