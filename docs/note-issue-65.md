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

`bmo-carico-calibrazione.service` (2 giri, 32 turni, senza pausa), lanciata
il 29/9/2026 alle 22:45, finita alle 22:53 (8,9 min). Risultati letti sia da
`systemd status` (accounting proprio della cgroup) sia dal CSV di
`pi/misura_sistema_24h.py`, coerenti fra loro:

- **picco memoria del processo (`memory.peak` della cgroup): 234.172 KB ≈
  228,7 MB** — sotto i 320 MB del criterio della fase 2.3, con margine
  (~90 MB). `systemd status` riporta lo stesso numero (228,6M) a fine corsa.
- **32/32 turni riusciti** (nessun errore o risposta vuota); la wake word
  sintetica non è scattata in 16 turni su 32 (attesa: la voce di edge-tts
  non è la stanza vera, `carico.py` parte comunque — non è un problema di
  questa prova, la soglia vera si tara alla fase 4.4 col microfono reale).
- **Temperatura**: 38,6°C → 44,5°C, mai oltre; `throttled` sempre `0x0` (mai,
  né "ora" né "dal boot").
- **zram: usata per davvero**, non solo dichiarata — è salita da 0 a un
  picco di **~59 MB usati su 462 MB di capacità** (~13%) durante il carico,
  poi è scesa di nuovo a prova finita. La combinazione bmo-carico (~228 MB)
  + bmo-face (~17-40 MB) + il resto del sistema (~150-190 MB a riposo)
  satura abbastanza la RAM libera da far intervenire lo zram di serie, ma
  resta ben lontana dal riempirlo: **su questo solo dato, `Mechanism=zram+file`
  di `rpi-swap` non sembra ancora necessario** (decisione condizionata,
  `decisioni-issue-58.md`) — da confermare con la prova di 24 h, che accumula
  molto più a lungo.
- **`journalctl -k | grep -i oom`**: vuoto, zero eventi.

## Prova di 24 h

`bmo-carico.service` (`--giri 24 --pausa-minuti 55`), avviata il 29/9/2026
alle 23:01 (dopo che Riccardo ha spostato fisicamente il Pi e dato il via
libera), finita il 30/9/2026 alle 22:19 — **1397,4 min ≈ 23,3 h reali**
(meno delle 24,2 h stimate: i giri sono durati un po' meno di 5,5 min in
media). CSV completo del campionatore in
[`misure_65_completa.csv`](misure_65_completa.csv) (include anche la
calibrazione, stesso file per `bmo-misura-65.service` che gira in append
per tutta la sessione).

- **384/384 turni completati.** 356 risposte riuscite, 28 con errore
  (7,3%) — **tutti timeout o sovraccarico di Gemini** (7× `503` su
  `gemini-3.1-flash-lite`, 1× errore di lettura su `gemini-3.5-flash-lite`,
  15× timeout di lettura, 5× "tutti sospesi" per il tetto dei tentativi):
  **zero errori di quota (429)**. Il dosaggio prudente scelto (24
  giri/giorno, ≈480 richieste, vedi decisione 1) non ha mai urtato contro
  un limite di quota — resta comunque non confermato il numero vero
  dell'RPD del free tier (vedi sopra e `decisioni-in-sospeso-65.md`).
- **Picco memoria (`memory.peak` della cgroup, accounting di systemd a fine
  corsa): 238,8 MB** — sotto i 320 MB del criterio della fase 2.3, margine
  ~81 MB. Poco sopra il picco della sola calibrazione (228,7 MB): coerente,
  24 giri hanno più probabilità di un giro isolato di trovare il worst case
  per un singolo componente (es. Gemini che accumula più contesto).
- **Zero eventi OOM** per tutta la corsa: sia `journalctl -k --since
  "2026-09-29 23:01:00" | grep -i oom` (vuoto) sia `memory.events` della
  cgroup (`oom 0`, `oom_kill 0`) a fine corsa.
- **Temperatura**: mai sopra **48,3°C** (plateau raggiunto presto e stabile
  per il resto della corsa); `throttled` sempre `0x0`, mai né "ora" né "dal
  boot" — enorme margine rispetto alla soglia di throttling del Pi (~80°C)
  e coerente con lo stress test sintetico del 29/9 (4 core al 100%: fino a
  53,7°C in 50 s).
- **zram: picco ~93 MB usati su 462 MB di capacità (~20%)**, cresciuta
  gradualmente nelle prime ore poi stabile, mai vicina a saturarsi.
  **Conclusione: `Mechanism=zram+file` di `rpi-swap` non è necessario** con
  il carico attuale — la zram di serie (senza configurazione custom) basta
  da sola. Da rivedere se in futuro si aggiunge altro (es. STT/TTS locale,
  #13) che alzi stabilmente l'uso di memoria.
- **#13 (whisper.cpp/Piper) non misurato**: fuori dallo scopo di questa
  sessione, resta una decisione aperta se farlo dentro questa PR o
  separatamente (`decisioni-in-sospeso-65.md`).

**Nota su un'interferenza esterna, verificata innocua**: un'altra sessione
ha lanciato sul Pi un breve test (decode ffmpeg/mpv di un video, ~1 min di
CPU al 100% su 2 core) alle 22:22 del 30/9 — **3 minuti dopo** che
`bmo-carico.service` era già terminato pulito (22:19:23, confermato dal
timestamp di creazione dei suoi file temporanei rispetto al log di
systemd). Nessun effetto sui numeri sopra.
