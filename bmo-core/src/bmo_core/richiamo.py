"""Il richiamo a voce (issue #22): «Hey Jarvis» al posto di Invio.

**Fase 1.5, soglia provvisoria.** Il piano (§2.6) sceglie apposta il modello
preaddestrato `hey_jarvis` di openWakeWord per lo sviluppo: addestrare un
modello «Hey BMO» proprio (via il Colab ufficiale, su dati sintetici) è una
rifinitura successiva, non un prerequisito. Il cancello vero — soglia tarata
nella stanza vera con la TV accesa, ≥ 9/10 a 3 m, < 1 falso positivo al
giorno — resta alla fase 4.4, sul microfono del HAT montato sul Pi. Qui la
soglia è solo un punto di partenza, con un comando apposta per tararla
(`main()` sotto, come `vad.py` per `SILENZIO_MS`).

**Perché openWakeWord e non un servizio in cloud.** Il §2.5 del piano lo dice
esplicitamente: la wake word è l'unica cosa che *deve* restare locale, perché
l'alternativa sarebbe streammare il microfono 24/7 verso Internet. openWakeWord
gira interamente offline via ONNX Runtime — nessun account, nessuna chiave,
nessuna rete — e i modelli preaddestrati (`hey_jarvis` incluso) sono dentro il
pacchetto pip stesso: non serve scaricare niente al primo avvio.

**Stessa forma di `richiamo_da_tastiera`.** `Macchina` prende già il richiamo
come `Callable[[], bool]` (macchina.py): questo modulo fornisce
`RichiamoWakeWord`, chiamabile allo stesso modo — bloccante finché non sente
la parola, poi restituisce `True`. Non tocca `Macchina` in nessun punto.

**Riuso del ritaglio in frame del VAD.** openWakeWord vuole campioni PCM a 16
bit, 16 kHz mono, a multipli di 1280 campioni (80 ms); `vad.ritaglia_in_frame`
fa esattamente questo lavoro — riaccorpare un flusso a pezzi arbitrari in
frame di dimensione fissa — già usato per i frame da 30 ms del VAD: stessa
funzione, dimensione diversa, nessuna duplicazione.

**Opt-in, non ancora il richiamo predefinito.** Deciso il 25/9 con Riccardo,
sullo stesso schema di `VoceTts` (#42): finché la soglia non è stata sentita
funzionare dal vivo nella stanza vera, `python -m bmo_core.macchina` continua
a partire con Invio. `--wake-word` la sostituisce per la prova.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

import numpy as np

from . import vad
from .adapters import AudioInputAdapter, crea_audio_input

# 16 kHz mono, come già registra `crea_audio_input()` sul PC (factory.py) e
# come richiede webrtcvad: nessuna conversione in più rispetto al VAD.
FREQUENZA_HZ = 16000
# openWakeWord accetta multipli di 80 ms (1280 campioni); più lungo riduce il
# carico di CPU ma alza la latenza di rilevamento (docstring di Model.predict
# nel pacchetto). 80 ms, il minimo, per restare vicini al requisito dei 150 ms
# del piano fra il richiamo sentito e la faccia che cambia.
CAMPIONI_PER_FRAME = 1280
BYTE_PER_FRAME = CAMPIONI_PER_FRAME * 2  # PCM a 16 bit

# Due dei tre modelli «Hey BMO» che Riccardo ha addestrato lui stesso
# (comunità openWakeWord, non pesi ufficiali): bmo1/bmo2, rinominati da lui,
# `bmo-core/modelli-wake-word/`. Non è ancora chiaro a quale frase esatta
# risponda ciascuno — vedi la nota nel README — ma insieme coprono diverse
# pronunce di "Bimo"/"Beemo", in italiano e inglese, e caricarli entrambi
# non costa nulla in più: basta che uno solo superi la soglia. Sostituiscono
# `hey_jarvis` come predefinito: deciso il 26/9, Riccardo non lo usa.
#
# Un terzo modello (bmo3) esiste ma resta deliberatamente **fuori dal
# repo**: Riccardo lo tiene solo in locale, sul suo BMO personale — mai
# committato, per nessun motivo (deciso il 26/9). Chi vuole caricarlo lo fa
# con `--modello-wake-word <percorso locale>`, in aggiunta a questi due.
_CARTELLA_MODELLI_BMO = Path(__file__).resolve().parents[2] / "modelli-wake-word"
MODELLI_PREDEFINITI = [str(_CARTELLA_MODELLI_BMO / f"bmo{i}.onnx") for i in (1, 2)]
SOGLIA_PREDEFINITA = 0.5  # punto di partenza (§2.6), non una misura


class RilevatoreWakeWord(Protocol):
    """Quello che serve di `openwakeword.Model`: isolato per i test (vedi vad.RilevatoreVoce)."""

    def predict(self, x: np.ndarray) -> dict[str, float]: ...


def attendi_wake_word(
    frame_pcm,
    rilevatore: RilevatoreWakeWord,
    soglia: float = SOGLIA_PREDEFINITA,
) -> float | None:
    """La logica pura: consuma frame finché un punteggio supera la soglia.

    Nessun I/O qui dentro, sul modello di `vad.ascolta_fino_al_silenzio`:
    `frame_pcm` è già ritagliato a `BYTE_PER_FRAME` byte per pezzo. Restituisce
    il punteggio che ha superato la soglia, o `None` se il flusso finisce
    prima — nel mondo reale, con un microfono sempre acceso, non succede mai:
    capita solo nei test o se `arecord` muore a metà.
    """
    for frame in frame_pcm:
        campioni = np.frombuffer(frame, dtype=np.int16)
        punteggi = rilevatore.predict(campioni)
        migliore = max(punteggi.values(), default=0.0)
        if migliore >= soglia:
            return migliore
    return None


def _percorso_modello(nome: str) -> str:
    """Un nome fra i preaddestrati di openWakeWord, o un percorso a un file .onnx.

    Il secondo caso è già pensato per quando arriverà il modello «Hey BMO»
    custom (§2.6): basterà puntare `--modello-wake-word` (o `--modello` del
    comando di taratura) al file .onnx addestrato, senza toccare il codice.
    """
    if nome.endswith(".onnx"):
        return nome
    import openwakeword

    try:
        return openwakeword.models[nome]["model_path"]
    except KeyError as errore:
        disponibili = ", ".join(sorted(openwakeword.models))
        raise ValueError(
            f"modello wake word {nome!r} sconosciuto; preaddestrati disponibili: {disponibili}, "
            "oppure un percorso che finisce per .onnx"
        ) from errore


def _carica_rilevatore(modelli: str | list[str]) -> RilevatoreWakeWord:
    """Uno o più modelli caricati insieme: basta che uno solo superi la soglia.

    `attendi_wake_word` prende già il massimo fra tutti i punteggi restituiti
    da `predict()` (dizionario con una chiave per modello caricato): caricare
    più file qui non richiede nessuna modifica alla logica di rilevamento,
    solo la lista di percorsi da passare a `Model`.
    """
    # Importato qui, non in testa al modulo: openwakeword/onnxruntime pesano
    # sull'avvio (§2.8, ~110 MB) e servono solo a chi chiede --wake-word,
    # stesso principio di ddgs ed edge-tts (pyproject.toml).
    from openwakeword.model import Model

    if isinstance(modelli, str):
        modelli = [modelli]
    return Model(wakeword_model_paths=[_percorso_modello(m) for m in modelli])


class RichiamoWakeWord:
    """Il richiamo vero (#22): ascolta finché non sente la wake word.

    Chiamabile come `richiamo_da_tastiera`, quindi si passa a `Macchina`
    senza toccarla. Il rilevatore si carica pigramente al primo utilizzo
    (~1,5 s misurati, coerente col BOOT del piano §2.1), non alla
    costruzione: così costruire l'oggetto resta economico anche se poi non
    viene mai chiamato.
    """

    def __init__(
        self,
        microfono: AudioInputAdapter | None = None,
        modello: str | list[str] = MODELLI_PREDEFINITI,
        soglia: float = SOGLIA_PREDEFINITA,
        rilevatore: RilevatoreWakeWord | None = None,
    ) -> None:
        self.microfono = microfono or crea_audio_input()
        # Uno o più nomi/percorsi .onnx: chiunque superi la soglia fa scattare
        # il richiamo, non importa quale (vedi _carica_rilevatore).
        self.modello = modello
        self.soglia = soglia
        # Iniettabile per i test (vedi tests/test_richiamo.py): senza,
        # richiederebbero onnxruntime e ~1,5 s di caricamento per ogni prova.
        self._rilevatore = rilevatore

    def _rilevatore_pronto(self) -> RilevatoreWakeWord:
        if self._rilevatore is None:
            self._rilevatore = _carica_rilevatore(self.modello)
        return self._rilevatore

    def ascolta_punteggio(self) -> float | None:
        """Un ascolto, fino al rilevamento: il punteggio che l'ha fatto scattare.

        Sta separato da `__call__` per il comando di taratura (`main()`
        sotto), che deve poter stampare il numero vero, non solo sì/no.
        """
        rilevatore = self._rilevatore_pronto()
        flusso = self.microfono.flusso_pcm()
        try:
            frame = vad.ritaglia_in_frame(flusso, BYTE_PER_FRAME)
            return attendi_wake_word(frame, rilevatore, self.soglia)
        finally:
            flusso.close()  # ferma subito arecord, come in vad.ArecordAdapter

    def __call__(self) -> bool:
        return self.ascolta_punteggio() is not None


def main() -> None:
    """Comando di taratura: ascolta in continuo, dice quando e con che punteggio.

    Nato dallo stesso bisogno di `vad.main()`: provare la soglia nella stanza
    vera, con la TV accesa (§2.6), senza dover passare da un giro completo di
    `macchina.py` a ogni tentativo.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Ascolta in continuo e segnala quando sente la wake word.")
    parser.add_argument(
        "--modello", action="append", default=None,
        help="nome fra i preaddestrati di openWakeWord (hey_jarvis, alexa, hey_mycroft, ...) o un file .onnx; "
        "ripetibile per caricarne più di uno insieme (basta che uno solo superi la soglia)",
    )
    parser.add_argument("--soglia", type=float, default=SOGLIA_PREDEFINITA)
    parser.add_argument("--volte", type=int, default=5, help="quanti rilevamenti aspettare prima di uscire")
    argomenti = parser.parse_args()
    modelli = argomenti.modello or MODELLI_PREDEFINITI

    richiamo = RichiamoWakeWord(modello=modelli, soglia=argomenti.soglia)
    print(
        f"In ascolto di {modelli} (soglia {argomenti.soglia}), {argomenti.volte} volte. Ctrl-C per uscire.",
        flush=True,
    )
    for i in range(argomenti.volte):
        punteggio = richiamo.ascolta_punteggio()
        print(f"[{i + 1}/{argomenti.volte}] rilevata, punteggio {punteggio:.2f}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
