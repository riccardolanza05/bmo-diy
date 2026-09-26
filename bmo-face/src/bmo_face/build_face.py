"""build_face.py — sul PC di sviluppo, una volta (§2.11, issue #23).

Genera `faces.bin` (fotogrammi RGB565 grezzi) e `faces.json` (il manifesto,
vedi `formato.py`) a partire dall'arte placeholder di `arte_placeholder.py`.
Parametrico su risoluzione: nessun pannello è ancora deciso (issue #1), e il
formato deve reggere anche un pannello più piccolo di quanto pianificato oggi.

`faces.bin` è un artefatto di build: si rigenera da qui, non va committato.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .arte_placeholder import (
    FPS_CORPO,
    GENERATORI_CORPO,
    N_FRAME_CORPO,
    overlay_bocca,
    overlay_espressioni,
    overlay_pupille,
)
from .formato import Animazione, Manifesto, NOME_BIN, NOME_JSON, rgb565, salva_manifesto


def _regione_cambiata(frame: list[Image.Image]) -> list[int]:
    """Il rettangolo che racchiude i pixel diversi fra un fotogramma e il
    successivo del ciclo (per il futuro blit a dirty-rect sul bus SPI, §2.11).

    Un solo fotogramma non cambia mai: la regione è l'intera tela, il caso
    più semplice e anche il più sicuro (nessuna assunzione su cosa disegnerà
    in futuro un'arte vera al posto del placeholder).
    """
    w, h = frame[0].size
    if len(frame) < 2:
        return [0, 0, w, h]
    x0, y0, x1, y1 = w, h, 0, 0
    base = frame[0].load()
    for altro in frame[1:]:
        pix = altro.load()
        for y in range(h):
            for x in range(w):
                if pix[x, y] != base[x, y]:
                    x0, y0 = min(x0, x), min(y0, y)
                    x1, y1 = max(x1, x + 1), max(y1, y + 1)
    if x1 <= x0 or y1 <= y0:
        return [0, 0, w, h]  # cicli identici (placeholder statico): tutta la tela
    return [x0, y0, x1 - x0, y1 - y0]


def _scrivi_frame(buffer: bytearray, frame: list[Image.Image]) -> int:
    """Accoda i fotogrammi (RGB565) al buffer, restituisce l'offset di partenza."""
    offset = len(buffer)
    for img in frame:
        buffer.extend(rgb565(img.convert("RGB").tobytes()))
    return offset


def costruisci(larghezza: int, altezza: int) -> tuple[bytes, Manifesto]:
    buffer = bytearray()
    manifesto = Manifesto(larghezza=larghezza, altezza=altezza)

    for stato, genera in GENERATORI_CORPO.items():
        frame = genera(larghezza, altezza, N_FRAME_CORPO[stato])
        offset = _scrivi_frame(buffer, frame)
        manifesto.corpo[stato] = Animazione(
            offset=offset, frames=len(frame), regione=_regione_cambiata(frame), fps=FPS_CORPO[stato]
        )

    frame_bocca, regione_bocca = overlay_bocca(larghezza, altezza)
    offset = _scrivi_frame(buffer, frame_bocca)
    manifesto.bocca = Animazione(offset=offset, frames=len(frame_bocca), regione=regione_bocca)

    frame_pupille, regione_pupille = overlay_pupille(larghezza, altezza)
    offset = _scrivi_frame(buffer, frame_pupille)
    manifesto.pupille = Animazione(offset=offset, frames=len(frame_pupille), regione=regione_pupille)

    for nome, (img, regione) in overlay_espressioni(larghezza, altezza).items():
        offset = _scrivi_frame(buffer, [img])
        manifesto.espressioni[nome] = Animazione(offset=offset, frames=1, regione=regione)

    return bytes(buffer), manifesto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--larghezza", type=int, default=320, help="larghezza del pannello in pixel")
    parser.add_argument("--altezza", type=int, default=240, help="altezza del pannello in pixel")
    parser.add_argument(
        "--destinazione", type=Path, default=Path("."), help="cartella dove scrivere faces.bin e faces.json"
    )
    argomenti = parser.parse_args()

    dati, manifesto = costruisci(argomenti.larghezza, argomenti.altezza)
    argomenti.destinazione.mkdir(parents=True, exist_ok=True)
    (argomenti.destinazione / NOME_BIN).write_bytes(dati)
    salva_manifesto(argomenti.destinazione / NOME_JSON, manifesto)
    print(
        f"{NOME_BIN}: {len(dati)} byte ({len(dati) / 1024:.1f} kB) per un pannello "
        f"{argomenti.larghezza}×{argomenti.altezza} → {argomenti.destinazione}"
    )


if __name__ == "__main__":
    main()
