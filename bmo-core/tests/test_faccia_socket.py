import json
import socket
import threading
import time

from bmo_core.adapters.faccia import FacciaSocket


class _ServerFinto:
    """Un socket Unix minimo, solo per verificare cosa FacciaSocket manda."""

    def __init__(self, percorso):
        self.percorso = percorso
        self.righe = []
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(percorso))
        self._server.listen(1)
        self._thread = threading.Thread(target=self._accetta, daemon=True)
        self._thread.start()

    def _accetta(self):
        conn, _ = self._server.accept()
        with conn:
            for riga in conn.makefile("r"):
                self.righe.append(json.loads(riga))

    def chiudi(self):
        self._server.close()


def test_manda_i_messaggi_giusti_per_ciascun_metodo(tmp_path):
    percorso = tmp_path / "bmo.sock"
    server = _ServerFinto(percorso)
    try:
        faccia = FacciaSocket(percorso)
        faccia.mostra("ascolto")
        faccia.esprimi("felice", ttl=2.5)
        faccia.livello(0.42)
        faccia.parla([0.1, 0.2], fps=10)
        faccia.timer(120, "pasta")
        faccia._socket.close()  # forza il flush lato client prima di leggere
    finally:
        time.sleep(0.2)
        server.chiudi()
    assert server.righe == [
        {"cmd": "state", "value": "ascolto"},
        {"cmd": "expression", "value": "felice", "ttl": 2.5},
        {"cmd": "level", "value": 0.42},
        {"cmd": "speak", "envelope": [0.1, 0.2], "fps": 10},
        {"cmd": "timer", "remaining": 120, "label": "pasta"},
    ]


def test_senza_server_in_ascolto_non_solleva(tmp_path):
    """bmo-face non ancora avviato: la faccia resta silenziosamente muta,
    non deve mai far fallire un turno di conversazione (#23)."""
    faccia = FacciaSocket(tmp_path / "nessuno-ascolta.sock")
    faccia.mostra("ascolto")  # nessuna eccezione
    faccia.livello(0.5)
