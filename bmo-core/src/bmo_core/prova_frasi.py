"""Frasi di prova per il prompt di sistema e gli strumenti (fase 4.1, issue #19).

Criterio di uscita della #19: almeno il 90% di frasi corrette (18 su 20
nella prima versione, 36 su 40 ora). Sotto quella soglia il problema è il
prompt di sistema, non il modello.

Ogni frase dice quali esiti sono accettabili: nessuno strumento, oppure uno
strumento preciso con alcuni argomenti (numeri uguali, testi contenuti senza
badare alle maiuscole). Contano solo le chiamate andate a buon fine: se il
modello sbaglia un parametro, viene corretto dall'errore e rifà la chiamata
giusta, l'effetto finale è quello giusto (la chiamata sbagliata resta
comunque visibile nell'output).

    python -m bmo_core.prova_frasi                      # frasi mandate come testo
    python -m bmo_core.prova_frasi --voce               # le leggi tu al microfono
    python -m bmo_core.prova_frasi --categoria foto     # solo una categoria
    python -m bmo_core.prova_frasi --prompt nuovo.txt   # prova un prompt fisso diverso
"""
from __future__ import annotations

import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from .adapters import crea_faccia
from .brain import (
    ERRORI_GEMINI,
    TETTO_TURNO_S,
    Cervello,
    Risposta,
    descrivi_errore,
    durata_in_secondi,
    prompt_da_file,
)
from .modelli import GeminiNonDisponibile
from .timer import ArchivioTimer, Timer

SOGLIA = 0.9


@dataclass(frozen=True)
class Atteso:
    strumento: str | None  # None = nessuno strumento
    argomenti: dict[str, Any] = field(default_factory=dict)


def nessuno() -> Atteso:
    return Atteso(None)


def usa(strumento: str, **argomenti: Any) -> Atteso:
    return Atteso(strumento, argomenti)


@dataclass(frozen=True)
class Frase:
    categoria: str
    testo: str
    attesi: tuple[Atteso, ...]
    timer_attivi: tuple[tuple[str, int], ...] = ()  # (etichetta, secondi rimanenti) prima della frase


def _f(categoria: str, testo: str, *attesi: Atteso, timer: tuple[tuple[str, int], ...] = ()) -> Frase:
    return Frase(categoria, testo, attesi, timer)


FRASI = [
    # Timer: la durata totale deve essere esatta, comunque sia divisa fra ore, minuti e secondi.
    _f("timer", "Metti un timer di dieci minuti", usa("imposta_timer", durata=600)),
    _f("timer", "Timer di cinque minuti per la pasta", usa("imposta_timer", durata=300)),
    _f("timer", "Avvisami fra mezz'ora", usa("imposta_timer", durata=1800)),
    _f("timer", "Mi imposti un timer da un minuto e mezzo per le uova?", usa("imposta_timer", durata=90)),
    _f("timer", "Fra quaranta secondi dimmi di girare la frittata", usa("imposta_timer", durata=40)),
    _f("timer", "Metti un timer di un'ora e un quarto per l'arrosto", usa("imposta_timer", durata=4500)),
    _f("timer", "Timer di tre minuti per il tè", usa("imposta_timer", durata=180)),
    _f("timer", "Ricordami tra venti minuti di togliere la lavatrice", usa("imposta_timer", durata=1200)),
    _f("timer", "Due minuti di timer, per favore", usa("imposta_timer", durata=120)),
    _f("timer", "Fammi partire un conto alla rovescia di quindici minuti", usa("imposta_timer", durata=900)),
    _f("gestione_timer", "Annulla il timer della pasta", usa("annulla_timer", etichetta="pasta"),
       timer=(("pasta", 300),)),
    _f("gestione_timer", "Quanti timer ho attivi?", usa("elenca_timer"), nessuno(),
       timer=(("pasta", 300), ("uova", 90))),
    # Foto: solo quando la domanda riguarda ciò che BMO vede.
    _f("foto", "Cosa vedi davanti a te?", usa("scatta_foto")),
    _f("foto", "Che cosa c'è sul tavolo?", usa("scatta_foto")),
    _f("foto", "Guarda questa pianta: secondo te sta bene?", usa("scatta_foto")),
    _f("foto", "Fai una foto e dimmi cosa vedi", usa("scatta_foto")),
    # Musica e radio.
    _f("musica", "Metti Radio Deejay", usa("riproduci_musica", sorgente="radio", query="deejay")),
    _f("musica", "Accendi la radio", usa("riproduci_musica", sorgente="radio")),
    _f("musica", "Metti Bohemian Rhapsody dei Queen", usa("riproduci_musica", sorgente="libreria", query="bohemian")),
    _f("musica", "Fammi sentire un po' di jazz", usa("riproduci_musica")),
    _f("musica", "Riproduci il video di Gangnam Style", usa("riproduci_musica", query="gangnam"), nessuno()),
    _f("musica", "Metti in pausa la musica", usa("controllo_riproduzione", azione="pausa")),
    _f("musica", "Passa alla canzone successiva", usa("controllo_riproduzione", azione="successivo")),
    _f("volume", "Alza il volume al settanta percento", usa("regola_volume", percentuale=70)),
    _f("volume", "Abbassa un po' il volume", usa("regola_volume")),
    _f("pausa", "Smetti di ascoltare per un'ora", usa("metti_in_pausa_l_ascolto", minuti=60)),
    # Web: meteo e fatti che cambiano nel tempo.
    _f("web", "Che tempo fa a Roma?", usa("cerca_sul_web", query="roma")),
    _f("web", "Che tempo farà a Torino domani alle otto di sera?", usa("cerca_sul_web", query="torino")),
    _f("web", "Chi ha vinto l'ultima partita dell'Inter?", usa("cerca_sul_web", query="inter")),
    _f("web", "Che ore sono a Tokyo?", nessuno(), usa("cerca_sul_web", query="tokyo")),
    # Nessuno strumento: BMO risponde e basta.
    _f("conversazione", "Ciao BMO, come stai?", nessuno()),
    _f("conversazione", "Raccontami una barzelletta", nessuno()),
    _f("conversazione", "Scrivi una poesia sui dinosauri", nessuno()),
    _f("conversazione", "Quanto fa sette per otto?", nessuno()),
    _f("conversazione", "Chi è Finn?", nessuno()),
    _f("conversazione", "Come si dice gatto in inglese?", nessuno()),
    _f("conversazione", "Che ore sono?", nessuno()),
    _f("conversazione", "Che giorno è oggi?", nessuno()),
    _f("conversazione", "Dammi un consiglio per cucinare la pasta al dente", nessuno()),
    _f("conversazione", "Grazie BMO, sei stato bravissimo", nessuno()),
]


def _argomenti_ok(attesi: dict[str, Any], ricevuti: dict[str, Any]) -> bool:
    for nome, valore in attesi.items():
        if nome == "durata":  # imposta_timer: ore, minuti e secondi sommati
            try:
                if durata_in_secondi(ricevuti) != valore:
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if nome not in ricevuti:
            return False
        if isinstance(valore, int):
            try:
                if int(ricevuti[nome]) != valore:
                    return False
            except (TypeError, ValueError):
                return False
        elif str(valore).lower() not in str(ricevuti[nome]).lower():
            return False
    return True


def valuta(frase: Frase, risposta: Risposta) -> bool:
    chiamate = [c for c in risposta.chiamate if "errore" not in c.risultato]
    for atteso in frase.attesi:
        if atteso.strumento is None:
            if not chiamate and risposta.testo:
                return True
        elif (
            len(chiamate) == 1
            and chiamate[0].nome == atteso.strumento
            and _argomenti_ok(atteso.argomenti, chiamate[0].argomenti)
        ):
            return True
    return False


def _prepara(cervello: Cervello, frase: Frase) -> None:
    ora = cervello.orologio()
    # Stato noto a ogni frase: i timer stanno su disco (#20), quindi si
    # riscrive l'elenco invece di riempire una lista in memoria.
    cervello.archivio.sostituisci([Timer(e, ora + timedelta(seconds=s)) for e, s in frase.timer_attivi])


def _descrivi_attesi(frase: Frase) -> str:
    return " oppure ".join(
        "nessuno strumento" if a.strumento is None else f"{a.strumento}({a.argomenti or ''})"
        for a in frase.attesi
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--voce", action="store_true", help="leggi ogni frase al microfono")
    parser.add_argument("--durata", type=float, default=4.0, help="secondi di ascolto per frase (--voce)")
    parser.add_argument("--categoria", help="prova solo questa categoria")
    parser.add_argument("--prompt", type=Path, help="file di testo da usare come prompt fisso")
    parser.add_argument("--pausa", type=float, default=4.0, help="secondi fra una frase e l'altra (limiti al minuto)")
    argomenti = parser.parse_args()

    frasi = [f for f in FRASI if not argomenti.categoria or f.categoria == argomenti.categoria]
    if not frasi:
        categorie = ", ".join(sorted({f.categoria for f in FRASI}))
        raise SystemExit(f"categoria sconosciuta; disponibili: {categorie}")

    esiti: dict[str, list[bool]] = {}
    errori = 0
    modelli: Counter[str] = Counter()
    riepiloghi = 0
    turno_piu_lungo = 0.0
    # I timer della prova stanno in un file usa e getta: `_prepara` riscrive
    # l'elenco a ogni frase, e non deve toccare i timer veri dell'utente.
    cartella_prova = tempfile.TemporaryDirectory(prefix="bmo-prova-")
    for numero, frase in enumerate(frasi, start=1):
        cervello = Cervello(
            # A voce c'è dell'attesa vera: la faccia sul terminale dice quando
            # BMO sta elaborando. Con le frasi scritte sarebbe solo rumore.
            faccia=crea_faccia(sul_terminale=argomenti.voce),
            archivio=ArchivioTimer(Path(cartella_prova.name) / "timers.json"),
            **prompt_da_file(argomenti.prompt),
        )  # stato pulito a ogni frase
        _prepara(cervello, frase)
        audio = None
        if argomenti.voce:
            input(f"\n[{numero}/{len(frasi)}] Premi Invio e di': «{frase.testo}»")
            audio = cervello.ascolta(argomenti.durata)
        risposta = None
        for tentativo in range(2):
            try:
                risposta = cervello.rispondi(audio_wav=audio, testo=None if audio else frase.testo)
                break
            except ERRORI_GEMINI as errore:
                if tentativo == 0 and isinstance(errore, GeminiNonDisponibile) and errore.tipo != "rete":
                    print(f"   … {descrivi_errore(errore)}: riprovo fra 30 s")
                    time.sleep(30)
                    continue
                print(f"!  {numero:2}. {frase.testo}\n     ERRORE (escluso dal punteggio): {descrivi_errore(errore)}")
                errori += 1
                break
        if risposta is not None:
            esito = valuta(frase, risposta)
            esiti.setdefault(frase.categoria, []).append(esito)
            modelli[risposta.modello] += 1
            chiamate = ", ".join(f"{c.nome}({c.argomenti})" for c in risposta.chiamate) or "nessuno strumento"
            faccia = f"[{risposta.espressione}] " if risposta.espressione else "[senza espressione] "
            testo = risposta.testo or f"(risposta vuota: {risposta.motivo_vuota})"
            riepiloghi += bool(risposta.riepilogo)
            turno_piu_lungo = max(turno_piu_lungo, risposta.durata_s)
            note = f" · {risposta.durata_s:.1f} s"
            if risposta.riepilogo:
                note += f" · riepilogo forzato ({risposta.riepilogo})"
            if risposta.ripetizioni:
                note += " · risposta con la sola etichetta ripetuta"
            print(
                f"{'✓' if esito else '✗'} {numero:2}. [{frase.categoria}] {frase.testo}  ({risposta.modello}{note})\n"
                f"     {chiamate} · {faccia}{testo}"
            )
            if not esito:
                print(f"     atteso: {_descrivi_attesi(frase)}")
        if numero < len(frasi):
            time.sleep(argomenti.pausa)

    print("\nPer categoria:")
    for categoria, lista in esiti.items():
        print(f"  {categoria:15} {sum(lista)}/{len(lista)}")
    corrette = sum(sum(lista) for lista in esiti.values())
    valutate = sum(len(lista) for lista in esiti.values())
    if len(modelli) > 1 or errori:
        print(f"Modelli che hanno risposto: {dict(modelli)} · errori esclusi: {errori}")
    print(
        f"Riepiloghi forzati: {riepiloghi} · turno più lungo: "
        f"{turno_piu_lungo:.1f} s su {TETTO_TURNO_S:.0f}"
    )
    percentuale = corrette / valutate if valutate else 0.0
    verdetto = "OK" if percentuale >= SOGLIA else "SOTTO SOGLIA: rivedere il prompt di sistema"
    print(f"\n{corrette}/{valutate} corrette ({percentuale:.0%}) — {verdetto}")


if __name__ == "__main__":
    main()
