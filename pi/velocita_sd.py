"""Velocità della microSD, per decidere cosa può vivere sul disco invece che in RAM (#58).

Misura quello che conta per lo "streaming dalla SD":
- lettura sequenziale (caricare un modello o una libreria la prima volta);
- lettura casuale a blocchi da 4 KiB (il kernel che rilegge dal disco una
  pagina di codice che aveva scartato per fare spazio: è sempre a caso, e
  sempre 4 KiB);
- la latenza di quella lettura casuale (quanto aspetta il processo).

Legge con O_DIRECT, che scavalca la cache di pagina del kernel: altrimenti
si misurerebbe la RAM, non la scheda. Scrive un file di prova da 256 MiB in
/var/tmp (su SD) e lo cancella alla fine. Solo libreria standard.

    python3 velocita_sd.py
"""

import mmap
import os
import random
import statistics
import time

PERCORSO = "/var/tmp/bmo-velocita-sd.bin"
DIMENSIONE = 256 * 1024 * 1024
BLOCCO_SEQ = 1024 * 1024
BLOCCO_CASUALE = 4096
LETTURE_CASUALI = 2000


def _buffer(dimensione: int) -> mmap.mmap:
    # O_DIRECT vuole memoria allineata: una mappa anonima lo è sempre.
    return mmap.mmap(-1, dimensione)


def prepara() -> None:
    if os.path.exists(PERCORSO) and os.path.getsize(PERCORSO) == DIMENSIONE:
        return
    blocco = os.urandom(BLOCCO_SEQ)
    inizio = time.monotonic()
    with open(PERCORSO, "wb") as file:
        for _ in range(DIMENSIONE // BLOCCO_SEQ):
            file.write(blocco)
        file.flush()
        os.fsync(file.fileno())
    durata = time.monotonic() - inizio
    print(f"scrittura sequenziale : {DIMENSIONE / durata / 1e6:6.1f} MB/s")


def lettura_sequenziale() -> None:
    fd = os.open(PERCORSO, os.O_RDONLY | os.O_DIRECT)
    buffer = _buffer(BLOCCO_SEQ)
    letti = 0
    inizio = time.monotonic()
    while True:
        n = os.readv(fd, [buffer])
        if n <= 0:
            break
        letti += n
    durata = time.monotonic() - inizio
    os.close(fd)
    print(f"lettura sequenziale   : {letti / durata / 1e6:6.1f} MB/s")


def lettura_casuale() -> None:
    fd = os.open(PERCORSO, os.O_RDONLY | os.O_DIRECT)
    buffer = _buffer(BLOCCO_CASUALE)
    blocchi = DIMENSIONE // BLOCCO_CASUALE
    latenze = []
    inizio = time.monotonic()
    for _ in range(LETTURE_CASUALI):
        os.lseek(fd, random.randrange(blocchi) * BLOCCO_CASUALE, os.SEEK_SET)
        t = time.perf_counter()
        os.readv(fd, [buffer])
        latenze.append((time.perf_counter() - t) * 1000)
    durata = time.monotonic() - inizio
    os.close(fd)
    latenze.sort()
    print(
        f"lettura casuale 4 KiB : {LETTURE_CASUALI / durata:6.0f} letture/s = "
        f"{LETTURE_CASUALI * BLOCCO_CASUALE / durata / 1e6:.2f} MB/s"
    )
    print(
        f"  latenza: mediana {statistics.median(latenze):.2f} ms, "
        f"95° percentile {latenze[int(len(latenze) * 0.95)]:.2f} ms, massima {latenze[-1]:.1f} ms"
    )


if __name__ == "__main__":
    try:
        prepara()
        lettura_sequenziale()
        lettura_casuale()
    finally:
        if os.path.exists(PERCORSO):
            os.remove(PERCORSO)
