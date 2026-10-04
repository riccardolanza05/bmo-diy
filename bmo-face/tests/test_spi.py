import numpy as np
import pytest
from PIL import Image

from bmo_face import spi as modulo_spi
from bmo_face.pannello import UscitaSpi
from bmo_face.spi import DisplayIli9341, crea_display_da_ambiente, rgb565_big_endian

DC, RST, BL = 25, 27, 12


class GpioFinto:
    def __init__(self):
        self.livelli = {}
        self.storia = []
        self.rilasciato = False

    def uscita(self, pin, alto):
        self.livelli[pin] = alto
        self.storia.append((pin, alto))

    def rilascia(self):
        self.rilasciato = True


class SpiFinto:
    """Registra (livello di DC, byte) di ogni scrittura: DC basso = comando, alto = dati."""

    def __init__(self, gpio):
        self.gpio = gpio
        self.scritture = []
        self.chiuso = False

    def scrivi(self, dati):
        self.scritture.append((self.gpio.livelli.get(DC), bytes(dati)))

    def chiudi(self):
        self.chiuso = True


def _display(larghezza=16, altezza=16, madctl=0x28):
    gpio = GpioFinto()
    spi = SpiFinto(gpio)
    display = DisplayIli9341(spi, gpio, dc=DC, rst=RST, bl=BL, madctl=madctl,
                             larghezza=larghezza, altezza=altezza, dormi=lambda s: None)
    return display, spi, gpio


def _comandi(spi):
    """I soli byte scritti con DC basso, cioè i codici dei comandi, in ordine."""
    return [dati[0] for dc, dati in spi.scritture if dc is False]


def test_rgb565_big_endian_ha_il_byte_alto_per_primo():
    rosso = np.array([[[255, 0, 0]]], dtype=np.uint8)
    verde = np.array([[[0, 255, 0]]], dtype=np.uint8)
    blu = np.array([[[0, 0, 255]]], dtype=np.uint8)
    assert rgb565_big_endian(rosso) == b"\xf8\x00"
    assert rgb565_big_endian(verde) == b"\x07\xe0"
    assert rgb565_big_endian(blu) == b"\x00\x1f"


def test_inizializza_esegue_la_sequenza_dell_ili9341():
    display, spi, gpio = _display(madctl=0x28)
    display.inizializza()
    assert _comandi(spi) == [0x01, 0x11, 0x3A, 0x36, 0x29]
    dati = {c: d for (dc, c_), (dc2, d) in zip(spi.scritture, spi.scritture[1:]) if dc is False and dc2 is True
            for c in [c_[0]]}
    assert dati[0x3A] == b"\x55"      # 16 bit per pixel
    assert dati[0x36] == b"\x28"      # orientamento e ordine dei colori
    assert gpio.livelli[BL] is True   # il backlight si accende
    # Reset hardware: alto, basso, alto.
    assert [alto for pin, alto in gpio.storia if pin == RST][:3] == [True, False, True]


def test_scrivi_imposta_la_finestra_e_poi_manda_i_pixel():
    display, spi, gpio = _display(larghezza=320, altezza=240)
    pixel = b"\xab\xcd" * (3 * 2)
    display.scrivi(10, 20, 3, 2, pixel)
    assert spi.scritture == [
        (False, b"\x2a"), (True, bytes([0, 10, 0, 12])),    # colonne 10..12
        (False, b"\x2b"), (True, bytes([0, 20, 0, 21])),    # righe 20..21
        (False, b"\x2c"), (True, pixel),                    # scrittura in RAM
    ]


def test_scrivi_con_coordinate_oltre_i_255():
    display, spi, _ = _display(larghezza=320, altezza=240)
    display.scrivi(300, 0, 20, 1, b"\x00\x00" * 20)
    assert spi.scritture[1] == (True, bytes([0x01, 0x2C, 0x01, 0x3F]))  # 300..319


@pytest.mark.parametrize("x, y, larghezza, altezza", [(-1, 0, 2, 2), (15, 0, 2, 2), (0, 15, 2, 2)])
def test_scrivi_rifiuta_un_rettangolo_fuori_dallo_schermo(x, y, larghezza, altezza):
    display, spi, _ = _display()
    with pytest.raises(ValueError, match="esce dallo schermo"):
        display.scrivi(x, y, larghezza, altezza, b"\x00" * (larghezza * altezza * 2))
    assert spi.scritture == []


def test_scrivi_rifiuta_un_numero_di_byte_sbagliato():
    display, _, _ = _display()
    with pytest.raises(ValueError, match="servono 8 byte"):
        display.scrivi(0, 0, 2, 2, b"\x00" * 7)


def test_riempi_copre_tutto_lo_schermo_con_quel_colore():
    display, spi, _ = _display(larghezza=4, altezza=2)
    display.riempi((255, 0, 0))
    assert spi.scritture[-1] == (True, b"\xf8\x00" * 8)


def test_chiudi_spegne_il_backlight_e_libera_i_pin():
    display, spi, gpio = _display()
    display.inizializza()
    display.chiudi()
    assert gpio.livelli[BL] is False
    assert spi.chiuso and gpio.rilasciato


# --- UscitaSpi -------------------------------------------------------------

def _frame(colore=(0, 0, 0), pixel=None, lato=16):
    immagine = Image.new("RGB", (lato, lato), colore)
    for (x, y), c in (pixel or {}).items():
        immagine.putpixel((x, y), c)
    return immagine


def _uscita(lato=16):
    display, spi, gpio = _display(larghezza=lato, altezza=lato)
    return UscitaSpi(display=display), spi, gpio


def _byte_pixel(spi):
    """I byte dell'ultima scrittura in RAM."""
    return spi.scritture[-1][1]


def test_uscita_spi_parte_con_lo_schermo_nero_non_bianco():
    uscita, spi, _ = _uscita()
    assert _byte_pixel(spi) == b"\x00\x00" * (16 * 16)


def test_il_primo_fotogramma_si_scrive_per_intero():
    uscita, spi, _ = _uscita()
    uscita.disegna_frame(_frame((255, 0, 0)))
    assert _byte_pixel(spi) == b"\xf8\x00" * (16 * 16)
    assert uscita.fotogrammi_inviati == 1


def test_un_fotogramma_uguale_non_scrive_niente():
    uscita, spi, _ = _uscita()
    uscita.disegna_frame(_frame((10, 20, 30)))
    scritture = len(spi.scritture)
    uscita.disegna_frame(_frame((10, 20, 30)))
    assert len(spi.scritture) == scritture
    assert uscita.fotogrammi_inviati == 1


def test_si_scrive_solo_il_rettangolo_cambiato():
    uscita, spi, _ = _uscita()
    uscita.disegna_frame(_frame())
    uscita.disegna_frame(_frame(pixel={(3, 5): (255, 0, 0), (6, 7): (0, 255, 0)}))
    # Rettangolo dal pixel (3,5) al (6,7): 4 colonne x 3 righe.
    assert spi.scritture[-6:-1] == [
        (False, b"\x2a"), (True, bytes([0, 3, 0, 6])),
        (False, b"\x2b"), (True, bytes([0, 5, 0, 7])),
        (False, b"\x2c"),
    ]
    assert len(_byte_pixel(spi)) == 4 * 3 * 2


def test_il_video_e_centrato_e_i_byte_sono_scambiati():
    uscita, spi, _ = _uscita(lato=16)
    uscita.inizio_video(8, 4)
    rosso_little_endian = (0xF800).to_bytes(2, "little") * (8 * 4)
    uscita.disegna_video(rosso_little_endian, 8, 4)
    assert _byte_pixel(spi) == b"\xf8\x00" * (8 * 4)       # big endian per l'ILI9341
    assert spi.scritture[-6:-1] == [
        (False, b"\x2a"), (True, bytes([0, 4, 0, 11])),    # colonne 4..11: (16-8)/2 = 4
        (False, b"\x2b"), (True, bytes([0, 6, 0, 9])),     # righe 6..9: (16-4)/2 = 6
        (False, b"\x2c"),
    ]


def test_un_video_piu_grande_dello_schermo_si_salta():
    uscita, spi, _ = _uscita(lato=16)
    scritture = len(spi.scritture)
    uscita.disegna_video(b"\x00\x00" * (20 * 20), 20, 20)
    assert len(spi.scritture) == scritture


def test_dopo_il_video_la_faccia_si_riscrive_per_intero():
    uscita, spi, _ = _uscita()
    uscita.disegna_frame(_frame((1, 2, 3)))
    uscita.inizio_video(4, 4)
    uscita.fine_video()
    uscita.disegna_frame(_frame((1, 2, 3)))  # stesso fotogramma di prima, ma lo schermo ha i resti del video
    assert len(_byte_pixel(spi)) == 16 * 16 * 2


def test_chiudi_arriva_al_display():
    uscita, _, gpio = _uscita()
    uscita.chiudi()
    assert gpio.livelli[BL] is False and gpio.rilasciato


def test_crea_display_da_ambiente_legge_i_pin(monkeypatch):
    creati = {}

    class SpiDevFinto:
        def __init__(self, bus, dispositivo, velocita_hz):
            creati["spi"] = (bus, dispositivo, velocita_hz)

    monkeypatch.setattr(modulo_spi, "SpiDev", SpiDevFinto)
    monkeypatch.setattr(modulo_spi, "GpioRpi", GpioFinto)
    display = crea_display_da_ambiente({"BMO_SPI_DC": "23", "BMO_SPI_RST": "24", "BMO_SPI_BL": "18",
                                        "BMO_SPI_HZ": "32000000", "BMO_SPI_MADCTL": "0xE8"})
    assert (display.dc, display.rst, display.bl, display.madctl) == (23, 24, 18, 0xE8)
    assert creati["spi"] == (0, 0, 32_000_000)
    predefiniti = crea_display_da_ambiente({})
    assert (predefiniti.dc, predefiniti.rst, predefiniti.bl, predefiniti.madctl) == (25, 27, 12, 0x28)


def test_senza_spidev_il_messaggio_e_chiaro(monkeypatch):
    def manca(*_):
        raise ImportError("No module named 'spidev'")

    monkeypatch.setattr(modulo_spi, "SpiDev", manca)
    with pytest.raises(RuntimeError, match="spidev"):
        crea_display_da_ambiente({})
