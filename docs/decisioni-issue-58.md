# Decisioni aperte — issue #58 (RAM sul Pi)

Nessuna ottimizzazione è ancora implementata: la PR #59 porta solo gli
strumenti di misura e i numeri. Queste sono le scelte che servono per
andare avanti, con quello che comporta ciascuna. Misure e fatti verificati
stanno in [`note-issue-58.md`](note-issue-58.md), l'analisi completa nel
testo della issue #58.

## 1. Alleggerire la wake word: come

Il guadagno è misurato sul Pi: bmo-core da **248 a 108 MB**, con punteggi
identici fino alla nona cifra su 12 clip di parlato (comprese due «Hey
BMO» in cui `bmo3` arriva a 0,73). Resta da scegliere il modo.

- **A · Modulo fittizio.** Prima di importare openwakeword si mette in
  `sys.modules` un `openwakeword.custom_verifier_model` vuoto, e le sessioni
  ONNX si creano senza arena e a un thread. ~15 righe in `richiamo.py`.
  *Conseguenza*: il più rapido e il più piccolo, ma dipende da come è scritto
  oggi `openwakeword/__init__.py` (0.4.0): un aggiornamento che sposta
  quell'import rompe il trucco in silenzio, e la RAM torna su senza errori.
  scikit-learn e scipy restano installati sul Pi (207 MB di microSD misurati,
  non di RAM). Serve un test che fallisca se `sklearn` finisce in `sys.modules`.
- **B · Pipeline propria, niente dipendenza.** Si riscrive la parte di
  openwakeword che serve (melspettrogramma ONNX → embedding ONNX → i
  classificatori, ~100 righe), adattandola da `openwakeword/utils.py`
  invece di reinventarla, e si toglie `openwakeword` dalle dipendenze
  (restano numpy e onnxruntime, che ci sono già).
  *Conseguenza*: più lavoro (mezza giornata con i test di confronto dei
  punteggi), ma niente più scipy e scikit-learn installati, nessun trucco
  fragile, e il controllo completo di come si creano le sessioni ONNX. I due
  modelli di feature (`melspectrogram.onnx`, `embedding_model.onnx`) vanno
  copiati nel repo accanto ai modelli `bmo*.onnx`, o scaricati
  all'installazione: **prima va verificata la loro licenza** (openwakeword
  distribuisce alcuni modelli con licenza non commerciale, e il repo è
  pubblico).
- **C · Niente, per ora.** Si aspetta la fase 2.3.
  *Conseguenza*: sul Pi resterebbero ~10 MB di margine a riposo con mpv
  acceso: la misura della 2.3 fallirebbe quasi certamente al primo turno.

**Consiglio**: B. A regge come prova, ma per un dispositivo acceso 24/7 un
risparmio che sparisce in silenzio a un aggiornamento è il rischio sbagliato.

## 2. Quanti modelli wake word in produzione

- **Oggi**: tre (`bmo1`, `bmo2`, `bmo3`), tutti caricati insieme.
- **Alternativa**: uno solo, il migliore dopo la taratura nella stanza vera
  (fase 4.4).

**Conseguenza della scelta**: sulla RAM quasi niente (~2 MB di differenza,
misurato) e nemmeno sulla CPU (il costo sta nel melspettrogramma e
nell'embedding condivisi). Quindi è una scelta di **qualità del
rilevamento**: tre modelli fanno scattare BMO se uno qualsiasi supera la
soglia, quindi più rilevamenti veri ma anche più falsi positivi. Nella prova
di fumo del 27/9 (microfono aperto per ~25 s, nessuno che lo chiamasse di
proposito) BMO si è attivato più volte: non so se fossero falsi positivi o
voci nella stanza. Da decidere con i dati della fase 4.4, non ora.

## 3. SDK `google-genai` o chiamate REST dirette

- **Oggi**: l'SDK ufficiale (+34–43 MB misurati sul Pi).
- **Alternativa**: chiamate HTTP dirette all'API REST di Gemini con `httpx`,
  che è già una dipendenza.

**Conseguenza della scelta**: ~35–40 MB in meno, al prezzo di riscrivere il
livello di trasporto di `brain.py` (che usa i tipi dell'SDK ovunque) e di
seguire a mano i cambiamenti dell'API invece di aggiornare un pacchetto.
**Consiglio**: non ora. Rivalutare solo se, dopo la decisione 1, la misura
della fase 2.3 sfora ancora.

## 4. Alpine Linux al posto di Raspberry Pi OS

- **Oggi**: Raspberry Pi OS trixie, irrobustito dalla #25 (equivale a un
  Lite).
- **Alternativa**: Alpine, con solo le dipendenze del progetto.

**Conseguenza della scelta**: guadagno realistico **20–40 MB** (a riposo i
processi di sistema occupano ~20 MB, il kernel sarebbe lo stesso). In cambio:
onnxruntime non ha pacchetti per musl su PyPI e su Alpine esiste solo nel
ramo `edge`, non in una versione stabile; si perdono `rpi-swap` e gli
strumenti mantenuti da Raspberry Pi; il piano va riscritto per un altro
sistema. **Consiglio**: no. Se un giorno servisse un sistema più piccolo, il
passo sensato è un riflash Raspberry Pi OS Lite, stessa Debian e stessa glibc.

## 5. Riscrivere bmo-core in Rust, C o Go

- **Oggi**: Python.
- **Alternativa**: riscrittura, tutta o solo il pezzo sempre acceso
  (microfono + wake word).

**Conseguenza della scelta**: stima 30–50 MB per un bmo-core in Rust, cioè
~60–70 MB in meno rispetto alla decisione 1. onnxruntime, la libreria C++
che pesa davvero, resterebbe. Il costo è riscrivere ~5.200 righe e 341 test
e perdere la velocità di modifica che ha chiuso la milestone 1.
**Consiglio**: no, per ora. Rivalutare solo se la fase 2.3 sfora anche dopo
le decisioni 1 e 3. Il compromesso più economico sarebbe un piccolo
processo nativo solo per l'ascolto.
