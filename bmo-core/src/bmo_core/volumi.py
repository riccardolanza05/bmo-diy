"""Volumi indipendenti per sorgente audio (dopo l'issue #23 di bmo-face).

Prima "abbassa il volume" cambiava un solo numero, quello dell'altoparlante
nel suo insieme (`adapters.volume`). Da qui in poi ci sono quattro canali:

- **radio**: solo `LettoreMpv`, tramite il suo IPC (`imposta_volume`, non il
  volume di sistema) — abbassare la radio non deve abbassare anche la voce.
- **voce**: solo `VoceTts`.
- **timer**: solo il tono della sveglia (`sveglia.py`).
- **sistema**: tutto il resto — l'altoparlante nel suo complesso (i suoni di
  `Suoni`, e qualunque sorgente audio futura senza un canale proprio) — il
  comportamento di prima, ed è il predefinito quando non si specifica un
  canale.

**Radio e sistema cambiano subito**, nello stesso processo che chiama questo
modulo (l'IPC di mpv per la radio, `wpctl`/`amixer` per il sistema). **Voce e
timer no**: `sveglia.py` gira in un processo separato da `bmo-core`
(`python -m bmo_core.sveglia`), quindi il loro livello vive in un file
(stesso schema di `memoria.py` per il diario, `timer.py` per l'archivio) che
chi suona rilegge a ogni riproduzione — un attributo in RAM in un processo
non lo vedrebbe mai l'altro.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .config import percorso_dati

NOME_FILE = "volumi.json"

# Questi passano dal file. "radio" si applica anche subito (IPC di mpv), ma
# va ricordato lo stesso (#60): ogni stazione nuova e ogni mpv riacceso
# ripartirebbero altrimenti dal 100% di mpv, sempre troppo alto. "sistema"
# resta solo nel mixer, che se lo ricorda da sé.
CANALI_FILE = ("radio", "voce", "timer")
CANALI = ("radio", "voce", "timer", "sistema")
VOLUME_PREDEFINITO = 100
# La radio parte al 40% (richiesta di Riccardo, #60): a 100 copre la voce di
# BMO e chi parla. Lo dice anche il prompt fisso, così il modello sa da dove
# parte quando gli si chiede "un po' più bassa".
VOLUMI_PREDEFINITI = {"radio": 40, "voce": VOLUME_PREDEFINITO, "timer": VOLUME_PREDEFINITO}


def carica_volumi(percorso: Path | None = None) -> dict[str, int]:
    """I volumi salvati per i canali "radio"/"voce"/"timer". Un file mancante o rotto
    non deve fermare BMO: si riparte dal volume predefinito per entrambi,
    come `memoria.carica_diario` per il diario."""
    percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        dati = {}
    if not isinstance(dati, dict):
        dati = {}
    return {canale: int(dati.get(canale, VOLUMI_PREDEFINITI[canale])) for canale in CANALI_FILE}


def leggi_volume(canale: str, percorso: Path | None = None) -> int:
    """Il volume attuale di "radio", "voce" o "timer": chiamato a ogni
    riproduzione da chi suona (`Radio`, `VoceTts.__call__`, `Sveglia`), non
    messo in cache."""
    return carica_volumi(percorso).get(canale, VOLUMI_PREDEFINITI.get(canale, VOLUME_PREDEFINITO))


def _salva_nel_file(canale: str, percentuale: int, percorso: Path | None = None) -> None:
    percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
    volumi = carica_volumi(percorso)
    volumi[canale] = int(percentuale)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(volumi), encoding="utf-8")


def regola_volume(
    percentuale: int,
    canale: str = "sistema",
    *,
    imposta_radio: Callable[[int], None] | None = None,
    imposta_sistema: Callable[[int], None] | None = None,
    percorso_file: Path | None = None,
) -> dict[str, Any]:
    """Lo strumento `regola_volume` (`strumenti.py`), con un canale in più.

    `imposta_radio`/`imposta_sistema` sono iniettati da chi costruisce lo
    strumento (`radio.Radio.regola_volume`): "radio" e "sistema" cambiano
    subito ("radio" finisce anche nel file, #60); "voce" e "timer" si scrivono
    solo nel file che `leggi_volume()`
    rilegge alla prossima riproduzione. Un canale "radio"/"sistema" senza la
    funzione corrispondente iniettata (es. nessuna radio collegata) non
    solleva: risponde comunque "ok", semplicemente non c'è niente da
    cambiare — coerente con "meglio muto che fermo" del resto del progetto.
    """
    percentuale = int(percentuale)
    if not 0 <= percentuale <= 100:
        raise ValueError("percentuale deve essere fra 0 e 100")
    if canale not in CANALI:
        raise ValueError(f"canale deve essere uno fra: {', '.join(CANALI)}")
    if canale == "radio":
        if imposta_radio is not None:
            imposta_radio(percentuale)
        _salva_nel_file(canale, percentuale, percorso_file)
    elif canale == "sistema":
        if imposta_sistema is not None:
            imposta_sistema(percentuale)
    else:
        _salva_nel_file(canale, percentuale, percorso_file)
    return {"stato": "ok", "percentuale": percentuale, "canale": canale}
