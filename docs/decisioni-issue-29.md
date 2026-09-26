# Decisioni aperte — issue #29 (memoria di sessione)

Scelte prese in autonomia durante l'implementazione, con l'opzione più
prudente come default, da rivedere quando la #29 sarà provata dal vivo con
`python -m bmo_core.brain --conversazione`. Le note puramente informative
(non decisioni) stanno in `docs/note-issue-29.md`.

## 1 · Trascrizione del turno: ripiego, non "output strutturato"

L'issue proponeva due strade per sapere cosa ha detto la persona (serve allo
storico, non alla risposta):

- **Implementato**: una seconda chiamata Gemini minuscola e dedicata
  (`Cervello._trascrivi`, prompt `ISTRUZIONE_TRASCRIZIONE`), come indicato
  dall'issue come "ripiego". Gira da `dopo_il_turno()`, cioè **dopo** che
  BMO ha già parlato: non allunga il tempo di risposta, allunga solo quanto
  BMO impiega a essere di nuovo pronto ad ascoltare. `dopo_il_turno()` può
  incatenare fino a quattro richieste (trascrizione, estrazione pendente,
  estrazione e riassunto del tetto) sotto un unico budget condiviso
  (`BUDGET_DOPO_IL_TURNO_S`, 8 secondi): nel caso comune (una sola
  trascrizione, tutto liscio) è questione di frazioni di secondo; nel caso
  peggiore (sovraccarico, tutte e quattro le richieste in coda) può arrivare
  fino agli 8 secondi pieni, oltre i quali le richieste rimaste in coda
  falliscono con lo stesso trattamento di un errore di rete.
- **Alternativa (non tentata)**: far restituire al modello principale
  trascrizione e risposta nello stesso output strutturato, eliminando la
  richiesta in più del tutto. L'issue stessa la segnalava "da verificare che
  funzioni insieme al function calling sui modelli Flash-Lite": verifica che
  richiede una chiave Gemini vera e prove dal vivo, non disponibili in
  questa sessione.

**Conseguenza della scelta**: un turno ad audio costa oggi una chiamata
Gemini in più (quota, non latenza percepita della risposta) rispetto al
minimo teorico, e BMO resta sordo per una frazione di secondo in più prima
di poter essere richiamato. Se in pratica risulta un problema di quota,
vale la pena tornare sull'output strutturato — ma solo dopo averlo provato
dal vivo.

## 2 · Diario (#14): protezione delle voci scritte a mano dallo sfratto

`memoria.aggiungi_voce` tiene solo le ultime `MAX_VOCI` (30) voci, qualunque
sia la loro `fonte`. L'estrazione di fine sessione (#29) può quindi, nel
tempo, far sfrattare voci scritte a mano da Riccardo via SCP (`fonte="manuale"`)
per far posto a fatti estratti automaticamente.

- **Implementato**: nessuna protezione — lo sfratto resta quello di prima,
  identico per ogni fonte. Le mitigazioni aggiunte (vedi `docs/note-issue-29.md`)
  riducono quante voci nuove un'estrazione può scrivere (al massimo
  `MAX_VOCI_PER_ESTRAZIONE`, 3 per chiamata) e le dedup, ma non proteggono
  le voci manuali da uno sfratto lento nel tempo.
- **Alternativa**: cambiare `memoria.MAX_VOCI` (o `aggiungi_voce`) per
  contare lo sfratto solo fra voci della stessa fonte, o per tenere le voci
  manuali indipendentemente dal tetto.

**Conseguenza della scelta**: è una modifica al comportamento della #14, non
solo della #29 — cambia una regola già in produzione, non solo il codice
nuovo di questa issue. Lasciata a Riccardo perché è lui a scrivere voci
manuali e a sapere se gliene sono già sparite.

## 3 · Compressione fallita al tetto di token: troncamento crudo

- **Implementato**: se il riassunto della conversazione (caso 2b) fallisce
  per rete o quota, tenere lo storico intero manderebbe di nuovo lo stesso
  errore ad ogni turno successivo (l'estrazione verso il diario, caso 2a, è
  un tentativo separato e può essere già andata a buon fine anche se questa
  fallisce). Si tiene solo l'ultimo turno, buttando via quelli più vecchi
  senza un riassunto.
- **Alternativa**: continuare a mandare tutto lo storico non compresso,
  accettando il rischio di ripetere lo stesso errore ogni turno finché la
  rete non torna; oppure chiudere la sessione del tutto in quel caso.

**Conseguenza della scelta**: nel caso raro in cui la compressione fallisce,
si perde il filo dei turni più vecchi di quella conversazione. Scelta per
non rischiare di restare bloccati a ripetere lo stesso 429 ad ogni turno.
