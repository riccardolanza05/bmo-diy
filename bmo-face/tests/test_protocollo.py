from bmo_face.animazione import ComandoFaccia
from bmo_face.protocollo import analizza_riga, applica


def test_analizza_riga_vuota_o_rotta_e_none():
    assert analizza_riga("") is None
    assert analizza_riga("   \n") is None
    assert analizza_riga("{non valido") is None
    assert analizza_riga("[1, 2, 3]") is None  # valido come JSON, ma non un dizionario


def test_analizza_riga_valida():
    assert analizza_riga('{"cmd":"state","value":"ascolto"}') == {"cmd": "state", "value": "ascolto"}


def test_applica_state_cambia_lo_stato():
    comando = ComandoFaccia(stato="idle")
    applica(comando, {"cmd": "state", "value": "ascolto"}, ora=0.0)
    assert comando.stato == "ascolto"


def test_applica_speak_imposta_linviluppo_e_lorigine_dei_tempi():
    comando = ComandoFaccia()
    applica(comando, {"cmd": "speak", "envelope": [0.1, 0.5, 0.9], "fps": 20}, ora=12.5)
    assert comando.inviluppo == [0.1, 0.5, 0.9]
    assert comando.inviluppo_fps == 20
    assert comando.inviluppo_inizio == 12.5


def test_applica_expression_imposta_scadenza_assoluta():
    comando = ComandoFaccia()
    applica(comando, {"cmd": "expression", "value": "felice", "ttl": 2.0}, ora=10.0)
    assert comando.espressione == "felice"
    assert comando.espressione_scadenza == 12.0


def test_applica_timer():
    comando = ComandoFaccia()
    applica(comando, {"cmd": "timer", "remaining": 312, "label": "pasta"}, ora=0.0)
    assert comando.timer_rimanente == 312
    assert comando.timer_etichetta == "pasta"


def test_applica_level():
    comando = ComandoFaccia()
    applica(comando, {"cmd": "level", "value": 0.34}, ora=0.0)
    assert comando.livello == 0.34


def test_applica_comando_sconosciuto_non_tocca_niente():
    comando = ComandoFaccia(stato="idle", livello=0.1)
    applica(comando, {"cmd": "boh"}, ora=0.0)
    assert comando.stato == "idle"
    assert comando.livello == 0.1


def test_applica_messaggio_senza_campi_richiesti_non_solleva():
    comando = ComandoFaccia(stato="idle")
    applica(comando, {"cmd": "state"}, ora=0.0)  # "value" mancante
    applica(comando, {"cmd": "level"}, ora=0.0)  # "value" mancante
    assert comando.stato == "idle"  # invariato, nessuna eccezione
