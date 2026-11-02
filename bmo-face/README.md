# bmo-face

La faccia di BMO: pipeline degli asset, motore di animazione, server del socket e uscita sul display SPI o in una
finestra sul PC. È un processo separato da `bmo-core`: se il cervello si ferma, la faccia continua a sbattere le
palpebre.

## Installazione

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

`--system-site-packages` serve solo alla finestra: GTK4 e PyGObject sono pacchetti di sistema (Arch: `python-gobject
gtk4`; Debian: `python3-gi gir1.2-gtk-4.0`). Sul Pi non servono.

## Generare gli asset

```bash
python -m bmo_face.build_face --destinazione assets/
```

Genera `assets/faces.bin`, fotogrammi RGB565 grezzi, e `assets/faces.json`, il manifesto. Con questo comando la faccia
è quella geometrica disegnata da `arte_placeholder.py`. La risoluzione predefinita è 320×240, modificabile con
`--larghezza` e `--altezza`, e il risultato pesa circa 2 MB. `assets/` è un artefatto di build e non si versiona.

### Arte vera invece della faccia geometrica

```bash
python -m bmo_face.build_face --sorgente /percorso/a/una/cartella --destinazione assets/
```

`--sorgente` legge fotogrammi `.png` nel layout a cartelle di
[brenpoly/be-more-agent](https://github.com/brenpoly/be-more-agent): `idle/`, `listening/`, `thinking/`, `speaking/`,
`error/`, `warmup/`. Le immagini vengono ridimensionate e ritagliate al centro sul pannello. I fotogrammi `speaking`
diventano la bocca, ordinati dal più chiuso al più aperto.

**Le immagini e `faces.bin` non entrano mai nel repository:** il codice di be-more-agent è MIT, ma le immagini non hanno
una licenza esplicita e raffigurano un personaggio protetto (Cartoon Network / Warner Bros. Discovery). Tienile in una
cartella a parte.

Limite noto: lo stato `error` di quell'arte è un'icona a piena larghezza, e il ritaglio centrato la taglia male.

## Sul Raspberry Pi

```bash
python -m bmo_face.pannello --assets assets/ --uscita spi     # sul display
python -m bmo_face.pannello --assets assets/ --uscita nulla   # senza schermo
```

`pannello` è il servizio di produzione. `spi.py` pilota l'ILI9341 da `spidev`, con tre GPIO per DC, RST e backlight, e
scrive solo il rettangolo cambiato. Cablaggio in [hardware](../docs/hardware.md), variabili in
[configurazione](../docs/configurazione.md#display).

## Sul PC

```bash
python -m bmo_face.finestra --assets assets/                 # dimensione fisica del pannello 2.4"
python -m bmo_face.finestra --assets assets/ --pixel         # 1 px del pannello = 1 px dello schermo
python -m bmo_face.finestra --assets assets/ --carta-prova   # tre righe da 20 caratteri, prova di leggibilità
```

A dimensione fisica la finestra occupa gli stessi millimetri del pannello, calcolati con `hyprctl monitors -j`. Senza
Hyprland usa `--pitch-mm X Y`. I video di YouTube compaiono nella finestra come sul pannello.

## Collegare bmo-core

```bash
BMO_FACCIA=socket python -m bmo_core.macchina --voce-tts
```

Il socket è `/run/bmo/bmo.sock` sul Pi; sul PC `$XDG_RUNTIME_DIR/bmo.sock`. `BMO_SOCKET` ha sempre la precedenza. Il
protocollo ha un messaggio JSON per riga, per esempio:

```json
{"cmd": "state", "value": "ascolto"}
{"cmd": "expression", "value": "felice", "ttl": 3.0}
{"cmd": "timer", "remaining": 312, "label": "pasta"}
```

Gli stati sono `assonnato`, `idle`, `ascolto`, `pensiero`, `parlato`, `timer`, `errore-rete` e `conferma`, e li
sceglie il codice. Le espressioni sono `felice`, `pensieroso`, `sorpreso`, `triste` e `assonnato`, e le sceglie il
modello. Se la finestra manca, `FacciaSocket` fallisce in silenzio: un turno di conversazione non si rompe mai per la
faccia.

Foto e video arrivano sullo stesso schermo. La foto resta qualche secondo, intera e centrata, poi torna la faccia. I
fotogrammi video viaggiano su un socket datagram a parte (`video.py`).

## Struttura del pacchetto

| Modulo | Cosa fa |
|---|---|
| `formato.py` | Formato di `faces.bin` e `faces.json`, lettura con `mmap` |
| `arte_placeholder.py` | Faccia geometrica disegnata a codice |
| `build_face.py` | Pipeline: arte → `faces.bin` + `faces.json` |
| `animazione.py` | `Renderer`: dal tempo e dai comandi al fotogramma |
| `protocollo.py` | Messaggi del socket |
| `servitore.py` | Server del socket Unix |
| `pannello.py` | Servizio per il Pi, senza dipendenze grafiche |
| `spi.py` | Pilota dell'ILI9341 |
| `video.py` | Ricezione dei fotogrammi video |
| `finestra.py` | Finestra GTK4 per il PC |
| `dimensione_fisica.py` | Calcolo mm↔px per la finestra |
