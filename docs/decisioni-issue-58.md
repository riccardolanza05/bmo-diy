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

## Decise da Riccardo il 28/9

- **La voce senza `loudnorm` va bene.** Resta il guadagno fisso nel preset
  `radiolina` (+6,4 dB e limitatore), sentito dal vivo.
- **Swap `zram+file` solo se serve.** Non si attiva ora: lo si attiva solo
  se la misura di 24 ore sul Pi (fase 2.3) mostra che la zram si riempie.
  Il meccanismo è quello ufficiale di `rpi-swap`: `Mechanism=zram+file` in
  un file dentro `/etc/rpi/swap.conf.d/`, poi riavvio. Motivi e misure della
  microSD in [`note-issue-58.md`](note-issue-58.md).
- **In produzione tre modelli di wake word** (`bmo1`, `bmo2`, `bmo3`). Sulla
  RAM e sulla CPU la differenza con uno solo è trascurabile (~1 MB, misurato
  sul Pi). `bmo3` resta fuori dal repo come deciso il 26/9, quindi lo
  script di deploy (#16) deve copiarlo sul Pi a parte e passarlo con
  `--modello-wake-word`.

## Ancora aperte

### 1. SDK `google-genai` o chiamate REST dirette

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

### 2. Alpine Linux e riscrittura in Rust/C

- **Oggi**: Raspberry Pi OS trixie, Python.
- **Consiglio**: no a entrambe, a maggior ragione dopo le misure del 28/9.

**Conseguenza della scelta**:
- **Alpine**: toglierebbe 20–40 MB di sistema, ma onnxruntime su Alpine
  esiste solo nel ramo `edge` e non ha pacchetti per musl su PyPI.
- **Rust**: toglierebbe forse altri 60 MB da bmo-core, al prezzo di
  riscrivere ~5.200 righe e 346 test.

Le ottimizzazioni di oggi hanno liberato di più di quanto avrebbe dato
Alpine, e senza cambiare linguaggio. Restano valide solo come ultima
risorsa se la fase 2.3 sfora anche dopo la decisione 1.
