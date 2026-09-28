"""Il rilevatore della wake word, leggero: gli stessi conti di openWakeWord (#58).

Adattato da `openwakeword/model.py` e `openwakeword/utils.py` (openWakeWord
0.4.0, Copyright 2022 David Scripka, Apache License 2.0), per la parte che
serve a BMO: audio a 16 kHz in pezzi da 80 ms (1280 campioni), modelli ONNX
senza verificatori, senza speex, senza il VAD di Silero. I punteggi sono gli
stessi di `openwakeword.Model` (i test lo controllano sugli stessi dati);
cambia solo quanto costa ottenerli.

Perché non `openwakeword.Model` (misurato sul Pi, `docs/note-issue-58.md`):

1. **`import openwakeword` costa +92 MB**: il suo `__init__` importa sempre
   `custom_verifier_model`, che si porta dietro scikit-learn e scipy, utili
   solo ad *addestrare* un verificatore. Qui il pacchetto non si importa mai:
   se ne trova solo la cartella, per i due modelli di feature, che restano
   quelli installati da pip e non vengono ridistribuiti nel repo.
2. **Arene di memoria di onnxruntime**: ogni sessione ne tiene una propria e
   non la restituisce più. Qui sono spente.
3. **L'audio in una coda di interi Python**: openWakeWord tiene gli ultimi
   10 s (160 000 campioni) in un `deque` di `int`, e ogni 80 ms lo ricopia
   tutto in una `list` per prenderne gli ultimi 1760. Qui si tengono solo i
   480 campioni che servono al pezzo successivo, in un array numpy. Idem per
   lo spettrogramma (76 righe invece di 970) e gli embedding (quante ne
   chiede il modello più lungo invece di 120).
"""

from __future__ import annotations

import importlib.util
from collections import defaultdict, deque
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

CAMPIONI_PER_PEZZO = 1280  # 80 ms a 16 kHz: l'unico formato che accetta `predict`
# Campioni del pezzo precedente che lo spettrogramma rilegge: openWakeWord
# passa al modello gli ultimi `n + 160*3` campioni.
SOVRAPPOSIZIONE = 160 * 3
FINESTRA_SPETTRO = 76  # righe di spettrogramma per un embedding
PASSO_SPETTRO = 8
BUFFER_PUNTEGGI = 30  # come `openwakeword.Model.prediction_buffer`
PUNTEGGI_A_ZERO = 5  # i primi 5 punteggi dopo un reset valgono 0, come nell'originale


def cartella_modelli_openwakeword() -> Path:
    """Dove pip ha messo i modelli di openWakeWord, senza importare il pacchetto."""
    spec = importlib.util.find_spec("openwakeword")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("openwakeword non è installato: servono i suoi modelli di feature (pip install openwakeword)")
    return Path(next(iter(spec.submodule_search_locations))) / "resources" / "models"


def percorso_modello(nome: str) -> str:
    """Un file .onnx, o il nome di un modello preaddestrato di openWakeWord (es. `hey_jarvis`)."""
    if nome.endswith(".onnx"):
        return nome
    cartella = cartella_modelli_openwakeword()
    trovati = sorted(cartella.glob(f"{nome}_v*.onnx"))
    if not trovati:
        disponibili = sorted(p.name.rsplit("_v", 1)[0] for p in cartella.glob("*_v*.onnx"))
        raise ValueError(
            f"modello wake word {nome!r} sconosciuto; preaddestrati disponibili: {', '.join(disponibili)}, "
            "oppure un percorso che finisce per .onnx"
        )
    return str(trovati[-1])


def _sessione(percorso: str) -> Any:
    import onnxruntime as ort

    opzioni = ort.SessionOptions()
    opzioni.intra_op_num_threads = 1
    opzioni.inter_op_num_threads = 1
    # Le arene: la voce di RAM più grossa dopo scikit-learn (#58). Senza,
    # onnxruntime alloca e libera a ogni `run`, per tensori minuscoli.
    opzioni.enable_cpu_mem_arena = False
    opzioni.enable_mem_pattern = False
    return ort.InferenceSession(percorso, sess_options=opzioni, providers=["CPUExecutionProvider"])


class RilevatoreLeggero:
    """Sostituto di `openwakeword.Model` per `richiamo.RichiamoWakeWord`: `predict` e `reset`."""

    def __init__(self, modelli: list[str]) -> None:
        cartella = cartella_modelli_openwakeword()
        self._spettro = _sessione(str(cartella / "melspectrogram.onnx"))
        self._embedding = _sessione(str(cartella / "embedding_model.onnx"))
        self._modelli: dict[str, Any] = {}
        self._ingressi: dict[str, tuple[str, int]] = {}
        self._etichette: dict[str, list[str]] = {}
        for percorso in (percorso_modello(m) for m in modelli):
            nome = Path(percorso).name[: -len(".onnx")]
            sessione = _sessione(percorso)
            ingresso = sessione.get_inputs()[0]
            self._modelli[nome] = sessione
            self._ingressi[nome] = (ingresso.name, int(ingresso.shape[1]))
            uscite = int(sessione.get_outputs()[0].shape[1])
            # Come l'originale senza `class_mapping_dicts`: un'uscita porta il
            # nome del modello, più uscite si chiamano "0", "1", ...
            self._etichette[nome] = [nome] if uscite == 1 else [str(i) for i in range(uscite)]
        self._righe_embedding = max(n for _, n in self._ingressi.values())

        self._coda_audio = np.zeros(0, dtype=np.int16)
        self._buffer_spettro = np.ones((FINESTRA_SPETTRO, 32), dtype=np.float32)
        # Come l'originale: 10 s di silenzio all'avvio, di cui si tengono solo
        # le ultime righe che un modello può chiedere.
        self._buffer_embedding = self._embedding_di(np.zeros(160000, dtype=np.int16))[-self._righe_embedding :]
        self.reset()

    def reset(self) -> None:
        """Azzera i punteggi recenti, non le feature (come `openwakeword.Model.reset`)."""
        self._punteggi: defaultdict[str, deque] = defaultdict(partial(deque, maxlen=BUFFER_PUNTEGGI))

    def _spettrogramma(self, campioni: np.ndarray) -> np.ndarray:
        uscita = self._spettro.run(None, {"input": campioni[None,].astype(np.float32)})
        return np.squeeze(uscita[0]) / 10 + 2  # la trasformazione di openWakeWord

    def _embedding_di(self, campioni: np.ndarray) -> np.ndarray:
        spettro = self._spettrogramma(campioni)
        finestre = [
            spettro[i : i + FINESTRA_SPETTRO]
            for i in range(0, spettro.shape[0], PASSO_SPETTRO)
            if spettro[i : i + FINESTRA_SPETTRO].shape[0] == FINESTRA_SPETTRO
        ]
        lotto = np.expand_dims(np.array(finestre), axis=-1).astype(np.float32)
        return self._embedding.run(None, {"input_1": lotto})[0].squeeze()

    def _aggiorna_feature(self, pezzo: np.ndarray) -> None:
        dati = np.concatenate((self._coda_audio, pezzo))
        self._coda_audio = dati[-SOVRAPPOSIZIONE:]
        self._buffer_spettro = np.vstack((self._buffer_spettro, self._spettrogramma(dati)))[-FINESTRA_SPETTRO:]
        finestra = self._buffer_spettro.astype(np.float32)[None, :, :, None]
        nuovo = self._embedding.run(None, {"input_1": finestra})[0].squeeze()
        self._buffer_embedding = np.vstack((self._buffer_embedding, nuovo))[-self._righe_embedding :]

    def predict(self, x: np.ndarray) -> dict[str, float]:
        if len(x) != CAMPIONI_PER_PEZZO:
            raise ValueError(f"servono pezzi da {CAMPIONI_PER_PEZZO} campioni (80 ms a 16 kHz), non {len(x)}")
        if x.dtype != np.int16:
            raise ValueError(f"servono campioni PCM a 16 bit (int16), non {x.dtype}")
        self._aggiorna_feature(x)
        punteggi: dict[str, float] = {}
        for nome, sessione in self._modelli.items():
            nome_ingresso, righe = self._ingressi[nome]
            feature = self._buffer_embedding[-righe:][None,].astype(np.float32)
            previsione = sessione.run(None, {nome_ingresso: feature})
            for indice, etichetta in enumerate(self._etichette[nome]):
                punteggi[etichetta] = previsione[0][0][indice]
            # Dentro il ciclo sui modelli e su TUTTI i punteggi visti finora,
            # proprio come `openwakeword.Model.predict`: il primo modello si
            # ritrova nel buffer un'aggiunta per ogni modello caricato, quindi
            # smette prima degli altri di valere 0 dopo un reset. Una
            # stranezza dell'originale, riprodotta apposta: i punteggi devono
            # essere gli stessi, non "più giusti".
            for etichetta in punteggi:
                if len(self._punteggi[etichetta]) < PUNTEGGI_A_ZERO:
                    punteggi[etichetta] = 0.0
                self._punteggi[etichetta].append(punteggi[etichetta])
        return punteggi
