# BMO DIY

Un assistente vocale domestico con le sembianze di **BMO**, il personaggio di *Adventure Time*, costruito su un
Raspberry Pi 3 A+. Gli parli, ti risponde a voce, ti mostra una faccia animata e sta acceso 24/7.

*A home voice assistant shaped like BMO from Adventure Time, built on a Raspberry Pi 3 A+.
[English overview below](#english).*

## Stato del progetto

| | |
|---|---|
| **Elettronica** | ✅ Completa, montata e collaudata |
| **Software** | ✅ Completo, in funzione sul Raspberry Pi |
| **Scocca stampata in 3D** | 🚧 Da realizzare: è l'ultima parte che manca ([guida](docs/stampa-3d.md)) |

## Cosa sa fare

- **Conversazione a voce**, in italiano e in inglese, con la wake word «Hey BMO» riconosciuta in locale o con il
  pulsante del HAT
- **Faccia animata** su un display da 2,4", che cambia a ogni stato e muove la bocca seguendo la voce
- **Foto**: BMO guarda con la sua fotocamera e descrive quello che vede
- **Ricerca sul web**
- **Timer** che sopravvivono ai riavvii
- **Radio via internet** e **video di YouTube** sullo schermo, con volumi separati
- **Memoria**: ricorda la conversazione in corso e tiene un diario delle tue preferenze
- **Riparte da solo** dopo uno stacco della corrente

## Come funziona

Il Pi ha solo 512 MB di RAM, quindi a bordo restano wake word, audio e faccia. Trascrizione, ragionamento e visione
stanno su **Gemini**, la voce su **edge-tts**. Con il piano gratuito di Gemini il costo di esercizio è zero, e
l'elettronica costa circa 68 € oltre al Pi e al suo alimentatore. Il dettaglio è in [architettura](docs/architettura.md).

## Costruirne uno

1. **[Compra e collega l'hardware](docs/hardware.md)**: serve un Pi 3 A+, un HAT audio WM8960, un display 2.4"
   ILI9341 e una fotocamera OV5647. Nessuna saldatura.
2. **[Installa il software](docs/installazione-pi.md)**: dalla microSD vuota a BMO funzionante, con una chiave Gemini
   gratuita.
3. **[Stampa e monta la scocca](docs/stampa-3d.md)**.

Per provarlo prima, senza hardware, basta un PC Linux: [sviluppo su PC](docs/sviluppo-pc.md).

## Dove trovare le cose

| | |
|---|---|
| [`docs/`](docs/README.md) | Guide, configurazione, risoluzione dei problemi, architettura, misure |
| [`bmo-core/`](bmo-core/README.md) | Il cervello: dialogo, wake word, voce, strumenti |
| [`bmo-face/`](bmo-face/README.md) | La faccia: animazione, display SPI, finestra per il PC |
| [`pi/`](pi/README.md) | Installazione, servizi e strumenti di misura per il Raspberry Pi |

## Sviluppi futuri

Idee aperte, tracciate nelle [issue](https://github.com/riccardolanza05/bmo-diy/issues): interrompere BMO mentre parla,
Spotify Connect, domotica con Home Assistant, modalità Live di Gemini, immagini generate da mostrare sullo schermo.

---

<a id="english"></a>

## English

**BMO DIY** is a home voice assistant shaped like BMO from *Adventure Time*, built on a Raspberry Pi 3 Model A+. You
talk to it, it answers out loud, shows an animated face and stays on 24/7.

### Status

The electronics and the software are complete, assembled and tested, and BMO runs on the Pi. The only part left is the
**3D-printed shell** ([guide, in Italian](docs/stampa-3d.md)).

### What it does

- **Voice conversation** in Italian and English, woken by a local "Hey BMO" wake word or by the HAT button
- **Animated face** on a 2.4" display, with a mouth that follows the voice
- **Photos**: BMO looks through its camera and describes what it sees
- **Web search**, **persistent kitchen timers**, **internet radio** and **YouTube videos** on its screen
- **Memory**: it remembers the current conversation and keeps a diary of your preferences
- **Automatic restart** after a power cut

### How it works

The Pi has only 512 MB of RAM, so only the wake word, audio and face run on the device. Speech recognition, reasoning
and vision run on **Google Gemini**, in a single call, and speech synthesis uses **edge-tts**.

```
microphones ─► bmo-core ─HTTPS─► Gemini, edge-tts, web search, radio, YouTube
                  │
             Unix socket
                  ▼
              bmo-face ─SPI─► 2.4" ILI9341 display
```

Three systemd services start at boot: one sets up the audio mixer once, the other two keep retrying until they are up.

### Hardware

| Part | Model |
|---|---|
| Computer | Raspberry Pi 3 Model A+ with a 5 V 2.5 A power supply |
| Storage | 32 GB A1 microSD |
| Audio | Waveshare WM8960 Audio HAT, with two MEMS microphones, 8 Ω speaker and a button |
| Display | Waveshare 2.4" LCD Module (ILI9341, 240×320, no touch) |
| Camera | OV5647 5 MP with a 15-pin CSI ribbon |
| Assembly | 2×20 extra-tall stacking header, F-F jumper wires, M2.5×6 self-tapping screws, 5×2 mm magnets, about 200 g of PETG |

The parts cost about €68 on top of the Pi and its power supply, and no soldering is needed. Wiring, including the one
pin that matters (the display backlight goes on **physical pin 32**, not 12), is in [`docs/hardware.md`](docs/hardware.md).

### Build your own

The step-by-step guides are in Italian, and the commands in them are the same in any language:

1. [Hardware and wiring](docs/hardware.md)
2. [Pi installation](docs/installazione-pi.md): Raspberry Pi OS 64-bit, then `pi/irrobustisci.sh`, `pi/abilita-hat.sh`
   and `pi/deploy.sh`
3. [3D printing and assembly](docs/stampa-3d.md)

You need a free [Gemini API key](https://aistudio.google.com/apikey). The default system prompt and the voice are
Italian: both can be changed, see [`docs/configurazione.md`](docs/configurazione.md).

You can try BMO on a Linux PC without any of this hardware: see [`docs/sviluppo-pc.md`](docs/sviluppo-pc.md).

---

## Note legali

BMO è un personaggio di *Adventure Time*, di Cartoon Network / Warner Bros. Discovery. Questo è un progetto amatoriale
non ufficiale e non commerciale, senza alcun legame con loro. *BMO is a character owned by Cartoon Network / Warner
Bros. Discovery; this is an unofficial, non-commercial fan project.*

I disegni del personaggio non sono in questo repository. I suoni inclusi sono CC0
([dettagli](bmo-core/src/bmo_core/audio/LICENZE.md)). Modelli, librerie e modelli 3D di terze parti restano soggetti
alle proprie licenze, elencate nei [riferimenti](docs/riferimenti.md).

Questo repository non ha ancora una licenza.
