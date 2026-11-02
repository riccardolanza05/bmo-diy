# Sviluppo su PC

Tutto il software gira anche su un PC Linux, senza hardware dedicato: webcam al posto della fotocamera, microfono e
casse del PC al posto del HAT, una finestra GTK al posto del display. Il confine è in `bmo-core/src/bmo_core/adapters/`.

## Installazione

Servono Python 3.11 o superiore, `mpv`, `ffmpeg`, `alsa-utils`, un compilatore C e, per la finestra, GTK4 con
PyGObject (Arch: `gtk4 python-gobject`; Debian: `python3-gi gir1.2-gtk-4.0`).

```bash
git clone https://github.com/riccardolanza05/bmo-diy.git
cd bmo-diy
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e "./bmo-core[dev]" -e "./bmo-face[dev]"
export GEMINI_API_KEY=...
```

## Provare BMO

In un terminale, la faccia:

```bash
cd bmo-face
python -m bmo_face.build_face --destinazione assets/
python -m bmo_face.finestra --assets assets/
```

In un altro, il cervello con voce, wake word e collegamento alla finestra:

```bash
cd bmo-core
BMO_FACCIA=socket python -m bmo_core.macchina --wake-word --voce-tts
```

Senza `--wake-word` il richiamo è il tasto Invio; senza `--voce-tts` BMO scrive sul terminale. Ctrl-C esce subito.
I dati finiscono in `~/.local/state/bmo/`: usa `BMO_DATI=/tmp/prova` per non toccarli.

I video di YouTube compaiono nella stessa finestra, alla dimensione fisica del pannello, con l'audio dal PC. Per
provare solo l'immagine, senza microfono né Gemini:

```bash
python -m bmo_core.anteprima_video "queen bohemian rhapsody video ufficiale"
```

## Test

```bash
(cd bmo-core && pytest)
(cd bmo-face && pytest)
```

I test sono offline e non usano l'hardware. La prova del prompt, invece, fa chiamate vere a Gemini:

```bash
python -m bmo_core.prova_frasi                       # tutte le frasi
python -m bmo_core.prova_frasi --categoria web       # una categoria
python -m bmo_core.prova_frasi --prompt nuovo.txt    # un prompt diverso
```

## Prove miste PC + Pi

`pi/strumenti/prova-ibrida/` copia il codice in `~/bmo-test` sul Pi e lo lancia senza toccare i servizi di produzione.
Vedi [strumenti del Pi](../pi/README.md#prova-ibrida).

## Struttura del repository

| Cartella | Contenuto |
|---|---|
| [`bmo-core/`](../bmo-core/README.md) | Dialogo, wake word, voce, strumenti |
| [`bmo-face/`](../bmo-face/README.md) | Faccia, pannello SPI, finestra per il PC |
| [`pi/`](../pi/README.md) | Installazione, servizi e strumenti per il Raspberry Pi |
| [`docs/`](README.md) | Documentazione |
