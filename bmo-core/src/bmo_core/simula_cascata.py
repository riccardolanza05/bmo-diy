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
COSTO_RITENTO_429_S = 1.8  # secondi in più con 2 tentativi dell'SDK (misura, docs/note-issue-73.md)


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
    lat_429_s: float = 0.2  # con 1 tentativo SDK; con 2 sale a ~2 s (misurato)
    # Richieste riuscite ma lente (code a 4-5 s viste anche sul modello più veloce).
    p_lento: float = 0.0
    lat_lenta_s: float = 4.5


@dataclass
class Esito:
    ok: bool
    durata_s: float
    richieste: dict[str, int] = field(default_factory=dict)


class Mondo:
    """Stato dei modelli nel tempo: episodi di guasto e finestre di richieste."""

    def __init__(
        self,
        profili: dict[str, ProfiloModello],
        rng: random.Random,
        comune: ProfiloModello | None = None,
    ) -> None:
        # `comune`: episodi di sovraccarico che colpiscono TUTTI i modelli insieme
        # (stessa infrastruttura, stessa rete): senza, i modelli sembrerebbero
        # guastarsi in modo indipendente e la cascata più sicura di quanto è.
        self.profili = dict(profili)
        self.comune = comune
        if comune is not None:
            self.profili["_comune"] = comune
        profili = self.profili
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
        guasto_proprio = self._aggiorna(modello)
        guasto_comune = self.comune is not None and self._aggiorna("_comune")
        if guasto_proprio or guasto_comune:
            if self.rng.random() < p.p_timeout:
                return "timeout", max_attesa_s
            return "503", min(p.lat_503_s, max_attesa_s)
        base = p.lat_lenta_s if self.rng.random() < p.p_lento else p.lat_mediana_s
        durata = self.rng.lognormvariate(0.0, p.lat_sigma) * base
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
        hedge_s: float | None = None,
    ) -> None:
        self.hedge_s = hedge_s
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

    def _con_hedge(self, primo: str, secondo: str, scadenza: float, conteggio: dict[str, int]) -> bool:
        """Lancia `secondo` se `primo` non ha risposto entro `hedge_s`: vince chi finisce prima.

        Costa una richiesta in più (quota) solo nella coda lenta; evita di
        aspettare il timeout intero del primo modello.
        """
        m = self.mondo
        t0 = m.t
        rimasto = scadenza - t0
        if rimasto < MINIMO_RICHIESTA_S:
            return False
        timeout = max(min(self.timeout_s(primo), rimasto), MINIMO_TIMEOUT_SERVER_S)
        e1, d1 = m.richiesta(primo, timeout)
        conteggio[primo] = conteggio.get(primo, 0) + 1
        if e1 == "ok" and d1 <= self.hedge_s:
            m.t = t0 + d1
            return True
        inizio2 = min(d1, self.hedge_s)
        m.t = t0 + inizio2
        e2, d2 = m.richiesta(secondo, timeout)
        conteggio[secondo] = conteggio.get(secondo, 0) + 1
        fine = [t0 + d for e, d, t in ((e1, d1, 0.0), (e2, d2, inizio2)) if e == "ok" for d in [d + t]]
        if fine:
            m.t = min(fine)
            return True
        m.t = t0 + max(d1, inizio2 + d2)
        for modello, esito in ((primo, e1), (secondo, e2)):
            if esito == "429":
                self._sospendi(modello, SOSPENSIONE_QUOTA_S, guasto=False)
            else:
                self._sospendi(modello, SOSPENSIONE_SOVRACCARICO_S, guasto=True)
        return False

    def richiesta(self, scadenza: float, conteggio: dict[str, int]) -> tuple[bool, str]:
        """Una `genera()`: (riuscita, motivo del fallimento). Fa avanzare l'orologio."""
        m = self.mondo
        candidati = self._disponibili() or self.modelli[:1]
        if self.hedge_s is not None and len(candidati) >= 2:
            if self._con_hedge(candidati[0], candidati[1], scadenza, conteggio):
                return True, ""
            candidati = candidati[2:]
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
                    # L'SDK ritenta anche i 429 (misurato: 1,5-3,3 s in tutto con
                    # 2 tentativi, 0,2 s con 1), ma restano 429 per un po'.
                    # Dentro il tetto di 20 s i tentativi sono sempre 1 (vedi sopra).
                    if tentativi > 1:
                        m.t += COSTO_RITENTO_429_S
                    break
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
    comune: ProfiloModello | None = None,
) -> list[Esito]:
    mondo = Mondo(profili, rng, comune)
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
    durate_ok = [e.durata_s for e in esiti if e.ok] or [0.0]
    richieste: dict[str, int] = {}
    for e in esiti:
        for m, n in e.richieste.items():
            richieste[m] = richieste.get(m, 0) + n
    return {
        "turni": len(esiti),
        "falliti_%": 100.0 * sum(not e.ok for e in esiti) / len(esiti),
        "mediana_s": statistics.median(durate),
        "p95_s": percentile(durate, 0.95),
        "p95_ok_s": percentile(durate_ok, 0.95),
        "mediana_ok_s": statistics.median(durate_ok),
        "lenti_>8s_%": 100.0 * sum(d > 8 for d in durate) / len(durate),
        "richieste": {m: n / len(esiti) for m, n in richieste.items()},
    }


# Profili presi dalle misure del 1/10/2026 (docs/note-issue-73.md). Le latenze
# sono per singola richiesta; un turno con strumento ne fa due o più.
PROFILI: dict[str, ProfiloModello] = {
    # Affidabilità misurata il 1/10 (25 richieste, 1 al minuto): 24/25 e 23/25.
    "gemini-3.5-flash-lite": ProfiloModello(0.8, p_lento=0.12, lat_lenta_s=4.5, p_guasto=0.04, lat_503_s=2.0),
    "gemini-3.1-flash-lite": ProfiloModello(2.8, lat_sigma=0.45, p_guasto=0.08, lat_503_s=2.3),
    "gemini-3.5-flash": ProfiloModello(1.8, p_guasto=0.08, rpm=5, lat_503_s=3.0),
    "gemini-3.6-flash": ProfiloModello(2.2, p_guasto=0.04, rpm=5, lat_503_s=3.0),
    # Misurati il 1/10: 503/504 sulla maggior parte delle richieste.
    "gemini-3.7-flash": ProfiloModello(3.0, p_guasto=0.6, durata_guasto_s=600, rpm=5, lat_503_s=4.0),
    "gemini-3.8-flash": ProfiloModello(2.5, p_guasto=0.7, durata_guasto_s=600, rpm=5, lat_503_s=3.0),
}
# Calibrato perché la cascata attuale dia ~7% di turni falliti (prova di 24 h, #65).
COMUNE = ProfiloModello(0.0, p_guasto=0.08, durata_guasto_s=150.0, p_timeout=0.6, lat_503_s=3.0)

L35, L31 = "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"
F35, F36 = "gemini-3.5-flash", "gemini-3.6-flash"
F37, F38 = "gemini-3.7-flash", "gemini-3.8-flash"

# (nome, modelli, opzioni della cascata). Le prime quattro sono realizzabili
# cambiando solo l'elenco dei modelli o le costanti; l'ultima è un meccanismo
# nuovo, valutato qui e NON implementato (vedi docs/decisioni-issue-73.md).
VARIANTI: list[tuple[str, list[str], dict]] = [
    ("A attuale (2 lite)", [L35, L31], {}),
    ("B + flash in coda (3.5 poi 3.1 poi 3.5-f, 3.6)", [L35, L31, F35, F36], {}),
    ("B2 = B con 3.6 prima di 3.5 (SCELTA, implementata)", [L35, L31, F36, F35], {}),
    ("C flash prima del lite lento", [L35, F35, F36, L31], {}),
    ("D = C con 3.7/3.8 nella cascata", [L35, F37, F38, F35, F36, L31], {}),
    ("E = C con timeout per tentativo 10 s (costante)", [L35, F35, F36, L31], {"timeout_s": 10.0}),
    ("F = C + salto RPM + sospensione lunga (non implem.)", [L35, F35, F36, L31],
     {"salta_se_al_limite": True, "sospensione_lunga": True}),
    ("G = C + hedging a 3 s (non implem.)", [L35, F35, F36, L31], {"hedge_s": 3.0}),
    ("H = C + timeout 10 s + hedging a 3 s (non implem.)", [L35, F35, F36, L31],
     {"timeout_s": 10.0, "hedge_s": 3.0}),
]


# Scenario "indipendenti": ogni modello si guasta per conto suo, nessun guasto
# comune. È l'estremo ottimistico per aggiungere modelli; il vero sta in mezzo
# (non si può distinguere con i dati della #65: contano solo i turni falliti).
PROFILI_INDIPENDENTI = {
    **PROFILI,
    "gemini-3.5-flash-lite": ProfiloModello(0.8, p_lento=0.12, lat_lenta_s=4.5, p_guasto=0.07, lat_503_s=2.0),
    "gemini-3.1-flash-lite": ProfiloModello(2.8, lat_sigma=0.45, p_guasto=0.10, lat_503_s=3.5),
}


def confronta(turni: int, prove: int, seme: int, pausa_media_s: float, guasti: str) -> None:
    indipendenti = guasti == "indipendenti"
    profili = PROFILI_INDIPENDENTI if indipendenti else PROFILI
    comune = None if indipendenti else COMUNE
    print(f"{prove} conversazioni da {turni} turni, pausa media fra i turni {pausa_media_s:.0f} s, "
          f"guasti {guasti}\n")
    print(f"{'variante':54} {'falliti':>8} {'mediana':>8} {'p95 ok':>7} {'>8 s':>6}  richieste/turno")
    for nome, modelli, opzioni in VARIANTI:
        tutti: list[Esito] = []
        for i in range(prove):
            rng = random.Random(seme + i)
            tutti += conversazione(
                profili, lambda mondo, mod=modelli, op=opzioni: CascataSimulata(mondo, mod, **op),
                turni, rng, pausa_media_s=pausa_media_s, comune=comune,
                avvio_s=rng.uniform(0, 3600),
            )
        r = riassunto(tutti)
        per_modello = " ".join(f"{m.replace('gemini-', '')}={n:.2f}" for m, n in r["richieste"].items())
        print(f"{nome:54} {r['falliti_%']:7.1f}% {r['mediana_ok_s']:7.2f}s {r['p95_ok_s']:6.1f}s "
              f"{r['lenti_>8s_%']:5.1f}%  {per_modello}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--turni", type=int, default=60)
    parser.add_argument("--prove", type=int, default=300)
    parser.add_argument("--seme", type=int, default=1)
    parser.add_argument("--pausa", type=float, default=25.0, help="pausa media fra i turni, secondi")
    parser.add_argument("--guasti", choices=["correlati", "indipendenti"], default="correlati")
    argomenti = parser.parse_args()
    confronta(argomenti.turni, argomenti.prove, argomenti.seme, argomenti.pausa, argomenti.guasti)


if __name__ == "__main__":
    main()
