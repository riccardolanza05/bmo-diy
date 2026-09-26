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

## Il "caso peggiore" di un pannello più piccolo di 2.4" non è nel BOM

Nessun documento del piano elenca oggi un pannello display più piccolo del
2.4" (le opzioni tracciate restano 2.4", 3.5", 5" — vedi §1.3). La pipeline
e la finestra sono state rese parametriche su risoluzione e dimensioni
fisiche proprio per reggere un eventuale pannello più piccolo senza dover
riscrivere codice, ma non esiste ancora un candidato preciso da verificare.

## La città "Milano" resta hardcoded nel prompt — non è questa issue

Come già notato per l'issue #15: `brain.PROMPT_FISSO` dice ancora "vivi in
una casa a Milano". Non riguarda #23 (che è sulla faccia, non sul prompt di
sistema), segnalato solo perché è emerso di nuovo leggendo il codice
circostante durante questo lavoro.
