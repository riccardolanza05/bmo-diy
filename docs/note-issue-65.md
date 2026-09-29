# Note — issue #65 (24 h sul Pi)

Numeri grezzi e come ripeterli. L'analisi e le decisioni stanno in
[`decisioni-issue-65.md`](decisioni-issue-65.md).

## Stato del Pi prima della prova (29/9/2026, verificato dal vivo via SSH)

- `~/bmo-pi/bmo-diy` era fermo a `0c426bb` (il merge della #67, *prima*
  della #68): niente adapter audio ALSA corretto (`PCM` invece di
  `Master`), niente conversione S32→S16 del microfono — aggiornato a
  `master` prima di installare le nuove unit (vedi sotto).
- `systemctl is-enabled bmo-core bmo-face`: `disabled` / `enabled` — coerente
  con la nota del 29/9 mattina, non con quella del 28/9 sera ("enabled ma
  fermato"): `bmo-core.service` è stato disabilitato nel frattempo.
- Kernel `6.18.50+rpt-rpi-v8` (≥ 6.12: `memory.peak` delle cgroup è
  scrivibile/azzerabile, anche se questa issue non ne ha avuto bisogno,
  vedi decisione 2).
- **zram già attivo di suo** (immagine Raspberry Pi OS trixie di serie,
  nessuna configurazione custom): `/dev/zram0`, ~462 MB (= la RAM totale),
  priorità 100, 0 usato a riposo. Nessun `/etc/rpi/swap.conf.d/`: il
  `Mechanism=zram+file` di `rpi-swap` deciso il 28/9
  (`decisioni-issue-58.md`) **non è ancora stato attivato** — resta
  condizionato a quello che mostra questa prova.
- `free -h`: 462 Mi totali, 155 Mi usati, 306 Mi disponibili a riposo (solo
  `bmo-face.service` attivo, `bmo-core.service` disabilitato: coerente con
  le ~20-40 MB di bmo-face viste il 28/9).
- Nessun dispositivo di cattura audio (`arecord -l` vuoto): l'HAT WM8960 non
  è ancora arrivato (confermato da Riccardo il 29/9), quindi questa prova usa
  `bmo_core.carico` (microfono finto) come da issue, non un giro con
  microfono vero.
- `vcgencmd measure_temp`/`get_throttled` funzionano senza sudo per
  l'utente `clanker_home` (gruppo `video`); idem la lettura dei file
  `memory.current`/`memory.peak`/`memory.events` delle cgroup in
  `/sys/fs/cgroup/system.slice/`: `pi/misura_sistema_24h.py` non ha bisogno
  di privilegi.

## RPD del free tier di Gemini: non trovato un numero pubblico affidabile

Cercato il 29/9/2026 (web search + `ai.google.dev/gemini-api/docs/rate-limits`):
la pagina ufficiale rimanda al pannello personale di AI Studio
(`aistudio.google.com/rate-limit`, richiede login, non raggiungibile da
questa sessione) per i numeri esatti per modello. Fonti di terze parti
discordanti (500-1000 RPD, riferite però a `gemini-2.5-flash-lite`, non alla
versione usata da BMO). **Dosaggio scelto per prudenza** (24 giri/giorno,
≈480 richieste), non per una cifra confermata — vedi decisione 1. Se
Riccardo ha accesso al pannello AI Studio, vale la pena controllare il
numero vero e aggiustare `--pausa-minuti` di conseguenza.

## Calibrazione breve (picchi durante un turno)

*Da riempire dopo `bmo-carico-calibrazione.service`.*

## Prova di 24 h

*Da riempire a fine corsa (avviata il 29/9/2026, vedi la nota di ripresa in
Basic Memory per come leggere i risultati se la sessione che l'ha avviata è
già finita).*
