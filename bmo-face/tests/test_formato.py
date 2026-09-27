from pathlib import Path

from bmo_face.formato import Animazione, Manifesto, carica_manifesto, mappa_bin, rgb565, rgb888_da_565, salva_manifesto


def test_rgb565_round_trip_approssimato():
    # RGB565 perde precisione (5/6/5 bit): il round trip non è esatto, ma
    # l'errore per canale deve restare piccolo (quantizzazione, non un bug).
    originale = bytes([12, 200, 47, 255, 0, 128])
    codificato = rgb565(originale)
    assert len(codificato) == 4  # due pixel, 2 byte l'uno
    decodificato = rgb888_da_565(codificato)
    assert len(decodificato) == len(originale)
    for a, b in zip(originale, decodificato):
        assert abs(a - b) <= 8


def test_rgb565_nero_e_bianco_esatti():
    assert rgb888_da_565(rgb565(bytes([0, 0, 0]))) == bytes([0, 0, 0])
    assert rgb888_da_565(rgb565(bytes([255, 255, 255]))) == bytes([248, 252, 248])


def test_manifesto_round_trip(tmp_path):
    manifesto = Manifesto(
        larghezza=176,
        altezza=220,
        corpo={"idle": Animazione(offset=0, frames=2, regione=[0, 0, 176, 220], fps=3.0)},
        bocca=Animazione(offset=1000, frames=5, regione=[10, 20, 30, 40]),
        pupille=Animazione(offset=2000, frames=5, regione=[1, 2, 3, 4]),
        espressioni={"felice": Animazione(offset=3000, frames=1, regione=[5, 6, 7, 8])},
    )
    percorso = tmp_path / "faces.json"
    salva_manifesto(percorso, manifesto)
    riletto = carica_manifesto(percorso)
    assert riletto == manifesto


def test_mappa_bin_legge_i_byte_scritti(tmp_path):
    percorso = tmp_path / "faces.bin"
    percorso.write_bytes(b"\x01\x02\x03\x04")
    with mappa_bin(percorso) as mappa:
        assert bytes(mappa[:4]) == b"\x01\x02\x03\x04"
