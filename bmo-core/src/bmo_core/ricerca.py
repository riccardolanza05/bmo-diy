"""`cerca_sul_web` con DuckDuckGo (§2.4 del piano, issue #20).

Perché non Google Search: il grounding nativo sarebbe più pulito, ma **non è
nel free tier**, e mescolare strumenti nativi e function declaration proprie
nella stessa richiesta è ancora in Preview. Quindi `ddgs`, tre risultati con
titolo, estratto e indirizzo. Il giorno del piano a pagamento si sostituisce
questa funzione con `google_search` e non cambia nient'altro (issue #6).

I risultati tornano al modello dentro un `functionResponse`, cioè costano
token a ogni giro del loop: tre risultati con l'estratto tagliato sono un
compromesso fra "abbastanza per rispondere" e "non riempiamo la richiesta".
"""
from __future__ import annotations

from typing import Any, Callable

QUANTI = 3
LUNGHEZZA_ESTRATTO = 240


def _con_ddgs(query: str, quanti: int) -> list[dict[str, Any]]:
    from ddgs import DDGS  # importata qui: senza rete o senza libreria BMO parte lo stesso

    with DDGS() as motore:
        return list(motore.text(query, region="it-it", max_results=quanti))


def _accorcia(testo: str) -> str:
    testo = " ".join((testo or "").split())
    if len(testo) <= LUNGHEZZA_ESTRATTO:
        return testo
    return testo[:LUNGHEZZA_ESTRATTO].rsplit(" ", 1)[0] + "…"


def cerca(
    query: str,
    quanti: int = QUANTI,
    cercatore: Callable[[str, int], list[dict[str, Any]]] = _con_ddgs,
) -> dict[str, Any]:
    """Cerca sul web e restituisce il risultato già pronto per il modello."""
    if not (query or "").strip():
        return {"errore": "la query è vuota"}
    try:
        trovati = cercatore(query, quanti)
    except ImportError:
        return {"stato": "non_disponibile", "motivo": "la ricerca sul web non è installata"}
    except Exception as errore:
        # La libreria non promette un tipo di eccezione suo e sotto c'è la
        # rete: qualunque cosa succeda, BMO deve poterlo dire e andare avanti.
        return {"stato": "errore", "motivo": f"la ricerca non ha funzionato ({type(errore).__name__})"}
    risultati = [
        {
            "titolo": r.get("title", ""),
            "estratto": _accorcia(r.get("body", "")),
            "url": r.get("href", ""),
        }
        for r in trovati[:quanti]
    ]
    if not risultati:
        return {"stato": "nessun_risultato", "query": query}
    return {"stato": "ok", "query": query, "risultati": risultati}
