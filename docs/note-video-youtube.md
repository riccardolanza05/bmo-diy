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

## RAM

- ffmpeg (video 320×180 + audio): **72 MB PSS** costanti, qualunque fps.
- Risolutore (yt-dlp con solo l'estrattore YouTube): **~46-48 MB**, vive ~3 s e **si chiude da solo
  subito dopo la prima risoluzione riuscita**, quindi non si sovrappone a ffmpeg.
- `bmo-core.service` ha `MemoryMax=280M`; il caso peggiore del 24 h (#65) è 238,8 MB con mpv radio
  (~47 MB). Il video sostituisce la radio e pesa ~25 MB in più di mpv: stima ~265 MB nel momento
  peggiore (BMO sta parlando con mpv ~48 MB *e* parte ffmpeg). **Vicino al limite.** Vedi le
  misure della cgroup nell'ultima corsa e la decisione 5.

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

## Come ripetere

```
# Pi (venv di produzione, con yt-dlp installato: `pip install -e ./bmo-core` lo porta)
~/bmo-pi/venv/bin/python pi/prova_video_e2e.py "queen bohemian rhapsody video ufficiale" 20   # catena completa
SINCRONO=1 ... (come sopra)                                                                     # senza avvio in background
systemd-run --user --scope -p MemoryMax=400M ~/bmo-pi/venv/bin/python pi/prova_video_e2e.py ...  # + memory.peak della cgroup
~/bmo-pi/venv/bin/python pi/peso_video_pi.py matrice "funny cats compilation" 15                # fps × scaler
~/bmo-pi/venv/bin/python pi/avvio_ffmpeg_pi.py "<ricerca>"                                      # opzioni di probing
# laptop
cd bmo-core && pytest tests/test_video.py tests/test_video_strumento.py     # senza rete (un test decodifica con ffmpeg)
```
