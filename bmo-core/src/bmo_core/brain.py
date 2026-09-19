"""Il cervello di BMO: ascolta → rispondi → strumenti, con Gemini in cloud.

Fasi 1.1 e 1.2 della roadmap (issue #19). Questo modulo dipende solo dai
Protocol di `adapters.base` e dalle funzioni `crea_*` della factory, mai
dalle classi concrete: gira identico sul PC di sviluppo e sul Pi.

Riferimenti nel piano: §2.1 (loop agentico, max 4 giri), §2.3 (prompt di
sistema a due strati), §2.4 (strumenti). Per ora c'è un solo strumento,
`imposta_timer`, e i timer vivono in memoria: la persistenza su disco e gli
altri strumenti arrivano con l'issue #20.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from google.genai import types

from .adapters import AudioInputAdapter, crea_audio_input

MODELLO_PREDEFINITO = "gemini-3.8-flash"
FUSO_ORARIO = ZoneInfo("Europe/Rome")
DURATA_ASCOLTO_S = 3.0
MAX_GIRI = 4

PROMPT_FISSO = """\
Sei BMO, la piccola console vivente di Adventure Time, e vivi in una casa a Milano.
Sei entusiasta, curioso e un po' ingenuo; ti preoccupi dei tuoi amici. Non sei servile.

REGOLE DI FORMA — sono vincolanti, il tuo testo va a un sintetizzatore vocale:
- Rispondi SEMPRE in italiano.
- Massimo 2 frasi. Se la risposta richiede più di 2 frasi, dai la sintesi e offri di continuare.
- Niente markdown, niente elenchi puntati, niente emoji, niente parentesi, niente sigle
  da leggere lettera per lettera. Scrivi i numeri come si pronunciano.
- Non descrivere quello che stai facendo ("sto cercando..."): lo dice già la faccia.

REGOLE SUGLI STRUMENTI:
- Usa uno strumento solo se la risposta lo richiede davvero. Una poesia sui dinosauri
  non richiede strumenti.
- Per imposta_timer converti sempre la durata in secondi e scegli un'etichetta breve
  che descriva a cosa serve il timer.
"""

DICHIARAZIONI = [
    types.FunctionDeclaration(
        name="imposta_timer",
        description="Avvia un timer che suona allo scadere della durata indicata.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "durata_secondi": types.Schema(
                    type=types.Type.INTEGER,
                    description="Durata del timer in secondi, ad esempio 600 per dieci minuti.",
                ),
                "etichetta": types.Schema(
                    type=types.Type.STRING,
                    description="Nome breve del timer, ad esempio 'pasta'.",
                ),
            },
            required=["durata_secondi", "etichetta"],
        ),
    ),
]

_GIORNI = ["LUNEDÌ", "MARTEDÌ", "MERCOLEDÌ", "GIOVEDÌ", "VENERDÌ", "SABATO", "DOMENICA"]
_MESI = [
    "GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
    "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE",
]


@dataclass
class Timer:
    etichetta: str
    scadenza: datetime


@dataclass
class ChiamataStrumento:
    nome: str
    argomenti: dict[str, Any]
    risultato: dict[str, Any]


@dataclass
class Risposta:
    testo: str
    chiamate: list[ChiamataStrumento] = field(default_factory=list)


def _durata_parlata(secondi: int) -> str:
    minuti, secondi = divmod(max(secondi, 0), 60)
    parti = []
    if minuti:
        parti.append(f"{minuti} minut{'o' if minuti == 1 else 'i'}")
    if secondi or not parti:
        parti.append(f"{secondi} second{'o' if secondi == 1 else 'i'}")
    return " e ".join(parti)


def contesto_dinamico(ora: datetime, timer: list[Timer], inietta_ora: bool = True) -> str:
    """Secondo strato del prompt (§2.3), rigenerato a ogni turno.

    `inietta_ora=False` serve solo all'esperimento della fase 0.3: senza
    l'ora il modello inventa, ed è la dimostrazione del perché questo strato esiste.
    """
    righe = []
    if inietta_ora:
        righe.append(
            f"[STATO ALLE {ora:%H:%M} DI {_GIORNI[ora.weekday()]} "
            f"{ora.day} {_MESI[ora.month - 1]} {ora.year}, {FUSO_ORARIO.key}]"
        )
    else:
        righe.append("[STATO]")
    attivi = [t for t in timer if t.scadenza > ora]
    if attivi:
        descrizioni = [
            f'"{t.etichetta}" scade fra {_durata_parlata(int((t.scadenza - ora).total_seconds()))}'
            for t in attivi
        ]
        righe.append("Timer attivi: " + "; ".join(descrizioni) + ".")
    else:
        righe.append("Timer attivi: nessuno.")
    return "\n".join(righe)


class Cervello:
    """Un turno di dialogo: audio in ingresso, testo e chiamate a strumenti in uscita.

    `client` è un `google.genai.Client` (o un sostituto con la stessa
    interfaccia `models.generate_content`, come nei test).
    """

    def __init__(
        self,
        client: Any = None,
        microfono: AudioInputAdapter | None = None,
        modello: str | None = None,
        orologio: Callable[[], datetime] | None = None,
        inietta_ora: bool = True,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client()  # legge GEMINI_API_KEY dall'ambiente
        self.client = client
        self.microfono = microfono or crea_audio_input()
        self.modello = modello or os.environ.get("BMO_GEMINI_MODEL", MODELLO_PREDEFINITO)
        self.orologio = orologio or (lambda: datetime.now(FUSO_ORARIO))
        self.inietta_ora = inietta_ora
        self.timer: list[Timer] = []
        self._esecutori: dict[str, Callable[..., dict[str, Any]]] = {
            "imposta_timer": self._imposta_timer,
        }

    def ascolta(self, durata_s: float = DURATA_ASCOLTO_S) -> bytes:
        """Registra `durata_s` secondi dal microfono e restituisce il WAV.

        Il file di appoggio sta in /dev/shm quando c'è (niente scritture su SD).
        """
        cartella = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=cartella) as file:
            percorso = Path(file.name)
            self.microfono.registra(percorso, durata_s)
            return percorso.read_bytes()

    def _configurazione(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=[
                PROMPT_FISSO,
                contesto_dinamico(self.orologio(), self.timer, self.inietta_ora),
            ],
            tools=[types.Tool(function_declarations=DICHIARAZIONI)],
        )

    def rispondi(self, audio_wav: bytes | None = None, testo: str | None = None) -> Risposta:
        """Manda audio (o testo, utile per le prove) a Gemini ed esegue il loop agentico.

        Ogni `functionCall` viene eseguito da `strumenti()` e il risultato
        rimandato al modello, per al massimo MAX_GIRI chiamate.
        """
        if audio_wav is None and testo is None:
            raise ValueError("serve audio_wav oppure testo")
        parti = []
        if audio_wav is not None:
            parti.append(types.Part.from_bytes(data=audio_wav, mime_type="audio/wav"))
        if testo is not None:
            parti.append(types.Part.from_text(text=testo))
        contenuti = [types.Content(role="user", parts=parti)]

        eseguite: list[ChiamataStrumento] = []
        risposta = None
        for _ in range(MAX_GIRI):
            risposta = self.client.models.generate_content(
                model=self.modello,
                contents=contenuti,
                config=self._configurazione(),
            )
            chiamate = risposta.function_calls or []
            if not chiamate:
                break
            contenuti.append(risposta.candidates[0].content)
            nuove = self.strumenti(chiamate)
            eseguite.extend(nuove)
            contenuti.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(name=c.nome, response=c.risultato)
                        for c in nuove
                    ],
                )
            )
        testo_finale = (risposta.text or "").strip() if risposta is not None else ""
        return Risposta(testo=testo_finale, chiamate=eseguite)

    def strumenti(self, chiamate: list[types.FunctionCall]) -> list[ChiamataStrumento]:
        """Esegue le chiamate richieste dal modello e ne raccoglie i risultati."""
        eseguite = []
        for chiamata in chiamate:
            argomenti = dict(chiamata.args or {})
            esecutore = self._esecutori.get(chiamata.name or "")
            if esecutore is None:
                risultato = {"errore": f"strumento sconosciuto: {chiamata.name}"}
            else:
                try:
                    risultato = esecutore(**argomenti)
                except (TypeError, ValueError) as errore:
                    risultato = {"errore": str(errore)}
            eseguite.append(ChiamataStrumento(chiamata.name or "", argomenti, risultato))
        return eseguite

    def _imposta_timer(self, durata_secondi: int, etichetta: str) -> dict[str, Any]:
        durata = int(durata_secondi)
        if durata <= 0:
            raise ValueError("la durata deve essere positiva")
        scadenza = self.orologio() + timedelta(seconds=durata)
        self.timer.append(Timer(etichetta=etichetta, scadenza=scadenza))
        return {"stato": "ok", "scadenza": scadenza.strftime("%H:%M:%S")}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Un turno di dialogo con BMO dal microfono del PC.")
    parser.add_argument("--durata", type=float, default=DURATA_ASCOLTO_S, help="secondi di ascolto")
    parser.add_argument("--wav", type=Path, help="usa un file WAV invece del microfono")
    parser.add_argument("--testo", help="manda testo invece di audio")
    parser.add_argument("--senza-ora", action="store_true", help="non iniettare l'ora (esperimento 0.3)")
    argomenti = parser.parse_args()

    cervello = Cervello(inietta_ora=not argomenti.senza_ora)
    audio = None
    if argomenti.wav:
        audio = argomenti.wav.read_bytes()
    elif not argomenti.testo:
        print(f"Parla per {argomenti.durata:g} secondi...")
        audio = cervello.ascolta(argomenti.durata)
    risposta = cervello.rispondi(audio_wav=audio, testo=argomenti.testo)
    for chiamata in risposta.chiamate:
        print(f"→ {chiamata.nome}({chiamata.argomenti}) = {chiamata.risultato}")
    print(f"BMO: {risposta.testo}")


if __name__ == "__main__":
    main()
