# Decisioni prese durante l'issue #65 (24 h sul Pi)

Decisioni mie, prese per non bloccare il lavoro: opzioni valutate, cosa è
implementato di default, conseguenze concrete di scegliere l'altra opzione.
Le misure vere stanno in [`note-issue-65.md`](note-issue-65.md).

## 1. Come dosare le richieste Gemini per una prova di 24 h

`bmo_core.carico` fa tutti i giri di seguito per costruzione (§58): a
~20 richieste/giro e ~5,5 min/giro, 24 h senza pause farebbero circa
5.200 richieste — troppe per il free tier, quale che sia l'RPD esatto.

**Opzioni:**
- (a) *Pausa fissa fra un giro e l'altro*, con un `time.sleep` semplice.
- (b) *Pausa "attiva"*: durante la pausa, la wake word continua ad ascoltare
  il silenzio (stesso costo di CPU della wake word sempre accesa in
  produzione, ~39% di un core), invece di addormentare tutto il processo.

**Implementato: (b)** — `tieni_viva_la_wake_word()` in `carico.py`, dietro
`--pausa-minuti` (0 di default: nessun cambiamento per chi già usa
`carico.py` senza l'opzione). Riusa `RichiamoWakeWord.ascolta_punteggio()`
già esistente, chiamato ripetutamente finché non passano i minuti richiesti:
ogni chiamata consuma un buffer di silenzio a ritmo reale
(`MicrofonoCopione.flusso_pcm`, ~4,4 s), quindi il punteggio della wake word
viene ricalcolato per tutta la pausa, non solo durante i turni.

**Conseguenza di (b) invece di (a):** la misura di temperatura/throttling
della checklist («wake word sempre accesa, ~39% di un core») è rappresentativa
anche durante le pause, non solo durante i 20 giri effettivi — con (a) il Pi
sarebbe stato quasi tutto il tempo idle, sottostimando il carico reale. Il
prezzo è che la prova di 24 h consuma più CPU del minimo indispensabile per
mandare le richieste Gemini: accettabile, è proprio quello che la checklist
chiede di misurare.

**Il numero scelto — `--giri 24 --pausa-minuti 55`** (≈24,2 h reali,
≈480 richieste/giorno) è una stima prudente, non una cifra confermata: non
ho trovato un RPD pubblico affidabile per `gemini-3.5-flash-lite` o
`gemini-3.1-flash-lite` (cercato il 29/9/2026, vedi sotto). Se il log della
unit mostra errori 429, va aumentato `--pausa-minuti` (parametro della unit
systemd, non del codice).

## 2. Come misurare i "picchi", vero criterio della fase 2.3

L'evento del 28/9 (un fork breve di `mpv` sfuggito al campionatore a
intervalli fissi di `bmo_core.misura_ram`) mostra che campionare a intervalli
fissi può mancare un picco breve.

**Opzioni:**
- (a) Solo `bmo_core.misura_ram --cerca bmo_core`, più fitto (es. ogni 1-2 s)
  per ridurre la probabilità di mancare un picco.
- (b) Leggere `memory.peak` della cgroup systemd della unit: un contatore che
  il kernel aggiorna lui stesso al vero picco istantaneo dalla creazione
  della cgroup, mai perso indipendentemente da quando/quanto spesso lo si
  legge.

**Implementato: (b)**, in un nuovo script (`pi/misura_sistema_24h.py`), **in
aggiunta a** (a) che resta comunque utile per la scomposizione per componente
(bmo-core vs mpv vs arecord) che `memory.peak` da solo non dà. Non è stato
necessario azzerare `memory.peak` a ogni campione (scartata l'idea di
scriverci "0", possibile dal kernel 6.12 in su — quello del Pi è 6.18): per
il criterio "picco assoluto in tutta la corsa" un contatore mai azzerato dà
la stessa risposta, con uno script più semplice e senza bisogno di permessi
di scrittura sul file cgroup.

**Conseguenza:** la calibrazione breve (`bmo-carico-calibrazione.service`,
2 giri senza pausa) e la prova di 24 h usano cgroup separate (unit diverse),
quindi ciascuna ha il proprio `memory.peak` "da zero" — non serve altro per
isolare "il picco durante i due giri di calibrazione" dal "picco in tutte le
24 h".

## 3. `MemoryMax` delle nuove unit diagnostiche: non 280 M come in produzione

**Opzioni:**
- (a) Stesso `MemoryMax=280M` di `bmo-core.service`, per verificare fin da
  subito se il vincolo di produzione regge.
- (b) Un tetto più largo (scelto: 400M, il Pi ne ha 462Mi totali), solo come
  rete di sicurezza contro una perdita di memoria vera.

**Implementato: (b).** Con (a), se un picco superasse 280 MB il cgroup
ucciderebbe il processo esattamente nel momento che si vuole misurare,
troncando `memory.peak` all'ultimo valore prima del kill invece di mostrare
quanto sarebbe salito davvero. Il criterio dell'issue («picco < 320 MB») si
verifica confrontando il numero misurato con 400M di margine, non
imponendolo come limite duro durante la misura stessa.

## 4. Le nuove unit restano fuori da `deploy.sh`

Installazione manuale (comandi nel commento di ciascun file `.service`), non
integrata nello script della #16. Sono diagnostiche, non fanno parte del
funzionamento normale di BMO: aggiungere logica di deploy per unit che si
useranno una volta sola (per questa issue) sarebbe scope creep rispetto a
quello che la #65 chiede.
