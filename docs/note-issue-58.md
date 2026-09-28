# Note — issue #58 (RAM sul Pi)

Misure del 27/9/2026. L'analisi e gli spunti stanno nel testo della issue
#58; qui ci sono i numeri grezzi e come ripeterli.

## Come sono state prese

- **Pi**: Raspberry Pi 3 A+, Raspberry Pi OS trixie, dopo l'irrobustimento
  della #25 (331 MB disponibili a riposo). Python 3.13.5, dipendenze di
  bmo-core installate con `pip` in un venv (`numpy 2.5.3`, `onnxruntime
  1.30.0`, `openwakeword 0.4.0`, `google-genai 2.25.0`), bmo-core e bmo-face
  copiati dal master del 27/9.
- **Script**: [`pi/peso_bmo_core.py`](../pi/peso_bmo_core.py) e
  [`pi/peso_bmo_face.py`](../pi/peso_bmo_face.py), che leggono RSS e PSS
  del proprio processo dopo ogni tappa. Nessuna chiamata di rete: il client
  Gemini viene solo costruito, con una chiave finta.
- **PC** (omarchy, x86_64, Python 3.14): [`bmo_core.misura_ram`](../bmo-core/src/bmo_core/misura_ram.py)
  su `python -m bmo_core.macchina --wake-word` vero, microfono aperto.

## bmo-core sul Pi, com'è oggi

| tappa | RSS | Δ | PSS | tempo |
|---|---|---|---|---|
| Python nudo | 10 | | 8 | |
| numpy + onnxruntime | 44 | +34 | 41 | 0,8 s |
| `import openwakeword` | 136 | **+92** | 130 | 7,1 s |
| `import google.genai` | 170 | +34 | 164 | 4,2 s |
| `bmo_core.macchina` (edge_tts, ddgs, …) | 173 | +3 | 167 | 0,3 s |
| 3 modelli wake word caricati | 248 | **+75** | 242 | 3,8 s |
| 50 finestre di ascolto (4 s di audio) | 249 | +1 | 243 | 1,7 s |
| `Cervello` costruito | 251 | +2 | 245 | 0,4 s |
| altre 250 finestre (20 s di audio) | 254 | +3 | **248** | 9,5 s |

## bmo-core sul Pi, alleggerito (`--leggero`)

| tappa | RSS | Δ | PSS |
|---|---|---|---|
| numpy + onnxruntime | 44 | +34 | 41 |
| `import openwakeword` senza verificatore | 46 | **+2** | 44 |
| `import google.genai` | 89 | +43 | 83 |
| 3 modelli caricati, ONNX senza arena | 108 | **+18** | 102 |
| dopo 24 s di ascolto e `Cervello` | 114 | | **108** |
| — con 1 modello invece di 3 | 112 | | 106 |

I punteggi della wake word sono **identici fino alla nona cifra decimale**
con e senza alleggerimento. Verificato sul PC su 12 clip di parlato vero
(10 risposte di BMO dalla cache della voce e 2 frasi «Hey BMO» sintetizzate
con edge-tts), confrontando per ogni modello sia il punteggio massimo sia
la somma su tutte le finestre da 80 ms. Nelle due clip «Hey BMO» `bmo3`
arriva a 0,73 e 0,57, sopra la soglia di 0,5: il confronto copre anche il
caso in cui la wake word scatta, non solo il silenzio.

## bmo-face sul Pi (senza GTK)

| tappa | RSS | PSS |
|---|---|---|
| Python nudo | 10 | 8 |
| numpy + PIL + animazione + socket | 36 | 31 |
| asset mappati (`faces.bin`, 2,3 MB, `mmap`) | 36 | 31 |
| dopo 100 fotogrammi | 39 | **33** |

Manca l'uscita SPI (`spidev`/`luma.lcd`, fase 4.7), che aggiungerà qualche MB.

## Sul PC

`bmo_core.macchina --wake-word` con tre modelli, a riposo per 40 s:
**bmo-core 276 MB PSS**, arecord 3 MB. Con un modello solo: ~279 MB RSS,
quasi uguale: il costo non sta nei modelli dei classificatori ma in
openwakeword + le arene ONNX. I numeri del PC sono più alti di quelli del
Pi (Python 3.14 contro 3.13, x86_64 contro aarch64, librerie diverse): per
il budget valgono **le misure sul Pi**, il PC serve per confrontare prima e
dopo una modifica.

Prova di fumo di `./avvia_demo.sh --misura-ram` (tutto BMO, ~25 s con un
paio di turni veri): picco **380 MB PSS** in totale, di cui bmo-core 267,
bmo-face 67 (con GTK), mpv 52, arecord 3.

## Cosa non è ancora misurato sul Pi

- **mpv**: non è installato sul Pi. Il bilancio usa i ~35 MB stimati dal
  piano, ma sul PC mpv ha toccato 52 MB. Il margine di ~150 MB calcolato
  nella issue per bmo-core alleggerito dipende da questo numero.
- **I picchi di un turno**: audio registrato, risposta JSON, foto, voce
  decodificata. Tutto sopra è misurato a riposo in ascolto. La fase 2.3 (con
  l'audio letto da WAV) è il posto per misurarli, con `bmo_core.misura_ram`.
- **bmo-face con l'uscita SPI**, che arriva alla fase 4.7.

## CPU della wake word

Sul Pi, 250 finestre da 80 ms (20 s di audio) richiedono ~9,5 s di calcolo,
con 1 o con 3 modelli: ~47% di un core, sempre, finché BMO ascolta.

## Alpine e onnxruntime

Verificato il 27/9: su PyPI `onnxruntime 1.30.0` pubblica 6 ruote
`manylinux` per aarch64 e **nessuna** `musllinux`, mentre numpy e scipy le
hanno. Su Alpine il pacchetto `py3-onnxruntime` esiste **solo nel ramo
`edge`** (community, aarch64), in nessuna versione stabile.

## 28/9 — prova di carico e ottimizzazioni

### La prova di carico (`bmo_core.carico`)

BMO intero (macchina a stati, Gemini vero, radio, voce, suoni, sveglia,
faccia, webcam), con un microfono che suona in tempo reale frasi
sintetizzate: 16 richieste che accumulano carico (due timer, radio accesa,
due foto, ricerca, `ricorda` con conferma, racconto lungo, inglese, cambio e
salvataggio di stazione), ripetute per `--giri`. Sul PC si lancia con
`avvia_carico.sh` nel worktree demo, che apre bmo-face e misura la RAM. La
wake word sulla voce sintetica scatta solo a volte: il turno parte lo
stesso, qui si misura la memoria.

### Sul PC: stessa sequenza, 2 giri (32 turni, ~11 min), prima e dopo

| picco PSS | prima | dopo (wake word + mpv) |
|---|---|---|
| **totale** | **530 MB** | **345 MB** |
| bmo-core | 338 | 182 |
| mpv (radio + voce insieme) | 161 | 126 |
| bmo-face (con GTK) | 68 | 68 |

La voce senza `loudnorm` (sotto) non era ancora compresa: vale altri
~27 MB in ogni momento in cui BMO parla.

**L'mpv della radio cresceva di ~5,5 MB al minuto** (da 52 a 107 MB in 10
minuti): la cache predefinita di mpv tiene fino a 50 MiB di stream già
ascoltato. Con `--demuxer-max-back-bytes=0 --cache-secs=10` non cresce più.

### Sul Pi: bmo-core ottimizzato (`pi/peso_bmo_core.py`, tre modelli)

| tappa | PSS |
|---|---|
| numpy + onnxruntime | 41 |
| `google.genai` | 84 |
| tre modelli caricati (picco transitorio all'avvio) | 153 |
| a regime, dopo 24 s di ascolto | **106** (prima: 248) |

Nessuno fra openwakeword, scikit-learn, scipy caricato. CPU della wake word:
20 s di audio in 7,9 s (prima 9,5 s), ~39% di un core.

### mpv e la voce

| mpv che dice una frase lunga | PSS | CPU |
|---|---|---|
| opzioni predefinite, catena con `loudnorm` | ~74 (RSS, 23/9) | |
| opzioni leggere, catena con `loudnorm` | 60 | 1,7 s |
| opzioni leggere, guadagno fisso + limitatore | **33** | ~0,4 s |

Il guadagno fisso (+6,4 dB, limitatore a −1,5 dBFS) è tarato su 25 frasi
vere: volume medio −18,5 LUFS contro −18,4 della catena con `loudnorm`,
stesso picco, frasi più uniformi (2,7 dB di escursione contro 7,7).

### La microSD (`pi/velocita_sd.py`, O_DIRECT)

| | microSD del Pi | NVMe del PC, per confronto |
|---|---|---|
| lettura sequenziale | **22,8 MB/s** | 902 MB/s |
| scrittura sequenziale | 18,8 MB/s | 489 MB/s |
| lettura casuale 4 KiB | **1430/s (5,9 MB/s)** | 7343/s |
| latenza di una lettura casuale | mediana 0,65 ms, max 4,1 ms | 0,12 ms |

Scheda SDHC in modalità «high speed» (il limite del bus del Pi 3 è ~25 MB/s).

### mpv sul Pi (mpv 0.40, `pi/peso_mpv.py`, uscita audio nulla)

| | picco PSS | CPU |
|---|---|---|
| voce (frase di 25 s), mpv normale, con `loudnorm` | 88 MB | 6,6 s |
| voce, mpv leggero, con `loudnorm` | 75 MB | 6,4 s |
| **voce, mpv leggero, guadagno fisso** | **48 MB** | **2,2 s** |
| radio (30 s di stream), mpv normale | 58 MB, poi cresce | 2,8 s |
| **radio, mpv leggero + cache corta** | **47 MB**, non cresce | 2,0 s |

Tutte le opzioni leggere sono accettate da mpv 0.40 (quello di trixie).

### Il bilancio sul Pi, radio accesa mentre BMO parla (il caso peggiore a regime)

| | prima (27/9) | dopo (28/9) |
|---|---|---|
| bmo-core | 248 | 106 |
| bmo-face senza GTK | 33 | 33 |
| mpv radio | 58 e oltre | 47 |
| mpv voce | 88 | 48 |
| arecord | 3 | 3 |
| **totale** | **≥ 430 MB su 331: OOM** | **~237 MB su 331** |

Prima, radio e voce insieme non ci stavano. Ora restano ~95 MB per i picchi
di un turno (audio registrato, foto, risposta), che sono l'ultima cosa da
misurare sul Pi: la fase 2.3, con `bmo_core.carico`.

In entrambe le prove sul PC (prima e dopo) nessun errore e 33–34 risposte
parlate su 32 turni: le ottimizzazioni non hanno rotto niente di visibile.
