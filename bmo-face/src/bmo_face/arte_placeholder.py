"""Arte placeholder, disegnata a codice (issue #23).

Non esiste ancora nessun disegno vero della faccia di BMO nel repository: la
pipeline della §2.11 assume delle GIF già pronte in ingresso a `build_face.py`,
ma finché nessuno le disegna serve comunque qualcosa da convertire in
`faces.bin` per collaudare tutto il resto (pipeline, protocollo socket,
finestra a dimensione fisica). Questo modulo genera forme geometriche
disegnate a codice con PIL, in modo che chiunque possa sostituirle in
seguito senza toccare il resto della pipeline: `build_face.py --sorgente
cartella/` prenderà il posto di `genera_placeholder()` il giorno in cui
esisterà un disegno vero.

**Nota sui diritti (26/9, su richiesta esplicita)**: i colori e le
proporzioni qui sotto (schermo chiaro, occhi grandi e ovali scuri) sono
scelti per richiamare l'aspetto di BMO — non un fotogramma copiato da
Adventure Time, non i file del progetto di riferimento esterno
(`brenpoly/be-more-agent`, che ha una licenza propria e non chiaramente
estesa alle sue immagini), ma nemmeno una forma neutra qualunque. BMO è un
personaggio protetto da copyright e marchio (Cartoon Network / Warner Bros.
Discovery): l'intero progetto bmo-diy è già, per sua natura, una
ricostruzione non ufficiale e non commerciale del personaggio (il guscio
stampato in 3D viene dagli stessi modelli "BMO" di Printables, §"Riferimenti
esterni"), quindi questa faccia non introduce un rischio nuovo — ma **non è
"open source" nel senso di essere liberamente riutilizzabile da chiunque per
qualunque scopo**: resta materiale di un progetto fan-made. La decisione se
e come distribuire pubblicamente questo repository (licenza, eventuale
disclaimer esplicito nel README principale — oggi assente, vedi
`docs/note-issue-23.md`) resta di Riccardo, proprietario del progetto: qui
si segnala soltanto, non si decide.

Tutto è parametrico su `larghezza`/`altezza`: nessuna forma assume 320×240,
perché il pannello del BOM non è ancora deciso (issue #1) e potrebbe finire
più piccolo di quanto pianificato oggi.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

# Schermo chiaro (crema/verde pallido) e tratti scuri: l'aspetto tipico dello
# schermo-faccia di BMO, non lo "schermo spento" nero della prima versione
# placeholder — vedi la nota sui diritti qui sopra.
SFONDO = (224, 234, 205)
CHIARO = (38, 42, 36)
ACCENTO_ERRORE = (176, 60, 60)
ACCENTO_TIMER = (196, 140, 30)


def _tela(larghezza: int, altezza: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (larghezza, altezza), SFONDO)
    return img, ImageDraw.Draw(img)


def _occhio(
    disegna: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    larghezza: int,
    altezza: int,
    aperto: float,
    colore: tuple[int, int, int] = CHIARO,
) -> None:
    """Un occhio rettangolare, largo `larghezza` px, alto in proporzione ad `aperto` (0-1).

    `aperto=0` è una fessura orizzontale (occhio chiuso, battito di palpebre);
    `aperto=1` è tutto aperto — un ovale, non un rettangolo: la forma grande
    e ovale è quella che rende un occhio riconoscibile come "occhio di BMO"
    invece che un rettangolo generico. Il centro è in frazione di schermo
    (0-1, 0-1), così la stessa funzione vale per qualunque risoluzione del
    pannello.
    """
    h = max(2, round(altezza * aperto))
    x0, x1 = cx - larghezza / 2, cx + larghezza / 2
    y0, y1 = cy - h / 2, cy + h / 2
    disegna.ellipse([x0, y0, x1, y1], fill=colore)


def _dimensioni_occhi(w: int, h: int) -> tuple[float, float, int, int]:
    """Centro verticale e dimensioni degli occhi, in frazione/pixel di (w, h)."""
    cy = h * 0.36
    larghezza_occhio = round(w * 0.15)
    altezza_occhio = round(h * 0.26)
    return cy, cy, larghezza_occhio, altezza_occhio


def _centri_occhi(w: int) -> tuple[float, float]:
    return w * 0.32, w * 0.68


def corpo_idle(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """Il ciclo di `idle`: occhi aperti, un solo fotogramma con gli occhi chiusi.

    Il *quando* mostrare quel fotogramma (il battito irregolare) lo decide
    `animazione.py` scegliendo l'indice a runtime in base al tempo, non
    questo generatore: qui bastano due pose, aperta e chiusa. `n_frame` è
    comunque rispettato (frame intermedi = dissolvenza lineare fra le due
    pose) per lasciare spazio a un battito più morbido in futuro.
    """
    _, cy, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    frame = []
    for i in range(n_frame):
        aperto = 1.0 if i < n_frame - 1 else 0.05  # l'ultimo fotogramma e' il battito
        img, disegna = _tela(w, h)
        _occhio(disegna, cx1, cy, lo, ao, aperto)
        _occhio(disegna, cx2, cy, lo, ao, aperto)
        # bocca a riposo, neutra: una linea leggermente curva
        disegna.line([(w * 0.38, h * 0.68), (w * 0.62, h * 0.68)], fill=CHIARO, width=max(1, h // 60))
        frame.append(img)
    return frame


def corpo_assonnato(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`assonnato` (boot e pausa): occhi sempre chiusi, respiro lento."""
    cy_base, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    frame = []
    for i in range(n_frame):
        deriva = (i / max(1, n_frame - 1) - 0.5) * h * 0.01
        img, disegna = _tela(w, h)
        _occhio(disegna, cx1, cy_base + deriva, lo, ao, 0.06)
        _occhio(disegna, cx2, cy_base + deriva, lo, ao, 0.06)
        disegna.line([(w * 0.42, h * 0.66), (w * 0.58, h * 0.66)], fill=CHIARO, width=max(1, h // 70))
        frame.append(img)
    return frame


def corpo_ascolto(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`ascolto`: occhi ben aperti e attenti. Le pupille sono un overlay a parte."""
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    img, disegna = _tela(w, h)
    _occhio(disegna, cx1, cy, lo, round(ao * 1.1), 1.0)
    _occhio(disegna, cx2, cy, lo, round(ao * 1.1), 1.0)
    disegna.ellipse(
        [w * 0.46, h * 0.62, w * 0.54, h * 0.62 + h * 0.06], fill=CHIARO
    )  # bocca piccola, "in ascolto"
    return [img] * max(1, n_frame)


def corpo_pensiero(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`pensiero`: pupille che girano in tondo, per dire "sto elaborando"."""
    import math

    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    raggio = min(lo, ao) * 0.18
    frame = []
    for i in range(n_frame):
        angolo = 2 * math.pi * i / n_frame
        img, disegna = _tela(w, h)
        for cx in (cx1, cx2):
            _occhio(disegna, cx, cy, lo, ao, 1.0)
            px = cx + raggio * math.cos(angolo)
            py = cy + raggio * math.sin(angolo)
            disegna.ellipse([px - 3, py - 3, px + 3, py + 3], fill=SFONDO)
        disegna.line([(w * 0.40, h * 0.68), (w * 0.60, h * 0.68)], fill=CHIARO, width=max(1, h // 60))
        frame.append(img)
    return frame


def corpo_timer(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`timer`: occhi neutri; il countdown vero lo scrive il renderer a runtime
    (non è un fotogramma pre-cotto: i numeri cambiano ogni secondo, disegnarli
    tutti in anticipo sprecherebbe spazio per niente)."""
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    img, disegna = _tela(w, h)
    _occhio(disegna, cx1, cy, lo, ao, 0.9)
    _occhio(disegna, cx2, cy, lo, ao, 0.9)
    disegna.ellipse([w * 0.45, h * 0.60, w * 0.55, h * 0.66], outline=ACCENTO_TIMER, width=2)
    return [img] * max(1, n_frame)


def corpo_errore(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`errore-rete`: occhi a "X", niente panico ma chiaramente qualcosa non va."""
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    img, disegna = _tela(w, h)
    for cx in (cx1, cx2):
        x0, x1 = cx - lo / 2, cx + lo / 2
        y0, y1 = cy - ao / 2, cy + ao / 2
        disegna.line([(x0, y0), (x1, y1)], fill=ACCENTO_ERRORE, width=max(2, ao // 6))
        disegna.line([(x0, y1), (x1, y0)], fill=ACCENTO_ERRORE, width=max(2, ao // 6))
    disegna.line([(w * 0.40, h * 0.70), (w * 0.60, h * 0.66)], fill=ACCENTO_ERRORE, width=max(1, h // 60))
    return [img] * max(1, n_frame)


def corpo_conferma(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`conferma` (#17): attento, in attesa di un sì/no — occhi grandi, fissi."""
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    img, disegna = _tela(w, h)
    _occhio(disegna, cx1, cy, round(lo * 1.15), round(ao * 1.15), 1.0)
    _occhio(disegna, cx2, cy, round(lo * 1.15), round(ao * 1.15), 1.0)
    disegna.ellipse([w * 0.47, h * 0.64, w * 0.53, h * 0.68], fill=CHIARO)
    return [img] * max(1, n_frame)


def corpo_parlato(w: int, h: int, n_frame: int) -> list[Image.Image]:
    """`parlato`: identico a `idle` da fermo — la bocca è tutta nell'overlay `bocca`."""
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    img, disegna = _tela(w, h)
    _occhio(disegna, cx1, cy, lo, ao, 1.0)
    _occhio(disegna, cx2, cy, lo, ao, 1.0)
    return [img] * max(1, n_frame)


# Ogni stato di `adapters.base.STATO_*` (bmo-core) ha qui il suo generatore:
# le stringhe sono duplicate apposta (vedi `formato.py`) per non far dipendere
# bmo-face da bmo-core, ma devono restare identiche a quelle vere.
GENERATORI_CORPO = {
    "assonnato": corpo_assonnato,
    "idle": corpo_idle,
    "ascolto": corpo_ascolto,
    "pensiero": corpo_pensiero,
    "parlato": corpo_parlato,
    "timer": corpo_timer,
    "errore-rete": corpo_errore,
    "conferma": corpo_conferma,
}

FPS_CORPO = {
    "assonnato": 1.0,
    "idle": 3.0,  # rilevante solo per l'ultimo fotogramma (il battito): vedi animazione.py
    "ascolto": 1.0,
    "pensiero": 6.0,
    "parlato": 1.0,
    "timer": 1.0,
    "errore-rete": 1.0,
    "conferma": 1.0,
}

# Il minimo che regge ciascuna animazione, non di più: ogni fotogramma in più
# è larghezza×altezza×2 byte in faces.bin, e la #23 chiede esplicitamente
# efficienza in RAM per il caso peggiore di un pannello piccolo su un Pi da
# 512 MB. L'irregolarità del battito di `idle` la decide `animazione.py` a
# runtime scegliendo QUANDO mostrare il fotogramma chiuso, non serve
# interpolare fotogrammi intermedi per ottenerla.
N_FRAME_CORPO = {
    "assonnato": 2,  # aperto al minimo / respiro, nessuna via di mezzo serve
    "idle": 2,  # aperto, chiuso (il battito): animazione.py sceglie quando
    "ascolto": 1,
    "pensiero": 4,  # un giro di pupille a 4 posizioni, non 8: basta a "girare"
    "parlato": 1,
    "timer": 1,
    "errore-rete": 1,
    "conferma": 1,
}


def regione_bocca(w: int, h: int) -> list[int]:
    """Il rettangolo della bocca: fisso, indipendente dallo stato."""
    x = round(w * 0.36)
    y = round(h * 0.58)
    return [x, y, round(w * 0.28), round(h * 0.18)]


def overlay_bocca(w: int, h: int, n_livelli: int = 5) -> tuple[list[Image.Image], list[int]]:
    """`n_livelli` forme di bocca, dalla chiusa alla spalancata (§2.11: RMS → bocca).

    Ogni fotogramma è ritagliato alla sola `regione_bocca()`, non alla tela
    intera: è quel che va scritto sopra il corpo quando lo stato è `parlato`,
    scelto in base al livello dell'inviluppo, non al tempo.
    """
    rx, ry, rw, rh = regione_bocca(w, h)
    frame = []
    for i in range(n_livelli):
        apertura = i / max(1, n_livelli - 1)
        img = Image.new("RGB", (rw, rh), SFONDO)
        disegna = ImageDraw.Draw(img)
        # Un ovale, non un rettangolo arrotondato: chiusa è una fessura
        # orizzontale sottile, spalancata è un piccolo ovale — la stessa
        # forma "a O" della bocca di BMO quando parla, non una barra.
        altezza_bocca = max(2, round(rh * (0.10 + 0.80 * apertura)))
        larghezza_bocca = rw * (0.62 - 0.10 * apertura)
        x0 = (rw - larghezza_bocca) / 2
        y0 = (rh - altezza_bocca) / 2
        disegna.ellipse([x0, y0, x0 + larghezza_bocca, y0 + altezza_bocca], fill=CHIARO)
        frame.append(img)
    return frame, [rx, ry, rw, rh]


def regione_pupille(w: int, h: int) -> list[int]:
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    x = round(cx1 - lo / 2)
    larghezza = round(cx2 + lo / 2 - x)
    y = round(cy - ao / 2)
    return [x, y, larghezza, round(ao)]


def overlay_pupille(w: int, h: int, n_livelli: int = 5) -> tuple[list[Image.Image], list[int]]:
    """`n_livelli` posizioni di pupille, dal centro allo scarto massimo (§2.2: `level`).

    Il livello del microfono durante `ascolto` non ha nessun significato
    direzionale reale: è solo un modo visibile di dire "ti sento", uno scarto
    orizzontale proporzionale al volume — non un vero indicatore di posizione.
    """
    rx, ry, rw, rh = regione_pupille(w, h)
    cy, _, lo, ao = _dimensioni_occhi(w, h)
    cx1, cx2 = _centri_occhi(w)
    raggio_pupilla = min(lo, ao) * 0.16
    frame = []
    for i in range(n_livelli):
        scarto = (i / max(1, n_livelli - 1) - 0.5) * lo * 0.3
        img = Image.new("RGB", (rw, rh), SFONDO)
        disegna = ImageDraw.Draw(img)
        # `paste()` sostituisce l'intera regione, non la fonde: bisogna
        # ridisegnare qui anche l'occhio chiaro (uguale a `corpo_ascolto`),
        # non solo la pupilla, altrimenti l'occhio sparirebbe del tutto
        # sotto un rettangolo di solo sfondo.
        for cx in (cx1, cx2):
            _occhio(disegna, cx - rx, cy - ry, lo, ao, 1.0)
        for cx in (cx1, cx2):
            px, py = cx - rx + scarto, cy - ry
            disegna.ellipse(
                [px - raggio_pupilla, py - raggio_pupilla, px + raggio_pupilla, py + raggio_pupilla], fill=SFONDO
            )
        frame.append(img)
    return frame, [rx, ry, rw, rh]


def regione_espressione(w: int, h: int) -> list[int]:
    """Un accento sopra l'occhio destro: piccolo apposta, non deve coprire la bocca.

    Il minimo di 6 px per lato non è arbitrario: sotto quella soglia
    `overlay_espressioni` non ha spazio per disegnare un arco o un contorno
    senza degenerare in un rettangolo di area nulla (visto rompersi davvero
    su un pannello piccolissimo, #23 — "caso peggiore").
    """
    _, cy, lo, ao = _dimensioni_occhi(w, h)
    _, cx2 = _centri_occhi(w)
    larghezza = max(6, round(lo))
    altezza = max(6, round(ao * 0.5))
    x = round(cx2 - larghezza / 2)
    y = round(cy - ao * 1.3)
    return [x, y, larghezza, altezza]


def overlay_espressioni(w: int, h: int) -> dict[str, tuple[Image.Image, list[int]]]:
    """Un accento per ciascuna di `brain.ESPRESSIONI`, sovrapposto durante `parlato`.

    Solo una forma/colore diverso sopra l'occhio destro: non stravolge la
    faccia, la etichetta per la durata (`ttl`) della battuta (§2.3).
    """
    rx, ry, rw, rh = regione_espressione(w, h)
    forme: dict[str, tuple[Image.Image, list[int]]] = {}
    # Colori scuri, non chiari: lo sfondo ora è chiaro (vedi SFONDO), un
    # accento chiaro come "sorpreso" prima della correzione sarebbe stato
    # invisibile sopra.
    colori = {
        "felice": (196, 140, 30),
        "pensieroso": (70, 95, 140),
        "sorpreso": (150, 60, 60),
        "triste": (60, 75, 120),
        "assonnato": (90, 90, 95),
    }
    # Margine di sicurezza per lato: su un pannello minuscolo `rw`/`rh` sono
    # piccoli quanto basta a far collassare un margine fisso di 2 px in un
    # rettangolo di area nulla (PIL solleva ValueError su x1<x0 o y1<y0).
    mx = min(2, max(0, (rw - 1) // 2))
    my = min(2, max(0, (rh - 1) // 2))
    x0, x1 = mx, max(mx + 1, rw - mx)
    for nome, colore in colori.items():
        img = Image.new("RGB", (rw, rh), SFONDO)
        disegna = ImageDraw.Draw(img)
        if nome == "sorpreso":
            disegna.ellipse([x0, my, x1, max(my + 1, rh - my)], outline=colore, width=2)
        elif nome == "triste":
            disegna.arc([x0, -rh * 0.6, x1, rh], start=200, end=340, fill=colore, width=2)
        else:
            disegna.arc([x0, -rh * 0.2, x1, rh * 1.4], start=200, end=340, fill=colore, width=2)
        forme[nome] = (img, [rx, ry, rw, rh])
    return forme
