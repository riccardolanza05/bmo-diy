# Decisioni in sospeso — video di YouTube sul Pi

Numeri e prove in [`note-video-youtube.md`](note-video-youtube.md). Qui solo ciò che aspetta te: per ogni
voce le opzioni, cosa è implementato di default e cosa cambia scegliendo altro.

## 1. Artista senza brano («fammi sentire i Queen»): YouTube o radio?

- **Default implementato: YouTube** (primo risultato per «queen video ufficiale»). Un genere o un umore
  senza artista né brano («un po' di jazz», «musica rock») resta radio.
- Se preferisci la radio per gli artisti: BMO cercherebbe una stazione che si chiama come l'artista e quasi
  sempre non la trova; la musica di quell'artista non la sentiresti mai. Validato 100% col default attuale.

## 2. Se YouTube cambia o ti blocca

yt-dlp funziona senza chiavi, cookie o JavaScript, ma dipende da come YouTube risponde. Ho visto (1) i
client «leggeri» dare indirizzi che poi rispondono 403, (2) un blocco anti-bot sul tuo IP dopo una raffica di
richieste (risolto da solo), (3) un video su cinque che resta appeso (si passa al successivo) e una corsa in cui
il primo risultato ha impiegato 16 s prima di cedere.

- **Default**: nessun cookie. Se un giorno non bastasse, `BMO_YT_COOKIES=/percorso/cookies.txt` (file
  **fuori dal repo**, formato Netscape) viene passato a yt-dlp. Io non ho usato né conservato i tuoi cookie: li
  avevo esportati, erano solo cookie anonimi di visita (nessun login Google) e non servivano; li ho cancellati.
- Serve aggiornare yt-dlp ogni tanto (`pip install -U yt-dlp` nel venv del Pi): YouTube rompe le versioni
  vecchie. Conseguenza di non farlo: «il video non parte». Puoi lasciarlo manuale o metterlo nel deploy.

## 3. Quanto aspettare dopo «metti…»

Il video parte **in background mentre BMO parla**: lo strumento risponde in ~0,7 s, il primo fotogramma arriva
~5 s dopo la richiesta (misurato: 5,1 s), quindi di norma poco dopo la fine della frase di BMO.

- **Se nessun risultato parte** (succede, raro) BMO ha già detto «metto il video»: lo segnala il suono di
  errore e la faccia triste, non una frase. Alternativa: far dire una frase a voce («non riesco a far partire il
  video»); richiede di far parlare BMO fuori da un turno, una modifica a `macchina.py`: dimmi se la vuoi.
- Se preferisci la versione **sincrona** (lo strumento aspetta il video, BMO dice «ecco!» quando c'è davvero):
  `in_background=False` in `macchina.py`. Lo strumento impiega ~5 s (fino a 20 s nei casi peggiori) e
  il turno ha un tetto di 20 s (`TETTO_TURNO_S`): rischia di sforarlo. Non consigliato.

## 4. Fluidità contro bus SPI (da confermare col display vero)

Default: il frame rate del video fino a **30 fps per un 16:9** (320×180, 115 kB a fotogramma), **26 per un 4:3**
(320×240); oltre si dimezza se torna fluido. La CPU e la RAM del Pi reggono i 30 fps (43-58% di un core, 72 MB),
ma il bus SPI è una stima dalle note dell'hardware (~5,5 MB/s), **non una misura**: il display non è arrivato.

- Se all'arrivo il bus regge meno: abbassare `BUS_SPI_BYTE_AL_SECONDO` in `video.py` (2 MB/s → 17 fps per un
  16:9). Se regge di più: alzarlo (e `FPS_MAX`).
- Il ridimensionamento è `lanczos` (come il bicubic per CPU, più nitido); `FLAG_SCALA` in `video.py`.

## 5. RAM: entra, ma stretta (da misurare in servizio)

`bmo-core.service` ha `MemoryMax=280M` e il video conta lì dentro (ffmpeg e il risolutore sono suoi figli).
Stima del momento peggiore: bmo-core ~106 MB + voce mpv ~48 MB + ffmpeg 72 MB ≈ **226 MB**, più il risolutore
(46 MB, ~3 s, si chiude prima che parta ffmpeg) ≈ 272 MB se si sovrappone alla voce. **Margine: ~8 MB.** Non l'ho
misurato nel servizio vero (bmo-core e la sua cgroup non giravano: serve la chiave Gemini, leggibile solo da root
in `/etc/bmo/env`) — il `memory.peak` di una cgroup di prova (72-74 MB) non è attendibile per questo scopo.

- **Da fare al deploy**: guardare `systemctl status bmo-core` (riga `Memory:` con il picco) dopo qualche richiesta
  di video mentre BMO parla. Se sfiora i 280 MB: alzare `MemoryMax` a 320M (il criterio della Fase 2.3; il Pi ha
  ~290 MB liberi a riposo con bmo-face acceso: c'è la zram), oppure far parlare BMO *prima* di risolvere il video.
- Il 24 h (#65) ha usato ~93 MB di zram su 462: c'è margine per assorbire un picco breve.

## 6. Audio del video sul Pi

Il video suona con ffmpeg su `alsa:default`; `BMO_VIDEO_AUDIO` per cambiarlo (`null` per tacere, `pulse`
non c'è sul Pi). Con la scheda WM8960 (un solo sottodispositivo ALSA) la voce di BMO (mpv) e il video
**non potranno suonare insieme senza un mixer software (dmix)**; oggi sull'uscita analogica del Pi (8
sottodispositivi) sì. Decisione per quando arriva l'HAT: configurare `dmix` in `/etc/asound.conf`
(senza, BMO non potrebbe parlare mentre un video suona, e viceversa).

## 7. Non costruito (aspetta l'hardware o un tuo via libera)

`UscitaSpi` (il disegno sul display vero, già col rettangolo centrato e `inizio_video`/`disegna_video`/`fine_video`
pronti), l'audio dalla scheda vera, e il **deploy sul Pi**: il servizio `bmo-core`/`bmo-face` sul Pi è ancora
alla versione precedente (serve `sudo` per riavviarli, vedi `pi/deploy.sh`).
