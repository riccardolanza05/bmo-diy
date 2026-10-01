"""Simulatore della cascata di modelli su una conversazione lunga (issue #73).

Serve a scegliere con i numeri, prima di toccare la cascata vera: confronta
l'ordine dei modelli e alcuni meccanismi (alcuni NON implementati, solo
valutati) su tante conversazioni di molti turni, con fallimenti e latenze
finti presi dalle misure reali (`docs/note-issue-73.md`).

    python -m bmo_core.simula_cascata                # confronto fra le varianti
    python -m bmo_core.simula_cascata --turni 200 --prove 300 --seme 7

Cosa riproduce della cascata vera (`modelli.py`): ordine di prova, sospensione
del modello dopo un errore (60 s quota, 30 s sovraccarico), tentativi
dell'SDK, timeout per tentativo, tetto del turno di 20 s (+ il minimo di 10 s
della scadenza lato server). Cosa NON riproduce: il contenuto delle risposte
(la qualità sugli strumenti si misura col banco di frasi, non qui).

I guasti non sono indipendenti: ogni modello alterna periodi buoni e periodi
di sovraccarico lunghi minuti (catena di Markov a due stati), come nella
prova di 24 h della #65. Con guasti indipendenti ogni meccanismo di memoria
dello stato sembrerebbe migliore di quello che è.
"""
from __future__ import annotations

import argparse
import random
import statistics
from dataclasses import dataclass, field
from typing import Callable

TETTO_TURNO_S = 20.0
MINIMO_RICHIESTA_S = 1.0
MINIMO_TIMEOUT_SERVER_S = 10.0
TIMEOUT_TENTATIVO_S = 15.0
TENTATIVI_SDK = 2
SOSPENSIONE_QUOTA_S = 60.0
SOSPENSIONE_SOVRACCARICO_S = 30.0
PAUSA_SDK_S = 1.0  # attesa fra i tentativi dell'SDK


@dataclass
class ProfiloModello:
    """Come si comporta un modello, preso dalle misure.

    `lat_mediana_s`/`lat_sigma`: tempo di una richiesta riuscita (lognormale).
    `p_guasto`: frazione di tempo in cui il modello è in sovraccarico;
    `durata_guasto_s`: lunghezza media di un episodio. In sovraccarico una
    richiesta finisce in `p_timeout` dei casi con un timeout (costa l'intero
    tempo dell'attesa), altrimenti con un 503 veloce (`lat_503_s`).
    `rpm`: richieste al minuto consentite (None = non si urta).
    """

    lat_mediana_s: float
    lat_sigma: float = 0.35
    p_guasto: float = 0.05
    durata_guasto_s: float = 180.0
    p_timeout: float = 0.5
    lat_503_s: float = 1.5
    rpm: int | None = None
    lat_429_s: float = 0.6


@dataclass
class Esito:
    ok: bool
    durata_s: float
    richieste: dict[str, int] = field(default_factory=dict)


class Mondo:
    """Stato dei modelli nel tempo: episodi di guasto e finestre di richieste."""

    def __init__(self, profili: dict[str, ProfiloModello], rng: random.Random) -> None:
        self.profili = profili
        self.rng = rng
        self.t = 0.0
        self._fino_a: dict[str, float] = {}  # fine dell'episodio in corso
        self._in_guasto: dict[str, bool] = {m: False for m in profili}
        self._finestra: dict[str, list[float]] = {m: [] for m in profili}

    def _aggiorna(self, modello: str) -> bool:
        p = self.profili[modello]
        fine = self._fino_a.get(modello, 0.0)
        while self.t >= fine:
            # Durate esponenziali: episodio buono lungo quanto serve a dare p_guasto.
            if p.p_guasto <= 0:
                self._in_guasto[modello] = False
                fine = float("inf")
                break
            guasto_prossimo = not self._in_guasto[modello]
            media = p.durata_guasto_s if guasto_prossimo else p.durata_guasto_s * (1 - p.p_guasto) / p.p_guasto
            self._in_guasto[modello] = guasto_prossimo
            fine = fine + self.rng.expovariate(1.0 / media)
        self._fino_a[modello] = fine
        return self._in_guasto[modello]

    def richiesta(self, modello: str, max_attesa_s: float) -> tuple[str, float]:
        """Una richiesta: ('ok'|'503'|'429'|'timeout', secondi spesi)."""
        p = self.profili[modello]
        finestra = [x for x in self._finestra[modello] if x > self.t - 60.0]
        self._finestra[modello] = finestra
        if p.rpm is not None and len(finestra) >= p.rpm:
            return "429", p.lat_429_s
        finestra.append(self.t)
        if self._aggiorna(modello):
            if self.rng.random() < p.p_timeout:
                return "timeout", max_attesa_s
            return "503", min(p.lat_503_s, max_attesa_s)
        durata = self.rng.lognormvariate(0.0, p.lat_sigma) * p.lat_mediana_s
        if durata > max_attesa_s:
            return "timeout", max_attesa_s
        return "ok", durata


class CascataSimulata:
    """La cascata di `modelli.py`, passo per passo, sull'orologio del Mondo."""

    def __init__(
        self,
        mondo: Mondo,
        modelli: list[str],
        *,
        timeout_s: Callable[[str], float] | float = TIMEOUT_TENTATIVO_S,
        tentativi_sdk: int = TENTATIVI_SDK,
        salta_se_al_limite: bool = False,
        sospensione_lunga: bool = False,
    ) -> None:
        self.mondo = mondo
        self.modelli = modelli
        self.timeout_s = timeout_s if callable(timeout_s) else (lambda _m, v=timeout_s: v)
        self.tentativi_sdk = tentativi_sdk
        self.salta_se_al_limite = salta_se_al_limite
        # Variante: dopo un timeout/503 ripetuto il modello resta fuori più a lungo.
        self.sospensione_lunga = sospensione_lunga
        self._sospesi: dict[str, float] = {}
        self._guasti_di_fila: dict[str, int] = {m: 0 for m in modelli}

    def _disponibili(self) -> list[str]:
        return [m for m in self.modelli if self._sospesi.get(m, 0.0) <= self.mondo.t]

    def _al_limite(self, modello: str) -> bool:
        p = self.mondo.profili[modello]
        if p.rpm is None:
            return False
        recenti = [x for x in self.mondo._finestra[modello] if x > self.mondo.t - 60.0]
        return len(recenti) >= p.rpm

    def _sospendi(self, modello: str, secondi: float, guasto: bool) -> None:
        if guasto:
            self._guasti_di_fila[modello] += 1
            if self.sospensione_lunga:
                secondi *= min(2 ** (self._guasti_di_fila[modello] - 1), 8)
        self._sospesi[modello] = self.mondo.t + secondi

    def richiesta(self, scadenza: float, conteggio: dict[str, int]) -> tuple[bool, str]:
        """Una `genera()`: (riuscita, motivo del fallimento). Fa avanzare l'orologio."""
        m = self.mondo
        candidati = self._disponibili() or self.modelli[:1]
        for modello in candidati:
            if self.salta_se_al_limite and self._al_limite(modello):
                continue
            rimasto = scadenza - m.t
            if rimasto < MINIMO_RICHIESTA_S:
                return False, "tempo"
            timeout = max(min(self.timeout_s(modello), rimasto), MINIMO_TIMEOUT_SERVER_S)
            tentativi = self.tentativi_sdk if rimasto >= self.tentativi_sdk * self.timeout_s(modello) else 1
            for tentativo in range(tentativi):
                esito, spesi = m.richiesta(modello, timeout)
                conteggio[modello] = conteggio.get(modello, 0) + 1
                m.t += spesi
                if esito == "ok":
                    self._guasti_di_fila[modello] = 0
                    return True, ""
                if esito == "429":
                    break  # l'SDK ritenta anche i 429, ma restano 429 per un minuto
                if tentativo + 1 < tentativi:
                    m.t += PAUSA_SDK_S
            if esito == "429":
                self._sospendi(modello, SOSPENSIONE_QUOTA_S, guasto=False)
            else:
                self._sospendi(modello, SOSPENSIONE_SOVRACCARICO_S, guasto=True)
        return False, "tutti falliti"


def conversazione(
    profili: dict[str, ProfiloModello],
    costruisci: Callable[[Mondo], CascataSimulata],
    turni: int,
    rng: random.Random,
    *,
    pausa_media_s: float = 25.0,
    richieste_per_turno: tuple[tuple[int, float], ...] = ((1, 0.55), (2, 0.35), (3, 0.10)),
    avvio_s: float = 0.0,
) -> list[Esito]:
    mondo = Mondo(profili, rng)
    mondo.t = avvio_s
    cascata = costruisci(mondo)
    esiti: list[Esito] = []
    for _ in range(turni):
        mondo.t += rng.expovariate(1.0 / pausa_media_s)
        partenza = mondo.t
        scadenza = partenza + TETTO_TURNO_S
        conteggio: dict[str, int] = {}
        n = rng.choices([k for k, _ in richieste_per_turno], [w for _, w in richieste_per_turno])[0]
        ok = True
        for giro in range(n):
            if giro and mondo.t >= scadenza - 6.0:
                break  # riepilogo forzato: qui conta solo se il turno ha dato una risposta
            riuscita, _ = cascata.richiesta(scadenza, conteggio)
            if not riuscita:
                ok = False
                break
        esiti.append(Esito(ok, mondo.t - partenza, conteggio))
    return esiti


def percentile(valori: list[float], q: float) -> float:
    valori = sorted(valori)
    return valori[min(len(valori) - 1, int(q * len(valori)))]


def riassunto(esiti: list[Esito]) -> dict[str, float | dict[str, float]]:
    durate = [e.durata_s for e in esiti]
    richieste: dict[str, int] = {}
    for e in esiti:
        for m, n in e.richieste.items():
            richieste[m] = richieste.get(m, 0) + n
    return {
        "turni": len(esiti),
        "falliti_%": 100.0 * sum(not e.ok for e in esiti) / len(esiti),
        "mediana_s": statistics.median(durate),
        "p95_s": percentile(durate, 0.95),
        "lenti_>8s_%": 100.0 * sum(d > 8 for d in durate) / len(durate),
        "richieste": {m: n / len(esiti) for m, n in richieste.items()},
    }
