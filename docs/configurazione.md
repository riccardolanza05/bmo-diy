# Configurazione

BMO si configura con variabili d'ambiente. Sul Pi stanno in `/etc/bmo/env`, letto dai servizi: dopo una modifica
serve `sudo systemctl restart bmo-core`. Sul PC bastano le normali variabili della shell.

## Cervello

| Variabile | Cosa fa | Predefinito |
|---|---|---|
| `GEMINI_API_KEY` | Chiave API di Gemini, obbligatoria | — |
| `BMO_GEMINI_MODELLI` | Cascata dei modelli, separati da virgole | `gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.6-flash` |
| `BMO_GEMINI_MODEL` | Usa un solo modello | — |

I nomi dei modelli Gemini cambiano spesso. Per vedere quelli disponibili con la tua chiave:

```bash
python -c "from google import genai; c = genai.Client(); [print(m.name) for m in c.models.list() if 'flash' in m.name]"
```

## Ascolto

| Variabile | Cosa fa | Sul Pi |
|---|---|---|
| `BMO_AUDIO_DISPOSITIVO` | Dispositivo ALSA del microfono | `hw:CARD=wm8960soundcard,DEV=0` |
| `BMO_SOGLIA_WAKE_WORD` | Soglia del richiamo: più bassa è, più BMO scatta | `0.20` |
| `BMO_SILENZIO_MS` | Silenzio che chiude l'ascolto, in ms | `1500` |
| `BMO_VOCE_MINIMA_MS` | Voce minima prima che il silenzio possa chiudere, in ms | `400` |
| `BMO_VAD_PASSA_ALTO_HZ` | Passa-alto sui frame giudicati dal VAD (non sull'audio mandato a Gemini): toglie il ronzio del HAT che teneva l'ascolto aperto fino al tetto; `0` lo spegne | `150` |
| `BMO_PULSANTE_PIN` | GPIO del pulsante del HAT | `17` |

Il modello `bmo2.onnx` risponde a «Hey BMO» e `bmo1.onnx` a «BMO». Per aggiungere un modello tuo, addestrato con
[openWakeWord](https://github.com/dscripka/openWakeWord), copialo sul Pi come
`bmo-core/modelli-wake-word/bmo3.onnx`: viene caricato se esiste, e git lo ignora.

## Voce

| Variabile | Cosa fa | Predefinito |
|---|---|---|
| `BMO_TTS_MOTORE` | `edge` o `gemini` | `edge` |
| `BMO_VOCE` | Forza la voce per tutte le lingue | `it-IT-DiegoNeural` (`Kore` su Gemini) |
| `BMO_VOCE_EN`, `BMO_VOCE_FR`… | Forza la voce di una lingua | una voce multilingua |
| `BMO_VOCE_VELOCITA` | Velocità SSML | `+35%` |
| `BMO_VOCE_FILTRO` | Timbro, vedi [bmo-core](../bmo-core/README.md#timbro) | `radiolina` |
| `BMO_VOCE_PAUSA` | Silenzio lasciato a fine frase, in secondi; `0` disattiva | `0.15` |
| `BMO_GEMINI_TTS_MODELLI` | Cascata dei modelli vocali, solo per il motore Gemini | i modelli TTS predefiniti |

## Suoni

| Variabile | Cosa fa |
|---|---|
| `BMO_SUONO_ERRORE`, `BMO_SUONO_SCATTO` | File da usare al posto del suono predefinito |
| `BMO_TONO` | File da suonare allo scadere di un timer |

In alternativa metti `timer.opus`, `.mp3`, `.ogg` o `.wav` nella cartella `suoni/` dei dati.

## Fotocamera

| Variabile | Cosa fa | Sul Pi |
|---|---|---|
| `BMO_CAMERA` | `grezza` legge il sensore direttamente con V4L2 | `grezza` |
| `BMO_CAMERA_RUOTA` | Rotazione dell'immagine in gradi | `180` |
| `BMO_CAMERA_SENSORE` | Entità del sensore | `ov5647 10-0036` |
| `BMO_CAMERA_MEDIA`, `BMO_CAMERA_VIDEO`, `BMO_CAMERA_SOTTO` | Nodi del dispositivo | `/dev/media0`, `/dev/video0`, `/dev/v4l-subdev0` |

## Display

| Variabile | Cosa fa | Predefinito |
|---|---|---|
| `BMO_SPI_DC`, `BMO_SPI_RST`, `BMO_SPI_BL` | GPIO BCM di DC, RST e backlight | `25`, `27`, `12` |
| `BMO_SPI_BUS`, `BMO_SPI_DISP` | Bus e dispositivo SPI | `0`, `0` |
| `BMO_SPI_HZ` | Frequenza del bus | `20000000` |
| `BMO_SPI_MADCTL` | Orientamento e ordine dei colori | `0x28` |

## Video di YouTube

| Variabile | Cosa fa |
|---|---|
| `BMO_VIDEO_AUDIO` | Dispositivo audio di ffmpeg per i video |
| `BMO_YT_COOKIES` | File di cookie per yt-dlp, se YouTube blocca l'indirizzo IP |
| `BMO_YT_ARGS` | Argomenti aggiuntivi per yt-dlp |

## Sistema

| Variabile | Cosa fa | Predefinito |
|---|---|---|
| `BMO_ENV` | `pi` o `dev-linux` | rilevato da solo |
| `BMO_DATI` | Cartella dei dati | `/var/lib/bmo` sul Pi, `~/.local/state/bmo` sul PC |
| `BMO_FACCIA` | `socket` collega `bmo-core` a `bmo-face` | faccia muta |
| `BMO_SOCKET` | Socket dei comandi | `/run/bmo/bmo.sock` sul Pi |
| `BMO_SOCKET_VIDEO` | Socket dei fotogrammi video | accanto a `BMO_SOCKET` |
| `BMO_ATTESA_SCHEDA_S` | Quanto `bmo-hat-audio` aspetta la scheda, in secondi | `60` |

## File nella cartella dati

| File | Contenuto | Come si modifica |
|---|---|---|
| `timers.json` | Timer attivi | da BMO |
| `radio.json` | Stazioni preferite | da BMO, o a mano |
| `memoria.json` | Diario delle preferenze | da BMO con conferma, o a mano |
| `persone.json` | Nomi di chi vive in casa, array JSON | a mano |
| `volumi.json` | Volumi dei canali | da BMO |
| `voce/` | Cache delle frasi sintetizzate | automatica |
| `suoni/` | Suoni personali | a mano |
