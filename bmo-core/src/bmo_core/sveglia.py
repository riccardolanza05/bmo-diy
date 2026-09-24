"""La sveglia: fa suonare i timer scaduti (issue #20).

Gira come processo a se': il cervello scrive i timer nel file e se ne
dimentica, la sveglia li guarda scadere. E' questa divisione che rende vera
la promessa del piano — un timer messo prima di un riavvio suona lo stesso —
e che permette la prova che conta: metti un timer, ammazza il processo,
rialzalo, e deve suonare all'ora giusta.

Il suono e' la clip "timer" della #21: un richiamo senza parole, sintetizzato
in `clip.py` e scritto nella cartella dei dati al primo uso. Il tono che mpv
genera da solo resta come ultimo ripiego, se quel file non si puo' scrivere.
"""
from __future__ import annotations

import os
import time
from typing import Callable

from .adapters import (
    STATO_TIMER,
    AudioOutputAdapter,
    FacciaAdapter,
    crea_audio_output,
    crea_faccia,
)
from .clip import percorso_clip
from .config import percorso_dati
from .timer import ArchivioTimer, Timer

# Ultimo ripiego: mpv genera il tono da solo, senza bisogno di nessun file.
# Suona solo se la clip "timer" (#21) non si riesce a scrivere su disco.
TONO_GENERATO = "av://lavfi:sine=frequency=880:duration=1.2"

# I suoni veri stanno fuori dal repository, accanto ai timer: sono file di
# terzi e il repository è pubblico. Il primo che esiste vince.
NOMI_SUONO_TIMER = ("timer.opus", "timer.mp3", "timer.ogg", "timer.wav")

INTERVALLO_S = 0.5


def tono_predefinito() -> str:
    """Cosa suona quando un timer scade.

    Ordine: `BMO_TONO`, poi un file in `<cartella dati>/suoni/`, poi la
    clip "timer" sintetizzata (#21), altrimenti il tono generato da mpv.
    Così chi vuole un suono suo lo mette in una cartella e non tocca il
    codice, e BMO suona lo stesso anche dove quel file non c'è.
    """
    forzato = os.environ.get("BMO_TONO")
    if forzato:
        return forzato
    cartella = percorso_dati() / "suoni"
    for nome in NOMI_SUONO_TIMER:
        if (cartella / nome).exists():
            return str(cartella / nome)
    try:
        return str(percorso_clip("timer"))
    except OSError:  # cartella dei dati non scrivibile
        return TONO_GENERATO


def stampa_subito(messaggio: str) -> None:
    """La sveglia è un processo che resta in piedi: senza flush i messaggi
    restano nel buffer e si perdono se viene ucciso (e nel journal del Pi non
    si vedrebbe niente finché il buffer non si riempie)."""
    print(messaggio, flush=True)


class Sveglia:
    def __init__(
        self,
        archivio: ArchivioTimer | None = None,
        altoparlante: AudioOutputAdapter | None = None,
        faccia: FacciaAdapter | None = None,
        tono: str | None = None,
        annuncia: Callable[[str], None] = stampa_subito,
    ) -> None:
        self.archivio = archivio or ArchivioTimer()
        self.altoparlante = altoparlante or crea_audio_output()
        self.faccia = faccia or crea_faccia()
        # Risolto qui e non nella firma: un valore predefinito nella firma
        # verrebbe deciso all'importazione, prima che BMO_DATI possa cambiare.
        self.tono = tono or tono_predefinito()
        self.annuncia = annuncia

    def controlla(self, dopo_una_pausa: bool = False) -> list[Timer]:
        """Fa suonare i timer scaduti e li restituisce.

        `dopo_una_pausa` e' il primo controllo dopo l'avvio: li' un timer
        scaduto lo e' mentre BMO era spento, e va detto, altrimenti chi
        sente il tono non capisce di cosa si tratti.
        """
        scaduti = self.archivio.preleva_scaduti()
        if not scaduti:
            return []
        self.faccia.mostra(STATO_TIMER)
        # Un tono solo anche se scadono insieme: mpv ne riproduce uno per
        # volta e il secondo interromperebbe il primo.
        self.altoparlante.riproduci(self.tono)
        for timer in scaduti:
            quando = timer.scadenza.strftime("%H:%M")
            if dopo_una_pausa:
                self.annuncia(f'Il timer "{timer.etichetta}" era scaduto alle {quando}, mentre ero spento.')
            else:
                self.annuncia(f'È scaduto il timer "{timer.etichetta}".')
        return scaduti

    def esegui(self, intervallo_s: float = INTERVALLO_S, giri: int | None = None) -> None:
        """Guarda scadere i timer finché non la si ferma (`giri` serve ai test)."""
        primo = True
        fatti = 0
        while giri is None or fatti < giri:
            self.controlla(dopo_una_pausa=primo)
            primo = False
            fatti += 1
            time.sleep(intervallo_s)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fa suonare i timer di BMO, anche dopo un riavvio.")
    parser.add_argument("--intervallo", type=float, default=INTERVALLO_S, help="secondi fra un controllo e l'altro")
    parser.add_argument(
        "--tono",
        help="cosa suonare quando un timer scade (predefinito: <dati>/suoni/timer.*, "
        "altrimenti un tono generato)",
    )
    argomenti = parser.parse_args()

    sveglia = Sveglia(faccia=crea_faccia(sul_terminale=True), tono=argomenti.tono)
    attivi = sveglia.archivio.attivi()
    stampa_subito(f"Sveglia avviata su {sveglia.archivio.percorso} · timer attivi: {len(attivi)}")
    stampa_subito(f"Suono dei timer: {sveglia.tono}")
    for timer in attivi:
        stampa_subito(f'  "{timer.etichetta}" alle {timer.scadenza.strftime("%H:%M:%S")}')
    try:
        sveglia.esegui(argomenti.intervallo)
    except KeyboardInterrupt:
        stampa_subito("\nSveglia fermata.")


if __name__ == "__main__":
    main()
