"""Il motore di animazione: funzione pura del tempo e dei comandi (issue #23).

Nessuna funzione qui dentro tocca un socket, una finestra o un orologio di
sistema: `Renderer.disegna(comando, t)` prende un tempo esplicito e restituisce
sempre lo stesso fotogramma per lo stesso `(comando, t)`. È quel che rende il
motore testabile senza schermo (dump dei fotogrammi in PNG) e senza dover
aspettare i tempi veri di un battito di palpebre nei test.

`ComandoFaccia` è lo stato che i cinque messaggi del socket (§2.2) aggiornano
(`state`, `speak`, `expression`, `timer`, `level`): chi legge il socket muta
questo oggetto, chi disegna lo legge soltanto.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .formato import Manifesto, rgb888_da_565

# Battito di palpebre irregolare (§2.11: "la regolarità è ciò che fa sembrare
# morta un'animazione"), ma calcolato una volta sola su un superperiodo fisso
# invece che accumulando cicli dall'avvio: a un BMO acceso per ore un calcolo
# che cresce con `t` diventerebbe via via più lento a ogni fotogramma.
# 47 s non è un numero tondo apposta, per non entrare in fase con l'fps di
# disegno o con altri periodi dell'interfaccia.
_SUPERPERIODO_BATTITO_S = 47.0
_DURATA_BATTITO_S = 0.15
_PERIODO_MIN_S = 2.0
_PERIODO_MAX_S = 4.5


def _tempi_battito() -> list[float]:
    tempi = []
    t = 0.0
    ciclo = 0
    while t < _SUPERPERIODO_BATTITO_S:
        seme = int.from_bytes(hashlib.sha256(str(ciclo).encode()).digest()[:4], "big")
        t += _PERIODO_MIN_S + (seme % 10_000) / 10_000 * (_PERIODO_MAX_S - _PERIODO_MIN_S)
        if t < _SUPERPERIODO_BATTITO_S:
            tempi.append(t)
        ciclo += 1
    return tempi


_TEMPI_BATTITO = _tempi_battito()


def in_battito(t: float) -> bool:
    """True nei ~150 ms in cui `idle` deve mostrare l'occhio chiuso."""
    fase = t % _SUPERPERIODO_BATTITO_S
    return any(inizio <= fase < inizio + _DURATA_BATTITO_S for inizio in _TEMPI_BATTITO)


def _indice_ciclico(t: float, fps: float, n_frame: int) -> int:
    if n_frame <= 1 or fps <= 0:
        return 0
    return int(t * fps) % n_frame


def indice_corpo(stato: str, t: float, manifesto: Manifesto) -> int:
    """Quale fotogramma del ciclo `corpo[stato]` mostrare al tempo `t`.

    `idle` è un caso speciale: i suoi due soli fotogrammi (aperto, chiuso)
    non scorrono a `fps` fissa come gli altri stati, li sceglie il battito
    irregolare qui sopra — è per questo che `arte_placeholder.corpo_idle`
    genera "aperto, aperto, ..., chiuso" e non un ciclo uniforme.
    """
    anim = manifesto.corpo[stato]
    if stato == "idle" and anim.frames >= 2:
        return anim.frames - 1 if in_battito(t) else 0
    return _indice_ciclico(t, anim.fps, anim.frames)


def indice_da_livello(livello: float, n_frame: int) -> int:
    """Quale fotogramma di un overlay (bocca/pupille) corrisponde a `livello` (0-1)."""
    if n_frame <= 1:
        return 0
    livello = max(0.0, min(1.0, livello))
    return round(livello * (n_frame - 1))


@dataclass
class ComandoFaccia:
    """Lo stato mutabile che i messaggi del socket (§2.2) aggiornano.

    `livello` serve a due cose diverse a seconda dello stato: il livello del
    microfono durante `ascolto` (comando `level`), il campione corrente
    dell'inviluppo RMS della voce durante `parlato` (comando `speak`, letto
    da chi gestisce il socket in base al tempo trascorso dall'inizio della
    battuta — questo modulo vede solo il valore già campionato).
    """

    stato: str = "idle"
    livello: float = 0.0  # dal comando `level` (§2.2): guida solo le pupille durante `ascolto`
    espressione: str | None = None
    espressione_scadenza: float | None = None  # tempo assoluto, stesso orologio di `t`
    timer_rimanente: int | None = None
    timer_etichetta: str | None = None
    # Dal comando `speak` (§2.2): la bocca durante `parlato` non segue
    # `livello` ma campiona questo inviluppo in base al tempo trascorso da
    # `inviluppo_inizio` — è così che bmo-core manda tutto l'inviluppo RMS
    # della battuta in un solo messaggio invece di uno per fotogramma.
    inviluppo: list[float] | None = None
    inviluppo_fps: float = 25.0
    inviluppo_inizio: float | None = None


def livello_bocca(comando: ComandoFaccia, t: float) -> float:
    """Il campione dell'inviluppo `speak` al tempo `t`, o 0 se non ce n'è uno attivo."""
    if not comando.inviluppo or comando.inviluppo_inizio is None:
        return 0.0
    trascorso = t - comando.inviluppo_inizio
    if trascorso < 0:
        return 0.0
    indice = int(trascorso * comando.inviluppo_fps)
    if indice >= len(comando.inviluppo):
        return 0.0  # la battuta è finita: bocca chiusa, non l'ultimo campione congelato
    return comando.inviluppo[indice]


_PERCORSI_FONT = (
    "/usr/share/fonts/liberation/LiberationMono-Bold.ttf",  # Arch/Omarchy
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",  # Debian/Raspberry Pi OS
)


@lru_cache(maxsize=8)
def _font(dimensione: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Liberation Mono se c'è (licenza permissiva, pacchetto comune su Linux);
    il bitmap predefinito di PIL altrimenti — mai un font mancante che blocca BMO.

    In cache: senza, il countdown del timer riaprirebbe e ricaricherebbe il
    file TTF dal disco a ogni fotogramma (fino a 25 volte al secondo), un
    costo di I/O per niente quando la dimensione richiesta è sempre la stessa
    per un dato pannello.
    """
    for percorso in _PERCORSI_FONT:
        if Path(percorso).exists():
            return ImageFont.truetype(percorso, dimensione)
    return ImageFont.load_default(size=dimensione)


def _mmss(secondi: int) -> str:
    secondi = max(0, secondi)
    m, s = divmod(secondi, 60)
    return f"{m}:{s:02d}"


class Renderer:
    """Legge `faces.bin` (bytes o `mmap`) secondo `manifesto` e compone i fotogrammi."""

    def __init__(self, manifesto: Manifesto, dati: Any) -> None:
        self.manifesto = manifesto
        self.dati = dati

    def _fotogramma(self, offset: int, indice: int, larghezza: int, altezza: int) -> Image.Image:
        dimensione = larghezza * altezza * 2
        grezzo = bytes(self.dati[offset + indice * dimensione : offset + (indice + 1) * dimensione])
        return Image.frombytes("RGB", (larghezza, altezza), rgb888_da_565(grezzo))

    def disegna(self, comando: ComandoFaccia, t: float) -> Image.Image:
        m = self.manifesto
        anim_corpo = m.corpo[comando.stato]
        immagine = self._fotogramma(anim_corpo.offset, indice_corpo(comando.stato, t, m), m.larghezza, m.altezza)

        if comando.stato == "parlato" and m.bocca:
            rx, ry, rw, rh = m.bocca.regione
            indice = indice_da_livello(livello_bocca(comando, t), m.bocca.frames)
            immagine.paste(self._fotogramma(m.bocca.offset, indice, rw, rh), (rx, ry))

        if comando.stato == "ascolto" and m.pupille:
            rx, ry, rw, rh = m.pupille.regione
            indice = indice_da_livello(comando.livello, m.pupille.frames)
            immagine.paste(self._fotogramma(m.pupille.offset, indice, rw, rh), (rx, ry))

        if (
            comando.espressione
            and comando.espressione_scadenza is not None
            and t < comando.espressione_scadenza
            and comando.espressione in m.espressioni
        ):
            anim_e = m.espressioni[comando.espressione]
            rx, ry, rw, rh = anim_e.regione
            immagine.paste(self._fotogramma(anim_e.offset, 0, rw, rh), (rx, ry))

        if comando.stato == "timer" and comando.timer_rimanente is not None:
            self._disegna_countdown(immagine, comando.timer_rimanente, comando.timer_etichetta)

        return immagine

    def _disegna_countdown(self, immagine: Image.Image, rimanenti: int, etichetta: str | None) -> None:
        """Il countdown non è pre-cotto in `faces.bin` (§2.11): i numeri cambiano
        ogni secondo, disegnarli tutti in anticipo sprecherebbe RAM per niente."""
        disegna = ImageDraw.Draw(immagine)
        w, h = immagine.size
        testo = _mmss(rimanenti)
        dimensione_font = max(8, round(h * 0.22))
        font = _font(dimensione_font)
        box = disegna.textbbox((0, 0), testo, font=font)
        x = (w - (box[2] - box[0])) // 2
        y = round(h * 0.74)
        disegna.text((x, y), testo, font=font, fill=(240, 200, 90))
        if etichetta:
            font_etichetta = _font(max(6, round(h * 0.09)))
            box_e = disegna.textbbox((0, 0), etichetta, font=font_etichetta)
            xe = (w - (box_e[2] - box_e[0])) // 2
            disegna.text((xe, round(h * 0.90)), etichetta, font=font_etichetta, fill=(200, 200, 200))
