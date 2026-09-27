"""Il server del socket Unix (§2.2): riceve i comandi di bmo-core.

Un thread per connessione (`socketserver.ThreadingMixIn`), niente di più:
bmo-core apre una sola connessione persistente e ci scrive una riga JSON per
comando (§2.2), quindi non serve altro che leggere finché non si chiude.
`ComandoFaccia` è condiviso con chi disegna (`animazione.Renderer`); un
`Lock` protegge le scritture del thread di rete dalle letture del ciclo di
disegno, che girano su thread diversi.
"""
from __future__ import annotations

import os
import socketserver
import threading
import time
from pathlib import Path
from typing import Callable

from .animazione import ComandoFaccia
from .protocollo import analizza_riga, applica

NOME_SOCKET = "bmo.sock"


def percorso_socket() -> Path:
    """Dove sta il socket: `/run/bmo.sock` sul Pi (un solo servizio, root),
    `$XDG_RUNTIME_DIR/bmo.sock` sul PC di sviluppo, `BMO_SOCKET` sempre prioritario.

    Stesso schema di `bmo_core.config.percorso_dati()`: bmo-face non importa
    bmo-core (pacchetti separati, isolamento dei guasti, §2.2), quindi la
    stessa idea si ripete qui invece di condividerla.
    """
    forzato = os.environ.get("BMO_SOCKET")
    if forzato:
        return Path(forzato)
    if Path("/run").is_dir() and os.access("/run", os.W_OK):
        return Path("/run/bmo.sock")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / NOME_SOCKET
    return Path(os.environ.get("TMPDIR", "/tmp")) / NOME_SOCKET


class _ThreadingUnixStreamServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class _Gestore(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: ServitoreFaccia = self.server.servitore_faccia  # type: ignore[attr-defined]
        for grezzo in self.rfile:
            messaggio = analizza_riga(grezzo.decode("utf-8", errors="replace"))
            if messaggio is None:
                continue
            with server.lock:
                applica(server.comando, messaggio, server.orologio())


class ServitoreFaccia:
    """Espone `comando` (un `ComandoFaccia` condiviso) e lo aggiorna dal socket.

    `avvia()`/`ferma()` girano il server in un thread separato: chi chiama
    (il loop di disegno della finestra) continua a girare sul thread
    principale, che su GTK deve restare libero per il main loop dell'interfaccia.
    """

    def __init__(
        self,
        percorso: Path | None = None,
        comando: ComandoFaccia | None = None,
        orologio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.percorso = percorso or percorso_socket()
        self.comando = comando or ComandoFaccia()
        self.orologio = orologio
        self.lock = threading.Lock()
        self._server: _ThreadingUnixStreamServer | None = None
        self._thread: threading.Thread | None = None

    def avvia(self) -> None:
        # Un socket Unix lasciato da un avvio precedente (crash, kill -9)
        # impedisce il bind col solito "Address already in use": un file
        # rimasto lì non significa che qualcuno lo stia ancora ascoltando.
        if self.percorso.exists():
            self.percorso.unlink()
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        self._server = _ThreadingUnixStreamServer(str(self.percorso), _Gestore)
        self._server.servitore_faccia = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def ferma(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self.percorso.exists():
            self.percorso.unlink()
