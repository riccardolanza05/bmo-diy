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

import numpy as np
import webrtcvad

from .. import vad

CHUNK_BYTES = 4096


def _registra_fino_al_silenzio_da_flusso(
    flusso: Iterator[bytes],
    frequenza: int,
    destinazione: Path,
    cap_s: float,
    silenzio_ms: float,
    aggressivita: int,
) -> tuple[Path, "vad.Diagnostica"]:
    """La logica condivisa fra `ArecordAdapter` e `ArecordConvertitoreAdapter`
    (issue #64): entrambi consegnano un flusso già mono a 16 bit, cambia solo
    da dove arrivano i byte (microfono nativo o convertito al volo)."""
    vad.valida_frequenza(frequenza)
    rilevatore = webrtcvad.Vad(aggressivita)
    dimensione = vad.dimensione_frame(frequenza)
    try:
        audio, diagnostica = vad.ascolta_fino_al_silenzio(
            vad.ritaglia_in_frame(flusso, dimensione), frequenza, rilevatore, cap_s, silenzio_ms
        )
    finally:
        flusso.close()  # ferma subito arecord, anche se ci si è fermati prima della fine del flusso
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destinazione), "wb") as scrittore:
        scrittore.setnchannels(1)
        scrittore.setsampwidth(2)
        scrittore.setframerate(frequenza)
        scrittore.writeframes(audio)
    return destinazione, diagnostica


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
        sul Pi va usato `ArecordConvertitoreAdapter` qui sotto, che cattura al
        formato nativo del microfono (S32_LE stereo, issue #64) e converte
        al volo — questa classe resta quella "muta" che non sa convertire.
        """
        if self.formato != "S16_LE" or self.canali != 1:
            raise ValueError(
                f"il VAD richiede mono a 16 bit (S16_LE), non {self.formato} a {self.canali} canali"
            )
        return _registra_fino_al_silenzio_da_flusso(
            self.flusso_pcm(), self.frequenza, destinazione, cap_s, silenzio_ms, aggressivita
        )


def _converti_s32_stereo_a_s16_mono(
    grezzo: bytes, avanzo: np.ndarray, fattore_decimazione: int
) -> tuple[bytes, np.ndarray]:
    """Un pezzo di PCM S32_LE stereo -> PCM S16_LE mono, a un fattore intero
    di frequenza più basso (issue #64: sul Pi il microfono registra a S32_LE
    stereo 48 kHz, VAD e wake word vogliono S16_LE mono 16 kHz).

    Tre passi, in quest'ordine:
    1. **downmix stereo -> mono**: media dei due canali (non se ne scarta
       uno: i due MEMS del WM8960 guardano punti diversi della stanza).
    2. **decimazione con filtro anti-aliasing**: la frequenza scende di un
       fattore intero (3, per 48000 -> 16000) facendo la media di ogni
       gruppo di `fattore_decimazione` campioni consecutivi invece di
       prenderne uno ogni tre (`[::3]`) — un filtro passa-basso elementare
       ma sufficiente per il parlato, che altrimenti farebbe rientrare come
       rumore le frequenze sopra i 8 kHz scartate senza attenuarle prima
       (aliasing).
    3. **da 32 a 16 bit**: `>> 16`, i 16 bit più significativi — uno shift
       aritmetico su interi con segno di numpy, non un troncamento che
       ignorerebbe il segno.

    `avanzo` sono i campioni mono (già scesi da stereo, non ancora
    decimati) rimasti dal pezzo precedente perché non abbastanza per un
    gruppo intero da `fattore_decimazione`: `flusso_pcm()` li ripassa al
    giro dopo, così nessun campione si perde o si sposta nel tempo
    all'incrocio fra due letture da 4096 byte di `arecord` (che non sono in
    generale un multiplo del fattore di decimazione).
    """
    campioni = np.frombuffer(grezzo, dtype="<i4").reshape(-1, 2)
    mono = campioni.astype(np.int64).mean(axis=1).astype(np.int32)
    tutto = np.concatenate([avanzo, mono]) if avanzo.size else mono
    n_utilizzabili = (len(tutto) // fattore_decimazione) * fattore_decimazione
    da_convertire, nuovo_avanzo = tutto[:n_utilizzabili], tutto[n_utilizzabili:]
    if n_utilizzabili == 0:
        return b"", nuovo_avanzo
    finestre = da_convertire.reshape(-1, fattore_decimazione)
    filtrato = finestre.astype(np.int64).mean(axis=1).astype(np.int64)
    campioni_16 = (filtrato >> 16).astype(np.int16)
    return campioni_16.tobytes(), nuovo_avanzo


class ArecordConvertitoreAdapter:
    """Come `ArecordAdapter`, ma cattura al formato nativo del microfono del
    Pi e converte al volo a quello che VAD e wake word vogliono (issue #64).

    Il resto del codice non vede la differenza: `flusso_pcm()`,
    `registra()` e `registra_fino_al_silenzio()` consegnano sempre S16_LE
    mono alla `frequenza` di uscita, lo stesso formato che il PC di sviluppo
    produce già nativamente (`factory.crea_audio_input`). Misurato dal vivo
    sul Pi 3 A+ reale il 28/9/2026 (dati sintetici, `docs/decisioni-issue-64.md`):
    la conversione costa il 2-3% di un core, trascurabile rispetto al resto
    di bmo-core (ONNX della wake word compreso).
    """

    def __init__(
        self,
        dispositivo: str = "hw:0,0",
        frequenza_nativa: int = 48000,
        canali_nativi: int = 2,
        formato_nativo: str = "S32_LE",
        frequenza: int = 16000,
    ) -> None:
        if formato_nativo != "S32_LE":
            raise ValueError(
                f"conversione non implementata per il formato nativo {formato_nativo} (solo S32_LE)"
            )
        if canali_nativi != 2:
            raise ValueError(f"conversione non implementata per {canali_nativi} canali nativi (solo 2)")
        if frequenza_nativa % frequenza != 0:
            raise ValueError(
                f"{frequenza_nativa} Hz non è multiplo intero di {frequenza} Hz: "
                "la decimazione richiede un fattore intero"
            )
        self._nativo = ArecordAdapter(
            dispositivo=dispositivo,
            frequenza=frequenza_nativa,
            canali=canali_nativi,
            formato=formato_nativo,
        )
        self.dispositivo = dispositivo
        self.frequenza = frequenza
        self.canali = 1
        self.formato = "S16_LE"
        self._fattore_decimazione = frequenza_nativa // frequenza

    def flusso_pcm(self) -> Iterator[bytes]:
        avanzo = np.empty(0, dtype=np.int32)
        flusso_nativo = self._nativo.flusso_pcm()
        try:
            for grezzo in flusso_nativo:
                convertito, avanzo = _converti_s32_stereo_a_s16_mono(grezzo, avanzo, self._fattore_decimazione)
                if convertito:
                    yield convertito
        finally:
            flusso_nativo.close()

    def registra(self, destinazione: Path, durata_s: float) -> Path:
        """A differenza di `ArecordAdapter.registra()`, non può delegare il
        conteggio dei campioni ad `arecord -s`: quello chiederebbe al
        dispositivo nativo un formato che non supporta. Si accumula dal
        flusso già convertito finché non si raggiunge la durata richiesta."""
        campioni_target = round(durata_s * self.frequenza)
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        pezzi: list[bytes] = []
        raccolti = 0
        flusso = self.flusso_pcm()
        try:
            for pezzo in flusso:
                pezzi.append(pezzo)
                raccolti += len(pezzo) // 2  # 2 byte per campione, S16_LE
                if raccolti >= campioni_target:
                    break
        finally:
            flusso.close()
        audio = b"".join(pezzi)[: campioni_target * 2]
        with wave.open(str(destinazione), "wb") as scrittore:
            scrittore.setnchannels(1)
            scrittore.setsampwidth(2)
            scrittore.setframerate(self.frequenza)
            scrittore.writeframes(audio)
        return destinazione

    def registra_fino_al_silenzio(
        self,
        destinazione: Path,
        cap_s: float,
        silenzio_ms: float = vad.SILENZIO_MS_PREDEFINITO,
        aggressivita: int = vad.AGGRESSIVITA_PREDEFINITA,
    ) -> tuple[Path, "vad.Diagnostica"]:
        return _registra_fino_al_silenzio_da_flusso(
            self.flusso_pcm(), self.frequenza, destinazione, cap_s, silenzio_ms, aggressivita
        )
