"""Adapter ingresso microfono: ALSA (arecord) su entrambi gli ambienti.

Sia il Pi (HAT WM8960) sia il PC di sviluppo (omarchy/Linux, ALSA o
PipeWire con compatibilita' ALSA) espongono `arecord`: cambia solo il
device. Va verificato sulla macchina reale con `arecord -l`.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path
from typing import Iterator

import webrtcvad

from .. import vad

CHUNK_BYTES = 4096


class ArecordAdapter:
    """Cattura microfono via `arecord`.

    Parametri di riferimento per il Pi: docs/02-piano-attuale.md §2.3
    (S32_LE, 48kHz, stereo, device hw:0,0).
    """

    def __init__(
        self,
        dispositivo: str = "default",
        frequenza: int = 48000,
        canali: int = 2,
        formato: str = "S32_LE",
    ) -> None:
        self.dispositivo = dispositivo
        self.frequenza = frequenza
        self.canali = canali
        self.formato = formato

    def _comando_base(self) -> list[str]:
        return [
            "arecord",
            "-D", self.dispositivo,
            "-f", self.formato,
            "-r", str(self.frequenza),
            "-c", str(self.canali),
        ]

    def flusso_pcm(self) -> Iterator[bytes]:
        processo = subprocess.Popen(
            self._comando_base() + ["-t", "raw", "-"],
            stdout=subprocess.PIPE,
        )
        assert processo.stdout is not None
        try:
            while True:
                dati = processo.stdout.read(CHUNK_BYTES)
                if not dati:
                    break
                yield dati
        finally:
            processo.terminate()

    def registra(self, destinazione: Path, durata_s: float) -> Path:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        # `-d` di arecord accetta solo secondi interi: si passa il numero di
        # campioni con `-s`, cosi' vanno bene anche durate come 1.5 s.
        campioni = round(durata_s * self.frequenza)
        subprocess.run(
            self._comando_base() + ["-s", str(campioni), str(destinazione)],
            check=True,
        )
        return destinazione

    def registra_fino_al_silenzio(
        self,
        destinazione: Path,
        cap_s: float,
        silenzio_ms: float = vad.SILENZIO_MS_PREDEFINITO,
        aggressivita: int = vad.AGGRESSIVITA_PREDEFINITA,
    ) -> tuple[Path, vad.Diagnostica]:
        """Registra finché non rileva silenzio (o scade `cap_s`) e scrive un WAV vero.

        A differenza di `registra()`, non decide la durata prima di cominciare:
        la logica di quando fermarsi è in `vad.py`, qui c'è solo il microfono e
        la scrittura del file (un WAV con l'header, non il flusso grezzo di
        `flusso_pcm()`: senza header Gemini riceverebbe rumore invece
        dell'errore chiaro che ci si aspetterebbe).

        Richiede mono a 16 bit: sul PC di sviluppo è già così (`factory.py`),
        sul Pi (S32_LE stereo) andrà convertito — non ancora fatto, si vedrà
        con l'hardware in mano (Fase 4).
        """
        if self.formato != "S16_LE" or self.canali != 1:
            raise ValueError(
                f"il VAD richiede mono a 16 bit (S16_LE), non {self.formato} a {self.canali} canali"
            )
        vad.valida_frequenza(self.frequenza)
        rilevatore = webrtcvad.Vad(aggressivita)
        dimensione = vad.dimensione_frame(self.frequenza)
        flusso = self.flusso_pcm()
        try:
            audio, diagnostica = vad.ascolta_fino_al_silenzio(
                vad.ritaglia_in_frame(flusso, dimensione), self.frequenza, rilevatore, cap_s, silenzio_ms
            )
        finally:
            flusso.close()  # ferma subito arecord, anche se ci si è fermati prima della fine del flusso
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destinazione), "wb") as scrittore:
            scrittore.setnchannels(1)
            scrittore.setsampwidth(2)
            scrittore.setframerate(self.frequenza)
            scrittore.writeframes(audio)
        return destinazione, diagnostica
