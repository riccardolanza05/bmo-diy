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


# Mappa cartella del riferimento esterno -> STATO_* di bmo-core (issue #23,
# nota sui diritti in arte_placeholder.py e in bmo-face/README.md — le
# immagini vere non entrano MAI nel repository, solo faces.bin che ne deriva,
# e nemmeno quello: è un artefatto di build).
MAPPA_CARTELLE_RIFERIMENTO = {
    "warmup": "assonnato",
    "idle": "idle",
    "listening": "ascolto",
    "thinking": "pensiero",
    "error": "errore-rete",
}


def _adatta_a_pannello(img: Image.Image, larghezza: int, altezza: int) -> Image.Image:
    """Ridimensiona `img` per coprire (larghezza × altezza) e ritaglia l'eccesso al centro.

    "Cover", non "stretch": il riferimento è 800×480 (5:3), il pannello
    predefinito è 320×240 (4:3) — deformare schiaccerebbe la faccia, un
    ritaglio centrato no, perché occhi e bocca nel riferimento stanno ben
    dentro il centro dell'immagine (verificato guardando i fotogrammi).
    """
    img = img.convert("RGB")
    scala = max(larghezza / img.width, altezza / img.height)
    nuova = (max(1, round(img.width * scala)), max(1, round(img.height * scala)))
    img = img.resize(nuova, Image.LANCZOS)
    x0 = (img.width - larghezza) // 2
    y0 = (img.height - altezza) // 2
    return img.crop((x0, y0, x0 + larghezza, y0 + altezza))


def _carica_cartella(cartella: Path, larghezza: int, altezza: int) -> list[Image.Image]:
    return [_adatta_a_pannello(Image.open(f), larghezza, altezza) for f in sorted(cartella.glob("*.png"))]


def _apertura_bocca(img: Image.Image) -> int:
    """Pixel non-sfondo in una finestra centrale-bassa (dove sta la bocca):
    un proxy per "quanto è aperta", per ordinare i fotogrammi `speaking`
    dal chiuso all'aperto senza doverlo specificare a mano frame per frame.
    """
    w, h = img.size
    zona = img.crop((round(w * 0.30), round(h * 0.40), round(w * 0.70), round(h * 0.80)))
    sfondo = zona.getpixel((0, 0))
    pix = zona.load()
    return sum(1 for y in range(zona.height) for x in range(zona.width) if pix[x, y] != sfondo)


def costruisci_da_sorgente(sorgente: Path, larghezza: int, altezza: int) -> tuple[bytes, Manifesto]:
    """Come `costruisci()`, ma da fotogrammi veri invece che dal placeholder.

    Nessun overlay di pupille o espressioni: le regioni di `arte_placeholder`
    sono calcolate sulla geometria del placeholder, non su dove stanno
    davvero occhi e bocca in un'immagine importata — comporrebbero pezzi
    nel punto sbagliato. La bocca invece funziona: i fotogrammi `speaking`
    diventano un overlay a **fotogramma intero** (`regione=[0,0,w,h]`), quindi
    "sovrapporlo" equivale a sostituire tutto il corpo con quel fotogramma —
    corretto, perché contiene già occhi e bocca insieme.
    """
    buffer = bytearray()
    manifesto = Manifesto(larghezza=larghezza, altezza=altezza)

    for cartella, stato in MAPPA_CARTELLE_RIFERIMENTO.items():
        frame = _carica_cartella(sorgente / cartella, larghezza, altezza)
        if not frame:
            continue
        if len(frame) == 1:
            frame = frame * 2  # indice_corpo("idle", ...) si aspetta almeno 2 fotogrammi
        offset = _scrivi_frame(buffer, frame)
        manifesto.corpo[stato] = Animazione(
            offset=offset, frames=len(frame), regione=[0, 0, larghezza, altezza], fps=FPS_CORPO.get(stato, 1.0)
        )

    # Nel riferimento non esistono cartelle per `timer`/`conferma`/`parlato`:
    # riusano il corpo di uno stato vicino (il countdown/la bocca restano
    # overlay separati, vedi sopra e sotto).
    if "idle" in manifesto.corpo:
        manifesto.corpo.setdefault("timer", manifesto.corpo["idle"])
        manifesto.corpo.setdefault("parlato", manifesto.corpo["idle"])
    if "ascolto" in manifesto.corpo:
        manifesto.corpo.setdefault("conferma", manifesto.corpo["ascolto"])

    bocca_frame = _carica_cartella(sorgente / "speaking", larghezza, altezza)
    if bocca_frame:
        bocca_frame.sort(key=_apertura_bocca)  # dal chiuso (meno pixel "bocca") allo spalancato
        offset = _scrivi_frame(buffer, bocca_frame)
        manifesto.bocca = Animazione(offset=offset, frames=len(bocca_frame), regione=[0, 0, larghezza, altezza])

    return bytes(buffer), manifesto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--larghezza", type=int, default=320, help="larghezza del pannello in pixel")
    parser.add_argument("--altezza", type=int, default=240, help="altezza del pannello in pixel")
    parser.add_argument(
        "--destinazione", type=Path, default=Path("."), help="cartella dove scrivere faces.bin e faces.json"
    )
    parser.add_argument(
        "--sorgente",
        type=Path,
        default=None,
        help="cartella con fotogrammi veri (layout del riferimento esterno: idle/, listening/, "
        "thinking/, speaking/, error/, warmup/, ciascuna con .png) invece del placeholder geometrico",
    )
    argomenti = parser.parse_args()

    if argomenti.sorgente:
        dati, manifesto = costruisci_da_sorgente(argomenti.sorgente, argomenti.larghezza, argomenti.altezza)
    else:
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
