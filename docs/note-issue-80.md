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

## Non verificato

L'errore «il modello non esiste» riferito da Riccardo non è nel journal di `bmo-core` (ultimo evento
alle 21:59) e non l'ho riprodotto. Se `/etc/bmo/env` sul Pi contiene un `BMO_GEMINI_MODELLI` con un
nome diverso da questi, è lì: non posso leggerlo (root). Comando: `sudo grep BMO_GEMINI /etc/bmo/env`.
