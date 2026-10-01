"""Misure dei modelli Gemini per la cascata (issue #73): chi regge BMO, e quanto costa.

Tre prove, ognuna su uno o più modelli (le richieste sono distanziate: i
modelli con pochi RPM vanno con `--pausa` alta):

    python -m bmo_core.misura_modelli compat  --modelli gemini-3.5-flash --pausa 15
    python -m bmo_core.misura_modelli latenza --modelli gemini-3.5-flash --ripetizioni 6 --pausa 15
    python -m bmo_core.misura_modelli limite  --modelli gemini-3.5-flash --raffica 7

- `compat`: con il prompt, le dichiarazioni e la configurazione VERI del
  cervello controlla che il modello (1) risponda a una frase semplice con le
  etichette, (2) chiami lo strumento giusto, (3) accetti l'audio WAV (il
  dispositivo manda audio, il banco di frasi no), (4) accetti di continuare
  un turno cominciato da un altro modello (cambio a metà turno, cioè il
  ripiego della cascata nel secondo giro).
- `latenza`: tempo di una risposta semplice e di un turno con strumento.
- `limite`: una raffica di richieste minuscole per vedere cosa risponde l'API
  oltre l'RPM (codice, `retryDelay`) e quanto costa il fallimento in secondi,
  con 1 e con 2 tentativi dell'SDK.

Le misure grezze vanno in JSON con `--uscita`.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

import httpx
from google.genai import errors, types

from .adapters import crea_faccia
from .brain import Cervello, durata_in_secondi, prompt_da_file
from .timer import ArchivioTimer

FRASE_SEMPLICE = "Dimmi una cosa curiosa sui gatti, in una frase"
FRASE_STRUMENTO = "Metti un timer di dieci minuti"


class ClienteRegistratore:
    """Avvolge il client: registra durata ed esito di ogni `generate_content`."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.chiamate: list[dict[str, Any]] = []
        self.models = self

    def generate_content(self, model: str, **richiesta: Any) -> Any:
        inizio = time.monotonic()
        voce: dict[str, Any] = {"modello": model}
        try:
            risposta = self._client.models.generate_content(model=model, **richiesta)
        except Exception as errore:  # noqa: BLE001 - è proprio ciò che si misura
            voce["durata_s"] = round(time.monotonic() - inizio, 2)
            voce["esito"] = esito_errore(errore)
            self.chiamate.append(voce)
            raise
        voce["durata_s"] = round(time.monotonic() - inizio, 2)
        voce["esito"] = "ok"
        self.chiamate.append(voce)
        return risposta


def esito_errore(errore: Exception) -> str:
    if isinstance(errore, errors.APIError):
        extra = ""
        corpo = errore.details if isinstance(errore.details, dict) else {}
        for dettaglio in corpo.get("error", {}).get("details", []) or []:
            if isinstance(dettaglio, dict) and dettaglio.get("retryDelay"):
                extra = f" retryDelay={dettaglio['retryDelay']}"
        stato = getattr(errore, "status", "") or ""
        return f"{errore.code} {stato}{extra}".strip()
    return type(errore).__name__


def wav_da_pcm(pcm: bytes, frequenza: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frequenza)
        w.writeframes(pcm)
    return buffer.getvalue()


def _cervello(modello: str, client: Any, cartella: str) -> Cervello:
    return Cervello(
        client=client,
        modelli=[modello],
        faccia=crea_faccia(sul_terminale=False),
        archivio=ArchivioTimer(Path(cartella) / "timers.json"),
        **prompt_da_file(None),
    )


def _client(tentativi: int, timeout_s: float) -> Any:
    from google import genai

    return genai.Client(
        http_options=types.HttpOptions(
            timeout=int(timeout_s * 1000), retry_options=types.HttpRetryOptions(attempts=tentativi)
        )
    )


def prova_compat(modello: str, altro: str, pausa: float) -> dict[str, Any]:
    """Quattro richieste col cervello vero; `altro` è il modello che apre il turno del cambio."""
    from .carico import pcm_della_frase

    esito: dict[str, Any] = {}
    cartella = tempfile.mkdtemp(prefix="bmo-compat-")
    registratore = ClienteRegistratore(_client(1, 30.0))
    cervello = _cervello(modello, registratore, cartella)

    def tenta(nome: str, funzione: Any) -> None:
        try:
            esito[nome] = funzione()
        except Exception as errore:  # noqa: BLE001
            esito[nome] = {"ok": False, "errore": esito_errore(errore), "dettaglio": str(errore)[:200]}
        time.sleep(pausa)

    def semplice() -> dict[str, Any]:
        r = cervello.rispondi(testo=FRASE_SEMPLICE)
        return {"ok": bool(r.testo) and r.espressione is not None, "etichetta": r.espressione,
                "lingua": r.lingua, "chiamate": [c.nome for c in r.chiamate], "testo": r.testo[:80],
                "durata_s": round(r.durata_s, 2)}

    def strumento() -> dict[str, Any]:
        r = cervello.rispondi(testo=FRASE_STRUMENTO)
        giusto = [c for c in r.chiamate if c.nome == "imposta_timer" and durata_in_secondi(c.argomenti) == 600]
        return {"ok": bool(giusto), "chiamate": [(c.nome, c.argomenti) for c in r.chiamate],
                "etichetta": r.espressione, "testo": r.testo[:80], "durata_s": round(r.durata_s, 2)}

    def audio() -> dict[str, Any]:
        wav = wav_da_pcm(pcm_della_frase(FRASE_STRUMENTO))
        r = cervello.rispondi(audio_wav=wav)
        giusto = [c for c in r.chiamate if c.nome == "imposta_timer" and durata_in_secondi(c.argomenti) == 600]
        return {"ok": bool(giusto), "chiamate": [(c.nome, c.argomenti) for c in r.chiamate],
                "testo": r.testo[:80], "durata_s": round(r.durata_s, 2)}

    def cambio() -> dict[str, Any]:
        # Giro 0 sul modello `altro`, giro 1 (risultato dello strumento) su `modello`.
        contenuti = [types.Content(role="user", parts=[types.Part.from_text(text=FRASE_STRUMENTO)])]
        config = cervello._configurazione()
        primo = registratore._client.models.generate_content(model=altro, contents=contenuti, config=config)
        chiamate = primo.function_calls or []
        if not chiamate:
            return {"ok": False, "errore": f"{altro} non ha chiamato lo strumento"}
        contenuti.append(primo.candidates[0].content)
        nuove = cervello.strumenti(chiamate)
        contenuti.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=c.nome, response=c.risultato) for c in nuove]))
        time.sleep(pausa)
        secondo = registratore._client.models.generate_content(model=modello, contents=contenuti, config=config)
        return {"ok": True, "testo": (secondo.text or "")[:80]}

    tenta("semplice", semplice)
    tenta("strumento", strumento)
    tenta("audio", audio)
    tenta("cambio_a_meta_turno", cambio)
    esito["richieste"] = registratore.chiamate
    return esito


def prova_latenza(modello: str, ripetizioni: int, pausa: float) -> dict[str, Any]:
    cartella = tempfile.mkdtemp(prefix="bmo-lat-")
    registratore = ClienteRegistratore(_client(1, 30.0))
    cervello = _cervello(modello, registratore, cartella)
    semplici: list[float] = []
    con_strumento: list[float] = []
    corretti = 0
    errori: list[str] = []
    for _ in range(ripetizioni):
        for frase, lista in ((FRASE_SEMPLICE, semplici), (FRASE_STRUMENTO, con_strumento)):
            try:
                r = cervello.rispondi(testo=frase)
                lista.append(round(r.durata_s, 2))
                if frase == FRASE_STRUMENTO:
                    corretti += any(c.nome == "imposta_timer" and durata_in_secondi(c.argomenti) == 600 for c in r.chiamate)
            except Exception as errore:  # noqa: BLE001
                errori.append(esito_errore(errore))
            time.sleep(pausa)

    def riassunto(valori: list[float]) -> dict[str, Any]:
        if not valori:
            return {}
        return {"n": len(valori), "mediana": round(statistics.median(valori), 2),
                "max": max(valori), "min": min(valori), "valori": valori}

    return {"semplice": riassunto(semplici), "con_strumento": riassunto(con_strumento),
            "strumento_corretto": f"{corretti}/{ripetizioni}", "errori": errori,
            "richieste": registratore.chiamate}


def prova_limite(modello: str, raffica: int, tentativi: int) -> dict[str, Any]:
    """`raffica` richieste minuscole senza pause: cosa torna oltre l'RPM e a che costo."""
    client = _client(tentativi, 30.0)
    voci: list[dict[str, Any]] = []
    for _ in range(raffica):
        inizio = time.monotonic()
        try:
            client.models.generate_content(model=modello, contents="Rispondi solo: ok")
            esito = "ok"
        except (errors.APIError, httpx.HTTPError) as errore:
            esito = esito_errore(errore)
        voci.append({"esito": esito, "durata_s": round(time.monotonic() - inizio, 2)})
    return {"tentativi_sdk": tentativi, "richieste": voci}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prova", choices=["compat", "latenza", "limite"])
    parser.add_argument("--modelli", required=True, help="id separati da virgola")
    parser.add_argument("--altro", default="gemini-3.5-flash-lite",
                        help="compat: modello che apre il turno del cambio a metà")
    parser.add_argument("--ripetizioni", type=int, default=5)
    parser.add_argument("--pausa", type=float, default=15.0, help="secondi fra richieste")
    parser.add_argument("--raffica", type=int, default=7, help="limite: richieste senza pausa")
    parser.add_argument("--tentativi", type=int, default=1, help="limite: tentativi dell'SDK")
    parser.add_argument("--uscita", type=Path, help="scrive il JSON qui")
    argomenti = parser.parse_args()

    risultati: dict[str, Any] = {}
    for modello in [m.strip() for m in argomenti.modelli.split(",") if m.strip()]:
        print(f"== {argomenti.prova}: {modello}", flush=True)
        if argomenti.prova == "compat":
            risultati[modello] = prova_compat(modello, argomenti.altro, argomenti.pausa)
        elif argomenti.prova == "latenza":
            risultati[modello] = prova_latenza(modello, argomenti.ripetizioni, argomenti.pausa)
        else:
            risultati[modello] = prova_limite(modello, argomenti.raffica, argomenti.tentativi)
        print(json.dumps(risultati[modello], indent=1, ensure_ascii=False), flush=True)
    if argomenti.uscita:
        argomenti.uscita.write_text(json.dumps(risultati, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
