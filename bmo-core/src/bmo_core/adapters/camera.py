"""Adapter fotocamera: libcamera-still sul Pi, webcam V4L2 sul PC di sviluppo."""
from __future__ import annotations

import subprocess
from pathlib import Path


class LibcameraAdapter:
    """Raspberry Pi + modulo camera CSI (OV5647), via libcamera-still.

    Comando di riferimento: docs/02-piano-attuale.md, Fase 5.
    """

    def __init__(
        self,
        larghezza: int = 640,
        altezza: int = 480,
        qualita: int = 75,
        timeout_ms: int = 800,
    ) -> None:
        self.larghezza = larghezza
        self.altezza = altezza
        self.qualita = qualita
        self.timeout_ms = timeout_ms

    def scatta_foto(self, destinazione: Path) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "libcamera-still",
                "-o", str(destinazione),
                "--width", str(self.larghezza),
                "--height", str(self.altezza),
                "-q", str(self.qualita),
                "-n",
                "-t", str(self.timeout_ms),
            ],
            check=True,
        )
        return destinazione


class WebcamV4L2Adapter:
    """Webcam del PC di sviluppo (omarchy/Linux), via ffmpeg + V4L2.

    `dispositivo` va verificato sulla macchina reale con `v4l2-ctl --list-devices`
    (di solito /dev/video0, ma non è garantito se ci sono più device video).
    """

    def __init__(
        self,
        dispositivo: str = "/dev/video0",
        larghezza: int = 640,
        altezza: int = 480,
    ) -> None:
        self.dispositivo = dispositivo
        self.larghezza = larghezza
        self.altezza = altezza

    def scatta_foto(self, destinazione: Path) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "v4l2",
                "-video_size", f"{self.larghezza}x{self.altezza}",
                "-i", self.dispositivo,
                "-frames:v", "1",
                str(destinazione),
            ],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        return destinazione


# --- Camera CSI "grezza" (issue #77) ----------------------------------------
#
# Con `gpu_mem=16` (la scelta per la RAM del Pi 3 A+) il firmware è quello
# ridotto: niente ISP, `rpicam`/libcamera non vedono nessuna camera
# (`vcgencmd get_camera` -> `supported=0`). Il kernel però vede lo stesso il
# sensore OV5647 e il controller `unicam`, e V4L2 dà il frame Bayer grezzo:
# qui lo si sviluppa a mano, con numpy, senza toccare `gpu_mem`.
#
# Il formato è `pGAA` (Bayer GBRG a 10 bit impacchettato: ogni 4 pixel sono 5
# byte, i primi quattro con gli 8 bit alti e il quinto con i 2 bit bassi).

NERO_BAYER = 16        # livello di nero del sensore, su 1023
GUADAGNO_MIN, GUADAGNO_MAX = 32, 1023
ESPOSIZIONE_MIN, ESPOSIZIONE_MAX = 4, 1431


def spacchetta_bayer_10bit(grezzo: bytes, larghezza: int, altezza: int, stride: int):
    """Un frame `pGAA` -> array uint16 (altezza, larghezza) coi valori a 10 bit."""
    import numpy as np

    righe = np.frombuffer(grezzo, dtype=np.uint8, count=stride * altezza).reshape(altezza, stride)
    gruppi = righe[:, : larghezza // 4 * 5].reshape(altezza, larghezza // 4, 5)
    pixel = np.empty((altezza, larghezza // 4, 4), dtype=np.uint16)
    for k in range(4):
        pixel[:, :, k] = (gruppi[:, :, k].astype(np.uint16) << 2) | ((gruppi[:, :, 4] >> (2 * k)) & 3)
    return pixel.reshape(altezza, larghezza)


def luminosita_media(bayer) -> float:
    """Media dei pixel verdi (GBRG: righe pari colonne pari, righe dispari colonne dispari), senza il nero."""
    verdi = (bayer[0::2, 0::2].astype("float32") + bayer[1::2, 1::2].astype("float32")) / 2
    return max(float(verdi.mean()) - NERO_BAYER, 0.0)


def sviluppa_bayer_gbrg(bayer):
    """Bayer GBRG -> RGB uint8 a **metà risoluzione** (un pixel per cella 2x2, nessuna interpolazione).

    Bilanciamento del bianco "mondo grigio" e curva gamma 2,2: niente ISP qui,
    ma per una foto da far guardare a un modello e a una persona basta. Il
    mezzo dimensionamento è anche ciò che tiene il picco di RAM sotto i 10 MB.
    """
    import numpy as np

    g1 = bayer[0::2, 0::2].astype(np.float32)
    b = bayer[0::2, 1::2].astype(np.float32)
    r = bayer[1::2, 0::2].astype(np.float32)
    g2 = bayer[1::2, 1::2].astype(np.float32)
    rgb = np.dstack([r, (g1 + g2) / 2, b])
    rgb -= NERO_BAYER
    np.clip(rgb, 0, None, out=rgb)
    medie = rgb.reshape(-1, 3).mean(axis=0)
    guadagni = np.clip(medie.mean() / np.maximum(medie, 1e-6), 0.5, 4.0)
    rgb *= guadagni
    rgb /= max(float(np.percentile(rgb, 99.5)), 1e-6)
    np.clip(rgb, 0, 1, out=rgb)
    return (np.power(rgb, 1 / 2.2) * 255 + 0.5).astype(np.uint8)


class CameraGrezzaV4L2:
    """Camera CSI del Pi (OV5647) via V4L2 grezzo, per quando libcamera non vede niente.

    Si attiva con `BMO_CAMERA=grezza` (vedi `factory.crea_camera`); non cambia
    niente per chi non lo chiede. Servono `v4l2-ctl` e `media-ctl`
    (pacchetto `v4l-utils`), già sul Raspberry Pi OS.

    Il sensore non ha auto-esposizione: si regolano esposizione e guadagno a
    mano, misurando la luminosità di un frame e correggendo fino a due volte
    (da 3 a 4 catture di mezzo secondo l'una al buio, una sola con luce buona).
    Gli ultimi valori usati si ricordano per le foto dopo.

    Variabili d'ambiente: `BMO_CAMERA_RUOTA` (0 o 180, per una camera montata
    a testa in giù), `BMO_CAMERA_SENSORE` (nome dell'entità V4L2, cambia con
    il bus I2C), `BMO_CAMERA_MEDIA` e `BMO_CAMERA_VIDEO`.
    """

    LARGHEZZA, ALTEZZA = 1296, 972
    OBIETTIVO = 200.0     # luminosità media del verde (0-1007) a cui puntare
    FRAME_DA_CATTURARE = 6  # i primi due, dopo un cambio di esposizione, sono ancora quelli vecchi

    def __init__(
        self,
        ruota: int | None = None,
        sensore: str | None = None,
        media: str | None = None,
        video: str | None = None,
        esegui=subprocess.run,
        qualita: int = 80,
        tentativi_esposizione: int = 2,
    ) -> None:
        import os

        self.ruota = int(os.environ.get("BMO_CAMERA_RUOTA", 0)) if ruota is None else ruota
        self.sensore = sensore or os.environ.get("BMO_CAMERA_SENSORE", "ov5647 10-0036")
        self.media = media or os.environ.get("BMO_CAMERA_MEDIA", "/dev/media0")
        self.video = video or os.environ.get("BMO_CAMERA_VIDEO", "/dev/video0")
        self.sotto_dispositivo = os.environ.get("BMO_CAMERA_SOTTO", "/dev/v4l-subdev0")
        self.esegui = esegui
        self.qualita = qualita
        self.tentativi_esposizione = tentativi_esposizione
        self.esposizione = 1000
        self.guadagno = 64

    def _v4l2(self, *argomenti: str) -> None:
        self.esegui(list(argomenti), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _configura(self) -> None:
        self._v4l2("media-ctl", "-d", self.media, "--set-v4l2",
                   f'"{self.sensore}":0[fmt:SGBRG10_1X10/{self.LARGHEZZA}x{self.ALTEZZA}]')
        self._v4l2("v4l2-ctl", "-d", self.video,
                   f"--set-fmt-video=width={self.LARGHEZZA},height={self.ALTEZZA},pixelformat=pGAA")

    def _cattura(self, cartella: Path):
        """Cattura qualche frame con l'esposizione corrente e restituisce l'ultimo, spacchettato."""
        self._v4l2("v4l2-ctl", "-d", self.sotto_dispositivo,
                   f"--set-ctrl=exposure={self.esposizione},analogue_gain={self.guadagno}")
        grezzo = cartella / "frame.raw"
        grezzo.unlink(missing_ok=True)
        self._v4l2("v4l2-ctl", "-d", self.video, "--stream-mmap",
                   f"--stream-count={self.FRAME_DA_CATTURARE}", f"--stream-to={grezzo}")
        dati = grezzo.read_bytes()
        dimensione = len(dati) // self.FRAME_DA_CATTURARE
        stride = dimensione // self.ALTEZZA
        return spacchetta_bayer_10bit(dati[-dimensione:], self.LARGHEZZA, self.ALTEZZA, stride)

    def _correggi_esposizione(self, luminosita: float) -> None:
        """Porta il prodotto esposizione x guadagno verso l'obiettivo: prima l'esposizione, poi il guadagno."""
        fattore = min(max(self.OBIETTIVO / max(luminosita, 1.0), 0.1), 10.0)
        prodotto = self.esposizione * self.guadagno * fattore
        guadagno = max(GUADAGNO_MIN, -(-int(prodotto) // ESPOSIZIONE_MAX))
        self.guadagno = min(guadagno, GUADAGNO_MAX)
        self.esposizione = int(min(max(prodotto / self.guadagno, ESPOSIZIONE_MIN), ESPOSIZIONE_MAX))

    def scatta_foto(self, destinazione: Path) -> Path:
        import tempfile

        from PIL import Image

        destinazione.parent.mkdir(parents=True, exist_ok=True)
        self._configura()
        with tempfile.TemporaryDirectory(prefix="bmo-camera-") as cartella:
            bayer = self._cattura(Path(cartella))
            for _ in range(self.tentativi_esposizione):
                luminosita = luminosita_media(bayer)
                if 0.6 * self.OBIETTIVO <= luminosita <= 1.6 * self.OBIETTIVO:
                    break
                self._correggi_esposizione(luminosita)
                bayer = self._cattura(Path(cartella))
        immagine = Image.fromarray(sviluppa_bayer_gbrg(bayer))
        if self.ruota == 180:
            immagine = immagine.rotate(180)
        immagine.save(destinazione, "JPEG", quality=self.qualita)
        return destinazione
