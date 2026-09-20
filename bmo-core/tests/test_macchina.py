from datetime import datetime, timedelta

import pytest
from google.genai import types

from bmo_core.adapters import (
    STATO_ASCOLTO,
    STATO_ASSONNATO,
    STATO_ERRORE,
    STATO_IDLE,
)
from bmo_core.brain import Cervello, Risposta
from bmo_core.config import FUSO_ORARIO
from bmo_core.macchina import Macchina, Stato
from bmo_core.modelli import GeminiNonDisponibile

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


class CervelloFinto:
    """Sostituto di Cervello: la macchina lo usa solo per ascoltare e rispondere."""

    def __init__(self, risposte, faccia=None):
        self._risposte = list(risposte)
        self.faccia = faccia
        self.ascolti = []
        self.strumenti_registrati = {}

    def registra_strumento(self, nome, esecutore):
        self.strumenti_registrati[nome] = esecutore

    def ascolta(self, durata_s):
        # Serve a controllare che la faccia cambi PRIMA di registrare.
        self.ascolti.append((durata_s, list(self.faccia.stati) if self.faccia else []))
        return b"RIFF"

    def rispondi(self, audio_wav=None, testo=None):
        risposta = self._risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta


def _macchina(risposte, orologio=None, richiami=1):
    faccia = FacciaFinta()
    cervello = CervelloFinto(risposte, faccia)
    dette = []
    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=lambda: True,
        voce=dette.append,
        orologio=orologio or OrologioFinto(),
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
