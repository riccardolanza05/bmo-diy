# Decisioni in sospeso — video di YouTube sul Pi

Numeri e prove in [`note-video-youtube.md`](note-video-youtube.md). Qui solo ciò che aspetta ancora te: per
ogni voce le opzioni, cosa è implementato di default e cosa cambia scegliendo altro.

**Già deciso (1/10/2026):** artista senza brano («fammi sentire i Queen») → YouTube (validato col prompt:
21/21); se un video non parte BMO lo dice a voce (implementato); aggiornamento di yt-dlp a ogni deploy
(implementato in `pi/deploy.sh`); audio e voce insieme con soluzione software (vedi 2).

## 1. `MemoryMax` di bmo-core: restare a 280M o salire a 320M?

Misurato nelle condizioni del servizio (turno reale con Gemini, voce edge-tts e video): picco **201 MB con
cache / 136 MB anonimi su un tetto di 294 MB**, nessun `high`/`max`/OOM e nessun thrash (refault +290 pagine).
Il risolutore (~41 MB, 3 s) e la partenza di ffmpeg (-9 MB grazie a un solo thread) sono il momento peggiore.
La prova non include microfono/VAD, la sveglia e un turno lungo, e non conosce la base reale del servizio.

- **Default: lascio 280M.** Dopo il deploy: `systemctl status bmo-core` (riga `Memory:` e `peak:`) dopo qualche
  richiesta di video mentre BMO parla.
- **Se preferisci essere sicuro subito: 320M** (il criterio della Fase 2.3). Costo: il kernel ha ~290 MB liberi
  a riposo con bmo-face acceso e la zram assorbe i picchi (il 24 h ne ha usati ~93 MB su 462), quindi alzare il
  tetto non peggiora niente di misurato; toglie solo la possibilità che un picco raro uccida bmo-core. Si cambia
  in `pi/systemd/bmo-core.service` e il prossimo `deploy.sh` lo installa.

## 2. Audio della WM8960: confermare `dmix` quando arriva l'HAT

Implementato e pronto, **non verificabile senza l'HAT** (il jack analogico del Pi non supporta `dmix`): modello
`pi/asound.conf.modello` (dmix + volume software «Video»), installato da `pi/installa-audio.sh` solo se
`aplay -l` mostra `wm8960soundcard`. Mentre BMO parla il video scende al 30% e poi torna al 100%.

- Alla prima prova con l'HAT: `pi/installa-audio.sh` esegue da sé un test (due flussi insieme per 2 s) e, se
  fallisce, dice come ripristinare il file precedente (`/etc/asound.conf.bak-bmo`). I parametri dello slave
  (`rate`, `period_size`, `buffer_size`) vanno confermati con la scheda vera.
- Alternativa scartata: **PipeWire** (mixer software con volume per flusso già pronto) costerebbe 35-50 MB che
  `irrobustisci.sh` ha deliberatamente tolto, richiede una sessione utente (`linger`) e variabili d'ambiente in
  tutte e due le unit, e tenere ALSA diretto per il microfono insieme a PipeWire per l'uscita dà «device busy» con
  una scheda a un solo sottodispositivo. Se la preferisci: dimmelo, è un cambiamento in `deploy.sh` e nelle unit.

## 3. Se all'avvio il video fallisce, la frase a voce non basta?

Ora BMO dice «Non riesco a far partire il video: YouTube non mi risponde» dopo il suono di errore e con la faccia
triste, **solo se nessuno dei primi tre risultati parte** (fino a ~36 s dopo la richiesta: ogni tentativo ha un
tetto di 12 s). Se preferisci un tetto più corto (es. 2 tentativi, ~25 s) cambia `tentativi` in `video.py`;
costo: più falsi errori quando YouTube è lento.

## 4. Fluidità contro bus SPI (da confermare col display vero)

Default: il frame rate del video fino a **30 fps per un 16:9** (320×180, 115 kB a fotogramma), **26 per un 4:3**
(320×240); oltre si dimezza se torna fluido. CPU e RAM del Pi reggono i 30 fps (con ffmpeg a un thread: 42-44% di
un core), ma il bus SPI è una stima dalle note dell'hardware (~5,5 MB/s), **non una misura**.

- Se all'arrivo il bus regge meno: `BUS_SPI_BYTE_AL_SECONDO` in `video.py` (2 MB/s → 17 fps per un 16:9). Se regge
  di più: alzarlo (e `FPS_MAX`).
- Il ridimensionamento è `lanczos` (stesso costo del bicubic, più nitido); `FLAG_SCALA` in `video.py`.

## 5. Un risolutore più leggero e veloce (opzionale)

Il risolutore usa yt-dlp (import ~1,3 s, ~41 MB transitori, ~3 s in tutto). Una versione leggera in Python (la
richiesta del client `visionos` con la sola stdlib, come fa yt-dlp) scenderebbe a ~1 s e ~10 MB, e porterebbe il
primo fotogramma da ~5 s a ~3 s. **Rust non cambierebbe nulla** (il costo è in libav e nell'import di yt-dlp).
Non l'ho fatto: la RAM ci sta e va mantenuto dietro a YouTube (yt-dlp resterebbe il ripiego). Se i ~5 s ti
pesano, è il passo da fare; costo: una dipendenza fragile in più da riparare quando YouTube cambia.

## 6. Aggiornamenti di yt-dlp fra un deploy e l'altro

`deploy.sh` ora aggiorna yt-dlp a ogni deploy. Se YouTube rompe la versione vecchia fra due deploy, «il video non
parte» finché non ne lanci uno. Alternativa: un timer di systemd settimanale (`pip install -U yt-dlp` + riavvio di
bmo-core): più robusto, ma cambia di nascosto qualcosa su un dispositivo che altri usano (la ragione per cui la
#16 ha scelto il deploy a mano). Default: solo a deploy.

## 7. Non costruito (aspetta l'hardware o un tuo via libera)

`UscitaSpi` (il disegno sul display vero: `inizio_video`/`disegna_video`/`fine_video` sono pronti, centrato sul
rettangolo), l'audio dalla scheda vera, il deploy sul Pi (serve `sudo`: lo facciamo insieme).
