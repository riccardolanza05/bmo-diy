"""Il lato bmo-face dei video: riceve i fotogrammi rgb565 che bmo-core decodifica.

bmo-core decodifica con ffmpeg (è lui che possiede audio e volume) e manda
ogni fotogramma come **un datagram Unix** a questo socket. Scelta deliberata:
un datagram è atomico e, se bmo-face è lento o non c'è, bmo-core lo scarta
senza bloccarsi. Uno stream o una FIFO farebbero l'opposto: bmo-face morto =
ffmpeg bloccato o ucciso = audio interrotto, cioè nessun isolamento dei guasti
(§2.2).

Il datagram è `<HH` (larghezza, altezza) seguito da larghezza×altezza×2 byte
di rgb565 little endian. Qui si tiene **solo l'ultimo** fotogramma: chi
disegna (il pannello) prende il più recente e scarta gli intermedi, così un
Pi lento perde fluidità ma non accumula ritardo.
"""
from __future__ import annotations

import os
import socket
import struct
import threading
import time
from pathlib import Path

NOME_SOCKET_VIDEO = "bmo-video.sock"
INTESTAZIONE = struct.Struct("<HH")
MASSIMO = INTESTAZIONE.size + 320 * 240 * 2


def percorso_socket_video(socket_comandi: Path) -> Path:
    """Accanto al socket dei comandi (stesso schema di `bmo_core.video`), salvo `BMO_SOCKET_VIDEO`."""
    forzato = os.environ.get("BMO_SOCKET_VIDEO")
    return Path(forzato) if forzato else socket_comandi.with_name(NOME_SOCKET_VIDEO)


class Fotogramma:
    __slots__ = ("larghezza", "altezza", "dati", "numero", "arrivato")

    def __init__(self, larghezza: int, altezza: int, dati: bytes, numero: int, arrivato: float) -> None:
        self.larghezza, self.altezza, self.dati, self.numero, self.arrivato = larghezza, altezza, dati, numero, arrivato


class RiceviFotogrammi:
    def __init__(self, percorso: Path, orologio=time.monotonic) -> None:
        self.percorso = percorso
        self.orologio = orologio
        self._condizione = threading.Condition()
        self._ultimo: Fotogramma | None = None
        self._contatore = 0
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self.scartati = 0  # datagram di forma sbagliata

    def avvia(self) -> None:
        if self.percorso.exists():
            self.percorso.unlink()
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        s.bind(str(self.percorso))
        s.settimeout(0.5)
        self._socket = s
        self._thread = threading.Thread(target=self._ascolta, daemon=True)
        self._thread.start()

    def _ascolta(self) -> None:
        while self._socket is not None:
            try:
                datagram = self._socket.recv(MASSIMO + 64)
            except socket.timeout:
                continue
            except OSError:
                return
            if len(datagram) < INTESTAZIONE.size:
                self.scartati += 1
                continue
            larghezza, altezza = INTESTAZIONE.unpack_from(datagram)
            dati = datagram[INTESTAZIONE.size:]
            if larghezza == 0 or altezza == 0 or len(dati) != larghezza * altezza * 2:
                self.scartati += 1
                continue
            with self._condizione:
                self._contatore += 1
                self._ultimo = Fotogramma(larghezza, altezza, dati, self._contatore, self.orologio())
                self._condizione.notify_all()

    def nuovo(self, dopo: int, attesa: float) -> Fotogramma | None:
        """Il fotogramma più recente se è più nuovo di `dopo`, altrimenti aspetta fino a `attesa` secondi."""
        with self._condizione:
            if self._ultimo is None or self._ultimo.numero <= dopo:
                self._condizione.wait(timeout=attesa)
            if self._ultimo is not None and self._ultimo.numero > dopo:
                return self._ultimo
            return None

    def numero_attuale(self) -> int:
        with self._condizione:
            return self._contatore

    def ultimo_arrivo(self) -> float | None:
        with self._condizione:
            return self._ultimo.arrivato if self._ultimo else None

    def ferma(self) -> None:
        s, self._socket = self._socket, None
        if s is not None:
            s.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self.percorso.exists():
            self.percorso.unlink()
