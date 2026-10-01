# Decisioni da prendere — issue #73 (cascata dei modelli Gemini)

Per ogni voce: le opzioni, cosa è implementato di default, e la conseguenza
concreta di scegliere l'una o l'altra. Numeri e metodo in
[`note-issue-73.md`](note-issue-73.md). Le cose solo informative stanno in
[`informazioni-issue-73.md`](informazioni-issue-73.md).

**Vincolo seguito (tuo):** il codice già presente sul Pi, ottimizzato per la
RAM, non cambia di struttura; nel codice del servizio è cambiata una sola
costante (l'elenco predefinito dei modelli, in coda). Tutto ciò che sarebbe un
meccanismo nuovo è stato solo simulato.

## 1. Quali modelli stanno nella cascata predefinita, e in che ordine

**Opzioni:**
- (a) *Lite in testa, Flash in coda*: `gemini-3.5-flash-lite` →
  `gemini-3.1-flash-lite` → `gemini-3.6-flash` → `gemini-3.5-flash`.
- (b) Come oggi, solo i due lite.
- (c) Flash prima del `3.1-flash-lite` (che è il più lento dei due lite: mediana
  4,1 s nella misura di affidabilità).
- (d) Aggiungere anche `gemini-3.7-flash`/`gemini-3.8-flash` o i Gemma 4.

**Implementato: (a).** Il caso normale non cambia (nel banco 45 turni su 48
sono serviti dal primo modello, uguale a prima) e i due Flash intervengono solo
quando i lite falliscono.

**Conseguenze:**
- (a) invece di (b): nel simulatore i turni falliti scendono da 6,4% a 5,6%
  (guasti correlati) o da 0,8% a 0,1% (indipendenti). Il guadagno è piccolo
  perché i fallimenti reali sono in buona parte sovraccarichi che colpiscono
  tutti i modelli insieme. Costo: nessuno nel traffico normale; i Flash hanno
  una quota giornaliera di circa 20 richieste (da confermare), quindi sono un
  aiuto d'emergenza, non una capacità in più.
- (a) invece di (c): sul simulatore i turni falliti sono uguali (5,6%) e (c)
  guadagna poco sulla latenza (turni sopra gli 8 s: 4,2% contro 4,9% con guasti
  indipendenti), ma consuma di più la quota giornaliera dei Flash (0,13
  richieste a turno contro 0,06) e li porta davanti a un modello che finora si
  è comportato bene (100% al banco). Se un giorno il `3.1-flash-lite`
  peggiorasse, (c) è la prima modifica da fare.
- (a) invece di (d): `3.7` e `3.8` danno 503/504 quasi a ogni richiesta (0/25 e
  2/25 riuscite), e nel simulatore peggiorano i risultati (1,4% di turni
  falliti contro 0,1% con guasti indipendenti, e più turni sopra gli 8 s). Gemma
  4 **rifiuta l'audio con 400**, e il 400 non passa al modello successivo: un
  solo turno con audio su Gemma interromperebbe la conversazione.

## 2. Salto preventivo dei modelli al limite (contatore RPM) e sospensione lunga

**Opzioni:**
- (a) *Niente*, resta la sospensione attuale (429 → `retryDelay`, 503 → 30 s).
- (b) Un contatore locale delle richieste per modello (finestra scorrevole) che
  salta un modello già al limite, più sospensioni crescenti dopo guasti
  ripetuti.

**Implementato: (a).**

**Conseguenza:** (b) nel simulatore non migliora il tasso di turni falliti
(6,0% contro 5,6%) e il tempo mediano resta uguale: un 429 costa solo 0,2 s,
quindi scoprire il limite "sbagliando" è quasi gratis. Aggiungerebbe stato e
codice nel servizio che gira sul Pi, per un guadagno non misurabile.
Diventerebbe utile solo se i modelli con pochi RPM finissero in testa, cosa che
la decisione 1 evita.

## 3. Hedging (lanciare il secondo modello se il primo tarda)

**Opzioni:**
- (a) *Niente.*
- (b) Se il primo modello non risponde entro ~3 s, partire in parallelo col
  secondo e prendere chi arriva prima.

**Implementato: (a).**

**Conseguenza:** (b) accorcia solo la coda lenta (p95 da 7,5 a 6,4 s con guasti
indipendenti; con guasti correlati non migliora, il tasso di fallimento sale a
6,7%), costa ~0,2 richieste in più a turno sul secondo modello (che con ~20
richieste al giorno si esaurirebbe in poche conversazioni) e richiede thread o
richieste concorrenti dentro il servizio: più RAM e codice nuovo sul Pi. Non
conviene finché i modelli di riserva sono quelli a quota bassa.

## 4. Timeout per tentativo e tentativi dell'SDK

**Opzioni:**
- (a) *Invariati* (15 s per tentativo, `TENTATIVI_SDK = 2`).
- (b) Timeout per tentativo a 10 s (il minimo accettato da Gemini).

**Implementato: (a).**

**Conseguenza:** i tentativi dell'SDK non contano dentro un turno (con meno di 30
s rimasti il codice già ne fa uno solo), quindi cambiare `TENTATIVI_SDK` non
accorcerebbe niente; contano solo per le richieste silenziose della #29. (b) nel
simulatore dà 5,7% contro 5,6% con guasti correlati, e **peggiora** con guasti
indipendenti (1,0% contro 0,1%): una richiesta lenta ma buona (il `3.5-lite` ha
code a 12,7 s) verrebbe tagliata inutilmente.

## 5. Dove vive l'elenco dei modelli sul Pi

**Opzioni:**
- (a) *Predefinito nel codice* (`MODELLI_PREDEFINITI`), come oggi: serve
  aggiornare il Pi con un deploy per averlo.
- (b) Impostare `BMO_GEMINI_MODELLI` in `/etc/bmo/env` sul Pi, senza toccare il
  codice (esempio aggiornato in `pi/bmo-core-env.esempio`).

**Implementato: (a)**, con (b) sempre disponibile per cambiare l'elenco al volo.

**Conseguenza:** con (a) basta il normale deploy (#16). Con (b) si cambia la
cascata senza deploy ma l'elenco vive solo sul Pi e può divergere dal repo.
**Limiti RPM per modello:** non sono configurabili, perché nessun meccanismo
del servizio li usa (decisione 2): sono documentati qui e nei commenti.

## 6. Cosa vede l'utente quando tutto fallisce

**Opzioni:** (a) lasciare il comportamento attuale (clip «non ci arrivo» e
faccia triste, dopo al massimo ~20 s di tetto); (b) una risposta più rapida,
per esempio dopo 8-10 s, con una frase preregistrata.

**Implementato: (a)**, invariato. Con la cascata a 4 modelli i casi di quota
esaurita su *tutti* i modelli sono più rari, ma il caso peggiore resta quello
del tetto del turno (20 s). (b) richiederebbe di cambiare il tetto o la logica
del turno: fuori dai vincoli di questa issue.

## 7. Un piano a pagamento

**Opzioni:** (a) restare sul free tier; (b) attivare la fatturazione (collegato
alla #6, "google_search nativo dopo il piano a pagamento").

**Implementato: (a).** **Conseguenza di (b):** i limiti giornalieri dei Flash
sparirebbero o crescerebbero molto, e i modelli più forti e più affidabili
(`3.6-flash`) potrebbero stare più in alto nella cascata; costo da stimare con i
token reali di BMO (nelle note del piano ~1 $/mese per la pipeline classica).
La decisione è tua perché è una spesa e un account; con (b) conviene rifare le
misure di questa issue.
