# Decisioni da prendere — issue #79 (WM8960 Audio HAT)

Per ogni voce: le opzioni, cosa è implementato di default e la conseguenza concreta
di scegliere l'una o l'altra. Numeri e metodo in [`note-issue-79.md`](note-issue-79.md).
Il codice che gira sul Pi non è stato ristrutturato (vincolo tuo): sono aggiunte.

## 1. Il jack analogico del Pi (`dtparam=audio`)

**Opzioni:** (a) lasciare `dtparam=audio=on`: il jack bcm2835 è la card 0 e il HAT la card 1,
indirizzato per nome; (b) `dtparam=audio=off`: il HAT diventa la card 0 e `hw:0,0` torna valido.

**Implementato: (a)**, con `BMO_AUDIO_DISPOSITIVO=hw:CARD=wm8960soundcard,DEV=0` in `/etc/bmo/env`
(lo scrive `abilita-hat.sh`) e `ctl.!default`/`pcm.!default` dell'asound.conf puntati al HAT.

**Conseguenza:** (a) non dipende dall'ordine di enumerazione ed è l'unico cambio minimo; il driver
bcm2835 resta caricato (qualche MB di kernel, non misurato). (b) toglie un'ambiguità e libera quel
poco, ma richiede di rilanciare `abilita-hat.sh` modificato e un riavvio; il rischio è che un
aggiornamento di `config.txt` lo riporti a `on` e `hw:0,0` torni sul jack senza cattura.

## 2. Il filo del backlight (pin 12 contro pin 32)

**Opzioni:** (a) spostare il filo dal pin fisico 12 (GPIO18, BCLK dell'I2S) al pin 32 (GPIO12), dove il
codice lo pilota (`BMO_SPI_BL=12`); (b) lasciarlo sul pin 12 e non pilotarlo; (c) collegare il
backlight a 3,3 V (sempre acceso).

**Implementato:** niente nel codice. A riposo l'audio funziona con il filo sul pin 12, ma il backlight
è agganciato al BCLK.

**Conseguenza:** (a) l'unico che mantiene audio e luminosità controllabile (il piano prevede di
spegnere lo schermo di notte). (b) funziona finché il clock è alto: la luminosità non è controllabile
e il carico sul BCLK può dare rumore sul DAC (**non misurato**). (c) schermo sempre acceso, nessun
rischio per l'audio.

## 3. La faccia in produzione

**Opzioni:** (a) l'arte del riferimento (`faces.bin` 2.304.000 byte, impronta `aa9f95d1`) copiata
nel clone di produzione, a mano; (b) l'asset di produzione costruito dal repo (impronta `3d37c00d`,
2.152.060 byte, quello che `deploy.sh` genera se manca `faces.bin`).

**Implementato: (a)**, con copia di sicurezza (`faces.bin.produzione-3d37c00d`,
`faces.json.produzione`). Sono file non versionati (la cartella `assets/` è nel `.gitignore`).

**Conseguenza:** (a) è la faccia vera di BMO; l'arte del riferimento sta fuori dal repo per licenza
(#23), quindi non è riproducibile da `deploy.sh`: su un Pi nuovo servirebbe copiarla. (b) è
riproducibile ma è l'asset che in passato ti ha dato la faccia sbagliata.

## 4. I moduli di sistema nel venv (`lgpio`, `spidev`, `RPi`)

**Opzioni:** (a) link simbolici dal Python di sistema nel venv, fatti da `deploy.sh`; (b) rifare il
venv con `--system-site-packages`; (c) installare da PyPI.

**Implementato: (a).** (c) non è possibile: `lgpio` su PyPI (0.0.0.2) non funziona e `spidev` si compila
(serve toolchain). (b) tirerebbe dentro anche il numpy di sistema e cambierebbe quello che pesa
in RAM (il venv è stato ottimizzato).

**Conseguenza:** (a) non cambia il venv se non per quattro link; se Debian cambia versione di Python
il nome del `.so` (`cpython-313-aarch64`) non corrisponde più e il link non si crea (il pulsante e lo
schermo smettono di partire, con un `ModuleNotFoundError` chiaro).

## 5. Il guadagno di cattura e il volume dell'altoparlante

**Opzioni:** (a) `Capture 40`, `Speaker 85%`, `Playback 255`, `Speaker AC/DC 5`, salvati con
`alsactl store`; (b) lasciare `Capture 63` (predefinito del kernel) e dare più margine al VAD.

**Implementato: (a)** (`abilita-hat.sh`).

**Conseguenza:** (a) parlato a 1 m con picchi attorno a −14 dBFS, senza saturare; a 3 m il segnale
cala di ~10 dB e il VAD potrebbe essere meno sensibile (**non misurato**). (b) satura già a distanza
ravvicinata (picco 0 dBFS) e distorce il parlato; più sensibile sulla stanza.

## 6. Il ramo del clone di produzione

**Opzioni:** (a) il clone di produzione resta su un ramo di integrazione (`prova-hat-completa`:
#79 + la PR #71 del pulsante), finché non mergi; (b) tornare a `master` ora.

**Implementato: (a).** Il ramo è pubblicato solo per il Pi, non va mergiato.

**Conseguenza:** (a) hai il pulsante e il HAT in produzione subito, ma `deploy.sh` segue quel ramo, non
`master`: dopo il merge delle PR #71 e #79 va fatto `git checkout master && git pull` nel clone e
poi `deploy.sh`. (b) niente pulsante e niente schermo SPI in produzione finché le PR non entrano.

## 7. `gpu_mem` (ancora aperta, dalla #77)

**Opzioni:** (a) `gpu_mem=16` e camera grezza; (b) `gpu_mem=64` e `rpicam`. **Implementato: (a).**
Con il servizio vero `MemAvailable` è 207-214 MB: (b) toglierebbe ~48 MB e la porterebbe a ~160 MB.
La camera in produzione usa la grezza in ogni caso (`BMO_CAMERA=grezza` in `/etc/bmo/env`).

## 8. Cascata Gemini

Trattata nella issue #80 / PR #81 (togliere i modelli deprecati). Qui solo il fatto che il 14/10 i
modelli in coda davano 503 a ondate.
