"""Il formato di `faces.bin` + `faces.json` (§2.11, issue #23).

Sul Pi il display non decodifica niente a runtime: `build_face.py` genera,
una volta sul PC di sviluppo, un file binario di fotogrammi RGB565 grezzi
(`faces.bin`) più un manifesto JSON (`faces.json`) che dice dove sta ogni
animazione dentro quel binario. Questo modulo legge e scrive entrambi, ed è
l'unico punto che conosce il formato: sia `build_face.py` (scrittura) sia il
renderer (lettura) passano di qui.

Tre famiglie di animazioni nel manifesto:
- **corpo**: un fotogramma pieno 320×240 per stato (`adapters.base.STATO_*`),
  in ciclo alla propria `fps` — il battito di palpebre e le altre animazioni
  "di fondo" che non dipendono da nient'altro che il tempo.
- **bocca** e **pupille**: piccole regioni sovrapposte al corpo, scelte non
  dal tempo ma da un livello continuo in [0, 1] — l'inviluppo RMS della voce
  per la bocca (stato `parlato`), il livello del microfono per le pupille
  (stato `ascolto`).
- **espressioni**: un'altra piccola regione sovrapposta, una per ciascuna di
  `brain.ESPRESSIONI`, mostrata per la durata (`ttl`) dichiarata dal comando
  `expression` del socket (§2.2), a prescindere da quale stato sia in corso.

`regione` in ogni voce è il rettangolo che *cambia* durante quell'animazione
(bounding box dei pixel diversi fra un fotogramma e il successivo): non serve
a questo renderer a finestra, che ridisegna sempre il fotogramma intero, ma è
il dato che userà il blit a dirty-rect sul bus SPI del Pi (§2.11) — calcolarlo
già ora evita di dover rifare la pipeline quando arriverà quel giorno.
"""
from __future__ import annotations

import json
import mmap
import struct
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Predefiniti solo per chi chiama `build_face.py` senza specificare altro: il
# pannello vero (2.4", 3.5", o qualunque candidato finisca nel BOM, compreso
# un caso peggiore più piccolo) si passa a riga di comando (--larghezza/
# --altezza/--mm-larghezza/--mm-altezza). Niente nel formato o nel renderer
# assume 320×240: quei due numeri stanno nel manifesto, non nel codice.
LARGHEZZA = 320
ALTEZZA = 240
NOME_BIN = "faces.bin"
NOME_JSON = "faces.json"


@contextmanager
def mappa_bin(percorso: Path) -> Iterator[mmap.mmap]:
    """Apre `faces.bin` mappato in memoria (`mmap`), mai letto tutto in RAM.

    È la stessa tecnica che userà il Pi (§2.11: "il Pi lo mappa in memoria"):
    le pagine si caricano dal filesystem solo quando un fotogramma le tocca
    davvero, e il kernel le tiene nella page cache condivisa invece che in un
    `bytes` duplicato per ogni processo. Provarlo così anche sul PC di
    sviluppo misura il comportamento vero, non una scorciatoia più comoda.
    """
    with percorso.open("rb") as file:
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mappa:
            yield mappa


def rgb565(pixel_rgb: bytes) -> bytes:
    """Converte pixel RGB888 (3 byte ciascuno) in RGB565 little-endian.

    Stessa formula di `build_face.py` nel piano (§2.11): 5 bit di rosso, 6 di
    verde, 5 di blu — il formato che il bus SPI del display scrive senza
    conversioni a runtime.
    """
    uscita = bytearray(len(pixel_rgb) // 3 * 2)
    for i in range(0, len(pixel_rgb), 3):
        r, g, b = pixel_rgb[i], pixel_rgb[i + 1], pixel_rgb[i + 2]
        valore = (r & 0xF8) << 8 | (g & 0xFC) << 3 | b >> 3
        struct.pack_into("<H", uscita, i // 3 * 2, valore)
    return bytes(uscita)


def rgb888_da_565(dati: bytes) -> bytes:
    """L'inverso di `rgb565`: da RGB565 a RGB888, per disegnare a schermo.

    Non è un giro a vuoto: `faces.bin` è quantizzato in RGB565 di proposito
    (è il formato che si vedrà davvero sul display fisico), quindi anche la
    finestra di prova deve leggerlo da lì e non dalle immagini sorgente
    originali — altrimenti la prova di leggibilità (criterio b, #23) non
    misurerebbe la stessa qualità d'immagine dell'hardware vero.
    """
    uscita = bytearray(len(dati) // 2 * 3)
    for i in range(0, len(dati), 2):
        valore = struct.unpack_from("<H", dati, i)[0]
        r = (valore >> 8) & 0xF8
        g = (valore >> 3) & 0xFC
        b = (valore << 3) & 0xF8
        uscita[i // 2 * 3 : i // 2 * 3 + 3] = bytes((r, g, b))
    return bytes(uscita)


@dataclass
class Animazione:
    """Una famiglia di fotogrammi dentro `faces.bin`: dove comincia, quanti sono."""

    offset: int
    frames: int
    regione: list[int]  # [x, y, w, h], nel sistema di coordinate del corpo
    fps: float = 0.0  # 0 per bocca/pupille/espressioni: non scorrono col tempo


@dataclass
class Manifesto:
    larghezza: int = LARGHEZZA
    altezza: int = ALTEZZA
    corpo: dict[str, Animazione] = field(default_factory=dict)
    bocca: Animazione | None = None
    pupille: Animazione | None = None
    espressioni: dict[str, Animazione] = field(default_factory=dict)

    def dimensione_regione(self, animazione: Animazione) -> tuple[int, int]:
        return animazione.regione[2], animazione.regione[3]


def _serializza_animazione(a: Animazione) -> dict:
    return {"offset": a.offset, "frames": a.frames, "regione": a.regione, "fps": a.fps}


def _leggi_animazione(d: dict) -> Animazione:
    return Animazione(offset=d["offset"], frames=d["frames"], regione=list(d["regione"]), fps=d.get("fps", 0.0))


def salva_manifesto(percorso: Path, manifesto: Manifesto) -> None:
    dati = {
        "larghezza": manifesto.larghezza,
        "altezza": manifesto.altezza,
        "corpo": {stato: _serializza_animazione(a) for stato, a in manifesto.corpo.items()},
        "bocca": _serializza_animazione(manifesto.bocca) if manifesto.bocca else None,
        "pupille": _serializza_animazione(manifesto.pupille) if manifesto.pupille else None,
        "espressioni": {nome: _serializza_animazione(a) for nome, a in manifesto.espressioni.items()},
    }
    percorso.write_text(json.dumps(dati, indent=1), encoding="utf-8")


def carica_manifesto(percorso: Path) -> Manifesto:
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    return Manifesto(
        larghezza=dati["larghezza"],
        altezza=dati["altezza"],
        corpo={stato: _leggi_animazione(a) for stato, a in dati["corpo"].items()},
        bocca=_leggi_animazione(dati["bocca"]) if dati.get("bocca") else None,
        pupille=_leggi_animazione(dati["pupille"]) if dati.get("pupille") else None,
        espressioni={nome: _leggi_animazione(a) for nome, a in dati.get("espressioni", {}).items()},
    )
