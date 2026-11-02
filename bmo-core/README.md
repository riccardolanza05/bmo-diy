# bmo-core

Il cervello di BMO: ascolta, parla con Gemini, esegue gli strumenti e dice a `bmo-face` cosa mostrare. Per il quadro
generale vedi [architettura](../docs/architettura.md), per le variabili [configurazione](../docs/configurazione.md).

## Struttura

```
src/bmo_core/
├── macchina.py            macchina a stati, il punto d'ingresso del servizio
├── brain.py               prompt, turno di dialogo, loop agentico
├── modelli.py             cascata dei modelli Gemini
├── strumenti.py           dichiarazioni degli strumenti per Gemini
├── sessione.py            memoria della conversazione in corso
├── memoria.py             diario delle preferenze
├── persone.py             chi vive in casa
├── richiamo.py            wake word e pulsante
├── wake_word.py           ascolto continuo e punteggi di openWakeWord
├── vad.py                 ascolto fino al silenzio
├── tts.py                 voce
├── inviluppo.py           inviluppo dell'audio per la bocca
├── suoni.py               suoni senza parole
├── volumi.py              volumi per canale
├── timer.py, sveglia.py   timer su disco e processo che li fa suonare
├── ricerca.py             ricerca sul web
├── radio.py               radio e stazioni preferite
├── video.py               video di YouTube
├── risolvi_youtube.py     risoluzione degli indirizzi, in un processo a parte
├── config.py              ambiente (PC o Pi) e percorsi dei dati
├── audio/                 suoni CC0 inclusi
└── adapters/              confine hardware: stesse interfacce su PC e Pi
modelli-wake-word/         bmo1.onnx («BMO»), bmo2.onnx («Hey BMO»)
prompt/                    bozze del prompt, per il confronto con prova_frasi
tests/                     test offline
```

Strumenti diagnostici, non usati dal servizio: `prova_frasi.py`, `misura_ram.py`, `misura_modelli.py`,
`simula_cascata.py`, `carico.py`, `anteprima_video.py`.

## Adapter

Il codice dipende solo dalle interfacce in `adapters/base.py` e dalle funzioni `crea_*` di `adapters/factory.py`. È
questo che permette di passare dal PC al Pi senza cambiare la logica.

| Interfaccia | Sul Pi | Sul PC |
|---|---|---|
| Fotocamera | `CameraGrezzaV4L2` (`BMO_CAMERA=grezza`) | `WebcamV4L2Adapter` |
| Microfono | `ArecordConvertitoreAdapter`, S32 stereo 48 kHz → mono 16 kHz | `ArecordAdapter` |
| Uscita audio | `MpvAdapter` | `MpvAdapter` |
| Volume | `VolumeAlsa` | `VolumePipeWire` |
| Faccia | `FacciaSocket` | `FacciaSocket`, `FacciaTerminale` o `FacciaMuta` |
| Pulsante | `PulsanteGpio` | — |

L'ambiente si rileva da solo; `BMO_ENV=pi` o `BMO_ENV=dev-linux` lo forza.

## Comandi

```bash
python -m bmo_core.macchina                         # Invio per parlare, testo sul terminale
python -m bmo_core.macchina --wake-word --voce-tts  # come sul Pi
python -m bmo_core.brain --testo "Metti un timer di dieci minuti"   # un turno scritto
python -m bmo_core.brain --conversazione            # più turni sulla stessa sessione
```

| Opzione di `macchina` | Effetto |
|---|---|
| `--silenzio-ms N` | Silenzio che chiude l'ascolto |
| `--aggressivita 0-3` | Aggressività del rilevatore di voce |
| `--senza-vad --durata N` | Ascolto a durata fissa |
| `--soglia-wake-word N` | Soglia del richiamo |
| `--modello-wake-word F` | Modello `.onnx` o preaddestrato di openWakeWord, ripetibile |
| `--senza-timer`, `--senza-radio`, `--senza-suoni` | Spengono una funzione |

`python -m bmo_core.brain` stampa gli strumenti chiamati, il modello che ha risposto e la durata del turno.

## Wake word

`RichiamoWakeWord` ascolta in continuo e scatta quando un modello supera la soglia. Tutto gira in locale con ONNX
Runtime, senza account né chiavi. `bmo1` e `bmo2` sono caricati insieme e basta che uno solo reagisca.

```bash
python -m bmo_core.richiamo --soglia 0.2 --volte 10      # prova il richiamo
python -m bmo_core.vad --silenzio-ms 1500                # prova la fine dell'ascolto
```

Il buffer di openWakeWord viene azzerato a ogni ascolto: senza, un punteggio residuo farebbe scattare richiami a
catena.

## Voce

BMO parla con **`it-IT-DiegoNeural`** al +35%, sintetizzata da edge-tts. Le altre lingue usano un'unica voce
multilingua.

```bash
python -m bmo_core.tts "Ciao, sono BMO"
python -m bmo_core.tts "Ciao" --velocita +0%
python -m bmo_core.tts "Ciao" --motore gemini
```

I file finiscono in `<dati>/voce/`, con una chiave che comprende testo, motore, voce e velocità: una frase già detta
non si sintetizza due volte. Gli errori e i ripieghi non usano mai una seconda voce: BMO è un personaggio, e una voce
diversa a metà conversazione stona più di una pausa.

Il motore alternativo è Gemini TTS (`BMO_TTS_MOTORE=gemini`), più lento e con quote molto basse. Se edge-tts smette di
funzionare, Azure Speech serve la stessa voce in modo ufficiale.

### Timbro

mpv applica il filtro in riproduzione, senza costi di RAM o latenza. `BMO_VOCE_FILTRO` sceglie fra:

| Preset | Effetto |
|---|---|
| `naturale` | La voce così com'è |
| `appena` | Toglie solo gli estremi |
| `radiolina` | Suono da piccolo altoparlante, voce naturale (predefinito) |
| `digitale` | `radiolina` più un velo digitale a 10 bit |
| `altoparlante` | Passa-banda 350-3400 Hz |
| `console` | Passa-banda e 6 bit |
| `bmo` | Passa-banda, 8 bit e flanger leggero |
| `metallico` | Flanger |
| `anello` | Modulazione a 55 Hz, il più robotico |

`BMO_VOCE_PAUSA` accorcia i silenzi fra le frasi, che i modelli neurali allungano come in una lettura ad alta voce.

## Suoni

`suoni.py` cerca ogni suono, nell'ordine: `BMO_SUONO_<NOME>`, un file `<nome>.{opus,mp3,ogg,wav}` in `<dati>/suoni/`, il
file incluso nel pacchetto, un tono generato da mpv.

| Suono | Quando | Predefinito |
|---|---|---|
| `errore` | La rete non risponde | `error_008` di Kenney, CC0 |
| `timer` | Un timer scade | Tono generato; `BMO_TONO` lo forza |
| `scatto` | `scatta_foto` scatta | "Camera Shutter Click" di Kodack, CC0 |

Nel repository stanno solo suoni CC0: vedi [`audio/LICENZE.md`](src/bmo_core/audio/LICENZE.md).

```bash
python -m bmo_core.suoni --solo-elenco    # da dove viene ogni suono
```

## Timer

I timer stanno in `<dati>/timers.json`:

- si salva la scadenza assoluta, così un riavvio non allunga un timer;
- si scrive con un file temporaneo e `rename`, così una caduta di corrente lascia il file intero;
- un lock `flock` protegge cervello e sveglia, che scrivono lo stesso file;
- un timer scaduto a BMO spento suona lo stesso, con un messaggio diverso.

```bash
python -m bmo_core.sveglia                  # fa suonare i timer scaduti
BMO_DATI=/tmp/prova python -m bmo_core.sveglia
```

## Radio, video e volume

`riproduci_musica` cerca prima fra le preferite (`<dati>/radio.json`), anche per frequenza, poi su
[radio-browser.info](https://www.radio-browser.info/). `successivo` e `precedente` scorrono l'elenco in ascolto come una
manopola e `salva_stazione` tiene quella che piace.

`riproduci_video` cerca su YouTube, risolve l'indirizzo con yt-dlp in un processo che muore subito e decodifica con
ffmpeg a un thread. I fotogrammi vanno a `bmo-face` su un socket datagram.

Il volume ha quattro canali: `radio`, `voce`, `timer` e `sistema`. Il modello sceglie il canale dal significato della
frase, con `regola_volume(percentuale, canale=...)`. La radio parte al 40%.

## Prompt e prova delle frasi

Il prompt fisso è `brain.PROMPT_FISSO`, e la copia in `prompt/bozza-v4.txt` serve al confronto. Ogni modifica va
verificata con chiamate vere a Gemini:

```bash
python -m bmo_core.prova_frasi                           # 43 frasi in 8 categorie
python -m bmo_core.prova_frasi --voce                    # lette al microfono
python -m bmo_core.prova_frasi --categoria inglese       # bilingue, fuori dal conteggio
python -m bmo_core.prova_frasi --prompt prompt/nuovo.txt # un prompt diverso
```

Un prompt va bene con almeno il 90% di frasi corrette.

## Persone di casa

`<dati>/persone.json` è un array di nomi, riletto a ogni turno. Non sta nel repository. BMO non sa chi sta parlando: il
prompt gli vieta di indovinare o salutare per nome di sua iniziativa.

## Cascata di modelli

| Errore | Cosa fa | Sospende il modello per |
|---|---|---|
| 429 quota | Passa al successivo | Il `retryDelay` di Google, altrimenti 60 s |
| 5xx sovraccarico | Passa al successivo | 30 s |
| 404 modello inesistente | Passa al successivo | 1 ora |
| Altri 4xx | Si ferma: cambiare modello non serve | — |
| Rete giù | Si ferma: i modelli sono sullo stesso server | — |

Scaduta la sospensione, il primo modello torna a essere provato per primo. Se falliscono tutti,
`GeminiNonDisponibile` dice il tipo di errore, e BMO lo mostra con il suono e la faccia di errore.

## Memoria di sessione

`sessione.py` tiene lo storico recente in RAM e lo antepone a ogni richiesta.

- Dopo 5 minuti di silenzio la sessione si chiude e una richiesta separata estrae i fatti utili verso il diario.
  L'estrazione è pensata per essere rara: al massimo 2 voci, e spesso nessuna.
- A 60.000 token la conversazione viene compressa in un riassunto, senza toccare il diario.
- Se l'estrazione fallisce il testo resta da parte e si ritenta al turno successivo.

Queste richieste non girano mai mentre qualcuno aspetta una risposta: partono da `Cervello.dopo_il_turno()`, dopo che
la voce ha finito.

## Test

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Misurare la RAM

```bash
python -m bmo_core.misura_ram --cerca bmo_core.macchina
python -m bmo_core.misura_ram --radice <PID> --csv misura.csv --riepilogo riepilogo.txt
```

Il numero da guardare è il picco di PSS totale, che divide le librerie condivise fra i processi. I valori misurati sono
in [misure](../docs/misure.md).
