"""Il diario di preferenze e fatti di BMO, editabile via SCP (issue #14).

La #14 chiede una memoria che sopravviva a un riavvio: un file che l'utente
modifica dal proprio computer via SSH/SCP, nello stesso spirito con cui
`radio.py` popola le stazioni preferite (§1.2bis del piano). `bmo-core`
rilegge il file a ogni turno e lo inietta nello strato dinamico del prompt
(`brain.contesto_dinamico`, §2.3).

La **scrittura** (#14.2) è per forza indiretta: BMO non chiama mai `salva_diario`
o `aggiungi_voce` direttamente. Propone una voce con lo strumento `ricorda`
(`strumenti.py`), e solo `Macchina._ricorda` (`macchina.py`), dopo la conferma
vocale obbligatoria dello stato `CONFERMA` (issue #17), chiama `aggiungi_voce`.
Questo modulo non sa niente della conferma: sa solo leggere e scrivere il file.

Ogni voce ha un `testo` in linguaggio naturale (non una coppia chiave-valore:
un diario di preferenze di casa è troppo eterogeneo per uno schema fisso),
una data e una `fonte` — "manuale" per quelle scritte via SCP, "modello" per
quelle proposte da BMO e confermate a voce (in futuro anche per l'estrazione
di fine sessione della #29). Il tetto sulle voci tiene il diario di
dimensione limitata: oltre il tetto si tengono solo le più recenti.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
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


def salva_diario(percorso: Path, voci: list[Voce]) -> None:
    """Scrittura atomica: temporaneo nella stessa cartella più `rename`.

    Stesso schema di `radio.salva_preferite` e `timer.ArchivioTimer._scrivi`:
    un file a metà scritto, per una scheda SD che perde corrente, sarebbe
    peggio di un diario che resta quello di prima.
    """
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=percorso.parent, prefix=".memoria-", delete=False
    ) as file:
        json.dump([asdict(v) for v in voci], file, ensure_ascii=False, indent=1)
        file.flush()
        os.fsync(file.fileno())
        temporaneo = Path(file.name)
    temporaneo.replace(percorso)


def aggiungi_voce(percorso: Path | None, testo: str, aggiunta_il: str, fonte: str = "modello") -> Voce:
    """Aggiunge una voce e riscrive il file, rispettando il tetto (#14.2).

    `aggiunta_il` arriva da chi chiama (l'orologio della macchina a stati),
    non da un `datetime.now()` qui dentro: questo modulo non ha un proprio
    concetto di "adesso" e i test non devono dipenderne.
    """
    percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
    voci = carica_diario(percorso)  # già tagliate al tetto in lettura
    nuova = Voce(testo=testo, aggiunta_il=aggiunta_il, fonte=fonte)
    voci = (voci + [nuova])[-MAX_VOCI:]
    salva_diario(percorso, voci)
    return nuova
