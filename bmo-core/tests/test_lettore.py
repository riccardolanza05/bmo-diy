"""Prove di LettoreMpv senza mpv vero: un ascoltatore Unix finto sul socket.

Bug del 21/9: BMO chiuso senza spegnere la radio prima lasciava mpv orfano
(acceso, udibile, incontrollabile), e la sessione successiva ne apriva un
secondo sopra cancellando il socket del primo — da qui "dice che è chiusa"
mentre la radio continuava a suonare.
"""
import json
import socket
import threading

from bmo_core.adapters.lettore import LettoreMpv


class AscoltatoreFinto:
    """Un socket Unix che risponde come farebbe mpv, senza esserlo."""

    def __init__(self, percorso, risposta=None):
        self.percorso = percorso
        self.risposta = risposta if risposta is not None else {"error": "success"}
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(percorso))
        self._sock.listen(1)
        self.ricevuti = []
        self._attivo = True
        self._thread = threading.Thread(target=self._ascolta, daemon=True)
        self._thread.start()

    def _ascolta(self):
        while self._attivo:
            self._sock.settimeout(0.2)
            try:
                connessione, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            with connessione:
                dati = connessione.recv(65536)
                if dati:
                    self.ricevuti.append(json.loads(dati.decode()))
                    connessione.sendall(json.dumps(self.risposta).encode() + b"\n")

    def chiudi(self):
        self._attivo = False
        self._thread.join(timeout=1)
        self._sock.close()


def test_raggiungibile_falso_senza_niente_al_socket(tmp_path):
    lettore = LettoreMpv(socket_path=tmp_path / "assente.sock")
    assert lettore._raggiungibile() is False


def test_raggiungibile_vero_con_un_ascoltatore_reale(tmp_path):
    percorso = tmp_path / "finto.sock"
    finto = AscoltatoreFinto(percorso)
    try:
        lettore = LettoreMpv(socket_path=percorso)
        assert lettore._raggiungibile() is True
    finally:
        finto.chiudi()


def test_accendi_non_apre_un_secondo_mpv_se_uno_e_gia_vivo(tmp_path):
    percorso = tmp_path / "finto.sock"
    finto = AscoltatoreFinto(percorso)
    try:
        lettore = LettoreMpv(socket_path=percorso)
        lettore._accendi()
        assert lettore._processo is None  # non ne ha acceso uno suo
        assert percorso.exists()  # non ha cancellato il socket di quello vivo
    finally:
        finto.chiudi()


def test_spegni_manda_quit_a_un_mpv_non_acceso_da_questa_istanza(tmp_path):
    """Il caso del bug: si riprende in mano un mpv orfano e lo si spegne per davvero."""
    percorso = tmp_path / "finto.sock"
    finto = AscoltatoreFinto(percorso)
    try:
        lettore = LettoreMpv(socket_path=percorso)
        assert lettore._acceso() is False  # non l'ha acceso questa istanza
        lettore.spegni()
        assert {"command": ["quit"]} in finto.ricevuti
    finally:
        finto.chiudi()


def test_spegni_senza_niente_acceso_non_solleva(tmp_path):
    lettore = LettoreMpv(socket_path=tmp_path / "assente.sock")
    lettore.spegni()  # non deve sollevare, e non deve provare a spegnere niente


def test_in_riproduzione_falso_senza_accendere_mpv(tmp_path):
    """Una semplice interrogazione non deve accendere mpv dal nulla.

    Prima del fix, `in_riproduzione()` passava da `_comanda()`, che chiama
    `_accendi()`: bastava chiedere lo stato per far partire un mpv idle,
    cosa che sarebbe capitata ad ogni turno di ascolto una volta collegata
    la sospensione della radio durante il microfono aperto.
    """
    percorso = tmp_path / "assente.sock"
    lettore = LettoreMpv(socket_path=percorso)
    assert lettore.in_riproduzione() is False
    assert lettore._processo is None
    assert not percorso.exists()


def test_in_riproduzione_vero_con_una_playlist_caricata(tmp_path):
    percorso = tmp_path / "finto.sock"
    finto = AscoltatoreFinto(percorso, risposta={"error": "success", "data": 1})
    try:
        lettore = LettoreMpv(socket_path=percorso)
        assert lettore.in_riproduzione() is True
        assert lettore._processo is None  # interrogazione, non accensione
    finally:
        finto.chiudi()
