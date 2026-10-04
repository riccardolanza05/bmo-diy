from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from bmo_core.adapters import camera
from bmo_core.adapters.camera import (
    CameraGrezzaV4L2,
    luminosita_media,
    spacchetta_bayer_10bit,
    sviluppa_bayer_gbrg,
)
from bmo_core.adapters.factory import crea_camera

LARGHEZZA, ALTEZZA, STRIDE = 1296, 972, 1632


def impacchetta(valori: np.ndarray, stride: int = STRIDE) -> bytes:
    """L'inverso di `spacchetta_bayer_10bit`: array uint16 -> `pGAA` (come lo scrive il driver unicam)."""
    altezza, larghezza = valori.shape
    gruppi = valori.reshape(altezza, larghezza // 4, 4)
    uscita = np.zeros((altezza, stride), dtype=np.uint8)
    blocco = np.zeros((altezza, larghezza // 4, 5), dtype=np.uint8)
    for k in range(4):
        blocco[:, :, k] = gruppi[:, :, k] >> 2
        blocco[:, :, 4] |= ((gruppi[:, :, k] & 3) << (2 * k)).astype(np.uint8)
    uscita[:, : larghezza // 4 * 5] = blocco.reshape(altezza, -1)
    return uscita.tobytes()


def bayer_uniforme(r: int, g: int, b: int, larghezza: int = LARGHEZZA, altezza: int = ALTEZZA) -> np.ndarray:
    """Un Bayer GBRG con ogni canale a un valore fisso."""
    bayer = np.zeros((altezza, larghezza), dtype=np.uint16)
    bayer[0::2, 0::2] = g
    bayer[0::2, 1::2] = b
    bayer[1::2, 0::2] = r
    bayer[1::2, 1::2] = g
    return bayer


def test_spacchetta_e_l_inverso_di_impacchetta():
    rng = np.random.default_rng(1)
    valori = rng.integers(0, 1024, size=(ALTEZZA, LARGHEZZA), dtype=np.uint16)
    assert np.array_equal(spacchetta_bayer_10bit(impacchetta(valori), LARGHEZZA, ALTEZZA, STRIDE), valori)


def test_spacchetta_usa_lo_stride_del_driver_non_la_larghezza():
    valori = np.full((ALTEZZA, LARGHEZZA), 1023, dtype=np.uint16)
    grezzo = impacchetta(valori, stride=1700)  # righe più lunghe di quelle utili
    assert np.array_equal(spacchetta_bayer_10bit(grezzo, LARGHEZZA, ALTEZZA, 1700), valori)


def test_la_luminosita_e_quella_dei_verdi_senza_il_nero():
    assert luminosita_media(bayer_uniforme(900, 216, 900)) == pytest.approx(200.0)
    assert luminosita_media(bayer_uniforme(0, 0, 0)) == 0.0  # sotto il nero non diventa negativa


def test_lo_sviluppo_e_a_meta_risoluzione_e_distingue_i_colori():
    bayer = bayer_uniforme(900, 100, 100)
    bayer[:, LARGHEZZA // 2:] = bayer_uniforme(100, 100, 900)[:, LARGHEZZA // 2:]
    rgb = sviluppa_bayer_gbrg(bayer)
    assert rgb.shape == (ALTEZZA // 2, LARGHEZZA // 2, 3) and rgb.dtype == np.uint8
    sinistra, destra = rgb[100, 50], rgb[100, LARGHEZZA // 2 - 50]
    assert sinistra[0] > sinistra[2] and destra[2] > destra[0]  # rosso a sinistra, blu a destra


def test_lo_sviluppo_riporta_a_grigio_una_dominante():
    """Mondo grigio: una scena tutta verdastra non esce tutta verde."""
    rgb = sviluppa_bayer_gbrg(bayer_uniforme(300, 600, 300))
    medie = rgb.reshape(-1, 3).mean(axis=0)
    assert medie.max() - medie.min() < 30


class ComandiFinti:
    """Finge `v4l2-ctl` e `media-ctl`: tiene la storia e, quando gli si chiede uno stream, scrive frame sintetici."""

    def __init__(self, luminosita_per_prodotto):
        self.storia: list[list[str]] = []
        self.esposizione, self.guadagno = 1000, 64
        self.luminosita_per_prodotto = luminosita_per_prodotto

    def __call__(self, argomenti, **_):
        self.storia.append(argomenti)
        for a in argomenti:
            if a.startswith("--set-ctrl="):
                for coppia in a.removeprefix("--set-ctrl=").split(","):
                    nome, valore = coppia.split("=")
                    if nome == "exposure":
                        self.esposizione = int(valore)
                    elif nome == "analogue_gain":
                        self.guadagno = int(valore)
            if a.startswith("--stream-to="):
                verde = int(self.luminosita_per_prodotto(self.esposizione * self.guadagno)) + camera.NERO_BAYER
                frame = impacchetta(bayer_uniforme(min(verde * 2, 1023), min(verde, 1023), min(verde * 2, 1023)))
                Path(a.removeprefix("--stream-to=")).write_bytes(frame * camera.CameraGrezzaV4L2.FRAME_DA_CATTURARE)


def _scatta(tmp_path, comandi, **opzioni):
    adattatore = CameraGrezzaV4L2(esegui=comandi, ruota=0, sensore="ov5647 10-0036", media="/dev/media0",
                                  video="/dev/video0", **opzioni)
    return adattatore, adattatore.scatta_foto(tmp_path / "foto.jpg")


def test_scatta_foto_scrive_un_jpeg_a_mezza_risoluzione(tmp_path):
    comandi = ComandiFinti(lambda prodotto: 200)  # già ben esposta
    _, percorso = _scatta(tmp_path, comandi)
    immagine = Image.open(percorso)
    assert immagine.format == "JPEG" and immagine.size == (LARGHEZZA // 2, ALTEZZA // 2)


def test_scatta_foto_configura_il_sensore_prima_di_catturare(tmp_path):
    comandi = ComandiFinti(lambda prodotto: 200)
    _scatta(tmp_path, comandi)
    primo, secondo = comandi.storia[0], comandi.storia[1]
    assert primo[:2] == ["media-ctl", "-d"] and '"ov5647 10-0036":0[fmt:SGBRG10_1X10/1296x972]' in primo
    assert "--set-fmt-video=width=1296,height=972,pixelformat=pGAA" in secondo
    assert any(a.startswith("--stream-to=") for a in comandi.storia[3])


def test_con_luce_buona_basta_una_cattura(tmp_path):
    comandi = ComandiFinti(lambda prodotto: 200)
    _scatta(tmp_path, comandi)
    assert sum(any(a.startswith("--stream-to=") for a in c) for c in comandi.storia) == 1


def test_al_buio_l_esposizione_sale_e_si_ricorda(tmp_path):
    # Luminosità proporzionale al prodotto esposizione x guadagno: 1000*64 -> 20, serve circa 10x.
    comandi = ComandiFinti(lambda prodotto: prodotto / 3200)
    adattatore, _ = _scatta(tmp_path, comandi)
    assert adattatore.esposizione * adattatore.guadagno > 4 * 1000 * 64
    assert adattatore.esposizione <= camera.ESPOSIZIONE_MAX and camera.GUADAGNO_MIN <= adattatore.guadagno <= camera.GUADAGNO_MAX


def test_la_correzione_alza_prima_l_esposizione_poi_il_guadagno():
    adattatore = CameraGrezzaV4L2(esegui=lambda *a, **k: None, ruota=0)
    adattatore.esposizione, adattatore.guadagno = 500, 32
    adattatore._correggi_esposizione(adattatore.OBIETTIVO / 2)      # serve il doppio
    assert (adattatore.esposizione, adattatore.guadagno) == (1000, 32)
    adattatore._correggi_esposizione(adattatore.OBIETTIVO / 8)      # serve 8x: l'esposizione arriva (quasi) al massimo
    assert adattatore.esposizione >= camera.ESPOSIZIONE_MAX - 5 and adattatore.guadagno > 32
    # Il prodotto richiesto (1000 x 32 x 8) è rispettato, a meno degli arrotondamenti.
    assert adattatore.esposizione * adattatore.guadagno == pytest.approx(1000 * 32 * 8, rel=0.02)


def test_la_correzione_non_supera_i_limiti_del_sensore():
    adattatore = CameraGrezzaV4L2(esegui=lambda *a, **k: None, ruota=0)
    for _ in range(10):
        adattatore._correggi_esposizione(0.0)  # buio totale
    assert adattatore.guadagno == camera.GUADAGNO_MAX and adattatore.esposizione <= camera.ESPOSIZIONE_MAX


def test_la_rotazione_di_180_gradi_capovolge_la_foto(tmp_path):
    bayer = bayer_uniforme(100, 100, 100)
    bayer[: ALTEZZA // 2, :] = bayer_uniforme(900, 100, 100)[: ALTEZZA // 2, :]  # in alto rosso

    class Comandi(ComandiFinti):
        def __call__(self, argomenti, **k):
            for a in argomenti:
                if a.startswith("--stream-to="):
                    Path(a.removeprefix("--stream-to=")).write_bytes(impacchetta(bayer) * camera.CameraGrezzaV4L2.FRAME_DA_CATTURARE)

    risultati = {}
    for ruota in (0, 180):
        adattatore = CameraGrezzaV4L2(esegui=Comandi(lambda p: 200), ruota=ruota, tentativi_esposizione=0)
        percorso = adattatore.scatta_foto(tmp_path / f"foto{ruota}.jpg")
        immagine = np.asarray(Image.open(percorso))
        risultati[ruota] = (immagine[10, 300].astype(int), immagine[-10, 300].astype(int))
    alto0, basso0 = risultati[0]
    alto180, basso180 = risultati[180]
    assert alto0[0] > alto0[2] and basso0[2] >= basso0[0]
    assert basso180[0] > basso180[2]  # il rosso, che era in alto, ora è in basso


def test_factory_sceglie_la_camera_grezza_solo_su_richiesta(monkeypatch):
    from bmo_core.config import Ambiente

    monkeypatch.delenv("BMO_CAMERA", raising=False)
    assert not isinstance(crea_camera(Ambiente.PI), CameraGrezzaV4L2)
    monkeypatch.setenv("BMO_CAMERA", "grezza")
    assert isinstance(crea_camera(Ambiente.PI), CameraGrezzaV4L2)
    assert isinstance(crea_camera(Ambiente.DEV_LINUX), CameraGrezzaV4L2)
