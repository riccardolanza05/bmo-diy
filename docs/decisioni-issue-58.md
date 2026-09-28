# Decisioni aperte — issue #58 (RAM sul Pi)

Misure e fatti verificati stanno in [`note-issue-58.md`](note-issue-58.md).
Qui ci sono solo le scelte: quelle già implementate con un valore
predefinito che si può cambiare, e quelle ancora da prendere.

**Già decisa e implementata (28/9), non più aperta**: la wake word non usa
più `openwakeword.Model` ma `wake_word.RilevatoreLeggero`, adattato dal suo
codice (Apache 2.0) e con punteggi identici. È la variante B della versione
precedente di questo file, con una correzione: i due modelli di feature non
vengono copiati nel repo, si leggono dalla cartella del pacchetto installato
da pip, senza importarlo. Così non si ridistribuisce niente e non c'è da
verificare nessuna licenza di modelli. bmo-core sul Pi: da 248 a 106 MB.

## 1. La voce: guadagno fisso al posto di `loudnorm` (implementato)

- **Implementato**: nel preset `radiolina`, quello predefinito, `loudnorm`
  è sostituito da un guadagno fisso di +6,4 dB più un limitatore a
  −1,5 dBFS, tarati su 25 frasi vere. Gli altri preset hanno ancora
  `loudnorm`.
- **Alternativa**: tornare a `loudnorm`.

**Conseguenza della scelta**: mpv mentre BMO parla passa da 60 a 33 MB e usa
circa un quarto della CPU. Sul Pi questo conta doppio, perché nello stesso
momento la wake word occupa già ~40% di un core. Sulla carta il volume medio
è lo stesso (−18,5 contro −18,4 LUFS) e le frasi sono persino più uniformi,
ma **non l'hai ancora sentita**: `loudnorm` in un passaggio solo cambiava il
volume dentro la frase, il guadagno fisso no. Se all'ascolto il timbro o il
volume ti suonano diversi, si torna indietro cambiando una riga
(`_GUADAGNO_RADIOLINA` in `adapters/audio_output.py`).

## 2. Lo "streaming dalla SD": zram con scrittura sul file (`zram+file`)

- **Oggi**: swap solo in zram (RAM compressa), il predefinito di Raspberry
  Pi OS. Non implementato niente.
- **Alternativa consigliata**: `Mechanism=zram+file` in
  `/etc/rpi/swap.conf.d/`. È il meccanismo ufficiale di `rpi-swap` per
  quello che chiamavi "SSD streaming": le pagine di memoria rimaste inattive
  a lungo vengono spostate dalla zram a un file di swap sulla SD. Per
  default la prima volta dopo 3 ore dall'avvio, poi ogni 24 ore.
- **Altra alternativa**: swap su file classico sulla SD (`swapfile`).

**Conseguenza della scelta**: quello che si può "streammare" dalla SD si
divide in due.

- **La memoria su file** (codice delle librerie, modelli) ci va già oggi,
  gratis: il kernel la scarta quando serve spazio e la rilegge dalla scheda.
  Nella prova di carico è circa il 28% del totale.
- **La memoria anonima** (oggetti Python, buffer) può andare sulla SD solo
  come swap. Con la microSD misurata (22,8 MB/s in sequenziale, 1430
  letture casuali da 4 KiB al secondo, 0,65 ms ciascuna) rileggere 10 MB di
  pagine sparse costa ~1,7 s: accettabile per pagine fredde (il codice di
  una funzione usata una volta al giorno), non per quelle calde. La wake
  word gira ogni 80 ms e non finirebbe mai sulla SD.

`zram+file` scrive solo pagine inattive da ore e solo una volta al giorno,
quindi consuma poco la scheda. `swapfile` scriverebbe invece a ogni picco, e
consumerebbe la SD in un dispositivo acceso 24/7. **Consiglio**: attivare
`zram+file` solo se la fase 2.3 (24 h sul Pi) mostra che la zram si riempie.
Con le ottimizzazioni di oggi probabilmente non servirà.

## 3. Quanti modelli wake word in produzione

- **Oggi**: tre (`bmo1`, `bmo2`, `bmo3`).
- **Alternativa**: uno solo, il migliore dopo la taratura nella stanza vera
  (fase 4.4).

**Conseguenza della scelta**: sulla RAM e sulla CPU quasi niente (~1 MB e
~0,4 s di CPU su 20 s di audio, misurati sul Pi). È una scelta di qualità
del rilevamento: con tre modelli scatta se uno qualsiasi supera la soglia,
quindi più rilevamenti veri ma anche più falsi positivi. Da decidere con i
dati della fase 4.4.

## 4. SDK `google-genai` o chiamate REST dirette

- **Oggi**: l'SDK ufficiale. Sul Pi `import google.genai` vale +43–46 MB,
  quasi tutti da `google.genai.types` (le definizioni pydantic dell'intera
  API, più aiohttp e websockets che BMO non usa).
- **Alternativa**: chiamate HTTP dirette con `httpx`, che è già una
  dipendenza.

**Conseguenza della scelta**: dopo le ottimizzazioni è la voce più grossa
rimasta dentro bmo-core, circa 40 dei suoi 106 MB. In cambio va riscritto il
livello di trasporto di `brain.py`, che usa i tipi dell'SDK ovunque (loop
agentico, storico, trascrizione), e vanno seguiti a mano i cambiamenti
dell'API. **Consiglio**: non ora. Solo se la fase 2.3 sfora.

## 5. Alpine Linux e riscrittura in Rust/C

- **Oggi**: Raspberry Pi OS trixie, Python.
- **Consiglio**: no a entrambe, a maggior ragione dopo le misure del 28/9.

**Conseguenza della scelta**:
- **Alpine**: toglierebbe 20–40 MB di sistema, ma onnxruntime su Alpine
  esiste solo nel ramo `edge` e non ha pacchetti per musl su PyPI.
- **Rust**: toglierebbe forse altri 60 MB da bmo-core, al prezzo di
  riscrivere ~5.200 righe e 346 test.

Le ottimizzazioni di oggi hanno liberato di più di quanto avrebbe dato
Alpine, e senza cambiare linguaggio. Restano valide solo come ultima
risorsa se la fase 2.3 sfora anche dopo la decisione 4.
