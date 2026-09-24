"""I suoni di BMO: file audio senza parole, scelti per nome (#21).

**Senza parole** perché BMO è bilingue (#42): una frase registrata sarebbe
in una lingua sola. **File, non sintesi**: i suoni generati dal codice sono
stati scartati all'ascolto il 25/9, e con loro la clip di attesa — un suono
a ogni risposta non aveva senso.

Per ogni nome si cerca, nell'ordine:

1. `BMO_SUONO_<NOME>` (per esempio `BMO_SUONO_ERRORE`), un file o un URL;
2. un file `<nome>.{opus,mp3,ogg,wav}` in `<cartella dati>/suoni/`: qui
   stanno i suoni di terzi, fuori dal repository che è pubblico — il timer
   di John Pork è `timer.opus`;
3. un file incluso nel pacchetto (`bmo_core/audio/`), solo se CC0 — vedi
   `LICENZE.md` lì accanto;
4. il ripiego passato da chi chiama, di solito un tono che mpv genera da
   solo: così BMO suona anche su una macchina appena installata.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .adapters import AudioOutputAdapter, crea_audio_output
from .config import percorso_dati

ESTENSIONI = (".opus", ".mp3", ".ogg", ".wav")

CARTELLA_PACCHETTO = Path(__file__).parent / "audio"

# L'ultimo ripiego per l'errore: un bip grave di un decimo di secondo.
BIP_ERRORE = "av://lavfi:sine=frequency=330:duration=0.12"

# L'errore dura poco (0,14 s); il tetto serve solo se mpv si pianta.
ATTESA_MAX_ERRORE_S = 2.0


def cartella_suoni() -> Path:
    return percorso_dati() / "suoni"


def trova_suono(nome: str, ripiego: str) -> str:
    """Il file (o l'URL) da suonare per `nome`, secondo l'ordine del modulo."""
    forzato = os.environ.get(f"BMO_SUONO_{nome.upper()}")
    if forzato:
        return forzato
    for cartella in (cartella_suoni(), CARTELLA_PACCHETTO):
        for estensione in ESTENSIONI:
            percorso = cartella / f"{nome}{estensione}"
            if percorso.exists():
                return str(percorso)
    return ripiego


class Suoni:
    """I suoni di un BMO acceso, sullo stesso altoparlante della voce.

    Per ora uno solo: l'errore di rete. Suona **per intero prima** della
    frase che segue, perché la voce passa per lo stesso adapter e
    `riproduci` comincerebbe fermandolo; senza rete, poi, quella frase
    finisce sul terminale e il suono è l'unica cosa che si sente.
    """

    def __init__(self, altoparlante: AudioOutputAdapter | None = None) -> None:
        self.altoparlante = altoparlante or crea_audio_output()

    def errore(self) -> None:
        try:
            self.altoparlante.riproduci(trova_suono("errore", BIP_ERRORE))
        except OSError as errore:  # mpv assente: meglio muto che fermo
            print(f"[suoni: errore non riprodotto — {errore}]", file=sys.stderr)
            return
        self.altoparlante.attendi(timeout_s=ATTESA_MAX_ERRORE_S)


class SuoniMuti:
    """Il predefinito di `Macchina`: i test e `prova_frasi` non lanciano mpv."""

    def errore(self) -> None:
        pass


def main() -> None:
    """Fa sentire i suoni che BMO userebbe adesso, e dice da dove vengono."""
    import argparse

    from .sveglia import tono_predefinito

    parser = argparse.ArgumentParser(description="Ascolta i suoni di BMO.")
    parser.add_argument("--solo-elenco", action="store_true", help="dice quali file userebbe, senza suonarli")
    argomenti = parser.parse_args()
    scelti = {"errore": trova_suono("errore", BIP_ERRORE), "timer": tono_predefinito()}
    altoparlante = None if argomenti.solo_elenco else crea_audio_output()
    for nome, sorgente in scelti.items():
        print(f"{nome}: {sorgente}", flush=True)
        if altoparlante is not None:
            altoparlante.riproduci(sorgente)
            altoparlante.attendi(timeout_s=15)


if __name__ == "__main__":
    main()
