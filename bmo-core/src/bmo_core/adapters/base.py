"""Interfacce (Protocol) che ogni adapter hardware deve rispettare.

bmo-core parla solo con queste interfacce: la scelta dell'implementazione
concreta (PC di sviluppo vs Raspberry Pi) avviene in un unico punto
(factory.py), cosi' il resto del codice non sa mai su quale hardware gira.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Protocol

from ..vad import Diagnostica

# Stati della faccia (§2.1). Sono un'altra cosa dalle espressioni che sceglie
# il modello per la risposta parlata: questi li decide il codice per dire a
# chi guarda cosa sta facendo BMO. Stanno qui, accanto al Protocol, perche'
# sono parte del contratto della faccia e perche' cosi' anche chi non parla
# con Gemini (la sveglia dei timer) puo' usarli senza importare il cervello.
STATO_ASSONNATO = "assonnato"  # acceso ma non in ascolto: avvio e pausa
STATO_IDLE = "idle"            # sveglio, in attesa di essere chiamato
STATO_ASCOLTO = "ascolto"
STATO_PENSIERO = "pensiero"
STATO_PARLATO = "parlato"
STATO_TIMER = "timer"
STATO_ERRORE = "errore-rete"
STATO_CONFERMA = "conferma"  # sotto-dialogo proponi/conferma, in attesa di un sì o un no (#17)


class CameraAdapter(Protocol):
    """Cattura una singola foto e la scrive su disco come JPEG."""

    def scatta_foto(self, destinazione: Path) -> Path: ...


class AudioInputAdapter(Protocol):
    """Ingresso microfono.

    flusso_pcm() serve alla wake word (ascolto continuo); registra() è la
    cattura a durata fissa, utile per prove scriptate (`--wav`, `--durata`).
    registra_fino_al_silenzio() è quella usata davvero in conversazione
    (macchina.py): si ferma da sola quando rileva silenzio dopo la voce
    (vad.py), non dopo un numero di secondi deciso in anticipo.
    """

    def flusso_pcm(self) -> Iterator[bytes]: ...

    def registra(self, destinazione: Path, durata_s: float) -> Path: ...

    def registra_fino_al_silenzio(
        self, destinazione: Path, cap_s: float, silenzio_ms: float, aggressivita: int
    ) -> tuple[Path, Diagnostica]: ...


class FacciaAdapter(Protocol):
    """La faccia di BMO: mostra lo stato in cui si trova (§2.1).

    BMO non ha pulsanti ne' spie: la faccia e' l'unico modo che ha di dire
    che sta ascoltando, che sta elaborando o che qualcosa e' andato storto.
    Serve soprattutto nei secondi in cui tace, che altrimenti non si
    distinguono da un guasto. Il disegno vero arriva con l'issue #23.
    """

    def mostra(self, stato: str) -> None: ...


class AudioOutputAdapter(Protocol):
    """Riproduzione audio breve e senza comandi: clip, toni, voce."""

    def riproduci(self, sorgente: Path | str) -> None: ...

    def attendi(self, timeout_s: float | None = None) -> None: ...

    def ferma(self) -> None: ...


class LettoreAdapter(Protocol):
    """Lettore musicale, che a differenza delle clip si comanda mentre suona.

    §2.4: mpv gira sempre con un socket IPC, e pausa, volume e ducking sono
    comandi su quel socket.
    """

    def riproduci(self, tracce: list[str]) -> None: ...

    def pausa(self) -> None: ...

    def riprendi(self) -> None: ...

    def stop(self) -> None: ...

    def successivo(self) -> None: ...

    def in_riproduzione(self) -> bool: ...

    def spegni(self) -> None: ...


class VolumeAdapter(Protocol):
    """Il volume dell'altoparlante: riguarda tutto quello che BMO emette."""

    def imposta(self, percentuale: int) -> None: ...

    def leggi(self) -> int | None: ...
