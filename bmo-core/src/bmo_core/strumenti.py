"""Dichiarazioni degli strumenti della §2.4, come le vede Gemini.

Qui c'è solo *cosa* il modello può chiedere. L'esecuzione vive in `brain.py`:
per ora sono veri solo i timer (in memoria); gli altri rispondono
`non_disponibile` finché non arrivano con l'issue #20. Servono già adesso
perché la prova delle frasi misura se il modello sceglie lo strumento giusto.

`imposta_espressione` della §2.4 non è uno strumento: l'espressione arriva
come etichetta all'inizio della risposta ("[felice] ..."), letta da
`brain.separa_espressione`. Come strumento costava un secondo giro di
richiesta su quasi ogni turno, solo per ottenere il testo.
"""
from __future__ import annotations

from google.genai import types

T = types.Type


def _schema(proprieta: dict[str, types.Schema], obbligatori: list[str] | None = None) -> types.Schema:
    return types.Schema(type=T.OBJECT, properties=proprieta, required=obbligatori or [])


def _testo(descrizione: str, valori: list[str] | None = None) -> types.Schema:
    return types.Schema(type=T.STRING, description=descrizione, enum=valori)


def _intero(descrizione: str) -> types.Schema:
    return types.Schema(type=T.INTEGER, description=descrizione)


DICHIARAZIONI = [
    types.FunctionDeclaration(
        name="scatta_foto",
        description=(
            "Scatta una foto con la fotocamera di BMO, che punta in avanti, e la guarda. "
            "Da usare solo quando la domanda riguarda ciò che BMO vede o l'ambiente fisico intorno."
        ),
        parameters=_schema({"motivo": _testo("Perché serve la foto, ad esempio 'descrivere il tavolo'.")}, ["motivo"]),
    ),
    types.FunctionDeclaration(
        name="cerca_sul_web",
        description=(
            "Cerca sul web e restituisce tre risultati con titolo, estratto e indirizzo. "
            "Per fatti che cambiano nel tempo: meteo, notizie, risultati sportivi, prezzi, orari."
        ),
        parameters=_schema({"query": _testo("La ricerca, ad esempio 'meteo Roma domani sera'.")}, ["query"]),
    ),
    types.FunctionDeclaration(
        name="imposta_timer",
        description=(
            "Avvia un timer che suona allo scadere della durata indicata. La durata si dà in ore, "
            "minuti e secondi, come la dice chi parla: 'un'ora e un quarto' è ore 1 e minuti 15. "
            "Serve almeno uno fra ore, minuti e secondi."
        ),
        parameters=_schema(
            {
                "etichetta": _testo("Nome breve del timer, ad esempio 'pasta'."),
                "ore": _intero("Ore della durata."),
                "minuti": _intero("Minuti della durata."),
                "secondi": _intero("Secondi della durata."),
            },
            ["etichetta"],
        ),
    ),
    types.FunctionDeclaration(
        name="annulla_timer",
        description="Annulla un timer attivo. Senza etichetta annulla tutti i timer.",
        parameters=_schema({"etichetta": _testo("Etichetta del timer da annullare.")}),
    ),
    types.FunctionDeclaration(
        name="elenca_timer",
        description="Elenca i timer attivi con il tempo rimanente.",
    ),
    types.FunctionDeclaration(
        name="riproduci_musica",
        description=(
            "Riproduce musica: dalla libreria locale di brani, oppure una stazione radio via internet. "
            "BMO non ha uno schermo per i video."
        ),
        parameters=_schema(
            {
                "query": _testo("Cosa riprodurre: titolo, artista, genere o nome della radio."),
                "sorgente": _testo("Da dove: 'libreria' per i brani, 'radio' per le stazioni.", ["libreria", "radio"]),
            },
            ["query", "sorgente"],
        ),
    ),
    types.FunctionDeclaration(
        name="controllo_riproduzione",
        description="Controlla la musica in riproduzione.",
        parameters=_schema(
            {"azione": _testo("Cosa fare.", ["pausa", "riprendi", "stop", "successivo"])},
            ["azione"],
        ),
    ),
    types.FunctionDeclaration(
        name="regola_volume",
        description="Imposta il volume dell'altoparlante.",
        parameters=_schema({"percentuale": _intero("Volume da 0 a 100.")}, ["percentuale"]),
    ),
    types.FunctionDeclaration(
        name="metti_in_pausa_l_ascolto",
        description="BMO smette di ascoltare la wake word per il numero di minuti indicato e si addormenta.",
        parameters=_schema({"minuti": _intero("Per quanti minuti non ascoltare.")}, ["minuti"]),
    ),
]
