"""Lettore musicale: mpv comandato dal suo socket IPC (§2.4 del piano).

La differenza con `MpvAdapter` e' che quello lancia un suono e se ne
dimentica (clip, toni), mentre qui mpv resta acceso in attesa e si comanda
mentre suona: pausa, traccia successiva, e in futuro il ducking quando BMO
parla sopra la musica.

Il socket sta nella cartella di runtime dell'utente (`XDG_RUNTIME_DIR`): il
piano dice `/run/mpv.sock`, che pero' sul PC di sviluppo vorrebbe i permessi
di root. Sul Pi, dove BMO e' un servizio di sistema, la variabile la mette
systemd.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path


def percorso_socket() -> Path:
    cartella = os.environ.get("XDG_RUNTIME_DIR") or "/dev/shm"
    return Path(cartella) / "bmo-mpv.sock"


class LettoreMpv:
    """mpv acceso in attesa, comandato da un socket."""

    def __init__(self, socket_path: Path | None = None, attesa_avvio_s: float = 3.0) -> None:
        self.socket_path = Path(socket_path) if socket_path else percorso_socket()
        self.attesa_avvio_s = attesa_avvio_s
        self._processo: subprocess.Popen | None = None

    # --- il processo ---------------------------------------------------------

    def _acceso(self) -> bool:
        return self._processo is not None and self._processo.poll() is None

    def _accendi(self) -> None:
        if self._acceso():
            return
        self.socket_path.unlink(missing_ok=True)
        self._processo = subprocess.Popen(
            [
                "mpv",
                "--idle=yes",          # resta acceso anche senza niente da suonare
                "--no-video",
                "--really-quiet",
                "--no-terminal",
                f"--input-ipc-server={self.socket_path}",
            ]
        )
        # mpv crea il socket dopo qualche decina di millisecondi: senza questa
        # attesa il primo comando andrebbe perso.
        scadenza = time.monotonic() + self.attesa_avvio_s
        while time.monotonic() < scadenza:
            if self.socket_path.exists():
                return
            time.sleep(0.02)

    def _comanda(self, *comando: object) -> dict | None:
        """Manda un comando a mpv e restituisce la sua risposta, se arriva."""
        self._accendi()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as presa:
                presa.settimeout(1.0)
                presa.connect(str(self.socket_path))
                presa.sendall(json.dumps({"command": list(comando)}).encode() + b"\n")
                risposta = presa.recv(65536).decode(errors="ignore")
        except (OSError, socket.timeout):
            return None
        for riga in risposta.splitlines():
            try:
                dato = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if "error" in dato:  # le righe senza "error" sono eventi, non risposte
                return dato
        return None

    # --- LettoreAdapter ------------------------------------------------------

    def riproduci(self, tracce: list[str]) -> None:
        for numero, traccia in enumerate(tracce):
            # La prima sostituisce quello che c'era, le altre si accodano.
            self._comanda("loadfile", traccia, "replace" if numero == 0 else "append")
        self._comanda("set_property", "pause", False)

    def pausa(self) -> None:
        self._comanda("set_property", "pause", True)

    def riprendi(self) -> None:
        self._comanda("set_property", "pause", False)

    def stop(self) -> None:
        self._comanda("stop")

    def successivo(self) -> None:
        self._comanda("playlist-next", "force")

    def in_riproduzione(self) -> bool:
        risposta = self._comanda("get_property", "playlist-count")
        return bool(risposta and risposta.get("error") == "success" and risposta.get("data"))

    def spegni(self) -> None:
        if self._acceso():
            self._comanda("quit")
            assert self._processo is not None
            try:
                self._processo.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._processo.terminate()
        self._processo = None
