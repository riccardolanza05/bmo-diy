# Note — issue #79 (WM8960 Audio HAT: microfono e altoparlante veri sul Pi)

Numeri grezzi e come ripeterli. Le decisioni che spettano a Riccardo stanno in
[`decisioni-issue-79.md`](decisioni-issue-79.md), le cose solo informative in
[`informazioni-issue-79.md`](informazioni-issue-79.md). Tutto del 14/10/2026, Pi 3 A+ (462 MB),
HAT montato, display Waveshare 2.4" e camera OV5647 collegati, kernel con overlay `wm8960-soundcard`.

## Cosa c'è

| Pezzo | Dove | Cosa fa |
|---|---|---|
| `pi/abilita-hat.sh` | Pi, sudo, una volta | `dtoverlay=wm8960-soundcard` (in `[all]`, controlla l'ultima sezione), `BMO_AUDIO_DISPOSITIVO` per nome, `BMO_PULSANTE_PIN=17`, `BMO_CAMERA=grezza`, `BMO_CAMERA_RUOTA=180`, mixer impostato e salvato (`alsactl store`) |
| `pi/misura_microfoni.py` | Pi, strumento | RMS, picco, clipping e offset **per canale** dei due MEMS |
| `pi/prova_hat.sh` | Pi, strumento | routing del mixer, bip, 5 s registrati, livelli, riascolto (`VOLUME=`, `CAPTURE=`) |
| `pi/prova_sensibilita.py` | Pi, strumento | punteggi della wake word col microfono vero, per modello, rilevazioni distinte a 0,3/0,5/0,7 e falsi positivi (**non ancora eseguito**: il servizio tiene il microfono) |
| `pi/ibrida/avvia_hat.sh` + `pi_avvia.sh --hat` | PC / Pi | la prova ibrida senza tunnel (usa microfono e altoparlante del HAT); non serve più per la produzione |
| `asound.conf.modello` | Pi | dmix ora in **S32_LE** (vedi sotto) |
| `bmo-face.service` | Pi | `--uscita spi` (prima `nulla`) |
| `deploy.sh`, `pyproject.toml` | Pi | extra `[pi]` = `gpiozero`; `lgpio`, `spidev` e `RPi` collegati dal Python di sistema nel venv |
| `edge-tts>=7.3.1` | `bmo-core` | la 7.2.8 prendeva 403 (stesso errore dal portatile) |

Il codice che gira sul Pi non cambia di struttura: solo aggiunte.

## Scheda e driver

- `arecord -l` prima dell'overlay: nessuna scheda di cattura; `aplay -l`: `card 0: Headphones`.
- Dopo l'overlay: `card 1: wm8960soundcard`, `/dev/i2c-1` compare, il codec si registra
  (`wm8960 1-001a`; gli avvisi `supply … not found, using dummy regulator` sono normali).
- Con `dtparam=audio=on` il jack bcm2835 resta la card 0: `hw:0,0` punterebbe al jack (senza
  cattura). Si indirizza per nome: `hw:CARD=wm8960soundcard,DEV=0`.
- `amixer scontrols` elenca `Speaker`, `Headphone`, `Playback`, `Capture`, ecc. `VolumeAlsa` sceglie
  `Speaker` (primo dei candidati preferiti con volume). Verificato che `amixer` senza `-c` arrivi sul
  HAT grazie a `ctl.!default` dell'asound.conf.

## Microfoni (due MEMS, S32_LE stereo 48 kHz, `misura_microfoni.py`)

| Condizione | Sinistro rms / picco | Destro rms / picco |
|---|---|---|
| Stanza silenziosa, ingresso **non** instradato (default del kernel), Capture 63 | −65,2 / −38,7 dBFS | −67,7 / −41,0 |
| Idem, 2ª misura | −63,8 / −38,6 | −66,2 / −41,0 |
| Con `Input Mixer Boost` + `LINPUT1/RINPUT1` a 2, Capture 63 (+30 dB), parlato vicino | −21,4 / −0,0 | −21,1 / −0,0 (**satura**) |
| Capture 40, parlato (`prova_hat.sh`) | −44,1 / −20,6 | −44,0 / −22,0 |
| Capture 40, parlato (voce.py, 8 s) | −31,9 / −14,4 | −31,7 / −14,4 |

- Entrambi i canali sono vivi e uguali entro 0,5 dB.
- Il VAD di bmo-core (`webrtcvad`, aggressività 2) classifica il **75%** (299/400 blocchi da 20 ms) di
  8 s di parlato di due persone come voce, con pause visibili.
- **Capture 63 con boost 2 satura** la voce vicina; con **40** il picco è ≈ −14 dBFS.
- Sensibilità portata **al massimo** il 14/10 (Capture 63, boost LINPUT1/RINPUT1 = 3), soglia della wake
  word invariata a 0,5, silenzio a 1500 ms e voce minima 400 ms. **Non misurato dopo** (il servizio tiene
  il microfono): da misurare con `pi/misura_microfoni.py` dopo `sudo systemctl stop bmo-core`.
- Dopo un riavvio il mixer torna ai valori di avvio (cattura 63, ingresso spento): `abilita-hat.sh`
  li imposta e li salva con `alsactl store`.

## Altoparlante

Il test a volume crescente (tono 1 kHz, ampiezza 0,3, Capture 30, mic come sensore):

| Speaker | 0% | 10% | 20% | 30% | 40% | 50% | 60% | 70% | 80% | 90% | 100% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mic sx dBFS | −48,8 | −52,3 | −50,5 | −54,8 | −36,1 | −39,9 | −34,5 | −38,7 | −33,2 | −38,9 | −37,6 |

Il livello **non cresce con il volume** (piatto sopra il 40%): il microfono vicino all'altoparlante
non è un buon sensore acustico, i numeri non dimostrano nulla da soli. Il giudizio vale l'ascolto.

- Con `Playback 200`, `Speaker 70%`: **nessun suono udito** (Riccardo).
- Con `Playback 255`, `Speaker 100%`, `Speaker AC/DC 5`: **udito tutto** (rumore rosa, 1 kHz, 200 Hz,
  anello microfono → altoparlante).
- Cuffie sul jack a `Headphone` 35%, 50%, 65%: **non udito**. Non l'ho ripetuto a volume più alto.
- Impostazione finale: `Playback 255`, `Speaker 85%`, `Speaker AC/DC 5`, switch
  `Left/Right Output Mixer PCM Playback Switch` accesi.
- Gli switch di uscita e l'ingresso sono **spenti all'avvio**: senza instradarli il tono non esce.

## Pulsante del HAT (GPIO17)

`lgpio` a 2 ms, 30 s, tre pressioni: a riposo 1; premuto 0; durate 0,18 s, 2,16 s, 1,96 s; 6 cambi di
stato e nessun rimbalzo. **Attivo-basso con pull-up**: coincide con `PulsanteGpio(pin, pull_up=True)`
della #70. `gpiozero` nel venv di produzione: `LGPIOFactory`, `is_pressed=False` a riposo.

## Display con il HAT montato

- `pi/ibrida/prova_schermo.sh` (faccia vera, impronta `aa9f95d1`) è girata fino in fondo: tutti gli
  stati, il timer, una foto in 1,6 s. **Non ho una conferma visiva di Riccardo** su colori e
  orientamento.
- Il filo del backlight è sul **pin fisico 12 = GPIO18 = PCM_CLK**: l'idle del clock è alto e il
  backlight si accende, ma il filo è sul BCLK dell'I2S. Atteso: sul pin 32 (GPIO12).
- `pinctrl`: GPIO18-21 in `a0` (PCM), GPIO12/25/27 input (DC e RST non pilotati a riposo), GPIO10/11
  SPI0.

## Il difetto del formato (visto dal vivo nel journal)

```
arecord: set_params:1387: Sample format non available
Available formats:
- S16_LE
[ascolto: 0.0 s, voce rilevata: no, fine per: flusso_finito]
```

Dopo la voce di BMO (mpv → dmix, slave `S16_LE` predefinito) la riapertura del microfono in S32_LE
veniva rifiutata: il driver I2S condivide il formato fra riproduzione e cattura. Il primo turno dopo
un avvio andava, i successivi (a pochi secondi dalla voce) no. Con `format S32_LE` nello slave di dmix:
dal 22:02 otto turni di fila, tutti «voce rilevata: sì», nessun errore di formato.

## edge-tts 403

`edge-tts 7.2.8`: «403 Invalid response status» sul websocket, sia dal Pi sia dal portatile (orologio
sincronizzato). `7.3.1`: sintesi in 1,2-1,7 s. Sul Pi il venv di produzione è stato aggiornato.

## lgpio di PyPI

`pip install lgpio` (ruota binaria `0.0.0.2`) → gpiozero: «`lgpio` has no attribute
`SET_BIAS_DISABLE`», ripiega su `NativeFactory` e fallisce. Funziona la `0.2.2.0` di sistema
(`python3-lgpio`), collegata nel venv con due link simbolici.

## RAM e temperatura (produzione sul Pi, servizi systemd, 14/10/2026)

| Quando | bmo-core | bmo-face | Altro |
|---|---|---|---|
| Prova da albero ~/bmo-test, 45 s, wake word + faccia SPI (`misura_ram`) | PSS 118,5 MB | 27,4 MB | totale 144,6 MB, MemAvailable min 150,5 MB |
| Servizi, ~14 min dopo il primo turno (cgroup `memory.current`) | 146 MB | 10 MB | MemAvailable 207-214 MB, 43,5-45,1 °C |
| Picco dall'avvio (cgroup `memory.peak`, dopo ~7 turni) | 175-184 MB | 28 MB | `MemoryMax` bmo-core = 280 MiB |

- **Dopo i test dal vivo di Riccardo (campionatore `misura_sistema_24h.py`, 22:31, ogni 5 s):** `bmo-core`
  213 MB in uso e **picco 252 MB** (cgroup, `MemoryMax` 280 MiB = 293,6 MB): il margine è ~40 MB. Il
  picco precedente era 175-184 MB; non so quale attività l'ha spinto a 252 MB (radio, video, camera?).
  **Lo stress test di RAM con carico voluto non è stato fatto**: il campionatore resta acceso sul Pi
  in `~/bmo-test/misure/live-*-sistema.csv`.
- Nessun throttling (`0x0`), swap in uso 29 MB.
- **MemAvailable è scesa da 214 a 207 MB in 60 s con BMO a riposo** (cache di pagina o altro,
  non l'ho distinto). Da guardare in una prova lunga.
- Criterio fase 2.3 (< 320 MB totali): rispettato col picco misurato (184 + 28 MB = ~212 MB).

## Non misurato / non verificato

- **Sensibilità vera della wake word** (veri positivi a 1-2-3 m, falsi positivi in 1 h): lo strumento
  c'è, non l'ho eseguito perché il servizio tiene il microfono; per farlo serve fermare `bmo-core`
  (`sudo systemctl stop bmo-core`).
- **Latenza voce→risposta**: dal log non è separabile (il journal stampa solo durata dell'ascolto e
  sintesi 1,0-2,0 s).
- Test di stress di RAM con raffiche di turni, radio e video insieme: non fatto.
- Colori e orientamento del display; camera con il HAT montato (la prova schermo l'ha scattata in
  1,6 s, non l'ho guardata); `gpu_mem`; cuffie.
