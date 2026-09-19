"""Le venti frasi di prova della fase 4.1 (issue #19).

Criterio di uscita: almeno 18 su 20 corrette. Sotto quella soglia il
problema è il prompt di sistema, non il modello.

Una frase è corretta se:
- per le richieste di timer, il modello chiama `imposta_timer` con la
  durata attesa in secondi;
- per tutte le altre, il modello NON chiama strumenti e risponde con del testo.

    python -m bmo_core.prova_frasi            # frasi mandate come testo
    python -m bmo_core.prova_frasi --voce     # le leggi tu al microfono, una per una
"""
from __future__ import annotations

from dataclasses import dataclass

from .brain import ERRORI_GEMINI, Cervello, Risposta, descrivi_errore


@dataclass(frozen=True)
class Frase:
    testo: str
    durata_attesa: int | None  # secondi per imposta_timer, None = nessuno strumento


FRASI = [
    Frase("Metti un timer di dieci minuti", 600),
    Frase("Timer di cinque minuti per la pasta", 300),
    Frase("Avvisami fra mezz'ora", 1800),
    Frase("Mi imposti un timer da un minuto e mezzo per le uova?", 90),
    Frase("Fra quaranta secondi dimmi di girare la frittata", 40),
    Frase("Metti un timer di un'ora e un quarto per l'arrosto", 4500),
    Frase("Timer di tre minuti per il tè", 180),
    Frase("Ricordami tra venti minuti di togliere la lavatrice", 1200),
    Frase("Due minuti di timer, per favore", 120),
    Frase("Fammi partire un conto alla rovescia di quindici minuti", 900),
    Frase("Ciao BMO, come stai?", None),
    Frase("Raccontami una barzelletta", None),
    Frase("Scrivi una poesia sui dinosauri", None),
    Frase("Quanto fa sette per otto?", None),
    Frase("Chi è Finn?", None),
    Frase("Come si dice gatto in inglese?", None),
    Frase("Che ore sono?", None),
    Frase("Che giorno è oggi?", None),
    Frase("Dammi un consiglio per cucinare la pasta al dente", None),
    Frase("Grazie BMO, sei stato bravissimo", None),
]


def valuta(frase: Frase, risposta: Risposta) -> bool:
    timer = [c for c in risposta.chiamate if c.nome == "imposta_timer"]
    if frase.durata_attesa is None:
        return not risposta.chiamate and bool(risposta.testo)
    return len(timer) == 1 and int(timer[0].argomenti.get("durata_secondi", -1)) == frase.durata_attesa


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--voce", action="store_true", help="leggi ogni frase al microfono")
    parser.add_argument("--durata", type=float, default=4.0, help="secondi di ascolto per frase (--voce)")
    argomenti = parser.parse_args()

    corrette = 0
    for numero, frase in enumerate(FRASI, start=1):
        cervello = Cervello()  # stato pulito a ogni frase
        try:
            if argomenti.voce:
                input(f"\n[{numero}/20] Premi Invio e di': «{frase.testo}»")
                risposta = cervello.rispondi(audio_wav=cervello.ascolta(argomenti.durata))
            else:
                risposta = cervello.rispondi(testo=frase.testo)
        except ERRORI_GEMINI as errore:
            print(f"✗ {numero:2}. {frase.testo}\n     ERRORE: {descrivi_errore(errore)}")
            continue
        esito = valuta(frase, risposta)
        corrette += esito
        chiamate = ", ".join(f"{c.nome}({c.argomenti})" for c in risposta.chiamate) or "nessuno strumento"
        print(f"{'✓' if esito else '✗'} {numero:2}. {frase.testo}\n     {chiamate} · {risposta.testo}")

    print(f"\n{corrette}/20 corrette — {'OK' if corrette >= 18 else 'SOTTO SOGLIA: rivedere il prompt di sistema'}")


if __name__ == "__main__":
    main()
