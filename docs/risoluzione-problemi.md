# Risoluzione dei problemi

Il primo posto dove guardare:

```bash
systemctl status bmo-hat-audio bmo-face bmo-core
journalctl -u bmo-core -b
```

I log stanno in RAM e si perdono a ogni riavvio.

## Audio

| Sintomo | Causa | Cosa fare |
|---|---|---|
| Nessuna scheda in `/proc/asound/cards` | Overlay assente, o HAT inserito male | `sudo pi/abilita-hat.sh`, riavvia e ricontrolla l'header |
| L'altoparlante non suona | Uscite del mixer spente, volume basso | `sudo systemctl restart bmo-hat-audio`; deve valere `Speaker 85%` |
| Il primo turno va, i successivi no; log con `Available formats: S16_LE` | `dmix` non è in `S32_LE` | `pi/installa-audio.sh` |
| Voce e video non suonano insieme | `/etc/asound.conf` assente | `pi/installa-audio.sh` |
| La voce vicina distorce | Guadagno di cattura troppo alto | Abbassa `Capture` in `pi/bmo-hat-audio.sh` e `pi/abilita-hat.sh` |
| `arecord` dice che il dispositivo è occupato | `bmo-core` tiene il microfono | `sudo systemctl stop bmo-core` prima di ogni misura |

## Richiamo

| Sintomo | Causa | Cosa fare |
|---|---|---|
| Bisogna urlare | Soglia alta | `BMO_SOGLIA_WAKE_WORD` più bassa; sotto 0,25 di solito non si guadagna altro |
| BMO scatta da solo | Soglia bassa, rumore o TV | Soglia più alta; ogni falso scatto consuma una richiesta a Gemini |
| Taglia le frasi a metà | Silenzio troppo corto | `BMO_SILENZIO_MS` più alto |
| Il pulsante non fa niente | `gpiozero` senza il `lgpio` di sistema | Rilancia `pi/deploy.sh`, che ricollega i moduli di apt; controlla `BMO_PULSANTE_PIN=17` |

## Voce e cervello

| Sintomo | Causa | Cosa fare |
|---|---|---|
| BMO risponde ma non parla; `403` nel log | `edge-tts` vecchio o endpoint cambiato | `~/bmo-pi/venv/bin/pip install -U edge-tts` |
| `No API key was provided` | `/etc/bmo/env` assente o incompleto | Vedi il [passo 4](installazione-pi.md#4-inserisci-la-chiave-api) |
| Errori `404` da Gemini | Modello ritirato | Aggiorna `BMO_GEMINI_MODELLI` |
| Errori `429` o `503` frequenti | Quota esaurita o sovraccarico | La cascata li gestisce; se persistono, riprova più tardi o cambia ordine dei modelli |
| BMO dice «non ci arrivo» | Rete assente | Controlla il Wi-Fi, BMO si riprende da solo |
| Il video non parte | `yt-dlp` vecchio | `pi/deploy.sh`, che lo aggiorna sempre |

## Display

| Sintomo | Causa | Cosa fare |
|---|---|---|
| Schermo bianco fisso | Alimentato ma non inizializzato: i dati non arrivano | Ricontrolla CLK, DIN, CS, DC e RST |
| Schermo nero, il Pi lavora | Backlight scollegato o sul pin sbagliato | Il filo BL va sul pin 32, [dettagli](hardware.md#collegamenti) |
| Il display va e l'audio no | BL sul pin 12, cioè sul clock I2S | Sposta il filo sul pin 32 |
| Colori invertiti o immagine ruotata | Orientamento | `BMO_SPI_MADCTL` |
| Righe o artefatti | Bus SPI troppo veloce, cavi lunghi | Abbassa `BMO_SPI_HZ` |
| La faccia non cambia più | `bmo-face` è senza socket | `sudo systemctl restart bmo-face bmo-core` |
| Faccia geometrica invece di BMO | `assets/` costruito senza arte | [Passo 7](installazione-pi.md#7-scegli-la-faccia) |

## Fotocamera

| Sintomo | Causa | Cosa fare |
|---|---|---|
| `rpicam` non vede la camera | Normale con `gpu_mem=16` | BMO usa `BMO_CAMERA=grezza` |
| Foto capovolta | Montaggio del modulo | `BMO_CAMERA_RUOTA` |
| Foto sfocata | Lente tarata all'infinito | [Regola il fuoco a 30 cm](hardware.md#fotocamera) |
| `/dev/video0` assente | Flat inserito male | Spegni, ricontrolla il flat e `camera_auto_detect=1` |

## Sistema

| Sintomo | Causa | Cosa fare |
|---|---|---|
| Il Pi si riavvia da solo | Contatto debole sui 5 V | Ricontrolla header e connettori; `vcgencmd get_throttled` deve dare `0x0` |
| `ModuleNotFoundError: lgpio` o `spidev` | Python di sistema cambiato | `pi/deploy.sh` collega i file `cpython-313`: aggiorna il nome in `deploy.sh` |
| `bmo-core` viene ucciso per memoria | Superato `MemoryMax=280M` | `journalctl -u bmo-core`, e controlla radio e video in corso |
| `clanker.local` non risponde | Rete diversa o `avahi-daemon` fermo | Trova l'IP dal router |
