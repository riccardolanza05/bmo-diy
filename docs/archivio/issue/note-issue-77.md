# Note — issue #77 (prova ibrida: microfono e altoparlanti del PC, camera e schermo del Pi)

Numeri grezzi e come ripeterli. Le decisioni che spettano a Riccardo stanno in
[`decisioni-issue-77.md`](decisioni-issue-77.md), le cose solo informative in
[`informazioni-issue-77.md`](informazioni-issue-77.md). Tutto del 4/10/2026,
Pi 3 A+ senza HAT audio, display Waveshare 2.4" (ILI9341) e camera OV5647
collegati, portatile `omarchy` sulla stessa rete (`LAMBRATE`).

## Cosa c'è

| Pezzo | Dove | Cosa fa |
|---|---|---|
| `UscitaSpi` + `bmo_face.spi` | `bmo-face` | Pilota l'ILI9341 su SPI0 (DC=GPIO25, RST=GPIO27, BL=GPIO12 da `BMO_SPI_*`); scrive solo il rettangolo cambiato; centra il video e scambia i byte (little → big endian) |
| `CameraGrezzaV4L2` | `bmo-core`, opt-in `BMO_CAMERA=grezza` | Cattura il frame Bayer `pGAA` con `v4l2-ctl`, regola esposizione e guadagno, sviluppa a mezza risoluzione (648×486) e scrive un JPEG |
| `pi/ibrida/avvia_ibrida.sh` | PC | Tunnel SSH inverso, modulo TCP di PulseAudio (solo `127.0.0.1`), `socat`+`parec` per il microfono, copia del codice sul Pi, chiave via stdin, ripulitura e scarico delle misure |
| `pi/ibrida/pi_avvia.sh` | Pi | Faccia sul display, campionatori di RAM, `macchina` (o `--solo-audio`, o `--testo=...`) |
| `pi/ibrida/bin/{arecord,mpv}` | Pi, solo nel `PATH` della prova | `arecord` finto che legge il microfono del PC in S32 stereo 48 kHz (come il HAT); `mpv --ao=pulse` verso il PC |

Il codice che gira sul Pi non cambia di struttura: sono tutte aggiunte, più il
metodo `chiudi()` di `UscitaPannello` e la costante `pillow` in `pyproject.toml`
di `bmo-core`.

## Fattibilità verificata prima di scrivere codice

- **Uscita audio:** `mpv` sul Pi ha l'output `pulse`; con `PULSE_SERVER=tcp:127.0.0.1:4713`
  (tunnel inverso) suona sul PC. Visto sul PC: un `sink-input` «mpv» con `process.host = "clanker"`.
- **Ingresso audio:** sul Pi `arecord` **non ha** un device `pulse` (manca il plugin ALSA,
  per installarlo serve `sudo`), né ci sono `parec`/`pactl`. Soluzione: il PC serve il microfono
  su una porta (`socat` che lancia un `parec` per connessione) e un `arecord` finto sul Pi lo legge.
  Misura: 384.000 byte (1 s a 48 kHz stereo 32 bit) ricevuti in 1,1 s.
- **Import:** il venv di produzione del Pi punta al clone di produzione; per non toccarlo la
  prova gira su una copia in `~/bmo-test/albero` con `PYTHONPATH`, e i moduli di sistema `spidev`,
  `RPi.GPIO`, `lgpio` (che il venv non ha) si espongono con dei link.

## Misure di RAM sul Pi (`bmo_core.misura_ram`, PSS, campionata ogni secondo)

| Prova | PSS totale: picco / media | `bmo-core` picco | `bmo-face` picco | mpv picco | MemAvailable minima |
|---|---|---|---|---|---|
| Avvio, senza voce (macchina con Invio, stdin chiuso) | 96,3 MB / 69,5 MB | 63,1 MB | 27,3 MB | — | 171,6 MB |
| Un turno scritto con la camera («Cosa vedi davanti a te?», 3,9 s) | 123,8 MB / 67,6 MB | 88,2 MB | 30,6 MB | — | 148,5 MB |
| Wake word + 3 turni a voce con TTS, 105 s | **176,1 MB** / 123,3 MB | 143,1 MB | 26,7 MB | 49,0 MB | **109,6 MB** |

Sistema nella corsa lunga: temperatura max 44,5 °C, **nessun throttling**, zram usata max 63,8 MB.
Il criterio della fase 2.3 è < 320 MB di PSS: **ampiamente rispettato** (176 MB). La somma conta solo
i processi della prova: il servizio di produzione `bmo-face.service` (circa 19-20 MB, letto
da `misura_sistema_24h.py`) restava acceso e va aggiunto per avere il totale del Pi (~196 MB).
Il picco di `altro` (38 MB) è un processo di breve durata dentro la prova, non identificato.

## Camera

- Scatto completo in **1,4-1,8 s** (configurazione del sensore, 1-3 catture da 6 frame, sviluppo, JPEG);
  file da ~28 kB a 648×486. Esposizione e guadagno trovati da soli: 1422/169 in una stanza normale.
- Giro scritto con Gemini: `scatta_foto` → foto → `immagine` sul display; risposta in 3,9 s in tutto.

## Schermo

- Il giro `pi/ibrida/prova_schermo.sh` (stati della faccia, bocca che parla, timer, foto della camera)
  gira senza errori con `--uscita spi` a 20 MHz. **Quello che si vede sul display lo può dire solo chi lo
  guarda**: orientamento e ordine dei colori (`BMO_SPI_MADCTL`) vanno confermati a occhio.
- Velocità effettiva (fotogrammi al secondo sul bus) **non misurata**.

## Come ripetere

```bash
# dal worktree demo, o da qualunque worktree con bmo-face/.venv
./avvia_demo.sh --pi                 # prova vera, a voce (equivale a pi/ibrida/avvia_ibrida.sh)
pi/ibrida/avvia_ibrida.sh --solo-audio              # controllo di microfono e altoparlanti (10 s)
pi/ibrida/avvia_ibrida.sh --testo="Cosa vedi davanti a te?"   # un turno scritto con camera e schermo
ssh clanker_home@clanker.local '$HOME/bmo-test/albero/pi/ibrida/prova_schermo.sh'   # solo schermo e camera
```

Le misure vanno in `misure_ram/ibrida/` (CSV, riepilogo e CSV di sistema) e sul Pi in `~/bmo-test/misure/`.
