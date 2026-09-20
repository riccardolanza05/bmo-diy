"""Musica, radio e volume: i tre strumenti della §2.4 che riguardano il suono.

Due sorgenti, nell'ordine di affidabilità che dà il piano:

1. **la libreria locale**, che funziona senza rete ed è la predefinita — sul
   Pi sta sulla microSD, sul PC in `~/Musica` o dove dice `BMO_MUSICA`;
2. **la radio via internet**, un elenco di stazioni curato a mano in
   `<cartella dati>/radio.json`, a cui mpv si attacca in un secondo.

YouTube è rimandato alla V2: su un Pi 3 A+ risolvere un indirizzo richiede
5-10 secondi e un centinaio di MB di memoria.

Questi strumenti non stanno nel cervello ma si collegano con
`registra_strumento`, come la pausa dell'ascolto: per suonare serve
dell'hardware, e il cervello non deve saperne niente.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .adapters import LettoreAdapter, VolumeAdapter, crea_lettore, crea_volume
from .config import percorso_dati

ESTENSIONI = (".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma")
MAX_BRANI = 50  # una coda più lunga di così non la ascolta nessuno


def cartella_musica() -> Path:
    """Dove stanno i brani. `BMO_MUSICA` vince su tutto."""
    scelta = os.environ.get("BMO_MUSICA")
    if scelta:
        return Path(scelta)
    predefinita = Path.home() / "Musica"
    return predefinita if predefinita.is_dir() else percorso_dati() / "musica"


def _parole(testo: str) -> list[str]:
    return [p for p in "".join(c if c.isalnum() else " " for c in testo.lower()).split() if p]


def scegli_brani(cartella: Path, query: str) -> list[Path]:
    """I brani che somigliano alla richiesta, per nome di file e di cartella.

    Niente indice e niente database: la ricerca è sul nome del file, che è
    dove stanno titolo e artista in una libreria di casa. Prima chi contiene
    tutte le parole chieste, poi chi ne contiene almeno una.
    """
    if not cartella.is_dir():
        return []
    parole = _parole(query)
    tutti = sorted(p for p in cartella.rglob("*") if p.suffix.lower() in ESTENSIONI)
    if not parole:
        return tutti[:MAX_BRANI]
    nomi = {p: " ".join(_parole(str(p.relative_to(cartella)))) for p in tutti}
    complete = [p for p in tutti if all(parola in nomi[p] for parola in parole)]
    if complete:
        return complete[:MAX_BRANI]
    return [p for p in tutti if any(parola in nomi[p] for parola in parole)][:MAX_BRANI]


def stazioni_radio(percorso: Path | None = None) -> dict[str, str]:
    """Le stazioni, da un file curato a mano: {"nome": "indirizzo dello stream"}.

    Non ce ne sono di predefinite nel codice: gli indirizzi degli stream
    cambiano, e un elenco che marcisce nel repository farebbe dire a BMO che
    sta suonando qualcosa che non suona.
    """
    percorso = percorso or percorso_dati() / "radio.json"
    try:
        dato = json.loads(percorso.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return {str(k): str(v) for k, v in dato.items()} if isinstance(dato, dict) else {}


class Musica:
    """I tre strumenti del suono, collegati a un lettore e al volume."""

    def __init__(
        self,
        lettore: LettoreAdapter | None = None,
        volume: VolumeAdapter | None = None,
        cartella: Path | None = None,
        stazioni: dict[str, str] | None = None,
    ) -> None:
        self.lettore = lettore or crea_lettore()
        self.volume = volume or crea_volume()
        self.cartella = Path(cartella) if cartella else cartella_musica()
        self.stazioni = stazioni if stazioni is not None else stazioni_radio()
        self.in_ascolto: str | None = None  # cosa sta suonando, per il risultato

    def registra(self, cervello: Any) -> None:
        cervello.registra_strumento("riproduci_musica", self.riproduci)
        cervello.registra_strumento("controllo_riproduzione", self.controllo)
        cervello.registra_strumento("regola_volume", self.regola_volume)

    # --- gli strumenti -------------------------------------------------------

    def riproduci(self, query: str, sorgente: str = "libreria") -> dict[str, Any]:
        if sorgente not in ("libreria", "radio"):
            raise ValueError("sorgente deve essere 'libreria' o 'radio'")
        if sorgente == "radio":
            return self._radio(query)
        return self._libreria(query)

    def _libreria(self, query: str) -> dict[str, Any]:
        if not self.cartella.is_dir():
            return {"stato": "non_disponibile", "motivo": "non ho ancora una libreria di musica"}
        brani = scegli_brani(self.cartella, query)
        if not brani:
            return {"stato": "non_trovato", "query": query}
        self.lettore.riproduci([str(b) for b in brani])
        self.in_ascolto = brani[0].stem
        return {
            "stato": "ok",
            "sorgente": "libreria",
            "titolo": brani[0].stem,
            "brani_in_coda": len(brani),
        }

    def _radio(self, query: str) -> dict[str, Any]:
        if not self.stazioni:
            return {"stato": "non_disponibile", "motivo": "non ho ancora un elenco di stazioni radio"}
        parole = _parole(query)
        for nome, indirizzo in self.stazioni.items():
            parole_nome = _parole(nome)
            if any(p in parole_nome for p in parole) or not parole:
                self.lettore.riproduci([indirizzo])
                self.in_ascolto = nome
                return {"stato": "ok", "sorgente": "radio", "stazione": nome}
        return {"stato": "non_trovato", "query": query, "stazioni": list(self.stazioni)}

    def controllo(self, azione: str) -> dict[str, Any]:
        azioni = {
            "pausa": self.lettore.pausa,
            "riprendi": self.lettore.riprendi,
            "stop": self.lettore.stop,
            "successivo": self.lettore.successivo,
        }
        if azione not in azioni:
            raise ValueError(f"azione deve essere una fra: {', '.join(azioni)}")
        if not self.lettore.in_riproduzione():
            return {"stato": "niente_in_riproduzione"}
        azioni[azione]()
        if azione == "stop":
            self.in_ascolto = None
        return {"stato": "ok", "azione": azione}

    def regola_volume(self, percentuale: int) -> dict[str, Any]:
        percentuale = int(percentuale)
        if not 0 <= percentuale <= 100:
            raise ValueError("percentuale deve essere fra 0 e 100")
        self.volume.imposta(percentuale)
        return {"stato": "ok", "percentuale": percentuale}
