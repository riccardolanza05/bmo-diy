import base64

from bmo_face.animazione import ComandoFaccia
from bmo_face.protocollo import analizza_riga, applica, messaggio_immagine


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


def test_applica_immagine_decodifica_il_base64_e_imposta_scadenza_assoluta():
    comando = ComandoFaccia()
    dati_b64 = base64.b64encode(b"jpeg-finto").decode("ascii")
    applica(comando, {"cmd": "immagine", "data": dati_b64, "ttl": 4.0}, ora=10.0)
    assert comando.immagine == b"jpeg-finto"
    assert comando.immagine_scadenza == 14.0


def test_applica_immagine_con_base64_corrotto_non_solleva_e_non_tocca_niente():
    comando = ComandoFaccia(immagine=None, immagine_scadenza=None)
    applica(comando, {"cmd": "immagine", "data": "!!! non e' base64 valido !!!", "ttl": 4.0}, ora=10.0)
    assert comando.immagine is None
    assert comando.immagine_scadenza is None


def test_messaggio_immagine_si_analizza_e_si_applica_correttamente():
    riga = messaggio_immagine(b"jpeg-vero", ttl=8.0)
    messaggio = analizza_riga(riga)
    assert messaggio["cmd"] == "immagine"
    comando = ComandoFaccia()
    applica(comando, messaggio, ora=0.0)
    assert comando.immagine == b"jpeg-vero"
    assert comando.immagine_scadenza == 8.0


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
