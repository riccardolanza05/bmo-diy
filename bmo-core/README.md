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

## Il cervello: primo giro con Gemini (issue #19)

`brain.py` fa un turno di dialogo: `ascolta()` registra dal microfono tramite
gli adapter, `rispondi()` manda l'audio a Gemini col prompt di sistema a due
strati (§2.3 del piano) ed esegue il loop agentico, `strumenti()` esegue le
chiamate del modello. Per ora c'è un solo strumento, `imposta_timer`, con i
timer tenuti in memoria (la persistenza arriva con l'issue #20).

La chiave API va nella variabile d'ambiente `GEMINI_API_KEY` (se è impostata
anche `GOOGLE_API_KEY`, l'SDK usa quella). Il modello predefinito è
`gemini-3.8-flash`, sovrascrivibile con `BMO_GEMINI_MODEL`.

```bash
export GEMINI_API_KEY=...
python -m bmo_core.brain --testo "Metti un timer di dieci minuti"
python -m bmo_core.brain                       # parli per 3 secondi al microfono
python -m bmo_core.brain --senza-ora --testo "Che ore sono?"   # esperimento fase 0.3
python -m bmo_core.prova_frasi                 # le 20 frasi di prova, come testo
python -m bmo_core.prova_frasi --voce          # le 20 frasi lette al microfono
```

Criterio di uscita della #19: almeno 18 frasi su 20 corrette.

## Cascata di modelli (issue #12)

Se il modello primario risponde con quota esaurita (429) o sovraccarico
(500/502/503/504), `modelli.py` passa subito al modello successivo della
cascata, configurata in una variabile d'ambiente e non nel codice:

```bash
# quali modelli ha a disposizione la tua chiave
python -c "from google import genai; [print(m.name) for m in genai.Client().models.list() if 'flash' in m.name]"

export BMO_GEMINI_MODELLI="gemini-3.8-flash,<modello-di-riserva>"
```

| Errore | Cosa fa | Per quanto sospende il modello |
|---|---|---|
| 429 quota | passa al successivo | il `retryDelay` indicato da Google, altrimenti 60 s |
| 5xx sovraccarico | passa al successivo | 30 s |
| 404 modello inesistente | passa al successivo | 1 ora |
| altri 4xx (richiesta, chiave) | si ferma subito: cambiare modello non serve | — |
| rete giù | si ferma subito: gli altri modelli sono sullo stesso server | — |

Scaduta la sospensione, il primario torna a essere provato per primo. Se
sono tutti sospesi si riprova comunque il primario; se falliscono tutti,
`GeminiNonDisponibile` dice il tipo (`quota`, `sovraccarico`, `rete`), che sul
dispositivo diventerà la frase e la faccia dello stato di errore. L'SDK fa 2
tentativi per modello invece dei 5 predefiniti, per non aspettare 15 s prima
di cambiare modello.

## Sviluppo

```bash
cd bmo-core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
