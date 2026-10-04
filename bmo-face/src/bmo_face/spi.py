"""Il display vero: un ILI9341 su SPI0 più tre GPIO (issue #77).

Il modulo è il Waveshare 2.4" LCD (ILI9341, 240×320, senza touch) del piano
(`docs/02-piano-attuale.md` §1.3). Qui sta solo il pilota del controller; chi
decide *cosa* disegnare è `pannello.UscitaSpi`.

Pin e parametri si leggono dall'ambiente, così cambiare cablaggio non vuol dire
toccare il codice (BCM, non numero del pin fisico):

    BMO_SPI_DC       25   dati/comando
    BMO_SPI_RST      27   reset
    BMO_SPI_BL       12   retroilluminazione (con il HAT audio GPIO18 non va: è l'I2S)
    BMO_SPI_BUS      0    /dev/spidev<bus>.<dispositivo>
    BMO_SPI_DISP     0
    BMO_SPI_HZ       20000000
    BMO_SPI_MADCTL   0x28 orientamento e ordine dei colori (0x28 = orizzontale, BGR)

I default sono i pin di fabbrica del Waveshare, con il backlight spostato sul
GPIO12 (pin 32): verificato dal vivo il 4/10/2026. Gli altri pin di fabbrica
(MOSI GPIO10, SCLK GPIO11, CS CE0/GPIO8) sono quelli di SPI0 e non si scelgono.

`spidev` e `RPi.GPIO` (su Raspberry Pi OS: `rpi-lgpio`) si importano solo
quando servono, così il resto del pacchetto resta usabile sul PC.
"""
from __future__ import annotations

import os
import time
from typing import Any, Protocol

import numpy as np

LARGHEZZA = 320
ALTEZZA = 240

# Comandi dell'ILI9341 usati qui.
SWRESET = 0x01
SLPOUT = 0x11
DISPON = 0x29
CASET = 0x2A
PASET = 0x2B
RAMWR = 0x2C
MADCTL = 0x36
COLMOD = 0x3A


class Spi(Protocol):
    def scrivi(self, dati: bytes) -> None: ...

    def chiudi(self) -> None: ...


class Gpio(Protocol):
    def uscita(self, pin: int, alto: bool) -> None: ...

    def rilascia(self) -> None: ...


class SpiDev:
    """`spidev` di sistema. `writebytes2` accetta direttamente `bytes` e spezza da sé."""

    def __init__(self, bus: int, dispositivo: int, velocita_hz: int) -> None:
        import spidev

        self._spi = spidev.SpiDev()
        self._spi.open(bus, dispositivo)
        self._spi.max_speed_hz = velocita_hz
        self._spi.mode = 0

    def scrivi(self, dati: bytes) -> None:
        self._spi.writebytes2(dati)

    def chiudi(self) -> None:
        self._spi.close()


class GpioRpi:
    """`RPi.GPIO` (su Raspberry Pi OS lo fornisce `rpi-lgpio`)."""

    def __init__(self) -> None:
        import RPi.GPIO as gpio

        self._gpio = gpio
        self._pin: list[int] = []
        gpio.setwarnings(False)
        gpio.setmode(gpio.BCM)

    def uscita(self, pin: int, alto: bool) -> None:
        if pin not in self._pin:
            self._gpio.setup(pin, self._gpio.OUT, initial=self._gpio.LOW)
            self._pin.append(pin)
        self._gpio.output(pin, self._gpio.HIGH if alto else self._gpio.LOW)

    def rilascia(self) -> None:
        if self._pin:
            self._gpio.cleanup(self._pin)
            self._pin = []


def rgb565_big_endian(rgb888: np.ndarray) -> bytes:
    """Un array (h, w, 3) uint8 in RGB565 con il byte alto per primo, come vuole l'ILI9341."""
    a = rgb888.astype(np.uint16)
    valore = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return valore.astype(">u2").tobytes()


class DisplayIli9341:
    """Il controller: inizializzazione, finestra di scrittura, pixel.

    `spi` e `gpio` sono iniettabili: nei test sono finti, sul Pi sono `SpiDev`
    e `GpioRpi`. `dormi` è iniettabile per non aspettare davvero.
    """

    def __init__(
        self,
        spi: Spi,
        gpio: Gpio,
        *,
        dc: int = 25,
        rst: int = 27,
        bl: int = 12,
        madctl: int = 0x28,
        larghezza: int = LARGHEZZA,
        altezza: int = ALTEZZA,
        dormi=time.sleep,
    ) -> None:
        self.spi, self.gpio = spi, gpio
        self.dc, self.rst, self.bl = dc, rst, bl
        self.madctl = madctl
        self.larghezza, self.altezza = larghezza, altezza
        self._dormi = dormi

    def _comando(self, codice: int, argomenti: bytes = b"") -> None:
        self.gpio.uscita(self.dc, False)
        self.spi.scrivi(bytes([codice]))
        if argomenti:
            self.gpio.uscita(self.dc, True)
            self.spi.scrivi(argomenti)

    def inizializza(self) -> None:
        """Reset hardware, uscita dal sonno, 16 bit per pixel, display acceso, backlight."""
        self.gpio.uscita(self.rst, True)
        self._dormi(0.05)
        self.gpio.uscita(self.rst, False)
        self._dormi(0.05)
        self.gpio.uscita(self.rst, True)
        self._dormi(0.15)
        self._comando(SWRESET)
        self._dormi(0.15)
        self._comando(SLPOUT)
        self._dormi(0.15)
        self._comando(COLMOD, b"\x55")
        self._comando(MADCTL, bytes([self.madctl]))
        self._comando(DISPON)
        self.gpio.uscita(self.bl, True)

    def scrivi(self, x: int, y: int, larghezza: int, altezza: int, pixel: bytes) -> None:
        """Scrive un rettangolo di pixel RGB565 big endian a partire da (x, y)."""
        if larghezza <= 0 or altezza <= 0:
            return
        if len(pixel) != larghezza * altezza * 2:
            raise ValueError(f"servono {larghezza * altezza * 2} byte per {larghezza}x{altezza}, non {len(pixel)}")
        x1, y1 = x + larghezza - 1, y + altezza - 1
        if x < 0 or y < 0 or x1 >= self.larghezza or y1 >= self.altezza:
            raise ValueError(f"il rettangolo ({x},{y})-({x1},{y1}) esce dallo schermo {self.larghezza}x{self.altezza}")
        self._comando(CASET, bytes([x >> 8, x & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._comando(PASET, bytes([y >> 8, y & 0xFF, y1 >> 8, y1 & 0xFF]))
        self._comando(RAMWR)
        self.gpio.uscita(self.dc, True)
        self.spi.scrivi(pixel)

    def riempi(self, colore_rgb: tuple[int, int, int]) -> None:
        pieno = np.empty((self.altezza, self.larghezza, 3), dtype=np.uint8)
        pieno[:] = colore_rgb
        self.scrivi(0, 0, self.larghezza, self.altezza, rgb565_big_endian(pieno))

    def chiudi(self) -> None:
        """Backlight spento, SPI chiuso, pin liberati (a script finito tornerebbero in ingresso)."""
        self.gpio.uscita(self.bl, False)
        self.spi.chiudi()
        self.gpio.rilascia()


def crea_display_da_ambiente(ambiente: dict[str, str] | None = None) -> DisplayIli9341:
    """Il display coi pin di `BMO_SPI_*` (vedi il docstring del modulo)."""
    env: Any = os.environ if ambiente is None else ambiente

    def numero(nome: str, predefinito: int) -> int:
        valore = env.get(nome)
        return int(valore, 0) if valore else predefinito

    try:
        spi = SpiDev(numero("BMO_SPI_BUS", 0), numero("BMO_SPI_DISP", 0), numero("BMO_SPI_HZ", 20_000_000))
        gpio = GpioRpi()
    except ImportError as errore:
        raise RuntimeError(
            f"il display SPI vuole `spidev` e `RPi.GPIO` (sul Pi: i pacchetti di sistema python3-spidev e "
            f"python3-rpi-lgpio): {errore}"
        ) from errore
    return DisplayIli9341(
        spi,
        gpio,
        dc=numero("BMO_SPI_DC", 25),
        rst=numero("BMO_SPI_RST", 27),
        bl=numero("BMO_SPI_BL", 12),
        madctl=numero("BMO_SPI_MADCTL", 0x28),
    )
