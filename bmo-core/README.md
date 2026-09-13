# bmo-core

Logica di dialogo di BMO. Punto di partenza: gli **adapter hardware**, l'unico
confine tra "gira sul PC di sviluppo (omarchy)" e "gira sul Raspberry Pi" —
vedi la discussione in cima a questo repository su come sviluppare senza
comprare i componenti fisici.

## Struttura

```
src/bmo_core/
├── config.py              rileva l'ambiente (dev-linux vs pi) via BMO_ENV o device-tree
└── adapters/
    ├── base.py            interfacce (Protocol): CameraAdapter, AudioInputAdapter, AudioOutputAdapter
    ├── camera.py           LibcameraAdapter (Pi, CSI/OV5647) · WebcamV4L2Adapter (PC, ffmpeg+V4L2)
    ├── audio_input.py       ArecordAdapter (ALSA, stesso comando su Pi e PC, cambia solo il device)
    ├── audio_output.py      MpvAdapter (identico su Pi e PC)
    └── factory.py           unico punto che sceglie quale implementazione usare
tests/                       test della factory e del rilevamento ambiente
```

Il resto del codice (`bmo-core` vero e proprio: wake word, chiamate a
Gemini, gestione stati) deve dipendere solo dai `Protocol` in `base.py` e
dalle funzioni `crea_*` di `factory.py`, mai dalle classi concrete — è
questo che permette di sviluppare su omarchy e spostarsi sul Pi cambiando
un solo file.

## Uso

```python
from bmo_core.adapters import crea_camera, crea_audio_input, crea_audio_output

camera = crea_camera()        # rileva l'ambiente da solo
mic = crea_audio_input()
altoparlante = crea_audio_output()
```

Per forzare l'ambiente (utile nei test o per sviluppare su un PC che non è
il Pi ma vuoi comunque testare i path Pi-specifici):

```bash
BMO_ENV=dev-linux python -m bmo_core...
BMO_ENV=pi python -m bmo_core...
```

## Verifiche da fare sul PC di sviluppo (omarchy) prima di usare gli adapter

- `arecord -l` per trovare il device audio giusto (di default si usa `default`,
  che su PipeWire con compatibilità ALSA di solito funziona già).
- `v4l2-ctl --list-devices` per confermare che la webcam sia su `/dev/video0`
  (`WebcamV4L2Adapter` lo assume, ma va verificato).
- `mpv --version` e `ffmpeg -version` installati.

## Sviluppo

```bash
cd bmo-core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
