# Note — video di YouTube sul Pi (fattibilità, 30/9/2026)

Numeri grezzi e come ripeterli. Le scelte aperte stanno in
[`decisioni-video-youtube.md`](decisioni-video-youtube.md).

## Cosa c'è

- `bmo-core/src/bmo_core/video.py`: ricerca (`cerca_video`), risoluzione
  degli indirizzi (`risolvi_flussi`) e riproduzione (`riproduci`). Un solo
  ffmpeg con due uscite a ritmo reale (`-re`): video rgb565 320×240 a 15 fps
  su stdout (il blit verso lo schermo) e audio sull'uscita scelta.
  `yt-dlp` gira sempre in un processo figlio che muore subito.
- `bmo-core/tests/test_video.py`: 7 test, senza rete (un test decodifica una
  clip locale vera con ffmpeg).
- `pi/peso_mpv.py` esteso: con un terzo argomento (`"nyan cat" [secondi]`)
  misura anche yt-dlp + ffmpeg su un video vero.
- **Non fatto**: il collegamento a bmo-face (nuovo messaggio del protocollo
  per i fotogrammi raw), lo strumento Gemini `riproduci_video`, i controlli
  (pausa/stop). Nessun hardware (schermo, HAT audio) è ancora arrivato.

## Formati di YouTube (provato su un video vero)

Senza chiave, `yt-dlp -F` espone per ogni video: `133` 240p h264 (~82 kbit/s),
`134` 360p, `140` audio m4a (130 kbit/s), e il `18`, 360p h264 + aac già
muxato. Il selettore in `video.FORMATO` prende 240p h264 + audio aac, altrimenti
il 18. **Solo h264**: VP9/AV1 il Pi 3 A+ non li decodifica con fatica sopportabile.

## Misure (clip: "Nyan Cat! [Official]", 30 fps, 240p, 40 s di decode, audio `null`)

| Dove | PSS ffmpeg | CPU | fps consegnati |
|---|---|---|---|
| **Pi 3 A+** (`clanker`, bmo-face attivo, bmo-core fermo) | **68,4 MB** | 11,4 s su 40 s = **29% di un core** (su 4) | **15,1** (primo fotogramma dopo 1,45 s) |
| laptop | 72,0 MB | 3,4 s su 30 s | 12,5 (la media include l'avvio di rete) |

- Pi durante la prova: 41,9 °C, `throttled=0x0`, RAM disponibile 276 MB
  (prima 277 MB: bmo-face + sistema, come a riposo).
- Gli indirizzi sono stati risolti **sul laptop** e passati al Pi, che li ha
  aperti senza problemi: sono legati all'IP pubblico di chi li risolve, e
  laptop e Pi escono dallo stesso.
- Budget: il caso peggiore del 24 h (#65) è 238,8 MB di picco di cgroup con
  mpv radio (~47 MB). Il video sostituisce la radio: ffmpeg pesa ~20 MB in più
  di mpv → ~260 MB, sotto i 320 MB del criterio 2.3, margine ~60 MB.
  Da confermare con bmo-core vero acceso insieme (non fatto: bmo-core era
  fermo nella prova).
- Bus SPI: un fotogramma pieno costa ~28 ms (nota dell'hardware), 15 fps ne
  lasciano 66 ms: ~42% del bus, fattibile.

## yt-dlp: il vero ostacolo non è la RAM

| Passo | Misura (laptop) |
|---|---|
| ricerca `ytsearch5:` | **56 MB** di picco, 0,7 s di CPU, 1,4 s, nessuna chiave |
| risoluzione di un video | una prima corsa riuscita ha toccato **341 MB** di picco tra i figli (yt-dlp + il runtime JavaScript `deno` che YouTube ora richiede; non separati) |

- **Risoluzione sul Pi: da escludere.** 341 MB > tutta la RAM libera.
  Va fatta altrove; il Pi riceve solo gli indirizzi (o un file).
- **Blocco anti-bot.** Dopo circa 10 richieste in pochi minuti dal mio IP,
  YouTube ha cominciato a rifiutare anche video diversi con «Sign in to confirm
  you're not a bot» / «This video is not available». Sono sensazioni del
  momento, non un limite documentato: ma mostra che il rischio di questa
  funzione è l'affidabilità del servizio di terzi (come per Gemini: 7,3% di
  errori nel 24 h), non la RAM. Aggirarlo con i cookie del browser è
  un'operazione che **non** ho fatto né documentato (vedi decisioni).

## Come ripetere

```
# laptop
venv/bin/python -W ignore pi/peso_mpv.py bmo-core clip.mp3 "nyan cat" 30
# Pi: risolvere altrove, poi
python3 pi/peso_video_pi.py bmo-core 40 urls.txt   # urls.txt: gli indirizzi risolti altrove, uno per riga
```
