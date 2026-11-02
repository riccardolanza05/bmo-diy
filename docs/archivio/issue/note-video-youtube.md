# Note — video di YouTube sul Pi (1/10/2026)

Numeri grezzi, cosa è stato provato e come ripeterlo. Le scelte aperte stanno in
[`decisioni-video-youtube.md`](decisioni-video-youtube.md); quello che va solo saputo in
[`informazioni-video-youtube.md`](informazioni-video-youtube.md).

## Com'è fatto

```
"metti Bohemian Rhapsody"
   │  Gemini: riproduci_video(query="queen bohemian rhapsody video ufficiale")      (prompt validato, vedi sotto)
   ▼
VideoYouTube.riproduci  ── ricerca diretta a YouTube (stdlib, ~0,6 s) ──────────────┐  in parallelo:
   │                        risolvi_youtube --serve parte subito e importa yt-dlp ──┘  il risolutore si carica
   ├─ risponde allo strumento (~0,7 s): {"stato":"ok","titolo":...,"nota":"sta partendo"}
   │     → BMO dice la sua frase (Gemini 2° giro + voce)
   └─ in background: risoluzione (~2,5-3,5 s) → ffmpeg (~1,3 s) → 1° fotogramma
         ffmpeg ─ video rgb565 LxA ─> SinkFotogrammi ─ datagram Unix ─> bmo-face (RiceviFotogrammi → pannello → uscita)
               └ audio ─> ALSA ("alsa:default", o BMO_VIDEO_AUDIO)
```

- `bmo-core/src/bmo_core/video.py`: ricerca, risoluzione, ffmpeg, `Riproduzione`, `SinkFotogrammi`,
  `RisolutorePronto`, `VideoYouTube` (lo strumento `riproduci_video` e i suoi controlli).
- `bmo-core/src/bmo_core/risolvi_youtube.py`: yt-dlp caricando **solo** l'estrattore di YouTube.
- `bmo-face/src/bmo_face/video.py` + `pannello.py` + `protocollo.py`: comando `video`
  (start/pause/resume/stop), ricevitore dei fotogrammi, il video prende il posto della faccia
  e la faccia torna da sola alla fine, allo `stop` o se i fotogrammi tacciono per 5 s.
- `Radio` ha `video=`: un solo media alla volta, `controllo_riproduzione` vale per quello che va,
  `sospesa()` mette in pausa anche il video mentre BMO ascolta, lo STATO lo descrive.
- Prompt di sistema e dichiarazioni degli strumenti: radio solo per radio/stazioni/generi, YouTube
  per brani, artisti e video precisi (sezione sotto).
- Nessun cookie, nessun JavaScript, nessuna chiave, nessun computer acceso: tutto sul Pi.

## Risolvere l'indirizzo: cosa ha funzionato e cosa no (tutto provato sul Pi 3 A+)

La prova che conta è **ffmpeg che decodifica davvero** dall'indirizzo, non "yt-dlp ha stampato un URL":
un primo giro contava gli URL restituiti e dava un falso 9 su 9.

| Via | Tempo / RAM | Esito |
|---|---|---|
| **yt-dlp, client predefinito (`visionos`), solo estrattore YouTube, `skip=hls`** | **2,4-4,1 s, 46 MB** | **4 su 5 video riproducibili**; il quinto (audio `140-17`) resta appeso senza dati: si passa al risultato successivo |
| yt-dlp `python -m yt_dlp` (tutti gli estrattori) | 4,5-5,1 s, 46 MB | stessi video; ~1,3 s sono l'import di ~1800 estrattori |
| client `android_vr`, `tv_embedded` (senza JS) | ~4 s | **403 a ffmpeg** per quasi tutti: gli indirizzi si ottengono ma non si aprono |
| client `web` con Node 22 (JS) | 20 s (8 s con cache del player), 180-290 MB | funziona ma troppo lento e pesante; per alcuni video il client web non dà indirizzi (manca il PO token) |
| client `web` con QuickJS | 57-65 s, 272-292 MB | scartato |
| istanze pubbliche Piped / Invidious | 0,5-3 s | **0 su 10** riproducibili (403 o stream vuoto); funzionano solo per pochissimi video celebri |
| saltare la pagina web (`player_skip=webpage`) | -0,8 s | YouTube risponde «Sign in to confirm you're not a bot» |
| ricerca via yt-dlp | 3,6 s | sostituita dalla richiesta diretta (0,6 s), resta come ripiego |

## Latenza (prova completa `pi/prova_video_e2e.py` sul Pi, audio nullo, display sostituito da `UscitaNulla`)

Risoluzione e ricerca avvengono **una volta sola per video**; ffmpeg ha una partenza fissa di ~1,0-1,5 s
(due connessioni TLS, una per il video e una per l'audio: le opzioni di probing non cambiano nulla,
provato 5 varianti, sempre 1,0 s).

| Configurazione | Dalla richiesta al 1° fotogramma |
|---|---|
| tutto in fila, risolutore avviato dopo la ricerca | 5,7-5,9 s (ricerca 0,6 + risoluzione 3,8-4,1 + ffmpeg 1,2-1,3) |
| + risolutore pre-avviato durante la ricerca | **4,8-5,3 s** (risoluzione 2,4-3,1) |
| + avvio in background (quello di produzione) | lo strumento risponde dopo **~0,7 s**; il video parte a ~4,5-5 s dalla richiesta, *mentre BMO sta ancora dicendo la sua frase* |

Il numero che si sente è quindi quello dopo la voce, non i ~5 s del video: vedi i risultati
dell'ultima corsa più sotto.

## Formato: fluidità e nitidezza (matrice sul Pi, 360p 30 fps → 320×180, 15 s per cella)

| fps | bicubic | fast_bilinear | lanczos |
|---|---|---|---|
| 15 | 41% | 42% | 52% |
| 20 | 48% | 38% | 46% |
| 25 | 52% | 40% | 52% |
| 30 | **57%** | 43% | **58%** |

(CPU di ffmpeg in % di **un** core su quattro; RAM 71-72 MB PSS in tutte le celle; temperatura 44-46 °C,
mai throttling.) Consegnati 15,5 / 20,6 / 25,7 / 30,9 fotogrammi al secondo: seguono l'obiettivo.

- La CPU e la RAM reggono anche i 30 fps. Il limite vero è **il bus SPI**: un fotogramma pieno
  320×240 costa ~28 ms (~5,5 MB/s, dalle note dell'hardware, *non misurato: manca il display*).
  Con un budget del 73% (4 MB/s): un 16:9 a 320×180 regge **30 fps** (63% del bus), un 4:3 a
  320×240 ne regge **26**. `video.fps_di_riproduzione` segue questa regola: fino al limite si
  tiene il frame rate del video; sopra si dimezza se torna fluido (60 → 30).
- Il ridimensionamento è **lanczos**: stesso costo del bicubic a 30 fps e più nitido nello
  scendere da 640×360 a 320×180. A occhio, su uno schermo di 2,4", le quattro varianti non si
  distinguono (confronto su un fotogramma vero: `nitidezza` non riportato qui, era una prova a vista).
- Il video è ridimensionato **alla sua vera proporzione** e bmo-face ridisegna solo quel rettangolo:
  un 16:9 manda 115 kB a fotogramma invece di 154 kB (le bande restano spente).
- Sorgente: sempre 360p h264 (formato 134 + audio 140, oppure 18). Il 240p non serve: l'estrazione
  costa uguale e il 360p ridotto a 320×180 è più nitido. Oltre i 360p non c'è guadagno: lo schermo è largo 320.

## RAM (misurata nelle condizioni del servizio: `pi/ram_video.py`, `pi/ffmpeg_ram.py`)

Il primo conto sommava i PSS (72 + 48 + 106 + 48 ≈ 270 MB contro `MemoryMax=280M`) ed era **troppo
pessimista**: il PSS conta anche le librerie condivise (file, che il kernel libera prima di uccidere
qualcuno), e ffmpeg è fatto per metà di librerie (72 MB PSS = 37 anonimi + 35 di file). Quello che conta per il
tetto è la memoria **anonima** e l'assenza di *thrash*. Misura vera, sul Pi 3 A+, in una cgroup con tetto 294 MB
(= `MemoryMax=280M` del servizio, 280 MiB), con un processo che carica come bmo-core (numpy + onnxruntime,
google.genai, macchina, i 3 modelli della wake word, Gemini, radio e video registrati, ascolto continuo) e un
**turno reale**: Gemini riceve «metti queen bohemian rhapsody video ufficiale», chiama `riproduci_video` davvero
(ricerca, risolutore pre-avviato, ffmpeg) e la risposta è letta da `VoceTts` (edge-tts + mpv):

| Fase | Picco con cache | Picco anonimo | Chi |
|---|---|---|---|
| avvio (caricamento: transitorio) | 172 MB | 151 MB | |
| **riposo** (bmo-core carico che ascolta) | 96 MB | 74 MB | python 70 |
| **turno** (Gemini + voce + risolutore + partenza ffmpeg) | **201 MB** | **136 MB** | python 111 (bmo-core 70 + risolutore ~41), mpv 9, ffmpeg 9 |
| **video** che suona | 176 MB | 104 MB | python 63, ffmpeg 37 |

- **Tetto 294 MB, picco 201 MB: margine ~93 MB (32%)**, eventi `high`/`max`/`oom_kill` = 0; `workingset_refault_file`
  +290 pagine (~1 MB) e `pgmajfault` +1222 in tutta la prova: sono i caricamenti delle librerie la prima volta,
  non un kernel che butta fuori librerie in uso. *Il criterio non è «niente OOM»: è niente thrash.*
- Il video costa quindi **+105 MB con cache / +62 MB anonimi** sul riposo, e il momento peggiore è il turno
  in cui il risolutore (~41 MB, ~3 s) si sovrappone alla voce e alla partenza di ffmpeg; il risolutore si chiude
  da solo prima che ffmpeg parta del tutto.
- **Ottimizzazione fatta: ffmpeg a un thread** (`-threads 1 -filter_threads 1 -filter_complex_threads 1`):
  RAM anonima di ffmpeg **36,7 → 27,6 MB**, CPU **55% → 42%** di un core, stessi fps (23,5 contro 23,9 con
  l'avvio). Il probing (`-probesize`) non cambia niente. Con la nuova opzione ffmpeg pesa 62 MB PSS invece di 72.
- **Rust non serve**: il costo è nelle librerie libav (già C) e nell'interprete Python di yt-dlp; un risolutore in
  Rust sarebbe lo stesso lavoro di richieste a YouTube che farebbe una versione in Python con la sola stdlib, più
  un toolchain di cross-compilazione, per risparmiare ~10 MB di interprete. Un risolutore leggero in Python
  (senza importare yt-dlp: -41 MB transitori e ~-1,3 s di latenza) si può fare, ma va mantenuto dietro a
  YouTube: non l'ho fatto perché la RAM ci sta e yt-dlp resta il ripiego automatico comunque.
- **Cosa la prova non copre**: il microfono e il VAD (arecord, ~poca RAM), la sveglia, i buffer di un turno
  più lungo, e la base reale del servizio (il 238,8 MB del 24 h è un `memory.peak` dalla nascita del servizio:
  contiene il picco di avvio, quindi non è una base di riposo). Per questo la decisione 5 chiede di guardare
  il picco vero dopo il deploy. `MemorySwapMax` non era impostato (come nel servizio): la zram assorbe i picchi.

## Pausa e ripresa

`SIGSTOP`/`SIGCONT` non vanno: con `-re` ffmpeg «recupera» il tempo perso e dopo la ripresa i
fotogrammi arrivavano a raffica (85 in 1,5 s invece di 37) con l'audio fuori passo. Ora la pausa
**ferma ffmpeg** e ricorda la posizione (fotogrammi ÷ fps); la ripresa lo rilancia con `-ss`:
primo fotogramma dopo 1,1-1,7 s, poi ritmo normale (verificato sul Pi con URL reali).
ffmpeg bloccato in una lettura di rete ignora SIGTERM: si passa a SIGKILL dopo 0,5 s.

## Prompt di sistema: radio o video (validato contro Gemini, `prova_frasi`)

Regola scelta (le tue): radio **solo** se chiedi la radio, una stazione o una frequenza; un brano, un
artista o un video preciso → si cerca su YouTube e si usa il videoclip (la query include «video
ufficiale»). Un genere o un umore senza brano né artista («un po' di jazz», «musica rock») resta radio.

- `riproduci_musica` riscritta come **solo radio** (dichiara esplicitamente «mai per un brano o un video»);
  `riproduci_video(query)` nuova; `controllo_riproduzione` e `regola_volume` descrivono anche il video
  (col video il volume è il canale «sistema»: ffmpeg non ha un canale suo).
- Categoria nuova **`video`** in `prova_frasi` (22 frasi, a parte come «inglese»: il banco storico resta
  di 48 frasi, due sole modificate perché ora vanno a YouTube). Include radio contro video, artista senza
  brano, generi, lo STATO con un video o la radio in corso (pausa, stop, successivo, volume, cambio di media).
  - **video 21/21 (100%)**, **musica 11/11 (100%)** alla prima corsa, senza toccare il prompt dopo la stesura.
  - Le risposte «Non posso farlo» che si leggono nell'output sono normali: in `prova_frasi` gli strumenti
    non sono collegati e rispondono `non_disponibile`; si valutano solo le chiamate.
- `python -m bmo_core.prova_frasi --categoria video` (ripetibile; attenzione alla quota di Gemini: a metà
  della prima corsa è comparso «quota esaurita su tutti i modelli» e ha ripreso da solo dopo 30 s).

## Anteprima sul portatile (prima del deploy)

`python -m bmo_core.anteprima_video "<ricerca>"` mostra in una finestra come lo vedrebbe lo schermo: stessa
catena di produzione (ricerca, risoluzione, ffmpeg con **la stessa risoluzione e gli stessi fps che sceglierebbe
sul Pi**), composta sul canvas 320×240 con le bande nere, ingrandita a pixel netti (`--scala 3` = 960×720),
audio dal PC. `--file clip.mp4` per un file, `--png f.png --png-dopo 20` per un fotogramma senza finestra.
Non simula la dimensione fisica del 2,4", la retroilluminazione né il bus SPI. Verificato: PNG su un video
vero (video 320×180 a 25 fps centrato su 320×240, con il banding dell'rgb565) e finestra mpv che gira senza errori.

## Audio: voce e video insieme (software, nessun costo)

- **In produzione PipeWire non gira** (nessuna sessione utente, `irrobustisci.sh` lo ha tolto: -35-50 MB; sul Pi
  lo vedevo acceso solo per via del mio SSH, `Linger=no`) e l'audio va in ALSA diretto. Non c'è `/etc/asound.conf`
  (mai distribuito: `docs/note-issue-64.md`).
- La WM8960 ha **un solo sottodispositivo** di riproduzione: voce (mpv) e video (ffmpeg) non possono aprirla
  insieme. La soluzione software già nel piano (§2.10) è **ALSA `dmix`**, il mixer in libasound: nessun demone,
  RAM trascurabile. `pi/asound.conf.modello` + `pi/installa-audio.sh` (con `sudo`, lanciato anche da `deploy.sh`)
  lo installano **solo quando c'è la WM8960**; senza l'HAT non fa nulla (sul jack analogico voce e video suonano
  insieme già oggi e il driver `bcm2835` non supporta nemmeno `dmix`: provato, «unable to open slave»).
- Il modello aggiunge `video_out` = `plug` → **volume software «Video»** (`softvol`) → `dmix`. Verificato sul Pi
  (scheda analogica) la parte del volume: il controllo `Video` compare in `amixer` e passa da 100% (0 dB) a
  30% (−28 dB) al volo. **Non verificato**: `dmix` con due flussi veri, impossibile finché non c'è l'HAT.
- Lato codice: `video.uscita_audio_predefinita()` sceglie `alsa:video_out` se l'ALSA di sistema lo definisce,
  altrimenti `alsa:default` (come oggi); `BMO_VIDEO_AUDIO` vince su tutto. **Mentre BMO parla il video si abbassa
  al 30%** (`VideoYouTube.abbassato()`, agganciato alla voce con `Macchina(abbassa_durante_voce=...)`) e poi torna
  al 100%; senza il controllo «Video» è un no-op. Resta la pausa del video mentre BMO ascolta (già c'era).

## Se il video non parte

Se nessuno dei primi tre risultati parte, BMO **lo dice a voce**: suono di errore, faccia triste e
«Non riesco a far partire il video: YouTube non mi risponde» (`Macchina.annuncia`). Una sola voce alla volta:
l'avviso aspetta che finisca la risposta in corso (lock sulla voce, testato).

## Come ripetere

```
# Pi (venv di produzione, con yt-dlp installato: `pip install -e ./bmo-core` lo porta)
~/bmo-pi/venv/bin/python pi/prova_video_e2e.py "queen bohemian rhapsody video ufficiale" 20   # catena completa
SINCRONO=1 ... (come sopra)                                                                     # senza avvio in background
systemd-run --user --scope -p MemoryMax=400M ~/bmo-pi/venv/bin/python pi/prova_video_e2e.py ...  # + memory.peak della cgroup
~/bmo-pi/venv/bin/python pi/peso_video_pi.py matrice "funny cats compilation" 15                # fps × scaler
~/bmo-pi/venv/bin/python pi/avvio_ffmpeg_pi.py "<ricerca>"                                      # opzioni di probing
~/bmo-pi/venv/bin/python pi/ffmpeg_ram.py "<ricerca>"                                           # RAM anonima di ffmpeg, per variante
systemd-run --user --scope -p MemoryMax=280M ~/bmo-pi/venv/bin/python pi/ram_video.py <repo> "<ricerca>" [--turno-reale]  # RAM nelle condizioni del servizio
# laptop: l'anteprima di come lo vedrebbe lo schermo
python -m bmo_core.anteprima_video "queen bohemian rhapsody video ufficiale"
# laptop
cd bmo-core && pytest tests/test_video.py tests/test_video_strumento.py     # senza rete (un test decodifica con ffmpeg)
```
