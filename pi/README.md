# pi

Tutto ciò che serve sul Raspberry Pi. La procedura completa è in
[installazione](../docs/installazione-pi.md).

## Installazione e servizi

| File | Cosa fa | Quando |
|---|---|---|
| `irrobustisci.sh` | Prepara il sistema per il 24/7 (`servizi`, `avvio`, `verifica`) | Una volta, idempotente |
| `abilita-hat.sh` | Overlay della WM8960, variabili in `/etc/bmo/env`, mixer | Una volta, idempotente |
| `deploy.sh` | Aggiorna codice e dipendenze, installa i servizi, riavvia BMO | A ogni aggiornamento |
| `installa-audio.sh` | Genera `/etc/asound.conf` da `asound.conf.modello` | Lo lancia `deploy.sh` |
| `bmo-core-env.esempio` | Modello di `/etc/bmo/env` | Una volta |
| `bmo-core-avvia.sh` | Avvia `bmo-core` con voce e wake word | Lo lancia il servizio |
| `bmo-hat-audio.sh` | Attende la scheda audio e imposta il mixer | Lo lancia il servizio |
| `systemd/` | `bmo-hat-audio`, `bmo-face`, `bmo-core` | Li installa `deploy.sh` |

Script e unit presumono l'utente `clanker_home` e la cartella `~/bmo-pi`, con il clone in `~/bmo-pi/bmo-diy` e il venv
in `~/bmo-pi/venv`.

## Strumenti

`strumenti/` contiene programmi di misura e prova: non servono al funzionamento di BMO. Quelli che usano il microfono
vanno lanciati con il servizio fermo, `sudo systemctl stop bmo-core`.

| Strumento | Cosa fa |
|---|---|
| `calibra_wake_word.py` | Calibrazione guidata della wake word: dici le parole, lui consiglia la soglia |
| `prova_sensibilita.py` | Punteggi e falsi positivi col microfono vero |
| `misura_microfoni.py` | Livello, picco e clipping dei due MEMS |
| `prova_hat.sh` | Bip, registrazione di 5 s e riascolto, con `VOLUME=` e `CAPTURE=` |
| `misura_sistema_24h.py` | Temperatura, throttling, zram e memoria dei servizi in un CSV |
| `peso_bmo_core.py`, `peso_bmo_face.py`, `peso_mpv.py` | RAM di ogni componente |
| `peso_video_pi.py`, `ram_video.py`, `ffmpeg_ram.py`, `avvio_ffmpeg_pi.py` | Prestazioni e memoria dei video |
| `prova_video_e2e.py` | Video di YouTube dall'inizio alla fine |
| `velocita_sd.py` | Velocità della microSD |
| `bmo-carico-avvia.sh`, `systemd/` | Prova di carico di 24 h con audio da file; le unit si copiano a mano |

## Prova ibrida

`strumenti/prova-ibrida/` lancia BMO sul Pi da una copia in `~/bmo-test`, senza toccare i servizi di produzione. Si
lancia dal PC, con la chiave Gemini in `~/.bashrc`. Gli script si fermano se la faccia non è costruita con l'arte vera;
`avvia_hat.sh` controlla anche l'impronta di `faces.bin`: con un'arte diversa va aggiornata `IMPRONTA_ATTESA`.

```bash
pi/strumenti/prova-ibrida/avvia_hat.sh       # microfono e altoparlante del HAT
pi/strumenti/prova-ibrida/avvia_ibrida.sh    # microfono e casse del PC, camera e schermo del Pi
```

Per riprovare il display sul Pi: `pi/strumenti/prova-ibrida/prova_schermo.sh`.
