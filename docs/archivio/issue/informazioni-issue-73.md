# Informazioni — issue #73 (cose da sapere, non da decidere)

Dettagli e numeri in [`note-issue-73.md`](note-issue-73.md); le decisioni in
[`decisioni-issue-73.md`](decisioni-issue-73.md).

## Cosa NON ho potuto verificare

- **I limiti veri (RPM, RPD, token) di ogni modello.** La documentazione
  ufficiale rimanda al pannello AI Studio (richiede login) e l'API non li
  espone. Quello che ho visto: il 429 dice *quale* quota è stata superata.
  Per `gemini-3.5-flash` e `gemini-3.6-flash` è
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, esaurita dopo circa 20
  richieste a testa: **stima ~20/giorno, non confermata**. Per i lite non ho
  visto alcun limite giornaliero (la prova di 24 h della #65 ha fatto ~480
  richieste senza 429). Se hai accesso al pannello, controlla i numeri veri.
- **Il banco di frasi completo sui due Flash in coda**: la quota giornaliera si
  è esaurita al primo turno. Di loro so solo: strumenti giusti 4/4 e 4/4 nelle
  misure di latenza, 1/1 al banco, audio sì per il `3.6-flash` (non verificato
  per il `3.5-flash`, la sonda cadde su 499/503/504). Il banco "dopo" non li ha
  messi alla prova.
- **L'orario di reset della quota giornaliera** (di solito mezzanotte, fuso
  del Pacifico: non verificato).
- **Il comportamento del Pi.** Tutte le misure sono dal laptop. I tempi di
  rete dal Pi (Wi-Fi del 3 A+) sono diversi, e la mia connessione era incerta.
- **La correlazione fra modelli** (se i 503 colpiscono tutti insieme): non si
  ricava dai dati della #65. I due scenari del simulatore sono il minimo e il
  massimo, il vero sta in mezzo.
- **Gemini 2.5**: compaiono nell'elenco dei modelli ma rispondono 404.

## Cose da sapere

- **Le mie prove hanno consumato la quota di oggi**: `3.5-flash` e `3.6-flash`
  restano a 429 fino al reset. Non è un guasto, ed è per questo che il banco
  "dopo" non li usa.
- **La chiave è una sola**: il laptop e il Pi la condividono, quindi RPM e RPD
  sono condivisi (le misure di oggi hanno tolto quota anche al Pi).
- **I due lite hanno un RPM sotto i ~15-20 richieste al minuto**: il banco
  (una frase ogni ~4 s, 1-2 richieste a frase) ha dato "quota esaurita su tutti
  i modelli" una volta in ogni corsa. Con una conversazione vera non succede.
- **Gemma 4**: rifiuta l'audio (400). Il 26B ha un limite sui token al minuto
  (il prompt di BMO è grande) più basso del "30 richieste al minuto" che avevo
  in mente; il 31B dà 504 sul testo.
- **`TENTATIVI_SDK = 2` non conta dentro un turno** (restano meno di 30 s): vale
  solo per le richieste senza scadenza, come quelle silenziose della #29.
- **Un 400 non passa al modello successivo** (`modelli.py`, "altri 4xx"): per
  questo ho provato l'audio e il cambio a metà turno su ogni candidato prima di
  inserirlo.
- **I 503/504 variano nel tempo**: `gemini-3.5-flash` nella prima sonda era
  lento e instabile (499/503/504, 9-13 s) e mezz'ora dopo era sano (2,2 s).
  Un modello "inaffidabile oggi" può esserlo meno domani; la lista è facile da
  cambiare con `BMO_GEMINI_MODELLI`.
- **`misura_modelli.py` e `simula_cascata.py` non sono importati dal
  servizio**: non cambiano la RAM del Pi.
- **Errore mio in corso d'opera**: la prima versione della sonda cercava il
  parametro `durata` (che non esiste) e segnava come sbagliate chiamate
  corrette; corretto e rifatto il confronto, i numeri in questi file sono
  quelli giusti.
