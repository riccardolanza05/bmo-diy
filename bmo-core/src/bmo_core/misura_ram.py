"""Misura la RAM di BMO mentre gira: bmo-core, bmo-face, mpv, arecord.

Campiona ogni `--intervallo` secondi tutti i processi discendenti di un PID
radice (tipicamente lo script che lancia BMO) e ne legge
`/proc/<pid>/smaps_rollup`. Scrive un CSV con una riga per componente per
campione e, alla fine (Ctrl-C, SIGTERM o fine della radice), stampa un
riepilogo con i picchi.

Perché PSS e non RSS: la RSS conta per intero in ogni processo le librerie
condivise (libc, libpython, ...), quindi sommare le RSS di bmo-core, bmo-face
e mpv gonfia il totale. La PSS divide ogni pagina condivisa fra i processi
che la usano: la somma delle PSS è la memoria che l'insieme occupa davvero,
cioè il numero da confrontare col budget del Pi («picco RSS totale < 320 MB»,
fase 2.3 del piano, che in realtà va letto come PSS totale). La RSS resta nel
CSV per confronto; la USS (memoria privata) dice quanto si libererebbe
uccidendo quel processo.

Solo libreria standard: deve girare anche sul Pi senza installare niente.

Uso:
    python -m bmo_core.misura_ram --radice <PID> [--csv file.csv]
    python -m bmo_core.misura_ram --cerca bmo_core   # tutti i processi col testo nella riga di comando
"""

from __future__ import annotations

import argparse
import csv
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROC = Path("/proc")

# Ordine di priorità: il primo che corrisponde nella riga di comando vince.
COMPONENTI: list[tuple[str, str]] = [
    ("bmo-core", "bmo_core"),
    ("bmo-face", "bmo_face"),
    ("mpv", "mpv"),
    ("arecord", "arecord"),
]


@dataclass
class Memoria:
    """Kilobyte, come in smaps_rollup."""

    rss: int = 0
    pss: int = 0
    uss: int = 0
    swap: int = 0
    # La PSS divisa per natura (#58): l'anonima (heap, oggetti Python, arene
    # di onnxruntime) può solo stare in RAM o finire compressa in zram; quella
    # su file (codice delle librerie, modelli mappati) il kernel la scarta
    # sotto pressione e la rilegge dal disco quando serve — è già "streaming
    # dalla SD", gratis.
    pss_anon: int = 0
    pss_file: int = 0

    def __iadd__(self, altra: "Memoria") -> "Memoria":
        self.rss += altra.rss
        self.pss += altra.pss
        self.uss += altra.uss
        self.swap += altra.swap
        self.pss_anon += altra.pss_anon
        self.pss_file += altra.pss_file
        return self


def leggi_smaps_rollup(testo: str) -> Memoria:
    """Estrae RSS, PSS, USS (Private_Clean + Private_Dirty) e swap."""
    valori: dict[str, int] = {}
    for riga in testo.splitlines():
        parti = riga.split()
        if len(parti) >= 2 and parti[0].endswith(":") and parti[1].isdigit():
            valori[parti[0][:-1]] = int(parti[1])
    return Memoria(
        rss=valori.get("Rss", 0),
        pss=valori.get("Pss", 0),
        uss=valori.get("Private_Clean", 0) + valori.get("Private_Dirty", 0),
        swap=valori.get("SwapPss", valori.get("Swap", 0)),
        pss_anon=valori.get("Pss_Anon", 0) + valori.get("Pss_Shmem", 0),
        pss_file=valori.get("Pss_File", 0),
    )


def componente_di(riga_comando: str) -> str:
    for nome, chiave in COMPONENTI:
        if chiave in riga_comando:
            return nome
    return "altro"


def _leggi(percorso: Path) -> str | None:
    try:
        return percorso.read_text(errors="replace")
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def riga_comando(pid: int) -> str:
    grezza = _leggi(PROC / str(pid) / "cmdline") or ""
    return grezza.replace("\0", " ").strip()


def genitori() -> dict[int, int]:
    """pid -> ppid per tutti i processi visibili."""
    mappa: dict[int, int] = {}
    for voce in PROC.iterdir():
        if not voce.name.isdigit():
            continue
        stat = _leggi(voce / "stat")
        if stat is None:
            continue
        # Il nome del comando fra parentesi può contenere spazi: si riparte
        # dall'ultima parentesi chiusa.
        dopo = stat.rsplit(")", 1)[-1].split()
        if len(dopo) >= 2:
            mappa[int(voce.name)] = int(dopo[1])
    return mappa


def discendenti(radice: int, mappa: dict[int, int]) -> list[int]:
    figli: dict[int, list[int]] = {}
    for pid, ppid in mappa.items():
        figli.setdefault(ppid, []).append(pid)
    trovati, da_visitare = [], [radice]
    while da_visitare:
        pid = da_visitare.pop()
        for figlio in figli.get(pid, []):
            trovati.append(figlio)
            da_visitare.append(figlio)
    return trovati


def processi_con(testo: str, mappa: dict[int, int], righe: dict[int, str] | None = None) -> list[int]:
    """I processi che hanno `testo` nella riga di comando, più i loro figli.

    Un processo il cui figlio corrisponde anche lui è un involucro
    (`timeout`, `bash -c`, `sudo`...) che ha nella sua riga di comando quella
    del figlio: si scarta, altrimenti si misura il lanciatore invece di BMO.
    """
    # Il campionatore stesso e chi l'ha lanciato (`timeout ... --cerca
    # bmo_core`) hanno il testo cercato fra gli argomenti: vanno esclusi.
    esclusi = {os.getpid()}
    pid = os.getpid()
    while pid in mappa and mappa[pid] not in esclusi:
        pid = mappa[pid]
        esclusi.add(pid)
    righe = righe if righe is not None else {pid: riga_comando(pid) for pid in mappa}
    trovati = {pid for pid in mappa if pid not in esclusi and testo in righe.get(pid, "")}
    involucri = {mappa[pid] for pid in trovati if mappa.get(pid) in trovati}
    radici = trovati - involucri
    risultato = set(radici)
    for pid in radici:
        risultato.update(discendenti(pid, mappa))
    return sorted(risultato)


def mem_disponibile_kb() -> int:
    for riga in (_leggi(PROC / "meminfo") or "").splitlines():
        if riga.startswith("MemAvailable:"):
            return int(riga.split()[1])
    return 0


@dataclass
class Riepilogo:
    campioni: int = 0
    picco_totale: Memoria = field(default_factory=Memoria)
    istante_picco: float = 0.0
    picchi: dict[str, Memoria] = field(default_factory=dict)
    somma_pss: int = 0
    minimo_disponibile: int = 0
    inizio: float = field(default_factory=time.time)

    def aggiungi(self, istante: float, per_componente: dict[str, Memoria], disponibile: int) -> None:
        totale = Memoria()
        for nome, mem in per_componente.items():
            totale += mem
            picco = self.picchi.setdefault(nome, Memoria())
            picco.rss = max(picco.rss, mem.rss)
            picco.pss = max(picco.pss, mem.pss)
            picco.uss = max(picco.uss, mem.uss)
            picco.swap = max(picco.swap, mem.swap)
            picco.pss_anon = max(picco.pss_anon, mem.pss_anon)
            picco.pss_file = max(picco.pss_file, mem.pss_file)
        self.campioni += 1
        self.somma_pss += totale.pss
        if totale.pss > self.picco_totale.pss:
            self.picco_totale = totale
            self.istante_picco = istante
        if disponibile and (not self.minimo_disponibile or disponibile < self.minimo_disponibile):
            self.minimo_disponibile = disponibile

    def testo(self) -> str:
        mb = lambda kb: f"{kb / 1024:6.1f} MB"  # noqa: E731
        durata = time.time() - self.inizio
        righe = [
            f"Misura RAM di BMO: {self.campioni} campioni in {durata / 60:.1f} min",
            f"  picco PSS totale : {mb(self.picco_totale.pss)}  "
            f"(alle {datetime.fromtimestamp(self.istante_picco):%H:%M:%S}; RSS sommata {mb(self.picco_totale.rss)})",
            f"    di cui anonima {mb(self.picco_totale.pss_anon)}, su file {mb(self.picco_totale.pss_file)} "
            "(la parte su file il kernel la può rileggere dal disco)",
        ]
        if self.campioni:
            righe.append(f"  media PSS totale : {mb(self.somma_pss // self.campioni)}")
        righe.append("  picchi per componente (ognuno nel suo momento peggiore):")
        for nome in sorted(self.picchi, key=lambda n: -self.picchi[n].pss):
            p = self.picchi[nome]
            righe.append(
                f"    {nome:<9} PSS {mb(p.pss)}  anon {mb(p.pss_anon)}  file {mb(p.pss_file)}"
                f"  USS {mb(p.uss)}  RSS {mb(p.rss)}  swap {mb(p.swap)}"
            )
        if self.minimo_disponibile:
            righe.append(f"  MemAvailable minima del sistema: {mb(self.minimo_disponibile)}")
        return "\n".join(righe)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    gruppo = parser.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("--radice", type=int, help="PID di cui misurare tutti i discendenti")
    gruppo.add_argument("--cerca", help="misura i processi la cui riga di comando contiene questo testo")
    parser.add_argument("--intervallo", type=float, default=0.5, help="secondi fra un campione e l'altro")
    parser.add_argument("--csv", type=Path, help="file CSV dove scrivere i campioni")
    parser.add_argument("--riepilogo", type=Path, help="file dove scrivere anche il riepilogo finale")
    argomenti = parser.parse_args()

    fermati = False

    def _ferma(*_: object) -> None:
        nonlocal fermati
        fermati = True

    signal.signal(signal.SIGINT, _ferma)
    signal.signal(signal.SIGTERM, _ferma)

    riepilogo = Riepilogo()
    file_csv = None
    scrittore = None
    if argomenti.csv:
        argomenti.csv.parent.mkdir(parents=True, exist_ok=True)
        file_csv = argomenti.csv.open("w", newline="")
        scrittore = csv.writer(file_csv)
        scrittore.writerow(
            ["istante", "componente", "processi", "pss_kb", "uss_kb", "rss_kb", "swap_kb", "mem_disponibile_kb",
             "pss_anon_kb", "pss_file_kb"]
        )

    try:
        while not fermati:
            mappa = genitori()
            if argomenti.radice is not None:
                if argomenti.radice not in mappa:
                    break
                # Lanciato da avvia_demo.sh il campionatore è anche lui un
                # discendente della radice: non deve misurare se stesso.
                pids = [pid for pid in discendenti(argomenti.radice, mappa) if pid != os.getpid()]
            else:
                pids = processi_con(argomenti.cerca, mappa)
            per_componente: dict[str, Memoria] = {}
            quanti: dict[str, int] = {}
            for pid in pids:
                testo = _leggi(PROC / str(pid) / "smaps_rollup")
                if not testo:
                    continue
                nome = componente_di(riga_comando(pid))
                per_componente.setdefault(nome, Memoria())
                per_componente[nome] += leggi_smaps_rollup(testo)
                quanti[nome] = quanti.get(nome, 0) + 1
            istante = time.time()
            disponibile = mem_disponibile_kb()
            riepilogo.aggiungi(istante, per_componente, disponibile)
            if scrittore is not None:
                for nome, mem in per_componente.items():
                    scrittore.writerow(
                        [f"{istante:.1f}", nome, quanti[nome], mem.pss, mem.uss, mem.rss, mem.swap, disponibile,
                         mem.pss_anon, mem.pss_file]
                    )
                file_csv.flush()
            time.sleep(argomenti.intervallo)
    finally:
        if file_csv is not None:
            file_csv.close()
        testo = riepilogo.testo()
        print(testo, file=sys.stderr, flush=True)
        if argomenti.riepilogo:
            argomenti.riepilogo.write_text(testo + "\n")


if __name__ == "__main__":
    main()
