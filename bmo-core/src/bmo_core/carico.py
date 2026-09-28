"""Prova di carico: BMO intero, con le frasi lette da file invece che dette (#58).

È la fase 2.3 del piano («il giro completo con l'audio letto da file WAV al
posto del microfono»), e serve a spingere la RAM al massimo in modo
ripetibile, identico sul PC e sul Pi: le funzioni si accumulano (timer che
corrono, radio accesa, foto, ricerche, diario, racconti lunghi) e la
sequenza si ripete per `--giri` volte, così una perdita di memoria si vede
come una crescita fra un giro e l'altro.

Tutto è quello vero di `python -m bmo_core.macchina --voce-tts --wake-word`:
`Macchina`, `Cervello` con Gemini, `Radio` con mpv, `VoceTts`, `Suoni`,
`Sveglia` in un thread, la faccia (`BMO_FACCIA=socket` per bmo-face), la
webcam. Cambia solo il microfono: `MicrofonoCopione` suona in tempo reale
le frasi della sequenza, sintetizzate una volta con edge-tts e messe in
cache. Anche il richiamo passa dalla wake word vera: ogni turno comincia con
«Hey BMO» detto dal copione. Se la wake word non scatta (una voce sintetica
non è la stanza vera), il turno parte lo stesso e lo si scrive nel log: qui
si misura la memoria, la soglia si tara alla fase 4.4.

Le risposte di BMO si sentono dalle casse, e ogni richiesta è una chiamata
vera a Gemini: una sequenza costa ~20 richieste per giro.

Uso (di solito tramite `avvia_carico.sh`, che apre anche bmo-face e
misura la RAM):

    python -m bmo_core.carico --giri 2
    python -m bmo_core.carico --elenco        # stampa la sequenza e basta
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Iterator

from .adapters.audio_input import ArecordAdapter
from .brain import Cervello
from .macchina import Macchina, VoceTts, crea_audio_output, crea_faccia
from .radio import Radio
from .richiamo import MODELLI_PREDEFINITI, SOGLIA_PREDEFINITA, RichiamoWakeWord
from .suoni import Suoni
from .sveglia import Sveglia
from .tts import sintetizza

FREQUENZA = 16000
BYTE_PER_SECONDO = FREQUENZA * 2
PEZZO_S = 0.08  # come le finestre della wake word
SILENZIO_PRIMA_S = 0.4
SILENZIO_DOPO_S = 4.0  # abbondante: il VAD si ferma dopo ~0,8 s di silenzio

# Ogni turno: la richiesta, più le eventuali risposte a una domanda di BMO
# (la conferma di `ricorda`, #17). L'ordine accumula carico: quando arriva la
# seconda foto, la radio suona e due timer corrono.
SEQUENZA: list[tuple[str, ...]] = [
    ("Metti un timer di tre minuti per la pasta",),
    ("Metti un timer di un minuto per il tè",),
    ("Metti un po' di jazz",),
    ("Cosa vedi davanti a te?",),
    ("Che tempo fa domani a Milano?",),
    ("Abbassa un po' la radio",),
    ("Ricordati che la pizza preferita di Finn è la diavola", "Sì"),
    ("Quanti timer ci sono?",),
    ("Raccontami una storia di un minuto sui dinosauri",),
    ("What time is it?",),
    ("Cambia stazione",),
    ("Scatta un'altra foto e dimmi che colori vedi",),
    ("Chi abita in questa casa?",),
    ("Salva questa stazione",),
    ("Qual è la pizza preferita di Finn?",),
    ("Spegni la radio",),
]

RICHIAMO = "Hey BMO"


def pcm_della_frase(testo: str) -> bytes:
    """La frase detta da edge-tts, in PCM 16 kHz mono 16 bit (cache di `sintetizza`)."""
    mp3 = sintetizza(testo)
    return subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(mp3), "-ar", str(FREQUENZA), "-ac", "1", "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    ).stdout


class MicrofonoCopione(ArecordAdapter):
    """Un microfono che dice le frasi del copione, in tempo reale.

    Ogni `flusso_pcm()` (un ascolto della wake word, una domanda, una
    conferma) consuma la frase successiva della coda: un po' di silenzio, la
    frase, e silenzio finché chi ascolta non si ferma. Il tempo reale conta:
    la wake word e il VAD consumano CPU come col microfono vero.
    """

    def __init__(self) -> None:
        super().__init__(dispositivo="copione", frequenza=FREQUENZA, canali=1, formato="S16_LE")
        self.coda: deque[bytes] = deque()
        self.pronto = threading.Event()

    def accoda(self, pcm: bytes) -> None:
        self.coda.append(pcm)

    def flusso_pcm(self) -> Iterator[bytes]:
        frase = self.coda.popleft() if self.coda else b""
        silenzio = bytes(int(PEZZO_S * BYTE_PER_SECONDO))
        pezzo = len(silenzio)
        dati = bytes(int(SILENZIO_PRIMA_S * BYTE_PER_SECONDO)) + frase
        dati += bytes(int(SILENZIO_DOPO_S * BYTE_PER_SECONDO))
        for inizio in range(0, len(dati), pezzo):
            yield dati[inizio : inizio + pezzo]
            time.sleep(PEZZO_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prova di carico di BMO con le frasi lette da file (#58).")
    parser.add_argument("--giri", type=int, default=1, help="quante volte ripetere la sequenza")
    parser.add_argument("--elenco", action="store_true", help="stampa la sequenza ed esce")
    parser.add_argument("--modello-wake-word", action="append", default=None)
    parser.add_argument("--soglia-wake-word", type=float, default=SOGLIA_PREDEFINITA)
    argomenti = parser.parse_args()

    if argomenti.elenco:
        for numero, turno in enumerate(SEQUENZA, 1):
            print(f"{numero:2}. " + "  →  ".join(turno))
        return

    print("[carico] preparo le frasi (edge-tts, in cache dopo la prima volta)...", flush=True)
    richiamo_pcm = pcm_della_frase(RICHIAMO)
    frasi = {testo: pcm_della_frase(testo) for turno in SEQUENZA for testo in turno}

    microfono = MicrofonoCopione()
    faccia = crea_faccia(sul_terminale=True)
    cervello = Cervello(faccia=faccia, microfono=microfono)
    radio = Radio()
    radio.registra(cervello)
    altoparlante = crea_audio_output()
    voce = VoceTts(altoparlante=altoparlante, faccia=faccia)
    suoni = Suoni(altoparlante)
    rilevatore = RichiamoWakeWord(
        microfono=microfono,
        modello=argomenti.modello_wake_word or MODELLI_PREDEFINITI,
        soglia=argomenti.soglia_wake_word,
    )

    turni = [turno for _ in range(argomenti.giri) for turno in SEQUENZA]
    stato = {"turno": 0, "mancati": 0}

    def richiamo() -> bool:
        if stato["turno"] >= len(turni):
            return False
        turno = turni[stato["turno"]]
        stato["turno"] += 1
        # Tutte le frasi del turno in coda: «Hey BMO», la richiesta, le
        # eventuali risposte alle domande di BMO.
        microfono.accoda(richiamo_pcm)
        for testo in turno:
            microfono.accoda(frasi[testo])
        print(f"\n[carico] turno {stato['turno']}/{len(turni)} ({time.strftime('%H:%M:%S')}): {turno[0]}", flush=True)
        if rilevatore.ascolta_punteggio() is None:
            stato["mancati"] += 1
            print("[carico] wake word NON rilevata sulla voce sintetica: parto lo stesso", flush=True)
        else:
            print("(bmo ascolta)", flush=True)
            suoni.ascolto()
        return True

    macchina = Macchina(
        cervello=cervello,
        faccia=faccia,
        richiamo=richiamo,
        voce=voce,
        qualcosa_attivo=lambda: False,  # a copione finito si esce, timer o no
        sospendi_ascolto=radio.sospesa,
        suoni=suoni,
    )
    sveglia = Sveglia(archivio=cervello.archivio, faccia=faccia)
    threading.Thread(target=sveglia.esegui, daemon=True).start()
    inizio = time.monotonic()
    try:
        macchina.esegui()
    finally:
        radio.lettore.spegni()
    durata = time.monotonic() - inizio
    print(
        f"\n[carico] finito: {len(turni)} turni in {durata / 60:.1f} min, "
        f"wake word mancata {stato['mancati']} volte",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
