"""Dichiarazioni degli strumenti della §2.4, come le vede Gemini.

Qui c'è solo *cosa* il modello può chiedere. L'esecuzione vive in `brain.py`:
per ora sono veri solo i timer (in memoria); gli altri rispondono
`non_disponibile` finché non arrivano con l'issue #20. Servono già adesso
perché la prova delle frasi misura se il modello sceglie lo strumento giusto.

Le descrizioni sono in inglese, la lingua in cui i modelli sono più abituati
a leggere le dichiarazioni di funzioni; nomi di strumenti e parametri e
valori ammessi restano in italiano, come il resto del codice. Il prompt di
sistema resta in italiano.

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
            "Takes a photo with BMO's forward-facing camera and looks at it. Use only when the user "
            "asks about what BMO can see or the physical surroundings (e.g. 'what's on the table?', "
            "'look at this plant'). Never use it out of curiosity or unprompted."
        ),
        parameters=_schema(
            {"motivo": _testo("Why the photo is needed, in Italian, e.g. 'descrivere il tavolo'.")},
            ["motivo"],
        ),
    ),
    types.FunctionDeclaration(
        name="cerca_sul_web",
        description=(
            "Searches the web and returns three results with title, snippet and URL. Use for facts "
            "that change over time: weather, news, sports results, prices, opening hours. Do not use "
            "it for general knowledge, arithmetic, the current time in Italy or the active timers."
        ),
        parameters=_schema(
            {
                "query": _testo(
                    "The search query in Italian, specific and including place and time if given, "
                    "e.g. 'meteo Roma domani sera'."
                )
            },
            ["query"],
        ),
    ),
    types.FunctionDeclaration(
        name="imposta_timer",
        description=(
            "Starts a timer that rings when the duration has elapsed. Use it for any request to be "
            "alerted or reminded after an amount of time ('avvisami fra', 'ricordami tra'). Give the "
            "duration split into ore, minuti and secondi, as integers, exactly as spoken: "
            "'un'ora e un quarto' = ore 1, minuti 15; 'un minuto e mezzo' = minuti 1, secondi 30; "
            "'quaranta secondi' = secondi 40. At least one of ore, minuti, secondi is required."
        ),
        parameters=_schema(
            {
                "etichetta": _testo(
                    "Short name for the timer in Italian, e.g. 'pasta'. Use 'timer' if no purpose is given."
                ),
                "ore": _intero("Hours of the duration (integer)."),
                "minuti": _intero("Minutes of the duration (integer, 0 to 59 when ore is given)."),
                "secondi": _intero("Seconds of the duration (integer, 0 to 59 when ore or minuti is given)."),
            },
            ["etichetta"],
        ),
    ),
    types.FunctionDeclaration(
        name="annulla_timer",
        description=(
            "Cancels an active timer by its label. Omit etichetta ONLY when the user explicitly asks "
            "to cancel all timers."
        ),
        parameters=_schema({"etichetta": _testo("Label of the timer to cancel, as shown in the active timers list.")}),
    ),
    types.FunctionDeclaration(
        name="elenca_timer",
        description="Lists the active timers with their remaining time. The active timers are also shown in the STATO section.",
    ),
    types.FunctionDeclaration(
        name="riproduci_musica",
        description=(
            "Turns on the radio. BMO has no local music library and no screen: every request for "
            "music, a song, an artist or a genre becomes an internet radio station. It first looks "
            "among the saved favourite stations, then searches the public station directory."
        ),
        parameters=_schema(
            {
                "query": _testo(
                    "Station name, frequency, genre or artist, e.g. 'radio deejay', '101.7', "
                    "'jazz'. Leave it out to turn the radio on where it was."
                )
            },
            [],
        ),
    ),
    types.FunctionDeclaration(
        name="controllo_riproduzione",
        description=(
            "Controls the radio that is currently playing. 'successivo' and 'precedente' tune to "
            "the next or previous station of the list being listened to, like turning a dial."
        ),
        parameters=_schema(
            {
                "azione": _testo(
                    "'pausa' pauses, 'riprendi' resumes, 'stop' turns the radio off, "
                    "'successivo' tunes to the next station, 'precedente' to the previous one.",
                    ["pausa", "riprendi", "stop", "successivo", "precedente"],
                )
            },
            ["azione"],
        ),
    ),
    types.FunctionDeclaration(
        name="salva_stazione",
        description=(
            "Saves the station playing right now among the favourites, so it can be asked for by "
            "name later. Use it when the person says they like it or asks to keep it."
        ),
        parameters=_schema(
            {
                "nome": _testo(
                    "What to call it, if the person said so, e.g. 'quella del jazz' or "
                    "'Radio Deejay 107.0'. Leave it out to keep the station's own name."
                )
            },
            [],
        ),
    ),
    types.FunctionDeclaration(
        name="elenca_stazioni",
        description="Lists the saved favourite radio stations.",
        parameters=_schema({}, []),
    ),
    types.FunctionDeclaration(
        name="regola_volume",
        description=(
            "Sets the speaker volume to an absolute level. For relative requests "
            "('un po' più basso') choose a sensible absolute value."
        ),
        parameters=_schema({"percentuale": _intero("Volume level from 0 to 100.")}, ["percentuale"]),
    ),
    types.FunctionDeclaration(
        name="metti_in_pausa_l_ascolto",
        description="BMO stops listening for its wake word for the given number of minutes and goes to sleep.",
        parameters=_schema(
            {"minuti": _intero("How many minutes to stop listening, e.g. 60 for 'un'ora'.")},
            ["minuti"],
        ),
    ),
]
