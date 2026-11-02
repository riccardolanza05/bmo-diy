# Decisioni aperte — issue #29 (memoria di sessione)

Le decisioni #1 (trascrizione via output strutturato) e #2 (voci manuali mai
sfrattate) di una versione precedente di questo file sono state prese
esplicitamente da Riccardo il 26/9 e sono già implementate — non compaiono
più qui. Resta aperta solo quella sotto. Le note puramente informative (non
decisioni) stanno in `docs/note-issue-29.md`.

## Compressione fallita al tetto di token: troncamento crudo

- **Implementato**: se il riassunto della conversazione (caso 2, tetto di
  token) fallisce per rete o quota, tenere lo storico intero manderebbe di
  nuovo lo stesso errore ad ogni turno successivo. Si tiene solo l'ultimo
  turno, buttando via quelli più vecchi non ancora riassunti.
- **Alternativa**: continuare a mandare tutto lo storico non compresso,
  accettando il rischio di ripetere lo stesso errore ogni turno finché la
  rete non torna; oppure chiudere la sessione del tutto in quel caso.

**Conseguenza della scelta**: nel caso raro in cui la compressione fallisce,
si perde il filo dei turni più vecchi di quella conversazione — non del
diario: dal 26/9 il diario si aggiorna solo alla chiusura vera della
sessione (caso 1), mai al tetto di token, quindi qui non c'è comunque
niente di permanente in gioco. Scelta per non rischiare di restare bloccati
a ripetere lo stesso 429 ad ogni turno.
