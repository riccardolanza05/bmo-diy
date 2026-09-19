"""Cascata di modelli Gemini con ripiego automatico (issue #12).

Se il modello primario risponde con quota esaurita (429) o è sovraccarico
(5xx), `bmo-core` prova subito il modello successivo della cascata invece
di restare muto. Il modello che ha fallito viene sospeso per un po' e poi
torna a essere provato per primo: nessun reset manuale.

La cascata sta in configurazione, non nel codice, perché i limiti reali del
free tier cambiano nel tempo e vanno verificati con la propria chiave:

    BMO_GEMINI_MODELLI="gemini-3.5-flash-lite,gemini-3.1-flash-lite,..."

Se la variabile non c'è, si usa solo `BMO_GEMINI_MODEL`; se manca anche
quella, la cascata predefinita qui sotto.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

import httpx
from google.genai import errors

# Primario e riserva scelti dopo le prime prove reali, quando
# gemini-3.8-flash rispondeva spesso 503 per sovraccarico.
MODELLI_PREDEFINITI = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

# Per quanto un modello resta sospeso dopo un errore, in secondi.
SOSPENSIONE_QUOTA_S = 60.0          # 429 senza retryDelay nella risposta
SOSPENSIONE_SOVRACCARICO_S = 30.0   # 500/502/503/504
SOSPENSIONE_INESISTENTE_S = 3600.0  # 404: nome sbagliato o modello non disponibile

# Tentativi dell'SDK per ogni modello, compreso il primo. L'SDK di default ne
# fa 5 con attese crescenti (oltre 15 s): con una cascata conviene passare
# subito al modello successivo.
TENTATIVI_SDK = 2

# Tempo massimo di ogni tentativo. Senza, una richiesta accettata ma mai
# servita lasciava BMO in attesa per sempre (prova del 19/9). L'SDK ripete
# anche i tentativi scaduti: con 2 tentativi sono circa 30 s per modello.
TIMEOUT_TENTATIVO_S = 15.0


class GeminiNonDisponibile(Exception):
    """Tutti i modelli della cascata hanno fallito.

    `tipo` è "quota", "sovraccarico" o "rete": sul dispositivo decide la
    frase e la faccia con cui BMO lo dice.
    """

    def __init__(self, tipo: str, errori: dict[str, Exception]) -> None:
        self.tipo = tipo
        self.errori = errori
        dettagli = "; ".join(f"{modello}: {errore}" for modello, errore in errori.items())
        super().__init__(f"nessun modello disponibile ({tipo}) — {dettagli or 'tutti sospesi'}")


def modelli_da_ambiente() -> list[str]:
    elenco = os.environ.get("BMO_GEMINI_MODELLI", "")
    modelli = [m.strip() for m in elenco.split(",") if m.strip()]
    if modelli:
        return modelli
    singolo = os.environ.get("BMO_GEMINI_MODEL", "").strip()
    return [singolo] if singolo else list(MODELLI_PREDEFINITI)


def attesa_suggerita(errore: errors.APIError) -> float | None:
    """Legge il `retryDelay` (es. "37s") che Google allega ai 429, se c'è."""
    corpo = errore.details if isinstance(errore.details, dict) else {}
    for dettaglio in corpo.get("error", {}).get("details", []) or []:
        ritardo = dettaglio.get("retryDelay") if isinstance(dettaglio, dict) else None
        if isinstance(ritardo, str) and (trovato := re.fullmatch(r"([\d.]+)s", ritardo)):
            return float(trovato.group(1))
    return None


class CascataModelli:
    def __init__(
        self,
        modelli: list[str] | None = None,
        orologio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.modelli = list(modelli) if modelli else modelli_da_ambiente()
        self.orologio = orologio
        self._sospesi_fino_a: dict[str, float] = {}
        self._motivi: dict[str, str] = {}

    @property
    def primario(self) -> str:
        return self.modelli[0]

    def disponibili(self) -> list[str]:
        adesso = self.orologio()
        return [m for m in self.modelli if self._sospesi_fino_a.get(m, 0.0) <= adesso]

    def sospendi(self, modello: str, secondi: float, motivo: str = "sovraccarico") -> None:
        self._sospesi_fino_a[modello] = self.orologio() + secondi
        self._motivi[modello] = motivo

    def genera(self, client: Any, **richiesta: Any) -> tuple[Any, str]:
        """Chiama `generate_content` sul primo modello disponibile.

        Restituisce la risposta e il nome del modello che l'ha prodotta.
        Gli errori non legati alla disponibilità (400, 401, 403...) salgono
        subito: cambiare modello non li risolverebbe.
        """
        errori: dict[str, Exception] = {}
        # Se sono tutti sospesi si riprova comunque il primo che esiste: un
        # sovraccarico di pochi secondi non deve lasciare BMO muto per 30.
        candidati = self.disponibili() or [
            m for m in self.modelli if self._motivi.get(m) != "inesistente"
        ][:1]
        for modello in candidati:
            try:
                return client.models.generate_content(model=modello, **richiesta), modello
            except errors.APIError as errore:
                if errore.code == 429:
                    self.sospendi(modello, attesa_suggerita(errore) or SOSPENSIONE_QUOTA_S, "quota")
                elif errore.code in (500, 502, 503, 504):
                    self.sospendi(modello, SOSPENSIONE_SOVRACCARICO_S, "sovraccarico")
                elif errore.code == 404:
                    self.sospendi(modello, SOSPENSIONE_INESISTENTE_S, "inesistente")
                else:
                    raise
                errori[modello] = errore
            except httpx.ReadTimeout as errore:
                # Il server ha accettato la richiesta ma non risponde: come un sovraccarico.
                self.sospendi(modello, SOSPENSIONE_SOVRACCARICO_S, "sovraccarico")
                errori[modello] = errore
            except httpx.TransportError as errore:
                # Rete giù: gli altri modelli stanno sullo stesso server, inutile provarli.
                raise GeminiNonDisponibile("rete", {modello: errore}) from errore
        # Tutti falliti o tutti già sospesi: se anche uno solo è fermo per
        # quota lo si dice, perché è l'unico caso che non passa in pochi secondi.
        motivi = {self._motivi.get(m) for m in self.modelli}
        raise GeminiNonDisponibile("quota" if "quota" in motivi else "sovraccarico", errori)
