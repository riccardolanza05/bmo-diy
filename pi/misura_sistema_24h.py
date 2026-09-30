"""Sistema durante la prova di 24 h della #65: temperatura/throttling del Pi,
zram e memoria delle cgroup delle unit systemd indicate — non solo la PSS per
processo di `bmo_core.misura_ram` (che non vede cgroup, zram o temperatura).

`memory.peak` di ciascuna cgroup è il picco istantaneo dalla creazione della
unit (mai resettato qui): anche campionando ogni 30 s, un fork breve di mpv
che sfugge al campione (successo il 28/9, vedi `docs/note-issue-58.md`) resta
comunque catturato lì, perché il kernel lo registra lui, non il campionatore
— basta leggerlo alla fine, non serve azzerarlo a ogni giro.

Solo libreria standard più `vcgencmd` (già sul Pi): deve girare anche durante
un burn-in di 24 h senza altre dipendenze, come `pi/peso_*.py` e
`bmo_core.misura_ram`.

Uso (di solito come unit systemd, vedi `pi/systemd/bmo-misura-65.service`):

    python3 misura_sistema_24h.py --unita bmo-carico.service --unita bmo-face.service \
        --intervallo 30 --csv misure_65/sistema.csv
"""

from __future__ import annotations

import argparse
import csv
import signal
import subprocess
import sys
import time
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup/system.slice")

# Bit di `vcgencmd get_throttled` che contano (raspberrypi-firmware): 0-3 lo
# stato "ora", 16-19 lo stesso evento ma "successo almeno una volta dal boot".
# Questi ultimi sono quelli che interessano davvero per un burn-in di 24 h: un
# episodio isolato fra un campione e l'altro non deve sfuggire solo perché il
# campionatore non stava guardando in quel preciso istante.
_BIT_THROTTLED = {
    0: "sottovolt-ora", 1: "freq-limitata-ora", 2: "throttling-ora", 3: "temp-limitata-ora",
    16: "sottovolt-dal-boot", 17: "freq-limitata-dal-boot", 18: "throttling-dal-boot", 19: "temp-limitata-dal-boot",
}


def _leggi(percorso: Path) -> str | None:
    try:
        return percorso.read_text().strip()
    except (FileNotFoundError, PermissionError):
        return None


def memoria_cgroup(unita: str) -> dict[str, int | None]:
    base = CGROUP / unita
    corrente = _leggi(base / "memory.current")
    picco = _leggi(base / "memory.peak")
    eventi = _leggi(base / "memory.events") or ""
    valori = dict(riga.split() for riga in eventi.splitlines() if riga)
    return {
        "corrente_kb": int(corrente) // 1024 if corrente else None,
        "picco_kb": int(picco) // 1024 if picco else None,
        "oom": int(valori.get("oom", 0)),
        "oom_kill": int(valori.get("oom_kill", 0)),
    }


def temperatura_c() -> float | None:
    try:
        grezzo = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, check=True).stdout
        return float(grezzo.strip().removeprefix("temp=").removesuffix("'C"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def throttled() -> tuple[str, str]:
    """Il valore esadecimale e un riassunto leggibile dei bit che contano."""
    try:
        grezzo = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, check=True).stdout
        valore = int(grezzo.strip().removeprefix("throttled="), 16)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return "?", "?"
    attivi = [nome for posizione, nome in _BIT_THROTTLED.items() if valore & (1 << posizione)]
    return f"0x{valore:x}", ",".join(attivi) or "nessuno"


def zram_usato_kb() -> int | None:
    righe = (_leggi(Path("/proc/swaps")) or "").splitlines()
    for riga in righe[1:]:
        parti = riga.split()
        # /proc/swaps: Filename Type Size Used Priority — "Used" è la
        # colonna 4 (indice 3), non la "Size" del device (indice 2, sempre
        # ~pari alla RAM totale, l'errore preso live il 29/9 su questo
        # stesso script).
        if len(parti) >= 4 and "zram" in parti[0]:
            return int(parti[3])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--unita", action="append", required=True,
        help="nome di una unit systemd (system.slice) da seguire, es. bmo-carico.service (ripetibile)",
    )
    parser.add_argument("--intervallo", type=float, default=30.0, help="secondi fra un campione e l'altro")
    parser.add_argument("--csv", type=Path, required=True)
    argomenti = parser.parse_args()

    fermati = False

    def _ferma(*_: object) -> None:
        nonlocal fermati
        fermati = True

    signal.signal(signal.SIGINT, _ferma)
    signal.signal(signal.SIGTERM, _ferma)

    argomenti.csv.parent.mkdir(parents=True, exist_ok=True)
    intestazione = ["istante"]
    for unita in argomenti.unita:
        intestazione += [f"{unita}:corrente_kb", f"{unita}:picco_kb", f"{unita}:oom", f"{unita}:oom_kill"]
    intestazione += ["temp_c", "throttled_hex", "throttled_bit", "zram_usato_kb"]

    picchi: dict[str, int] = {}
    massimo_temp = 0.0
    massimo_zram = 0
    throttle_visto: set[str] = set()

    # In coda ("a"), non sovrascritto ("w"): se la unit si riavvia (crash,
    # `Restart=always`) durante le 24 h, un `open("w")` avrebbe perso i
    # campioni già raccolti. L'intestazione si scrive solo una volta, quando
    # il file non esiste ancora o è vuoto.
    file_gia_iniziato = argomenti.csv.exists() and argomenti.csv.stat().st_size > 0
    with argomenti.csv.open("a", newline="") as file_csv:
        scrittore = csv.writer(file_csv)
        if not file_gia_iniziato:
            scrittore.writerow(intestazione)
        while not fermati:
            riga: list[object] = [f"{time.time():.1f}"]
            for unita in argomenti.unita:
                m = memoria_cgroup(unita)
                riga += [m["corrente_kb"], m["picco_kb"], m["oom"], m["oom_kill"]]
                if m["picco_kb"]:
                    picchi[unita] = max(picchi.get(unita, 0), m["picco_kb"])
            temp = temperatura_c()
            hex_, bit = throttled()
            zram = zram_usato_kb() or 0
            riga += [temp, hex_, bit, zram]
            scrittore.writerow(riga)
            file_csv.flush()
            if temp:
                massimo_temp = max(massimo_temp, temp)
            massimo_zram = max(massimo_zram, zram)
            if bit not in ("nessuno", "?"):
                throttle_visto.add(bit)
            time.sleep(argomenti.intervallo)

    print("\n--- riepilogo misura_sistema_24h ---", file=sys.stderr)
    for unita, picco in picchi.items():
        print(f"{unita}: picco memory.peak {picco / 1024:.1f} MB", file=sys.stderr)
    print(f"temperatura massima osservata: {massimo_temp:.1f}°C", file=sys.stderr)
    print(f"zram usata al massimo: {massimo_zram / 1024:.1f} MB", file=sys.stderr)
    print(f"throttling osservato: {', '.join(sorted(throttle_visto)) or 'mai'}", file=sys.stderr)


if __name__ == "__main__":
    main()
