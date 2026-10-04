"""Il punto d'ingresso senza schermo di bmo-face, per il Pi (issue #63).

`finestra.py` (issue #23) resta il tool di sviluppo su GTK; questo modulo è
quello che gira davvero sul Pi, dove non c'è né schermo né GTK: avvia
`ServitoreFaccia` e `Renderer` (già misurati senza GTK, 33 MB/215 fps sul Pi,
issue #58) e disegna su un'`UscitaPannello` scelta da riga di comando.

Il fotogramma va ridisegnato solo quando cambia (§2.11: niente 25 fps fissi
a vuoto se la faccia è ferma) — confrontando i byte del fotogramma appena
calcolato con l'ultimo inviato, non affidandosi a un evento esplicito di
"stato cambiato": molte animazioni (il battito irregolare, il countdown del
timer) cambiano il fotogramma senza che nessun comando del socket arrivi nel
frattempo.

Uso:
    python -m bmo_face.pannello --assets assets/                    # calcola e scarta (fase 2.3)
    python -m bmo_face.pannello --assets assets/ --uscita spi        # display vero (fase 4.5/4.7)
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .animazione import Renderer
from .formato import NOME_BIN, NOME_JSON, carica_manifesto, mappa_bin
from .servitore import ServitoreFaccia
from .spi import rgb565_big_endian
from .video import RiceviFotogrammi, percorso_socket_video

FPS_PANNELLO = 25.0
# Se un video è "attivo" e non arriva un fotogramma da tanto (bmo-core morto
# senza dire `stop`), la faccia torna da sola invece di restare congelata.
SILENZIO_VIDEO_S = 5.0


class UscitaPannello:
    """Dove finiscono i fotogrammi disegnati. Un solo metodo, un fotogramma
    completo alla volta: se in futuro l'uscita SPI vorrà limitarsi alle
    regioni cambiate, è lei a poterlo scoprire tenendo il fotogramma
    precedente — qui basta sapere quando chiamarla."""

    def disegna_frame(self, frame: Image.Image) -> None:
        raise NotImplementedError

    # Il video (bmo-core lo decodifica, qui arriva già in rgb565 della forma
    # giusta): l'uscita SPI disegnerà solo quel rettangolo, centrato, e
    # lascerà spente le bande. I tre metodi hanno un default che non fa
    # niente, così un'uscita che non sa di video non si rompe.
    def inizio_video(self, larghezza: int, altezza: int) -> None:
        """Il video parte: l'uscita può pulire le bande e preparare la finestra."""

    def disegna_video(self, dati: bytes, larghezza: int, altezza: int) -> None:
        """Un fotogramma rgb565 (2 byte per pixel, little endian)."""

    def fine_video(self) -> None:
        """Il video è finito: la faccia sta per tornare, da ridisegnare per intero."""

    def chiudi(self) -> None:
        """Si esce: l'uscita libera ciò che ha preso (SPI, pin, backlight)."""


class UscitaNulla(UscitaPannello):
    """Calcola e butta via: serve alla fase 2.3 per misurare RAM e CPU veri
    di bmo-face senza bisogno del display, e a qualunque test automatico."""

    def __init__(self) -> None:
        self.fotogrammi_inviati = 0
        self.fotogrammi_video = 0
        self.video_iniziati = 0
        self.video_finiti = 0

    def disegna_frame(self, frame: Image.Image) -> None:
        self.fotogrammi_inviati += 1

    def inizio_video(self, larghezza: int, altezza: int) -> None:
        self.video_iniziati += 1

    def disegna_video(self, dati: bytes, larghezza: int, altezza: int) -> None:
        self.fotogrammi_video += 1

    def fine_video(self) -> None:
        self.video_finiti += 1


class UscitaSpi(UscitaPannello):
    """Il display vero, un ILI9341 su SPI0 (issue #77; pin e orientamento da `BMO_SPI_*`, vedi `spi.py`).

    Un fotogramma pieno 320×240 sono 150 kB: a 20 MHz un'intera schermata costa
    ~60 ms, troppo per tenere i 25 fps. Per questo si tiene l'ultimo fotogramma
    inviato e si scrive solo il rettangolo che contiene i pixel cambiati (un
    battito di palpebre o la bocca che si muove ne toccano una piccola parte).

    I video arrivano in RGB565 little endian (`bmo_core.video`); l'ILI9341 vuole
    il byte alto per primo, quindi si scambia l'ordine dei byte. Il video occupa
    un rettangolo centrato e le bande restano nere.
    """

    def __init__(self, display=None) -> None:
        if display is None:
            from .spi import crea_display_da_ambiente

            display = crea_display_da_ambiente()
        self.display = display
        self.display.inizializza()
        self.display.riempi((0, 0, 0))  # senza, un ILI9341 appena acceso mostra il bianco
        self._ultimo: np.ndarray | None = None
        self._origine_video = (0, 0)
        self.fotogrammi_inviati = 0
        self.byte_inviati = 0

    def _scrivi(self, x: int, y: int, larghezza: int, altezza: int, pixel: bytes) -> None:
        self.display.scrivi(x, y, larghezza, altezza, pixel)
        self.byte_inviati += len(pixel)

    def disegna_frame(self, frame: Image.Image) -> None:
        corrente = np.asarray(frame.convert("RGB"), dtype=np.uint8)
        if self._ultimo is None or self._ultimo.shape != corrente.shape:
            x, y, larghezza, altezza = 0, 0, corrente.shape[1], corrente.shape[0]
        else:
            diversi = np.any(corrente != self._ultimo, axis=2)
            righe = np.flatnonzero(diversi.any(axis=1))
            if righe.size == 0:
                return
            colonne = np.flatnonzero(diversi.any(axis=0))
            x, y = int(colonne[0]), int(righe[0])
            larghezza, altezza = int(colonne[-1]) - x + 1, int(righe[-1]) - y + 1
        self._scrivi(x, y, larghezza, altezza, rgb565_big_endian(corrente[y:y + altezza, x:x + larghezza]))
        self._ultimo = corrente
        self.fotogrammi_inviati += 1

    def inizio_video(self, larghezza: int, altezza: int) -> None:
        self.display.riempi((0, 0, 0))
        self._origine_video = (
            max(0, (self.display.larghezza - larghezza) // 2),
            max(0, (self.display.altezza - altezza) // 2),
        )
        self._ultimo = None

    def disegna_video(self, dati: bytes, larghezza: int, altezza: int) -> None:
        if larghezza > self.display.larghezza or altezza > self.display.altezza:
            return  # più grande dello schermo: nessun ritaglio, meglio saltarlo che disegnare male
        grezzo = np.frombuffer(dati, dtype="<u2").astype(">u2").tobytes()
        self._scrivi(*self._origine_video, larghezza, altezza, grezzo)
        self.fotogrammi_inviati += 1

    def fine_video(self) -> None:
        self._ultimo = None  # sullo schermo ci sono i resti del video: la faccia si riscrive per intero

    def chiudi(self) -> None:
        self.display.chiudi()


def crea_uscita(nome: str) -> UscitaPannello:
    if nome == "nulla":
        return UscitaNulla()
    if nome == "spi":
        return UscitaSpi()
    raise ValueError(f"uscita sconosciuta: {nome!r}")


def esegui_pannello(
    renderer: Renderer,
    servitore: ServitoreFaccia,
    uscita: UscitaPannello,
    *,
    fps: float = FPS_PANNELLO,
    orologio=time.monotonic,
    dormi=time.sleep,
    ancora=lambda: True,
    ricevitore: RiceviFotogrammi | None = None,
) -> None:
    """Il loop principale: nessun main loop di GTK qui, solo un polling a
    `fps` che disegna e manda all'uscita solo i fotogrammi diversi dal
    precedente. `ancora` e `dormi` sono iniettabili per i test (nessuna
    attesa reale, nessun loop infinito)."""
    ultimo_grezzo: bytes | None = None
    periodo = 1.0 / fps
    in_video = False
    primo = False
    ultimo_numero = 0
    ultima_attivita = orologio()
    while ancora():
        inizio = orologio()
        comando = servitore.comando_snapshot()
        if comando.video_attivo and ricevitore is not None:
            # Il video prende il posto della faccia. Si aspetta il prossimo
            # fotogramma (al massimo un periodo) invece di sondare a 25 Hz:
            # un video a 24 fps non deve perdere fotogrammi per l'aliasing.
            if not in_video:
                in_video = True
                ultima_attivita = inizio
                primo = True
                # I fotogrammi di un video precedente ancora nel ricevitore non contano.
                ultimo_numero = ricevitore.numero_attuale()
            fotogramma = ricevitore.nuovo(ultimo_numero, periodo)
            if fotogramma is not None:
                if primo:
                    primo = False
                    uscita.inizio_video(fotogramma.larghezza, fotogramma.altezza)
                ultimo_numero = fotogramma.numero
                ultima_attivita = orologio()
                uscita.disegna_video(fotogramma.dati, fotogramma.larghezza, fotogramma.altezza)
            elif not comando.video_in_pausa and orologio() - ultima_attivita > SILENZIO_VIDEO_S:
                with servitore.lock:
                    servitore.comando.video_attivo = False
                    servitore.comando.video_titolo = None
            elif comando.video_in_pausa:
                ultima_attivita = orologio()
            continue
        if in_video:
            in_video = False
            uscita.fine_video()
            ultimo_grezzo = None  # lo schermo ha i resti del video: la faccia si ridisegna per intero
        frame = renderer.disegna(comando, inizio)
        grezzo = frame.tobytes()
        if grezzo != ultimo_grezzo:
            uscita.disegna_frame(frame)
            ultimo_grezzo = grezzo
        trascorso = orologio() - inizio
        resto = periodo - trascorso
        if resto > 0:
            dormi(resto)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assets", type=Path, default=Path("."), help="cartella con faces.bin e faces.json")
    parser.add_argument("--uscita", choices=("nulla", "spi"), default="nulla", help="dove disegnare i fotogrammi")
    parser.add_argument("--socket", type=Path, default=None, help="percorso del socket Unix (predefinito: automatico)")
    parser.add_argument("--fps", type=float, default=FPS_PANNELLO, help="frequenza massima di ridisegno")
    argomenti = parser.parse_args()

    uscita = crea_uscita(argomenti.uscita)
    manifesto = carica_manifesto(argomenti.assets / NOME_JSON)

    with mappa_bin(argomenti.assets / NOME_BIN) as dati:
        renderer = Renderer(manifesto, dati)
        servitore = ServitoreFaccia(percorso=argomenti.socket)
        servitore.avvia()
        ricevitore = RiceviFotogrammi(percorso_socket_video(servitore.percorso))
        ricevitore.avvia()
        print(f"[pannello: uscita={argomenti.uscita}, socket su {servitore.percorso}]", file=sys.stderr)

        fermare = False

        def gestisci_stop(signum, frame) -> None:  # noqa: ANN001 - firma imposta da signal
            nonlocal fermare
            fermare = True

        signal.signal(signal.SIGTERM, gestisci_stop)
        signal.signal(signal.SIGINT, gestisci_stop)

        try:
            esegui_pannello(renderer, servitore, uscita, fps=argomenti.fps, ancora=lambda: not fermare,
                            ricevitore=ricevitore)
        finally:
            ricevitore.ferma()
            servitore.ferma()
            uscita.chiudi()


if __name__ == "__main__":
    main()
