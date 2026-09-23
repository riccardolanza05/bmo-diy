# bmo-core

Logica di dialogo di BMO. Punto di partenza: gli **adapter hardware**, l'unico
confine tra "gira sul PC di sviluppo (omarchy)" e "gira sul Raspberry Pi" —
vedi la discussione in cima a questo repository su come sviluppare senza
comprare i componenti fisici.

## Struttura

```
src/bmo_core/
├── config.py              rileva l'ambiente (dev-linux vs pi) e dove stanno i dati persistenti
├── timer.py               i timer su disco: scadenza assoluta, scrittura atomica, lock
├── sveglia.py             il processo che fa suonare i timer scaduti
├── macchina.py            la macchina a stati: attesa → ascolto → pensiero → parlato
├── ricerca.py             cerca_sul_web con DuckDuckGo
├── radio.py               radio online: sintonia, scorrimento, stazioni preferite, volume
└── adapters/
    ├── base.py            interfacce (Protocol): CameraAdapter, AudioInputAdapter, AudioOutputAdapter, FacciaAdapter
    ├── camera.py           LibcameraAdapter (Pi, CSI/OV5647) · WebcamV4L2Adapter (PC, ffmpeg+V4L2)
    ├── audio_input.py       ArecordAdapter (ALSA, stesso comando su Pi e PC, cambia solo il device)
    ├── audio_output.py      MpvAdapter (identico su Pi e PC)
    ├── faccia.py            FacciaMuta (predefinita) · FacciaTerminale (stato sullo standard error)
    ├── lettore.py           LettoreMpv: mpv acceso e comandato dal socket IPC (radio)
    ├── volume.py            VolumePipeWire (PC, wpctl) · VolumeAlsa (Pi, amixer)
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
- `gcc`/`cc` disponibile: `webrtcvad-wheels` (il VAD, vedi sotto) si compila da
  sorgente, non ha ruote precompilate per ogni versione di Python.

## Il cervello: primo giro con Gemini (issue #19)

`brain.py` fa un turno di dialogo: `ascolta()` registra dal microfono tramite
gli adapter, `rispondi()` manda l'audio a Gemini col prompt di sistema a due
strati (§2.3 del piano) ed esegue il loop agentico, `strumenti()` esegue le
chiamate del modello. Gli strumenti sono i nove della §2.4, dichiarati in
`strumenti.py`: per ora funzionano davvero solo i timer (in memoria), gli altri
rispondono `non_disponibile` finché non arrivano con l'issue #20.

La chiave API va nella variabile d'ambiente `GEMINI_API_KEY` (se è impostata
anche `GOOGLE_API_KEY`, l'SDK usa quella). Il modello predefinito è
`gemini-3.5-flash-lite`, con `gemini-3.1-flash-lite` come riserva (vedi la
cascata sotto); per usare un solo modello basta `BMO_GEMINI_MODEL`.

```bash
export GEMINI_API_KEY=...
python -m bmo_core.brain --testo "Metti un timer di dieci minuti"
python -m bmo_core.brain                       # parli per 3 secondi al microfono
python -m bmo_core.brain --senza-ora --testo "Che ore sono?"   # esperimento fase 0.3
python -m bmo_core.brain --max-giri 1 --testo "Che tempo farà domani sera?"  # forza il riepilogo
python -m bmo_core.prova_frasi                 # le 40 frasi di prova, come testo
python -m bmo_core.prova_frasi --voce          # le 40 frasi lette al microfono
python -m bmo_core.prova_frasi --categoria web # solo una categoria
python -m bmo_core.prova_frasi --prompt nuovo.txt   # prova un prompt fisso diverso
```

Criterio di uscita della #19: almeno il 90% di frasi corrette (36 su 40).

L'espressione della faccia non è uno strumento: BMO la mette all'inizio della
risposta tra parentesi quadre (`[felice] Fatto!`), il codice la toglie prima
della sintesi vocale e la tiene in `Risposta.espressione`.

`python -m bmo_core.brain` stampa sempre quali strumenti ha chiamato il modello
(o `Strumenti chiamati: nessuno`), con argomenti e risultato, quale modello
ha risposto e quanto è durato il turno: nelle prove a voce è il modo di vedere
se un timer è stato impostato davvero o solo annunciato.

## Il tetto del turno e il riepilogo forzato (issue #18)

Il loop agentico ha due limiti (§2.1): **4 giri** in cui BMO può chiamare
strumenti e **20 secondi** per tutto il turno. Quando uno dei due finisce senza
che ci sia una risposta da dire ad alta voce, parte **una richiesta di riepilogo
in più**, fuori dal conteggio dei giri: stessi contenuti raccolti fino a lì,
nessuno strumento chiamabile e un'istruzione in più che spiega al modello di
rispondere con quello che sa. Due ricerche a metà valgono più di un «non ci
arrivo», e senza quell'istruzione il modello a volte restava semplicemente muto.

Il tetto è un limite vero, non un'intenzione: il tempo che resta diventa il
timeout della singola richiesta, quindi un modello lento non lo sfonda. I giri
con gli strumenti si fermano sei secondi prima della scadenza, tenuti da parte
per il riepilogo. Se anche il riepilogo non produce testo, `Risposta.testo` resta
vuota e `Risposta.motivo_vuota` ne dice la ragione: sul dispositivo sarà il punto
in cui parte la clip di errore (issue #21).

`Risposta.riepilogo` dice se la richiesta in più c'è stata e perché
(`tetto di 4 giri`, `tempo finito`, `modello non disponibile`); `--max-giri 1`
serve a provarla senza aspettare che un caso vero saturi il loop.

## BMO acceso: la macchina a stati (issue #20)

```
ATTESA ──richiamo──► ASCOLTO ──► PENSIERO ──► PARLATO ──► ATTESA
   ▲                                                         │
   └──────── PAUSA (metti_in_pausa_l_ascolto) · ERRORE ───────┘
```

```bash
python -m bmo_core.macchina                       # premi Invio e parla; Ctrl-D per spegnere
python -m bmo_core.macchina --silenzio-ms 500      # si ferma prima, dopo mezzo secondo di silenzio
python -m bmo_core.macchina --aggressivita 3       # VAD più aggressivo (utile con la TV accesa)
python -m bmo_core.macchina --senza-vad --durata 5 # torna all'ascolto a durata fissa (5 s)
python -m bmo_core.macchina --senza-timer          # senza la sveglia dei timer
python -m bmo_core.macchina --voce-tts             # BMO parla davvero invece di scrivere (#42)
```

**L'ascolto si ferma da solo quando rileva silenzio**, non dopo una durata
fissa (`vad.py`, con `webrtcvad`): registrare per un tempo deciso in anticipo
non è realistico, una frase può durare quanto vuole. Ogni ascolto stampa una
riga di diagnostica su stderr (`[ascolto: 1.4 s, voce rilevata: sì, fine per:
silenzio]`) per capire cosa ha deciso il VAD. Per tarare `--silenzio-ms` e
`--aggressivita` senza passare da un turno intero con Gemini di mezzo:

```bash
python -m bmo_core.vad                              # una registrazione, solo la diagnostica
python -m bmo_core.vad --silenzio-ms 500 --aggressivita 3
```

**A ogni transizione cambia la faccia**, ed è il punto del piano che conta di
più: senza pulsanti e senza spie, la faccia è l'unico modo di sapere che BMO ha
sentito il richiamo. La faccia si mostra *prima* di cominciare l'azione, mai
dopo — il piano chiede che il passaggio ad ASCOLTO si veda entro 150 ms,
altrimenti la persona ripete la frase e rovina la registrazione.

La sveglia dei timer gira nello stesso processo, in un thread: un timer deve
suonare anche mentre BMO sta ascoltando o pensando.

`metti_in_pausa_l_ascolto` è vero: durante la pausa la faccia è `assonnato`, i
richiami vengono ignorati e i timer suonano lo stesso. Lo strumento appartiene
alla macchina, non al cervello, e si collega con `registra_strumento`.

Due pezzi sono ancora provvisori e isolati apposta in due funzioni: il
**richiamo** è Invio sulla tastiera (la wake word «Hey BMO» è la #22) e la
**voce** stampa il testo (il TTS e le clip sono la #21).

## La voce di BMO (issue #42)

BMO parla con **`it-IT-DiegoNeural`** al **+35%** di velocità, sintetizzata da
**edge-tts**. Di default la macchina a stati scrive ancora sul terminale
(`voce_sul_terminale`): la voce si chiede con `--voce-tts`.

```bash
python -m bmo_core.macchina --voce-tts            # il giro completo, parlato
python -m bmo_core.tts "Ciao, sono BMO"           # solo la sintesi
python -m bmo_core.tts "Ciao" --zitto             # scrive il file e basta
python -m bmo_core.tts "Ciao" --velocita +0%      # alla velocità naturale
python -m bmo_core.tts "Ciao" --motore gemini     # l'altro motore
```

### Una voce sola, sempre la stessa

BMO è un personaggio: una pausa è un difetto minore, **una voce diversa a metà
conversazione è un difetto peggiore**. Da cui due regole che sembrano dettagli
e non lo sono:

1. Le **clip fisse pre-generate della #21 vanno generate con questo stesso
   motore e questa stessa voce**. La #21 dice «col TTS di Gemini» perché è
   stata scritta prima di questa decisione: generarle con Gemini mentre BMO
   risponde con Diego gli darebbe due voci.
2. **Il ripiego non è un'altra voce**: è il terminale, il silenzio, o una clip
   già registrata nella voce giusta.

### ⚠️ edge-tts non è ufficiale

È un client non ufficiale dell'endpoint di lettura di Microsoft Edge: nessuna
quota documentata, nessun permesso d'uso da terze parti, e **si è già rotto in
passato**. Se un giorno BMO ammutolisce, è il primo sospetto.

La cura è **Azure Speech F0**, che serve la **stessa identica voce**
`it-IT-DiegoNeural` ufficialmente e gratis fino a 500.000 caratteri al mese
(20 richieste ogni 60 secondi, regione Italy North). Migrare non cambia come
suona BMO, quindi non viola la regola della voce unica: per questo si può
rimandare senza costi.

### Perché non Gemini

Misurato il 22–23/9 sul PC di sviluppo:

| | sintesi (frase breve) | richieste/minuto |
|---|---|---|
| edge-tts | **~0,6 s** | ~102 misurate, nessun rallentamento |
| Gemini TTS | ~2,6 s (1,2 s fissi + 0,5 s per secondo di audio) | 3 per modello, ~9 con la cascata |

Per confronto, il modello di **testo** risponde in ~0,67 s: con Gemini la voce
era l'88% dell'attesa di un turno. Il motore Gemini resta disponibile con
`--motore gemini` o `BMO_TTS_MOTORE=gemini`, con la sua cascata di tre modelli.

### Voce robotica, a costo zero

mpv applica i filtri **in riproduzione** (`--af`), quindi il trattamento non
costa né un passaggio ffmpeg, né un file intermedio, né latenza. Misurato: il
picco di memoria di mpv è 74,2–74,9 MB con o senza filtro, cioè rumore.

Si sceglie con `BMO_VOCE_FILTRO`, predefinito **`radiolina`**:

Sono in ordine, dal più leggero al più marcato. La prova d'ascolto del 23/9 ha
detto che i trattamenti forti rendono BMO **troppo robotico**: la strada giusta
è suggerire un piccolo altoparlante, non simulare un robot.

| preset | cosa fa |
|---|---|
| `naturale` | la voce come esce dal motore |
| `appena` | toglie solo gli estremi: si sente a malapena, ed è voluto |
| `radiolina` | si capisce che il suono esce da qualcosa di piccolo, ma la voce resta naturale |
| `digitale` | come `radiolina` più un velo digitale a 10 bit |
| `altoparlante` | passa-banda 350–3400 Hz: l'altoparlantino da 40 mm che BMO avrà davvero |
| `console` | passa-banda + 6 bit: sapore da console portatile |
| `anello` | modulazione d'ampiezza a 55 Hz: il robot più marcato, il meno intelligibile |
| `metallico` | flanger: come se parlasse dentro una scatola |
| `bmo` | passa-banda + 8 bit + flanger leggero: il compromesso |

Il filtro è un argomento della **singola riproduzione**, non dell'adapter: lo
stesso `MpvAdapter` suona anche il tono della sveglia, che non deve diventare
robotico solo perché la voce lo è.

### Le pause a fine frase

I modelli neurali prendono fiato a ogni punto con la lunghezza di una lettura
ad alta voce: in una conversazione sembra esitazione. `silenceremove` accorcia
i silenzi oltre 0,25 s lasciandone `BMO_VOCE_PAUSA` (predefinito **0,15 s**),
e sta nella stessa catena `--af`, quindi anche questo **non costa niente**.

Misurato su una risposta di quattro frasi: da **7,9 s a 6,3 s**, un quinto in
meno, tolto solo dai silenzi.

Taglia anche il silenzio **iniziale**, e quello non è un vezzo: è tempo fra il
momento in cui BMO dovrebbe cominciare a parlare e la prima sillaba, cioè
latenza percepita in meno gratis.

`BMO_VOCE_PAUSA=0` disattiva il taglio; un valore illeggibile non zittisce BMO,
si torna al predefinito con un avviso sullo stderr.

### Configurazione

| Variabile | Cosa cambia | Default |
|---|---|---|
| `BMO_TTS_MOTORE` | `edge` o `gemini` | `edge` |
| `BMO_VOCE` | il nome della voce | `it-IT-DiegoNeural` (`Kore` su Gemini) |
| `BMO_VOCE_VELOCITA` | la velocità SSML | `+35%` |
| `BMO_VOCE_FILTRO` | il timbro | `radiolina` |
| `BMO_VOCE_PAUSA` | quanto silenzio lasciare a fine frase, in secondi (`0` disattiva) | `0.15` |
| `BMO_GEMINI_TTS_MODELLI` | la cascata, solo per il motore Gemini | i tre modelli TTS |

I file sintetizzati finiscono in `<cartella dati>/voce/`, con una chiave che
comprende testo, motore, voce e velocità: una frase già detta non si paga due
volte, e cambiare voce o velocità non serve l'audio vecchio. edge-tts produce
mp3 (non offre alternative), Gemini produce WAV.

Con `--voce-tts` ogni risposta stampa sullo stderr i due tempi che servono a
dimensionare le clip della #21:

```
[voce: sintesi 0.58 s, primo suono +0.01 s]
```

Sono separati apposta: il primo è l'attesa di rete (si copre con una clip di
attesa), il secondo è l'avvio di mpv (si cura tenendo un processo pronto).
Sommati non si distinguerebbero più.

## Ricerca sul web, radio e volume (issue #20)

**`cerca_sul_web`** usa DuckDuckGo (`ddgs`), non il grounding con Google Search:
quello non è nel free tier, e mescolare strumenti nativi e dichiarazioni proprie
nella stessa richiesta è ancora in Preview (§2.4). Tornano tre risultati con
titolo, estratto accorciato e indirizzo — finiscono in un `functionResponse` e
costano token a ogni giro, quindi tre e corti. Il giorno del piano a pagamento
si sostituisce `ricerca.cerca` con `google_search` e non cambia altro (#6).

**La radio** ha preso il posto della musica: niente libreria locale da riempire
di file, e quindi «metti un po' di jazz» diventa una stazione che suona jazz.
Ci sono due elenchi, e la differenza conta:

- le **preferite**, salvate in `<cartella dati>/radio.json`, che sono le tue;
- i **risultati di una ricerca** su [radio-browser.info](https://www.radio-browser.info/),
  l'elenco pubblico e gratuito di radio online — nessuna chiave, nessun account —
  che serve a trovarne di nuove.

`riproduci_musica` guarda prima fra le preferite (anche per frequenza: «quella
sui 101 e 7»), e solo se non trova niente cerca online. Da lì si **scorre come
con una manopola**: `successivo` e `precedente` girano in tondo sull'elenco che
si sta ascoltando, che siano le preferite o i risultati della ricerca. Quando ne
passa una che piace, `salva_stazione` la mette fra le preferite, con il nome che
le hai dato tu e con la frequenza se compare nel nome; `elenca_stazioni` le
elenca. Il file si riscrive in modo atomico, come quello dei timer.

YouTube resta alla V2 (#4).

**Il volume** è quello dell'altoparlante, non del lettore: «abbassa il volume»
detto a un BMO che parla troppo forte non riguarda la radio. Sul PC passa per
`wpctl` (PipeWire), sul Pi per `amixer`.

La radio gira su un mpv separato da quello delle clip, tenuto acceso e comandato
dal suo socket IPC (§2.4), perché va messa in pausa e cambiata mentre suona.

## Timer persistenti e sveglia (issue #20)

I timer non stanno più in memoria: vivono in `timers.json`, e sopravvivono a un
riavvio. Il piano li chiama «la funzione col costo di errore più alto» e detta
tre regole, tutte rispettate da `timer.py`:

- si salva la **scadenza assoluta**, mai i secondi rimanenti, così cinque minuti
  di spegnimento non allungano un timer di dieci;
- il file si riscrive con un temporaneo più `rename`, che è atomico: una
  caduta di corrente a metà scrittura lascia il file vecchio intero, non mezzo
  file illeggibile;
- un timer scaduto mentre BMO era spento suona lo stesso, con un messaggio
  diverso.

Il cervello e la sveglia sono due processi che scrivono lo stesso file, quindi
ogni operazione prende un lock esclusivo (`flock`) su `timers.lock`: senza,
la sveglia che riscrive l'elenco cancellerebbe il timer appena aggiunto dal
cervello, e il difetto sarebbe silenzioso — un timer che non suona.

Dove sta il file: `/var/lib/bmo/` sul Pi, dove BMO è un servizio di sistema, e
`~/.local/state/bmo/` sul PC di sviluppo, dove scrivere in `/var/lib` vorrebbe
i permessi di root. `BMO_DATI` ha la precedenza su entrambi.

```bash
python -m bmo_core.sveglia                  # resta in piedi e fa suonare i timer
python -m bmo_core.sveglia --intervallo 1   # controlla ogni secondo invece di mezzo
python -m bmo_core.sveglia --tono FILE      # un suono solo per questo avvio
BMO_DATI=/tmp/prova python -m bmo_core.sveglia   # timer usa e getta, per le prove
```

**Il suono del timer** si sceglie mettendo un file in `<cartella dati>/suoni/`
(`timer.opus`, `.mp3`, `.ogg` o `.wav`), cioè `~/.local/state/bmo/suoni/` sul PC.
Se non c'è, BMO suona un tono generato da `mpv`, così funziona anche su una
macchina appena installata. `BMO_TONO` ha la precedenza, e `--tono` su tutto.

I file audio stanno **fuori dal repository**, che è pubblico: sono roba di terzi
e non vanno ridistribuiti. Le clip di BMO registrate col TTS di Gemini sono
l'issue #21 e useranno la stessa cartella.

La prova che conta (criterio di uscita della #20): far partire un timer, uccidere
il processo, riavviarlo e verificare che suoni all'ora giusta.

## La faccia dice cosa sta facendo BMO

BMO non ha pulsanti né spie, e fra la domanda e la risposta c'è del silenzio: la
faccia è l'unico modo di distinguere un BMO che sta elaborando da uno bloccato.
`brain.py` mostra `ascolto` mentre registra, `pensiero` per tutto il loop
agentico, e alla fine l'espressione scelta dal modello (`felice`, `pensieroso`,
…), oppure `parlato` se non ce n'è una e `errore-rete` se il turno finisce senza
risposta.

Sono due vocabolari diversi: le **espressioni** le sceglie il modello per la
risposta parlata, gli **stati della faccia** li decide il codice. Per ora
l'unica implementazione è `FacciaTerminale`, che scrive `[faccia: pensiero]`
sullo standard error (attiva nei comandi `brain` e `prova_frasi --voce`); il
disegno vero è l'issue #23 e sostituirà solo l'implementazione dell'adapter.

Le frasi di prova coprono timer, gestione dei timer, foto, musica e radio,
volume, pausa dell'ascolto, ricerche sul web (meteo, risultati) e
conversazione senza strumenti; alla fine il punteggio è diviso per categoria.

Il prompt predefinito è la bozza v4 (`prompt/bozza-v4.txt`, 40/40 nella prova
del 19/9). Le bozze in `prompt/` restano come storico: la v2 fece 23/40
perché il modello annunciava le azioni senza chiamare gli strumenti. Un nuovo
prompt si confronta col predefinito così:

```bash
python -m bmo_core.prova_frasi                           # prompt predefinito
python -m bmo_core.prova_frasi --prompt prompt/nuovo.txt
```

## Cascata di modelli (issue #12)

Se il modello primario risponde con quota esaurita (429) o sovraccarico
(500/502/503/504), `modelli.py` passa subito al modello successivo della
cascata. Quella predefinita è `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`;
si cambia con una variabile d'ambiente, senza toccare il codice:

```bash
# quali modelli ha a disposizione la tua chiave
python -c "from google import genai; c = genai.Client(); [print(m.name) for m in c.models.list() if 'flash' in m.name]"

export BMO_GEMINI_MODELLI="<primario>,<riserva>,..."
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
`GeminiNonDisponibile` dice il tipo (`quota`, `sovraccarico`, `rete`, `tempo`),
che sul dispositivo diventerà la frase e la faccia dello stato di errore. L'SDK
fa 2 tentativi per modello invece dei 5 predefiniti, per non aspettare 15 s prima
di cambiare modello; dentro il tetto del turno (#18) il tempo per due tentativi
non c'è quasi mai, quindi in pratica si passa subito alla riserva.

## Sviluppo

```bash
cd bmo-core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
