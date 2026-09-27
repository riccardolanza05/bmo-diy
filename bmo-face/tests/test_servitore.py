import socket
import time

from bmo_face.servitore import ServitoreFaccia


def _connetti_e_manda(percorso, righe, attesa_s=1.0):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(percorso))
        for riga in righe:
            client.sendall(riga.encode("utf-8"))
        client.shutdown(socket.SHUT_WR)
        time.sleep(0.1)  # lascia tempo al thread del server di leggere


def test_servitore_riceve_e_applica_i_comandi(tmp_path):
    percorso = tmp_path / "bmo.sock"
    servitore = ServitoreFaccia(percorso=percorso, orologio=lambda: 42.0)
    servitore.avvia()
    try:
        _connetti_e_manda(
            percorso,
            [
                '{"cmd":"state","value":"ascolto"}\n',
                '{"cmd":"level","value":0.7}\n',
            ],
        )
        assert servitore.comando.stato == "ascolto"
        assert servitore.comando.livello == 0.7
    finally:
        servitore.ferma()


def test_servitore_ignora_righe_rotte_senza_chiudere_la_connessione(tmp_path):
    percorso = tmp_path / "bmo.sock"
    servitore = ServitoreFaccia(percorso=percorso, orologio=lambda: 0.0)
    servitore.avvia()
    try:
        _connetti_e_manda(
            percorso,
            [
                "{questo non e' json\n",
                '{"cmd":"state","value":"pensiero"}\n',
            ],
        )
        assert servitore.comando.stato == "pensiero"
    finally:
        servitore.ferma()


def test_avvia_rimuove_un_socket_lasciato_da_un_avvio_precedente(tmp_path):
    percorso = tmp_path / "bmo.sock"
    percorso.write_text("file lasciato da un crash precedente")
    servitore = ServitoreFaccia(percorso=percorso)
    servitore.avvia()
    try:
        assert percorso.exists()  # ora è un vero socket, non il file di prima
    finally:
        servitore.ferma()
    assert not percorso.exists()  # ferma() pulisce anche lei
