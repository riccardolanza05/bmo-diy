# Decisioni da prendere — issue #80 (cascata Gemini, modelli deprecati)

Per ogni voce: le opzioni, cosa è implementato di default e la conseguenza concreta
di scegliere l'una o l'altra. Numeri e metodo in [`note-issue-80.md`](note-issue-80.md).
Nel codice che gira sul Pi cambia solo l'elenco predefinito dei modelli.

## 1. Quali modelli restano nella cascata

**Opzioni:**
- (a) `3.5-flash-lite`, `3.1-flash-lite`, `3.6-flash` (tolto solo `3.5-flash`).
- (b) `3.5-flash-lite`, `3.6-flash` (tolti anche i `3.1-flash-lite`, deprecato).
- (c) (b) più `3.8-flash` in coda.

**Implementato: (a).**

**Conseguenze:**
- (a): `3.5-flash` è deprecato e Google lo instrada già al `3.6-flash`, quindi toglierlo non cambia
  cosa risponde e non perde nessun modello vero. Il `3.1-flash-lite` è deprecato anch'esso, ma chiude
  solo il 07/05/2027 e il 14/10 era il modello più affidabile dopo il primo (risposte in 1,5-4,2 s,
  mai 503 nelle due sonde): toglierlo oggi lascerebbe una cascata a due modelli.
- (b): cascata pulita da deprecati, ma con due soli modelli; il `3.6-flash` ha dato 503 in tutte
  le sonde del 14/10, quindi quando il primo ha un singolo 429/503 BMO non risponde.
- (c): più riserve, ma `3.8-flash` ha dato 503 in tutte le sonde e nelle misure della #73
  (503/504 quasi a ogni richiesta). Aggiunge attesa (fino a ~30 s per modello) senza dare risposte.

## 2. Il TTS di Gemini (motore `gemini`, opt-in)

**Opzioni:** (a) lasciare l'elenco com'è; (b) sostituire i tre modelli preview con
`gemini-3.8-flash-tts` e `gemini-3.8-flash-lite-tts`.

**Implementato: nessuna modifica (a).** Il motore predefinito di BMO è `edge`, non `gemini`.

**Conseguenza:** `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts` e
`gemini-2.5-pro-preview-tts` chiudono il **17/11/2026** (pagina ufficiale delle deprecazioni). Chi
usa `BMO_TTS_MOTORE=gemini` dopo quella data avrà errori; non l'ho cambiato perché i modelli 3.8 non
sono stati provati con la voce `it-IT-DiegoNeural` e il motore non è quello in produzione. Va fatto
prima del 17/11 se si vuole tenere il ripiego a Gemini.

## 3. Ordine dei due lite (nuova, dai test del 14/10)

**Opzioni:** (a) `3.5-flash-lite` poi `3.1-flash-lite` (com'è); (b) `3.1-flash-lite` poi `3.5-flash-lite`.

**Implementato: (a).** Non l'ho cambiato perché mi hai detto di lasciare la cascata com'è finché i
primi modelli rispondono: rispondono (4,3-5,2 s in tre richieste di prova).

**Conseguenza:** nelle 48 frasi il `3.1-flash-lite` ha il turno più lungo a 8,7 s e nessun riepilogo
forzato, il `3.5-flash-lite` a 16,8 s con due (il tetto è 20 s). (b) accorcerebbe i turni lunghi, ma mette
in testa il modello che chiude il 07/05/2027 e che Google ha già sostituito; quando sparirà, il
primo modello della cascata diventerebbe una chiamata 404 (0,2 s, poi sospeso 1 h) a ogni riavvio.
