# Note — issue #80 (cascata Gemini, modelli deprecati)

Numeri grezzi. Le decisioni stanno in [`decisioni-issue-80.md`](decisioni-issue-80.md). Tutto del
14/10/2026, sonde da `omarchy` con la chiave del progetto (mai stampata).

## Pagina ufficiale delle deprecazioni (ai.google.dev/gemini-api/docs/deprecations)

| Modello | Stato | Sostituto |
|---|---|---|
| `gemini-3.5-flash-lite` | nessuna chiusura annunciata | — |
| `gemini-3.1-flash-lite` | **deprecato, chiude il 07/05/2027** | `gemini-3.5-flash-lite` |
| `gemini-3.6-flash` | nessuna chiusura annunciata | — |
| `gemini-3.5-flash` | **deprecato**, instradato in automatico | `gemini-3.6-flash` |
| `gemini-3.7-flash` | **deprecato**, instradato in automatico | `gemini-3.8-flash` |
| `gemini-3.8-flash` | nessuna chiusura annunciata | — |
| `gemini-3.1-flash-tts-preview`, `gemini-2.5-{flash,pro}-preview-tts` | chiudono il 17/11/2026 | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` |

## Sonda con una richiesta di solo testo («Rispondi solo: ok»)

| Modello | 1ª sonda (tardi 14/10) | 2ª sonda |
|---|---|---|
| `gemini-3.5-flash-lite` | OK 0,9 s | OK 5,3 s |
| `gemini-3.1-flash-lite` | OK 1,5 s | OK 4,2 s |
| `gemini-3.6-flash` | 503 (14,4 s) | 503 (0,4 s) |
| `gemini-3.5-flash` | 503 (8,6 s) | 503 (0,9 s) |
| `gemini-3.7-flash` | OK 3,5 s | 503 (5,5 s) |
| `gemini-3.8-flash` | 503 (3,7 s) | 503 (3,9 s) |

Nessun 404 su nessun nome: i modelli deprecati esistono ancora (instradati), non c'è «il modello non
esiste». I 503 sono «This model is currently experiencing high demand».

## Cervello sul Pi (`Cervello.rispondi(testo=...)`, codice di produzione, cascata predefinita)

- Primo tentativo: «Gemini sovraccarico su tutti i modelli della cascata» (tutti e quattro).
- Secondo, pochi minuti dopo: risposta normale («Sono una piccola console vivente…»).

I picchi di 503 vanno e vengono nel giro di minuti.

## Banco `compat` + `latenza` (`bmo_core.misura_modelli`, prompt e strumenti veri, 14/10/2026 sera)

Una richiesta di testo con etichette, una con strumento (`imposta_timer`), una con audio WAV; poi
3 ripetizioni di latenza (mediana in secondi). «ko» = errore, tra parentesi il codice.

| Modello | Testo | Strumento | Audio | Latenza testo / strumento | Strumento giusto |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | OK | OK | OK | 1,98 / 1,68 | 3/3 |
| `gemini-3.1-flash-lite` | OK | OK | OK | 1,49 / 2,89 | 3/3 |
| `gemini-flash-lite-latest` | OK | OK | OK | 1,39 / 2,36 | 3/3 |
| `gemini-3.6-flash` | ko (503/504) | ko | ko | — | 0/3 |
| `gemini-3.5-flash` (deprecato) | ko (503) | OK | OK | — | 0/3 |
| `gemini-3.7-flash` (deprecato) | OK | ko | OK | 4,11 / 3,61 | 1/3 |
| `gemini-3.8-flash` | ko (503) | ko | OK | — / 4,85 | 1/3 |
| `gemini-flash-latest` | OK | ko | OK | — | 0/3 |
| `gemini-2.5-flash-lite` | **404** | — | — | — | 0/3 |
| `gemini-2.5-flash` | **404** | — | — | — | 0/3 |
| `gemma-4-31b-it` | OK (7,6 s) | OK | 429 | — / 4,35 | 1/3 (429) |
| `gemma-4-26b-a4b-it` | 504 | OK | **400** (rifiuta l'audio) | 5,66 / 8,05 | 1/3 |

- `gemini-2.5-flash-lite` e `gemini-2.5-flash`: **404 «no longer available to new users»**. Non c'è modo
  di usarli con questa chiave: non vanno in cascata.
- Gemma 4: il 31B tocca la quota (429 dopo tre richieste, `retryDelay` 9-56 s) e impiega 4-8 s; il
  26B A4B rifiuta l'audio con 400, che è l'ingresso di BMO. Nessuno dei due è adatto.
- `gemini-flash-lite-latest` dà lo stesso testo del `3.5-flash-lite` alla stessa domanda: è con ogni
  probabilità un alias di quello.

## Frasi di prova (`bmo_core.prova_frasi`, 48 frasi, un solo modello alla volta con `BMO_GEMINI_MODEL`)

| Modello | Corrette | Riepiloghi forzati | Turno più lungo (tetto 20 s) |
|---|---|---|---|
| `gemini-3.5-flash-lite` | **48/48 (100%)** | 2 | 16,8 s |
| `gemini-3.1-flash-lite` | **48/48 (100%)** | 0 | 8,7 s |
| `gemini-flash-lite-latest` | 46/47 (98%), 1 errore escluso | 6 | 19,1 s |

Il `3.1-flash-lite` (deprecato, ma attivo fino al 07/05/2027) è il più rapido sulle frasi lunghe; il
`3.5-flash-lite` ha un turno da 16,8 s e due riepiloghi forzati (il tetto del turno è 20 s). Va in
`decisioni-issue-80.md` come scelta sull'ordine, non cambiato.

## Cascata predefinita, verificata (3 richieste di testo)

`['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.6-flash']`: ha risposto sempre il primo,
in 4,3 s, 4,9 s e 5,2 s, senza ripiego. Il resto non è stato toccato (timeout, tentativi, ordine).

## Non verificato

L'errore «il modello non esiste» riferito da Riccardo non è nel journal di `bmo-core` (ultimo evento
alle 21:59) e non l'ho riprodotto. Se `/etc/bmo/env` sul Pi contiene un `BMO_GEMINI_MODELLI` con un
nome diverso da questi, è lì: non posso leggerlo (root). Comando: `sudo grep BMO_GEMINI /etc/bmo/env`.
