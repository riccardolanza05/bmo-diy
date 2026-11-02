# Installazione sul Raspberry Pi

Da una microSD vuota a BMO che risponde. Serve l'hardware già [collegato](hardware.md#collegamenti), un PC con cui
scrivere la microSD e una chiave API di Gemini gratuita, da [Google AI Studio](https://aistudio.google.com/apikey).

I singoli passi sono stati eseguiti sul Pi del progetto con Raspberry Pi OS 64 bit (Debian 13 trixie). La sequenza
completa non è stata ripetuta su una microSD vuota: se un passo si comporta diversamente, apri una issue.

## 1. Scrivi la microSD

Con [Raspberry Pi Imager](https://www.raspberrypi.com/software/) scegli **Raspberry Pi OS (64-bit)** e, nelle
impostazioni avanzate, configura:

| Campo | Valore |
|---|---|
| Hostname | `clanker` |
| Utente | `clanker_home` |
| Wi-Fi | la tua rete |
| SSH | attivo, con la tua chiave pubblica |

Il 64 bit è obbligatorio: `onnxruntime`, che esegue la wake word, non pubblica pacchetti per ARM a 32 bit.

Usa esattamente quell'utente: le unit systemd e gli script di avvio contengono il percorso
`/home/clanker_home/bmo-pi`. Con un nome diverso devi sostituirlo in `pi/` e rifare la sostituzione dopo ogni
aggiornamento.

Inserisci la microSD, accendi il Pi e collegati:

```bash
ssh clanker_home@clanker.local
```

## 2. Installa i pacchetti di sistema

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev build-essential mpv ffmpeg alsa-utils v4l-utils \
  python3-lgpio python3-spidev python3-rpi-lgpio
```

`lgpio`, `spidev` e `RPi` arrivano da apt perché il pacchetto `lgpio` di PyPI non funziona sul Pi: `deploy.sh` li
collega nel venv. `build-essential` serve a compilare il rilevatore di voce (`webrtcvad-wheels`).

## 3. Scarica BMO

```bash
mkdir -p ~/bmo-pi
git clone https://github.com/riccardolanza05/bmo-diy.git ~/bmo-pi/bmo-diy
python3 -m venv ~/bmo-pi/venv
cd ~/bmo-pi/bmo-diy
~/bmo-pi/venv/bin/pip install -e "./bmo-core[pi]" -e ./bmo-face
```

La struttura è fissa: `~/bmo-pi/bmo-diy` è il clone, `~/bmo-pi/venv` è un solo ambiente Python condiviso da
`bmo-core` e `bmo-face`.

## 4. Inserisci la chiave API

```bash
sudo mkdir -p /etc/bmo
sudo cp pi/bmo-core-env.esempio /etc/bmo/env
sudo chmod 600 /etc/bmo/env
sudo nano /etc/bmo/env        # GEMINI_API_KEY=...
```

Il file non va mai versionato né stampato. I servizi lo leggono tramite systemd.

## 5. Prepara il sistema al funzionamento 24/7

Lo script è idempotente. Ogni blocco chiede un riavvio: dopo ciascuno controlla che SSH torni su.

```bash
sudo bash pi/irrobustisci.sh servizi     # senza desktop, servizi inutili spenti, watchdog a 15 s
sudo reboot
```

```bash
cd ~/bmo-pi/bmo-diy
sudo bash pi/irrobustisci.sh avvio       # config.txt e cmdline.txt, con copia .bak-25
sudo reboot
```

Se il Pi non torna, rimetti dal PC `cmdline.txt.bak-25` e `config.txt.bak-25` al posto degli originali, sulla
partizione di boot della microSD.

```bash
sudo bash ~/bmo-pi/bmo-diy/pi/irrobustisci.sh verifica
```

La verifica deve mostrare `multi-user.target`, `get_throttled` a `0x0` e `memory` fra i controller cgroup.
`lambrate-login.timer` compare come inattivo: è specifico della rete dell'autore e non serve.

## 6. Abilita il HAT audio

```bash
sudo ~/bmo-pi/bmo-diy/pi/abilita-hat.sh
sudo reboot
```

Lo script aggiunge l'overlay, scrive in `/etc/bmo/env` microfono, pulsante e fotocamera, poi imposta il mixer.
Dopo il riavvio `cat /proc/asound/cards` deve elencare `wm8960soundcard`. Rilancia lo script una volta: ora che la
scheda esiste, salva anche il mixer.

```bash
sudo ~/bmo-pi/bmo-diy/pi/abilita-hat.sh
```

## 7. Scegli la faccia

Se non fai nulla, `deploy.sh` costruisce una faccia geometrica inclusa nel repository.

Per la faccia con l'aspetto di BMO servono i disegni del progetto
[brenpoly/be-more-agent](https://github.com/brenpoly/be-more-agent), che non possono stare in questo repository
([perché](../bmo-face/README.md#arte-vera-invece-della-faccia-geometrica)). Metti le loro cartelle `idle/`, `listening/`,
`thinking/`, `speaking/`, `error/` e `warmup/` in una cartella sul Pi, poi:

```bash
~/bmo-pi/venv/bin/python -m bmo_face.build_face --sorgente /percorso/arte --destinazione ~/bmo-pi/bmo-diy/bmo-face/assets
```

## 8. Avvia BMO

```bash
~/bmo-pi/bmo-diy/pi/deploy.sh
```

Lo script aggiorna il codice, installa le dipendenze, copia e abilita i tre servizi, configura l'audio e riavvia BMO.
Finisce con `== deploy riuscito`, altrimenti stampa il log del servizio che non è partito.

Da questo momento BMO riparte da solo a ogni accensione.

## 9. Provalo

Di' **«Hey BMO»** o premi il pulsante del HAT, aspetta il bip, poi fai una domanda. Una prova rapida:

1. «Che ore sono?»
2. «Metti un timer di un minuto»
3. «Cosa vedi?», per la fotocamera
4. «Metti la radio», poi «abbassa la radio» e «ferma»

Per seguire cosa succede:

```bash
journalctl -u bmo-core -f
```

Se qualcosa non va: [risoluzione dei problemi](risoluzione-problemi.md).

## 10. Regola BMO per casa tua

- **Città.** Il prompt in `bmo-core/src/bmo_core/brain.py` dice che BMO vive a Milano: cambiala se vuoi.
- **Persone.** `/var/lib/bmo/persone.json` contiene un array di nomi, per esempio `["Finn", "Jake"]`, e non serve
  riavviare.
- **Wake word nella tua stanza.** La soglia dipende dalla stanza e da dove metti BMO. Fermalo, così il microfono si
  libera, e lancia la calibrazione guidata:

  ```bash
  sudo systemctl stop bmo-core
  ~/bmo-pi/venv/bin/python ~/bmo-pi/bmo-diy/pi/strumenti/calibra_wake_word.py
  sudo systemctl start bmo-core
  ```

  La soglia si cambia con `BMO_SOGLIA_WAKE_WORD` in `/etc/bmo/env`.
- **Fotocamera.** Se la foto esce capovolta o dritta al contrario, cambia `BMO_CAMERA_RUOTA` in `/etc/bmo/env`.

Le altre opzioni sono in [configurazione](configurazione.md).

## Aggiornare BMO

```bash
~/bmo-pi/bmo-diy/pi/deploy.sh
```

`deploy.sh` segue il branch del clone con soli fast-forward: non sovrascrive modifiche locali e si ferma se il branch
ha divergenze.
