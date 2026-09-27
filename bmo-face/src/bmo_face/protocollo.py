"""I cinque messaggi del socket Unix bmo-core → bmo-face (piano, §2.2).

```
{"cmd":"state",      "value":"listening"}
{"cmd":"speak",      "envelope":[0.10,0.42,0.71,...], "fps":25}
{"cmd":"expression", "value":"felice", "ttl":3.0}
{"cmd":"timer",      "remaining":312, "label":"pasta"}
{"cmd":"level",      "value":0.34}
```

Con una correzione rispetto al piano: `state.value` qui sono le stesse
stringhe di `adapters.base.STATO_*` di bmo-core (`"ascolto"`, non
`"listening"`) — il piano usa un esempio in inglese, ma bmo-core ha già
quelle costanti come contratto vero, testato altrove: usarne un'altra qui
significherebbe due vocabolari per la stessa cosa.

Ogni funzione qui muta un `ComandoFaccia` esistente, non ne crea uno nuovo:
è il server socket (`servitore.py`) a possedere l'unico `ComandoFaccia` di
processo, e il renderer lo legge in sola lettura mentre disegna.
"""
from __future__ import annotations

import json
from typing import Any

from .animazione import ComandoFaccia


def analizza_riga(riga: str) -> dict[str, Any] | None:
    """Una riga JSON in un dizionario, o `None` se è vuota o non valida.

    Un messaggio rotto non deve chiudere la connessione né far cadere
    `bmo-face`: si scarta e si continua, stesso principio di un file di
    configurazione mancante altrove nel progetto.
    """
    riga = riga.strip()
    if not riga:
        return None
    try:
        messaggio = json.loads(riga)
    except json.JSONDecodeError:
        return None
    return messaggio if isinstance(messaggio, dict) else None


def applica(comando: ComandoFaccia, messaggio: dict[str, Any], ora: float) -> None:
    """Aggiorna `comando` in base a un messaggio già analizzato.

    `ora` è il tempo del server (lo stesso orologio che poi userà il
    renderer per `Renderer.disegna(comando, t)`), passato da fuori e non
    letto qui: rende questa funzione testabile senza un orologio vero.
    """
    cmd = messaggio.get("cmd")
    if cmd == "state":
        valore = messaggio.get("value")
        if isinstance(valore, str) and valore:
            comando.stato = valore
    elif cmd == "speak":
        inviluppo = messaggio.get("envelope")
        if isinstance(inviluppo, list) and inviluppo:
            comando.inviluppo = [float(v) for v in inviluppo]
            comando.inviluppo_fps = float(messaggio.get("fps", comando.inviluppo_fps))
            comando.inviluppo_inizio = ora
    elif cmd == "expression":
        valore = messaggio.get("value")
        if isinstance(valore, str) and valore:
            comando.espressione = valore
            comando.espressione_scadenza = ora + float(messaggio.get("ttl", 3.0))
    elif cmd == "timer":
        rimanente = messaggio.get("remaining")
        if isinstance(rimanente, (int, float)):
            comando.timer_rimanente = int(rimanente)
            comando.timer_etichetta = messaggio.get("label")
    elif cmd == "level":
        valore = messaggio.get("value")
        if isinstance(valore, (int, float)):
            comando.livello = float(valore)
    # Un `cmd` sconosciuto o mancante si ignora: un bmo-core più recente che
    # manda un comando nuovo non deve rompere un bmo-face più vecchio, lo
    # stesso principio del riepilogo forzato che ignora strumenti sconosciuti.


def messaggio_state(valore: str) -> str:
    return json.dumps({"cmd": "state", "value": valore}) + "\n"


def messaggio_speak(inviluppo: list[float], fps: float = 25.0) -> str:
    return json.dumps({"cmd": "speak", "envelope": inviluppo, "fps": fps}) + "\n"


def messaggio_expression(valore: str, ttl: float = 3.0) -> str:
    return json.dumps({"cmd": "expression", "value": valore, "ttl": ttl}) + "\n"


def messaggio_timer(rimanente: int, etichetta: str | None = None) -> str:
    return json.dumps({"cmd": "timer", "remaining": rimanente, "label": etichetta}) + "\n"


def messaggio_level(valore: float) -> str:
    return json.dumps({"cmd": "level", "value": valore}) + "\n"
