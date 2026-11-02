# Decisioni aperte — issue #23 (bmo-face in una finestra)

Questo file elenca le scelte prese come predefinite per poter consegnare
l'issue #23 senza fermarsi ad aspettare risposte a metà lavoro (vedi la
convenzione di sessione). Ognuna spiega cosa comporta scegliere diversamente,
così Riccardo può correggerle in un solo passaggio.

## 1. Il criterio di leggibilità (b) — serve il tuo giudizio, non è rimandabile al codice

**Correzione rispetto alla prima stesura di questo file**: "il caso peggiore"
dell'issue è il pannello **2.4" stesso** — è già il più piccolo nel BOM
(§1.3), non un pannello ancora più piccolo (non esiste ancora nel BOM). La
prima versione di questo file cercava il candidato sbagliato.

**Cosa è già pronto**: `bmo-face/README.md` spiega come costruire gli asset e
aprire la finestra; il comando per il criterio (b) è:

```bash
cd bmo-face
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m bmo_face.build_face --destinazione assets/
.venv/bin/python -m bmo_face.finestra --assets assets/ --carta-prova
```

`--carta-prova` mostra tre righe da 20 caratteri (non la faccia), quantizzate
come `faces.bin` (RGB565) — è quello il test, non la faccia stessa — e ne
salva anche una copia in `assets/carta_prova.png`.

Su questo laptop la finestra stamperà un avviso: il pitch dello schermo di
sviluppo (~0,177 mm/px) è più grosso di quello del pannello 2.4" target
(~0,153 mm/px), quindi l'immagine viene mostrata a 276×209 px invece che
320×240 — **sottocampionata**, meno nitida di quanto sarà il pannello vero.
La prova che ne segue è quindi più severa, non più ottimista, del display
reale: se le tre righe restano leggibili a mezzo metro così, lo saranno a
maggior ragione sul pannello.

**Perché non l'ho deciso io**: è letteralmente un giudizio ("è leggibile
questo testo a mezzo metro?") che solo chi guarda lo schermo può dare. Il
codice fornisce il dato di input (l'immagine alla dimensione fisica corretta,
con l'avviso quando è sottocampionata), non il verdetto.

**Cosa cambia in base alla risposta**: se il testo *non* è leggibile a questa
dimensione, è un segnale concreto contro il 2.4" (§1.3) prima di comprarlo —
esattamente il dato che l'issue chiede di produrre.

## 2. L'arte: placeholder geometrico di default, arte vera disponibile con `--sorgente` (aggiornato 26/9)

**Corretto rispetto alla prima stesura**: su richiesta esplicita di
Riccardo ("Voglio che sia uguale alla faccia di bmo della repo di
riferimento"), `build_face.py --sorgente cartella/` ora esiste davvero e
legge i fotogrammi veri del progetto di riferimento esterno
(`brenpoly/be-more-agent`) — non li copia nel repository (restano in una
cartella a parte, mai `git add`), ma li usa per costruire `faces.bin`. Il
placeholder geometrico di `arte_placeholder.py` resta il *default* di
`build_face.py` senza argomenti (serve a mantenere i test offline).

**La distribuzione pubblica resta un rischio aperto, non risolto da me**:
uso l'arte del riferimento e la cito (README, "Arte vera invece del
placeholder"), ma non decido se e come questo repository debba restare
pubblico con quell'arte dentro — quella è una scelta di Riccardo come
proprietario del progetto, non qualcosa che il codice possa decidere da solo.

**Limiti noti dell'arte vera** (diversi dal placeholder):
- Nessun overlay di pupille reattive al microfono, nessuna espressione del
  modello sovrapposta — le regioni geometriche del placeholder non
  corrispondono a dove stanno occhi/bocca in un'immagine importata.
- `timer` e `conferma` riusano `idle`/`ascolto`: il riferimento non ha
  cartelle proprie per questi due stati (non esistono nel suo vocabolario).
- Lo stato `errore-rete` è tagliato male (vedi README): l'icona del
  riferimento è pensata per tutta la larghezza, il ritaglio centrato la
  spezza.
- Solo 3 livelli di bocca (i fotogrammi `speaking` del riferimento), non un
  continuo: l'inviluppo RMS sceglie fra 3, non fra 5 come il placeholder.

## 3. Formato del countdown del timer: disegnato a runtime, non pre-cotto

**Impostato come predefinito**: lo stato `timer` disegna il numero
(minuti:secondi) con un font (Liberation Mono se disponibile, altrimenti il
bitmap predefinito di PIL) al momento del rendering, non come fotogrammi
pre-generati in `faces.bin`.

**L'alternativa**: pre-generare tutte le combinazioni di cifre come
fotogrammi — più fedele all'idea "zero decodifica a runtime" del piano
(§2.11), ma con un costo in RAM/spazio molto più alto per un beneficio
minimo (disegnare del testo è già economico) e nessun modo pratico di coprire
ogni countdown possibile in anticipo.

**Conseguenza**: sul Pi vero, disegnare testo a ogni tick del timer costa
qualche ciclo di CPU in più rispetto a un blit puro — non misurato ancora,
ma il countdown cambia una volta al secondo, non a 25 fps, quindi il costo
reale è probabilmente trascurabile.

## 4. La bocca durante `parlato` segue l'inviluppo reale, in un thread separato

**Impostato come predefinito**: `VoceTts` (macchina.py) calcola l'inviluppo
RMS della voce sintetizzata con `ffmpeg` (`inviluppo.py`) **in un thread a
parte**, avviato subito prima di far partire la riproduzione, così il calcolo
non si aggiunge alla latenza percepita di "primo suono" che l'issue #42 aveva
esplicitamente protetto (vedi il commento in `_stampa_tempi`, macchina.py, che
spiega perché leggere la durata dell'audio a ogni risposta era stato evitato).

**Conseguenza pratica**: nei primi fotogrammi di una battuta la bocca può
restare ferma finché il thread non ha finito di decodificare (tipicamente
sotto i 100 ms per una frase breve) — un'imperfezione visiva minore, mai un
ritardo nel far sentire la voce.

**L'alternativa**: calcolare l'inviluppo prima di avviare la riproduzione
(sincrono) — bocca perfettamente sincronizzata dal primo fotogramma, ma con
un ritardo reale nell'avvio del suono, la stessa cosa che l'issue #42 aveva
deciso di evitare.

## 5b. Lo scarto delle pupille e l'accento dell'espressione sono piccoli — da verificare insieme al punto 1

Non misurato con precisione: a 0,153 mm/px lo scarto delle pupille durante
`ascolto` è dell'ordine di ±1 mm, e l'accento sopra l'occhio destro durante
un'espressione è un arco di ~2 px di spessore. Non è detto che si vedano a
mezzo metro sul pannello vero, anche se il resto (occhi, bocca, il testo
della carta di prova) resta leggibile. Non li ho allargati perché non so
quanto dovrebbero essere vistosi senza il tuo giudizio — se nella stessa
sessione in cui guardi `--carta-prova` noti che pupille/espressione sono
invisibili, dimmelo e li ingrandisco (`arte_placeholder.overlay_pupille`,
`overlay_espressioni`).

## 5. `BMO_FACCIA=socket` è opt-in, non il default

**Impostato come predefinito**: `crea_faccia()` resta muta finché non si
imposta esplicitamente `BMO_FACCIA=socket`; `FacciaSocket` fallisce sempre in
silenzio se non trova nessuno in ascolto (mai un turno di conversazione rotto
perché la finestra non è aperta).

**L'alternativa**: rilevare automaticamente se il socket esiste e collegarsi
da solo — eviterebbe la variabile d'ambiente, ma introdurrebbe un
comportamento diverso a seconda di cosa gira in quel momento sulla macchina,
più difficile da prevedere nei test e nelle prove a voce.
