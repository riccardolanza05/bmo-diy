"""Fine turno per silenzio (VAD), invece di una durata fissa.

Chiesto da Riccardo il 20/9, provando la #14.2 a voce: registrare per una
durata fissa (3 s, 8 s...) non è realistico — una frase può essere più corta
o più lunga, e nessuno sa in anticipo quale sia la durata giusta. Qui dentro
c'è solo la logica di decidere *quando smettere di ascoltare*: nessun I/O,
nessun microfono vero, per poterla provare senza hardware.

**Il numero che conta: `SILENZIO_MS = 800`.** Punto di partenza, non una
misura: le pause dentro una frase durano tipicamente 200-500 ms, sotto i
~600 ms si rischia di tagliare a metà chi sta ancora pensando, sopra il
secondo l'attesa comincia a sentirsi (coerente con l'argomento di latenza
del §2.9). È anche il valore che il piano aveva già abbozzato al §2.1. Va
verificato con l'uso reale, non deciso qui: per questo è un parametro, non
una costante murata, e c'è un comando apposta per provarlo (vedi `main()`).

**L'aggressività del VAD conta quanto il silenzio.** `webrtcvad.Vad` ha
quattro modalità (0-3): più aggressiva = più propensa a chiamare "silenzio"
qualunque cosa non sia chiaramente voce. Con la TV accesa, modalità 3 e
modalità 0 allo stesso `SILENZIO_MS` si comportano in modo completamente
diverso: è per questo un secondo parametro esposto, non fissato per sempre.

**Perché serve aspettare che la voce inizi.** Senza questo, il silenzio
prima ancora che chi parla apra bocca farebbe scattare subito l'endpoint su
una clip vuota. Si aspettano i primi frame di voce, *poi* si comincia a
contare il silenzio che segue. Il silenzio finale resta nella clip mandata
a Gemini (l'"hangover"): tagliarlo rischia di troncare l'ultima consonante.

Semplificazione consapevole: il primo frame classificato come voce fa
scattare subito il cancello, senza richiedere N frame di fila. Un rumore
isolato (una porta, un colpo di tosse breve) potrebbe quindi far partire la
registrazione un frame prima del previsto — accettato per ora, da rivedere
se in pratica risulta un problema.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Protocol

# Le uniche frequenze che webrtcvad accetta.
FREQUENZE_VALIDE = (8000, 16000, 32000, 48000)
# webrtcvad accetta solo frame da 10, 20 o 30 ms: 30 è il più permissivo
# (meno frame da classificare al secondo, meno probabilità di un singolo
# frame ambiguo che confonde la decisione).
DURATA_FRAME_MS = 30
BYTE_PER_CAMPIONE = 2  # webrtcvad vuole PCM a 16 bit (mono)

SILENZIO_MS_PREDEFINITO = 800.0
AGGRESSIVITA_PREDEFINITA = 2  # 0 = permissivo, 3 = aggressivo (vedi sopra)


class RilevatoreVoce(Protocol):
    """Quello che serve di `webrtcvad.Vad`: isolato per poterlo sostituire nei test."""

    def is_speech(self, frame: bytes, frequenza: int) -> bool: ...


def valida_frequenza(frequenza: int) -> None:
    if frequenza not in FREQUENZE_VALIDE:
        raise ValueError(
            f"il VAD richiede una di queste frequenze: {FREQUENZE_VALIDE} (ricevuta {frequenza}); "
            "sul Pi il HAT registra a 48000 Hz stereo 32 bit, va convertito prima di arrivare qui"
        )


def dimensione_frame(frequenza: int, durata_ms: int = DURATA_FRAME_MS) -> int:
    """Byte per frame: campioni-per-frame × byte-per-campione (mono, 16 bit)."""
    return int(frequenza * durata_ms / 1000) * BYTE_PER_CAMPIONE


def ritaglia_in_frame(pezzi: Iterable[bytes], dimensione: int) -> Iterator[bytes]:
    """Riaccorpa chunk di dimensione arbitraria in frame di dimensione fissa.

    webrtcvad accetta solo frame esatti da 10/20/30 ms; un flusso audio (es.
    `AudioInputAdapter.flusso_pcm()`) consegna pezzi di qualunque dimensione.
    L'avanzo fra un pezzo e l'altro resta in un buffer, non si perde né si
    duplica. L'ultimo resto, più corto di un frame intero, si scarta: sono
    al più `dimensione - 1` byte, meno di un millisecondo di audio.
    """
    buffer = b""
    for pezzo in pezzi:
        buffer += pezzo
        while len(buffer) >= dimensione:
            yield buffer[:dimensione]
            buffer = buffer[dimensione:]


@dataclass
class Diagnostica:
    """Cosa è successo durante l'ascolto, per poter tarare i parametri (vedi `main()`)."""

    durata_totale_s: float
    voce_rilevata: bool
    frame_di_rumore_scartati: int
    motivo_fine: str  # "silenzio" | "tetto" | "mai_iniziato" | "flusso_finito"


def ascolta_fino_al_silenzio(
    frame: Iterable[bytes],
    frequenza: int,
    rilevatore: RilevatoreVoce,
    cap_s: float,
    silenzio_ms: float = SILENZIO_MS_PREDEFINITO,
    durata_frame_ms: int = DURATA_FRAME_MS,
) -> tuple[bytes, Diagnostica]:
    """La logica pura di endpointing, senza I/O: prende frame, restituisce audio.

    `frame` è già ritagliato alla dimensione giusta (vedi `ritaglia_in_frame`).
    `cap_s` è un tetto di sicurezza sempre attivo, dal primo frame: senza,
    un rumore di fondo continuo che il VAD non riconosce mai come silenzio
    farebbe ascoltare BMO per sempre.
    """
    valida_frequenza(frequenza)
    voce_iniziata = False
    silenzio_di_fila_ms = 0.0
    scartati = 0
    audio: list[bytes] = []
    accumulato_s = 0.0
    passo_s = durata_frame_ms / 1000
    for pezzo in frame:
        e_voce = rilevatore.is_speech(pezzo, frequenza)
        accumulato_s += passo_s
        if not voce_iniziata:
            if e_voce:
                voce_iniziata = True
                audio.append(pezzo)
            else:
                scartati += 1
            if accumulato_s >= cap_s:
                return b"", Diagnostica(accumulato_s, False, scartati, "mai_iniziato")
            continue
        audio.append(pezzo)
        silenzio_di_fila_ms = 0.0 if e_voce else silenzio_di_fila_ms + durata_frame_ms
        if silenzio_di_fila_ms >= silenzio_ms:
            return b"".join(audio), Diagnostica(accumulato_s, True, scartati, "silenzio")
        if accumulato_s >= cap_s:
            return b"".join(audio), Diagnostica(accumulato_s, True, scartati, "tetto")
    # Il flusso è finito da sé: capita nei test con una lista finita di
    # frame, mai nel mondo reale con un microfono sempre acceso.
    return b"".join(audio), Diagnostica(accumulato_s, voce_iniziata, scartati, "flusso_finito")


def main() -> None:
    """Comando di taratura: una registrazione, i numeri per capire cosa è successo.

    Nato dal bisogno di provare `silenzio_ms` e `aggressivita` senza passare
    ogni volta da un turno intero con Gemini di mezzo: due secondi invece di
    dover parlare, aspettare la risposta e indovinare cosa ha visto il VAD.
    """
    import argparse
    import sys

    from .adapters.factory import crea_audio_input

    parser = argparse.ArgumentParser(description="Registra una volta e mostra cosa ha visto il VAD.")
    parser.add_argument("--cap", type=float, default=15.0, help="tetto massimo di ascolto, in secondi")
    parser.add_argument("--silenzio-ms", type=float, default=SILENZIO_MS_PREDEFINITO)
    parser.add_argument("--aggressivita", type=int, default=AGGRESSIVITA_PREDEFINITA, choices=[0, 1, 2, 3])
    parser.add_argument("--wav", type=Path, help="se indicato, salva la clip qui per riascoltarla")
    argomenti = parser.parse_args()

    microfono = crea_audio_input()
    if not hasattr(microfono, "registra_fino_al_silenzio"):
        raise SystemExit("il microfono di questo ambiente non supporta ancora l'ascolto a silenzio")

    print("Parla quando vuoi, BMO si ferma da solo dopo il silenzio...", flush=True)
    destinazione = argomenti.wav or Path("/tmp/prova-vad.wav")
    _, diagnostica = microfono.registra_fino_al_silenzio(
        destinazione, argomenti.cap, argomenti.silenzio_ms, argomenti.aggressivita
    )
    print(
        f"registrato {diagnostica.durata_totale_s:.1f} s totali, "
        f"voce rilevata: {'sì' if diagnostica.voce_rilevata else 'no'}, "
        f"{diagnostica.frame_di_rumore_scartati} frame di rumore scartati prima della voce, "
        f"fine per: {diagnostica.motivo_fine}",
        file=sys.stderr,
    )
    print(f"Clip salvata in {destinazione}", flush=True)


if __name__ == "__main__":
    main()
