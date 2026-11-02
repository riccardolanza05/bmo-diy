# Note informative — issue #23 (bmo-face in una finestra)

Cose utili da sapere, ma che non richiedono una decisione: a differenza di
`decisioni-issue-23.md`, qui non c'è niente in sospeso.

## Il progetto di riferimento esterno ha già un renderer di facce, ma più semplice

`brenpoly/be-more-agent` (linkato in `docs/03-riferimenti-esterni.md`) ha un
suo sistema di facce: cartelle di PNG per stato, Tkinter, un timer fisso che
cicla i fotogrammi. Due differenze rilevanti:

- **Non ha un vero inviluppo RMS**: durante "speaking" sceglie a caso un
  fotogramma fra quelli disegnati, non segue l'audio vero. Il nostro design
  (bocca guidata dall'inviluppo reale) è più elaborato apposta — è un
  requisito esplicito di questa issue, non un'invenzione.
- **Non ha vincoli di RAM/bus SPI**: gira su un Pi 5 da 16 GB con schermo
  vero, quindi non serve niente come RGB565/mmap/manifesto/socket. Il nostro
  design più elaborato non è over-engineering: esiste perché il nostro Pi 3
  A+ da 512 MB e il bus SPI del display hanno vincoli che il riferimento non
  ha.

Il loro codice usa comunque un concetto di layer "overlay" separato dal
corpo (per loro: la foto scattata dalla camera, sovrapposta durante
thinking/speaking) — non lo stesso overlay di bocca/pupille/espressioni di
qui, ma conferma che l'idea di comporre più livelli sopra un fotogramma base
non è insolita.

## Correzione: il "caso peggiore" è il 2.4" stesso, non un pannello ancora più piccolo

Prima lettura sbagliata di questa nota: ho cercato nel BOM un pannello "poco
più di 2 pollici" distinto dal 2.4" già scelto, non trovandolo. Rileggendo,
il significato più semplice è che il 2.4" **è già** il pannello più piccolo
del BOM (le opzioni restano 2.4", 3.5", 5" — §1.3): il caso peggiore da
verificare è quello, non un ipotetico pannello ancora più piccolo che non
esiste. La risposta pratica è quindi il criterio (b) stesso — leggibilità a
mezzo metro **sul 2.4"**, con la modalità test-card della finestra
(`--carta-prova`, vedi `bmo-face/README.md`).

La pipeline resta comunque parametrica su risoluzione e dimensioni fisiche
(costa poco e non fa danno), quindi se in futuro comparisse davvero un
pannello più piccolo nel BOM, funzionerebbe senza modifiche — ma non è la
risposta al "caso peggiore" di cui parlava la richiesta originale.

## La città "Milano" resta hardcoded nel prompt — non è questa issue

Come già notato per l'issue #15: `brain.PROMPT_FISSO` dice ancora "vivi in
una casa a Milano". Non riguarda #23 (che è sulla faccia, non sul prompt di
sistema), segnalato solo perché è emerso di nuovo leggendo il codice
circostante durante questo lavoro.

## Due correzioni trovate con la prova dal vivo (26/9, dopo la prima finestra)

**Loop del wake word.** `openwakeword.Model` tiene un `prediction_buffer`
interno che sopravvive fra un ascolto e l'altro finché lo stesso `Model`
resta in vita (`RichiamoWakeWord` lo riusa per ogni giro): senza azzerarlo,
un rumore di fondo o la radio potevano far risuperare la soglia quasi
subito dopo un "Hey BMO" vero, con una cascata di richiami che esauriva i
limiti dell'API. Corretto con `rilevatore.reset()` a ogni ascolto
(`richiamo.py`), che è l'API pensata apposta per questo dalla libreria.

**Volumi indipendenti.** Nuovo modulo `volumi.py`: quattro canali (radio,
voce, timer, sistema) invece di un solo volume condiviso per tutto quello
che BMO emette. Radio e sistema cambiano subito (IPC di mpv per la radio,
`wpctl`/`amixer` per il sistema); voce e timer passano da un file
(`volumi.json` in `percorso_dati()`) perché `sveglia.py` gira in un
processo separato da `bmo-core` e non vedrebbe mai un attributo in RAM.
Verificato dal vivo con chiamate reali a Gemini (`prova_frasi.py`,
categoria "volume", 7/7): il modello sceglie il canale giusto dal
significato della frase, senza bisogno di toccare il prompt.
