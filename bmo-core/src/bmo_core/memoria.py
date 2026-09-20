"""Il diario di preferenze e fatti di BMO, editabile via SCP (issue #14).

La #14 chiede una memoria che sopravviva a un riavvio: un file che l'utente
modifica dal proprio computer via SSH/SCP, nello stesso spirito con cui
`radio.py` popola le stazioni preferite (§1.2bis del piano). Questo modulo
copre solo la **lettura**: `bmo-core` rilegge il file a ogni turno e lo
inietta nello strato dinamico del prompt (`brain.contesto_dinamico`, §2.3).

La **scrittura** — BMO che propone di aggiungere una voce durante la
conversazione — resta fuori apposta: richiede la conferma vocale obbligatoria
dello stato `CONFIRM` (issue #17), non ancora costruito. Finché non c'è, il
prompt fisso dice al modello di rispondere onestamente che non può ancora
ricordare nulla da solo, invece di fingere di averlo fatto.

Ogni voce ha un `testo` in linguaggio naturale (non una coppia chiave-valore:
un diario di preferenze di casa è troppo eterogeneo per uno schema fisso),
una data e una `fonte` — "manuale" per quelle scritte via SCP, "modello" per
quelle che un giorno arriveranno dall'estrazione di fine sessione della #29.
Il tetto sulle voci tiene il diario dalla dimensione limitata: oltre il
tetto si tengono solo le più recenti, cioè le ultime righe del file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import percorso_dati

NOME_FILE = "memoria.json"

# Oltre questo numero di voci il prompt comincia a gonfiarsi per poco
# guadagno: si tengono le più recenti e si lasciano cadere le più vecchie.
MAX_VOCI = 30


@dataclass
class Voce:
    testo: str
    aggiunta_il: str
    fonte: str = "manuale"


def carica_diario(percorso: Path | None = None, tetto: int = MAX_VOCI) -> list[Voce]:
    """Le voci del diario, dalla più vecchia alla più recente nel file.

    Un file mancante o rotto non deve fermare BMO: si riparte da un diario
    vuoto, come `radio.carica_preferite` per le stazioni. Una riga malformata
    da sola non butta via le altre, come in `timer.ArchivioTimer._leggi`.
    """
    percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
    try:
        righe = json.loads(percorso.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    voci = []
    for riga in righe if isinstance(righe, list) else []:
        if isinstance(riga, dict) and riga.get("testo"):
            voci.append(
                Voce(
                    testo=str(riga["testo"]),
                    aggiunta_il=str(riga.get("aggiunta_il", "")),
                    fonte=str(riga.get("fonte", "manuale")),
                )
            )
    return voci[-tetto:] if tetto and len(voci) > tetto else voci
