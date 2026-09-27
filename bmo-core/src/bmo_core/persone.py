"""L'elenco delle persone di casa, per il prompt di sistema (issue #15).

BMO non è di proprietà esclusiva: è condiviso da più persone in casa. Per la
V1 non c'è riconoscimento vocale (troppo costoso in RAM/complessità su 512 MB,
vedi anche #13): il prompt non sa mai CHI sta parlando in un dato momento, ma
deve comunque sapere CHI vive in casa, per non trattare BMO come se avesse un
solo proprietario.

I nomi sono un dato personale, non tecnico: stanno in un file di
configurazione privato, fuori dal repository pubblico, nella stessa cartella
dati di `config.percorso_dati()` usata da `memoria.py` per il diario e da
`timer.py` per l'archivio — non serve altro `.gitignore`, quella cartella non
fa mai parte del repo.

Il riconoscimento vocale per personalizzare le risposte in base a chi sta
parlando resta un'idea V2, segnata nell'issue: non serve finché non esiste
un modo di riconoscere il parlante.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import percorso_dati

NOME_FILE = "persone.json"


def carica_persone(percorso: Path | None = None) -> list[str]:
    """I nomi delle persone di casa, dal file di configurazione privato.

    Un file mancante o rotto non deve fermare BMO: si riparte da una lista
    vuota, come `memoria.carica_diario` per il diario e `radio.carica_preferite`
    per le stazioni — il prompt semplicemente non menziona nessuno.
    """
    percorso = Path(percorso) if percorso is not None else percorso_dati() / NOME_FILE
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(dati, list):
        return []
    return [nome.strip() for nome in dati if isinstance(nome, str) and nome.strip()]
