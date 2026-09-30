# Decisioni in sospeso — video di YouTube sul Pi

Numeri e prove in [`note-video-youtube.md`](note-video-youtube.md). Qui solo
ciò che aspetta te. Ogni voce dice cosa è implementato di default e cosa
cambia scegliendo altro.

## 1. Dove si risolve l'indirizzo del video (il punto decisivo)

`yt-dlp` è l'unico modo gratuito e senza chiave. Sul Pi non ci sta (la
risoluzione ha toccato 341 MB di picco sul laptop, per il runtime JavaScript
che YouTube ormai richiede; la ricerca da sola ne vuole ~56).

| Opzione | Costo / vincolo | Conseguenza |
|---|---|---|
| **A. Sul laptop / un server di casa** (default nel codice: `video.py` accetta qualunque callable `esegui`) | il laptop deve essere acceso e raggiungibile (es. via Tailscale) quando chiedi un video | Provato: il Pi ha aperto e decodificato gli indirizzi risolti dal laptop (stesso IP pubblico). Zero RAM extra sul Pi. BMO senza laptop acceso = "non posso" per i video, non per il resto |
| **B. Istanze Piped/Invidious pubbliche** | gratuite, senza JS, ma instabili e spesso bloccate da YouTube | Nessuna macchina in più; affidabilità peggiore di A, cambia tutto quando un'istanza muore. Non provata |
| **C. yt-dlp sul Pi** | 341 MB > RAM libera | Escluso dai numeri |
| **D. YouTube Data API ufficiale** | chiave Google; la ricerca costa 100 unità su 10 000 al giorno (~100 ricerche/giorno) | Copre solo la *ricerca*: i suoi termini vietano di estrarre lo stream, quindi non dà nulla da riprodurre. Utile al massimo insieme ad A |

Raccomandazione: **A**, con la risoluzione dietro un piccolo servizio (o uno
script lanciato via SSH) che restituisce gli indirizzi; B solo come ripiego.

## 2. Blocco anti-bot di YouTube

Dopo ~10 richieste in pochi minuti dal mio IP, YouTube ha cominciato a
rifiutare anche video diversi («Sign in to confirm you're not a bot»), e
dopo una decina di minuti era ancora così. Il modo noto di aggirarlo è dare a
yt-dlp i cookie di un account Google (`--cookies-from-browser`).

- **Default implementato: nessun cookie.** Non l'ho usato: lega la funzione al
  tuo account, e un workaround che viola i termini di YouTube non va
  documentato in un repo pubblico.
- Se non usi i cookie: le richieste vanno diluite (una ricerca + una
  risoluzione per video, con cache degli indirizzi ~qualche minuto) e BMO deve
  saper dire "YouTube non mi risponde" come già fa per Gemini (7,3% di errori
  nel 24 h, tutti 503/timeout).
- Se vuoi i cookie: è una scelta tua e privata (file fuori dal repo); io non
  la documenterei nel repo.

## 3. Risoluzione e formato

Default: 320×240 a 15 fps (4:3, bande nere sui video 16:9), 240p h264 + aac.

- 15 → 24/25 fps: più fluido, ~+60% di CPU e di bus SPI (al Pi resterebbe
  margine: 29% di un core a 15 fps), ma i fotogrammi pieni a 25 fps riempiono
  ~70% del bus e il blit di bmo-face andrebbe ottimizzato.
- 360p sorgente: più nitido dopo il ridimensionamento, ~2× la CPU di decode.

## 4. Cosa resta da costruire (se dici di procedere)

Protocollo di bmo-face per i fotogrammi raw, strumento Gemini
`riproduci_video` con ricerca → conferma del titolo → riproduzione, pausa e
stop, e la misura con bmo-core acceso contemporaneamente (non fatta: era
fermo). Da fare quando arrivano schermo e HAT audio per vedere sul serio.
