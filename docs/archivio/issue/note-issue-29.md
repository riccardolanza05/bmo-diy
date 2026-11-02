# Note informative — issue #29 (memoria di sessione)

Cose da sapere su questa implementazione, non decisioni da prendere (quelle
sono in `docs/decisioni-issue-29.md`, quasi vuoto: Riccardo ha già deciso i
punti aperti principali il 26/9).

## Seconda versione (26/9): trascrizione inline, memoria selettiva

Su richiesta esplicita di Riccardo, dopo la prima bozza (due chiamate
separate, estrazione ad ogni scadenza) sono cambiate tre cose, tutte provate
dal vivo con una chiave Gemini vera:

- **Trascrizione nella stessa chiamata**, non più una seconda richiesta
  dedicata. Il primo giro di ogni turno ad audio scrive un blocco
  `[TRASCRIZIONE] ... \n===` prima di qualunque altra cosa — anche prima di
  chiamare uno strumento — grazie a un'eccezione esplicita aggiunta alla
  regola "non scrivere niente prima di uno strumento" del prompt fisso.
  **Prova dal vivo (26/9, gemini-3.5-flash-lite)**: senza l'eccezione
  esplicita, un turno italiano con richiesta di timer ha risposto a voce
  senza chiamare lo strumento (il modello ha interpretato l'istruzione di
  trascrizione come un'alternativa alla chiamata, non un'aggiunta prima).
  Con l'eccezione, 6 prove su 6 (italiano e inglese) hanno chiamato lo
  strumento correttamente, mantenendo il blocco di trascrizione. La seconda
  chiamata dedicata (`Cervello._trascrivi`, `ISTRUZIONE_TRASCRIZIONE`) resta
  solo come ripiego per quando il blocco manca dalla risposta — non
  osservato nelle prove dal vivo, ma non garantito da nessuna API.
- **Il diario si aggiorna solo alla chiusura vera della sessione** (scadenza
  per inattività), mai al tetto di token: a metà conversazione il tetto
  comprime soltanto, senza scrivere nulla di permanente. Quel che c'è da
  ricordare in quella conversazione arriva comunque al diario quando la
  sessione chiuderà per davvero (il riassunto della compressione resta nello
  storico e viene incluso nell'estrazione finale).
- **Estrazione molto più selettiva**: il prompt (`ISTRUZIONE_ESTRAZIONE`)
  ora dice esplicitamente che `NIENTE` deve essere la risposta più
  frequente, non l'eccezione, elenca cosa NON scrivere mai (azioni
  occasionali come timer, calcoli, meteo; cose vaghe o dette per scherzo;
  doppioni anche riformulati) e il tetto di voci per chiamata è sceso da 3 a
  2 (`MAX_VOCI_PER_ESTRAZIONE`). **Prova dal vivo (26/9)**: 8 conversazioni
  di prova (4 routine — timer, ora, meteo, barzelletta — più 4 con un fatto
  potenzialmente degno di nota) hanno dato l'esito atteso in tutti gli 8
  casi: `NIENTE` per le routine, un'estrazione concreta e breve per i fatti
  durevoli (allergie, abitudini ricorrenti, nome e gusti dichiarati
  esplicitamente), `NIENTE` anche per un evento occasionale non ricorrente
  (aver mangiato una pizza) — il prompt distingue correttamente un fatto
  durevole da un episodio isolato.
- **Le voci scritte a mano (`fonte="manuale"`) non vengono mai sfrattate**:
  `memoria.MAX_VOCI_AUTOMATICHE` conta solo le voci `fonte="modello"`. Una
  voce manuale resta nel diario per sempre, qualunque sia il suo numero.

## Un bug trovato e corretto durante le prove dal vivo

La prima versione del budget di tempo condiviso per le richieste silenziose
(`BUDGET_DOPO_IL_TURNO_S = 8.0`) era **sotto il minimo che il server Gemini
accetta** (10 secondi): ogni richiesta della catena (estrazione, riassunto,
trascrizione di ripiego) sarebbe arrivata con un timeout di 8 secondi o
meno e sarebbe stata rifiutata con un `400 INVALID_ARGUMENT`. L'errore
finiva dentro `except ERRORI_GEMINI`, quindi **in produzione il diario non
si sarebbe mai aggiornato, in silenzio**, senza nessun sintomo visibile se
non un diario che resta sempre vuoto. Scoperto grazie al banco di prova dal
vivo (il messaggio d'errore compare lì, su una richiesta diversa ma con lo
stesso problema di fondo), corretto portando il budget a 30 secondi e
aggiunta una prova offline dedicata
(`test_budget_dopo_il_turno_da_un_timeout_valido_per_gemini`) che lo
avrebbe intercettato prima di arrivare in produzione.

Anche il prompt di estrazione aveva lo stesso genere di problema in piccolo:
diceva esplicitamente di non scrivere mai informazioni di salute, ma la
prima prova dal vivo ha comunque estratto un'allergia dichiarata
("Ricordati che sono allergico alle arachidi" → "La persona è allergica
alle arachidi"). Il divieto era già nella prima stesura del prompt (non è
una regola nuova), ma formulato in modo abbastanza morbido da farsi
scavalcare quando l'informazione sembrava praticamente utile. Riformulato
in modo più netto (con allergie e diete esplicitamente elencate come
esempi di "salute") e riprovato dal vivo: 5/5 per allergia e dieta ora
rispondono `NIENTE`.

## Cose da sapere, invariate dalla prima versione

- **`dopo_il_turno()` va chiamato da chi usa `Cervello` direttamente.**
  `Macchina.turno()` lo fa già (dopo `self.voce(...)`), ma chi scrive un
  altro punto di ingresso e dimentica di chiamarlo perde silenziosamente lo
  storico di quel turno — nessun errore, semplicemente BMO non si ricorda
  più niente di quel turno al giro dopo.
- **`memoria.md` (#14) non era ancora documentato nel README** di `bmo-core`
  prima di questa issue: la sezione "Memoria di sessione" lo introduce di
  striscio ma non documenta lo strumento `ricorda` né la conferma vocale
  dell'#17. Non ampliato oltre perché fuori dallo scopo della #29.
- **La tabella `Struttura` in cima al README di `bmo-core`** era già
  disallineata prima di questa modifica: non l'ho toccata per non allargare
  lo scopo di questo PR.

## Verificato dal vivo in questa sessione (26/9, con una chiave Gemini vera)

- Trascrizione inline: 6/6 fra chiamate a strumento (timer, IT/EN) e
  risposte dirette (IT/EN), vedi sopra.
- Selettività dell'estrazione: 8/8 fra conversazioni routine e conversazioni
  con un fatto degno di nota, vedi sopra.
- **Trascrizione inline con audio vero** (non testo simulato):
  `edge_tts` → WAV 16 kHz mono → `Cervello.rispondi(audio_wav=...)` vero.
  IT e EN, chiamata a strumento: entrambe corrette, trascrizione inline
  catturata, nessun blocco `[TRASCRIZIONE]`/`===`/etichetta finito nella
  risposta parlata.
- **Il criterio di uscita dell'issue**, con audio vero, sullo stesso
  `Cervello`: turno 1 «Metti un timer di dieci minuti» → `imposta_timer(10)`;
  turno 2 «Anzi, mettilo a venti minuti» → BMO ha capito il riferimento al
  timer del turno prima, chiamando `annulla_timer` e poi `imposta_timer(20)`
  da solo, senza che nessuno glielo dicesse esplicitamente. Verificato.
- **La correzione del bug del timeout** (vedi sopra), verificata end-to-end
  con audio vero e `inattivita_sessione_s=0.0`: dopo due turni il diario
  contiene davvero la voce estratta — prima della correzione questo sarebbe
  fallito in silenzio con un 400.
- **Banco di prova storico** (`python -m bmo_core.prova_frasi`, le 43 frasi
  già validate dal progetto): rilanciato dopo la modifica al prompt fisso
  (l'eccezione aggiunta alla regola sugli strumenti, vedi sopra), per
  verificare che non abbia peggiorato il comportamento sulle frasi normali.
  **Esito: 35/35 corrette (100%)** sulle frasi che hanno avuto una risposta;
  8 escluse dal punteggio per errori transitori lato Gemini (sovraccarico
  "riprova fra poco", e un paio di `400 INVALID_ARGUMENT: Manually set
  deadline 6s is too short` — un problema preesistente, non introdotto da
  questa issue, nel calcolo del timeout di `modelli.CascataModelli` quando
  il tempo rimasto nel turno è poco: vale la pena aprirci un'issue a parte).
  Nessuna frase risposta è stata sbagliata: il prompt fisso modificato si
  comporta come quello originale sulle frasi normali.
