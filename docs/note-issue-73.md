# Note — issue #73 (cascata dei modelli Gemini)

Numeri grezzi e come ripeterli. Le decisioni che spettano a Riccardo stanno in
[`decisioni-issue-73.md`](decisioni-issue-73.md), le cose solo informative in
[`informazioni-issue-73.md`](informazioni-issue-73.md).

Tutte le misure sono del **1/10/2026**, dal laptop `omarchy` (connessione che
Riccardo descrive come non ottima: in un momento la rete verso l'API era
buona — ping ~10 ms, TLS 0,07-0,25 s — quindi i 503/504 visti sembrano lato
Google, ma le due cause non si separano del tutto), con la chiave Gemini del
free tier. Strumento: `python -m bmo_core.misura_modelli` (moduli
`misura_modelli.py` e `simula_cascata.py`, mai importati dal servizio sul Pi).

## Come funziona oggi la cascata (`modelli.py`, `brain.py`)

- Ordine fisso `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`; modello
  provato per primo = il primo non sospeso.
- Errori: 429 → sospeso per il `retryDelay` di Google (o 60 s); 500/502/503/504
  e `ReadTimeout` → 30 s; 404 → 1 ora; rete giù → si ferma; altri 4xx →
  l'errore sale (**un 400 su un modello nuovo bloccherebbe il turno**, non
  passerebbe al successivo: per questo i candidati sono stati provati con
  l'audio prima di entrare nella lista).
- Tetto del turno `TETTO_TURNO_S = 20 s`; con meno di 30 s rimasti l'SDK fa **un
  solo tentativo** (`_entro_la_scadenza`), quindi `TENTATIVI_SDK = 2` conta solo
  per le richieste senza scadenza (le richieste silenziose della #29,
  `brain.py:750`). Timeout per tentativo 15 s, ma mai sotto i 10 s (minimo
  lato server di Gemini).
- Se tutto fallisce: `GeminiNonDisponibile` con tipo `quota` / `sovraccarico` /
  `rete` / `tempo`; sul dispositivo diventa la clip "non ci arrivo".

## Modelli esistenti con questa chiave (`client.models.list()`)

Candidati presenti: `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`,
`gemini-3.8-flash`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it`, oltre ai due lite.
Elencati ma **404 NOT_FOUND** alla chiamata: `gemini-2.5-flash-lite`,
`gemini-2.5-flash`. Non usati gli alias `*-latest` (si spostano).

## Compatibilità col cervello vero (prompt + strumenti + audio)

| Modello | Testo+etichette | Strumento | Audio WAV | Cambio modello a metà turno |
|---|---|---|---|---|
| gemini-3.6-flash | sì | sì (`minuti: 10`) | **sì** | sì |
| gemini-3.5-flash | sì | sì | non verificato (499/503/504 in quella sonda) | 503 in quella sonda |
| gemini-3.7-flash | sì | non verificato (503) | non verificato (503) | sì |
| gemini-3.8-flash | 503 | 503 | 503 | sì |
| gemma-4-26b-a4b-it | sì | sì | **no: 400 "Audio input modality is not enabled"** | 429 |
| gemma-4-31b-it | 504 (13 s) | 504 | **no: 400** | 400 |

Il cambio a metà turno (giro 0 su un modello, giro 1 su un altro, con la
`functionResponse` nella storia) funziona sui Gemini; con Gemma 31B dà 400.
Un modello senza audio non può stare nella cascata: il dispositivo manda audio
e il 400 **non** passa al modello successivo (vedi sopra).

(La sonda iniziale confrontava `durata == 600`, parametro che non esiste:
`imposta_timer` prende `ore/minuti/secondi`. `minuti: 10` è corretto; errore
mio, corretto con `durata_in_secondi`.)

## Latenza e strumenti (turno completo, richiesta di testo)

Per richiesta (dal registratore) e per turno (`rispondi`), secondi.

| Modello | Semplice (mediana) | Con strumento (mediana, 2 richieste) | Strumento giusto | Altro |
|---|---|---|---|---|
| gemini-3.5-flash-lite | 0,89 (n=8) | 1,69 (n=8) | 8/8 | 3 richieste su 24 lente (4-5 s) |
| gemini-3.1-flash-lite | 2,89 (n=8) | 6,29 (n=7) | 7/8 | 503 su 2 richieste su 24 |
| gemini-3.6-flash | 3,24 (n=5) | 3,60 (n=4) | 4/4 completati | 429 oltre i 5 RPM |
| gemini-3.5-flash | 2,17 (n=4) | 3,27 (n=4) | 4/4 | nella prima sonda 9-13 s e 499/503/504 |
| gemini-3.7-flash | — | 7,06 (n=1) | — | 503/504 su 7 richieste su 11 |
| gemini-3.8-flash | — | 10,5 (n=1) | — | 503 su 7 richieste su 9 |
| gemma-4-26b-a4b-it | 10,1 (n=2) | 5,85 (n=2) | 2/5 completati | 429 dopo 4 richieste (token/minuto) |

## Affidabilità: una richiesta vera al minuto, 25 volte

`python -m bmo_core.misura_modelli affidabilita --modelli <id> --ripetizioni 25 --pausa 60`

| Modello | Riuscite | Cadute | Costo medio di una caduta | Mediana (riuscite) |
|---|---|---|---|---|
| gemini-3.5-flash-lite | 24/25 (96%) | 1× 504 | 13,6 s | 0,83 s |
| gemini-3.1-flash-lite | 23/25 (92%) | 2× 503 | 2,3 s | 4,09 s |
| gemini-3.8-flash | 2/25 (8%) | 7× 503, 16× 429 | 0,9 s | 6,4 s |
| gemini-3.7-flash | 0/25 | 1× 503, 1× 504, 23× 429 | 1,3 s | — |
| gemini-2.5-flash(-lite) | — | 404 | 0,2 s | — |

(Per 3.5-flash e 3.6-flash non è stato possibile: vedi sotto, quota
giornaliera esaurita dalle prove precedenti.)

## Comportamento al limite

- **429 al superamento dell'RPM: veloce.** 0,15-0,25 s con 1 tentativo SDK
  (3.6-flash: `retryDelay=15s`; Gemma: 19-39 s; 3.7-flash: 0-10 s decrescente).
  Con 2 tentativi dell'SDK lo stesso 429 costa 1,5-3,3 s, e un 503 6-9,5 s: i
  ritenti dell'SDK sono il costo vero, e dentro il turno non scattano
  (vedi sopra).
- **Quota giornaliera, scoperta a metà lavoro.** Dopo circa 20 richieste a testa
  (le mie prove di compatibilità, latenza e un banco) `gemini-3.5-flash` e
  `gemini-3.6-flash` rispondono 429 con la violazione
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier` e un `retryDelay` di 8 s
  che **non** riflette la realtà (la quota è giornaliera): la cascata li
  riproverebbe ogni 8 s, a 0,2 s l'una. Il valore esatto dell'RPD non è
  leggibile dall'API; il pannello AI Studio richiede login. Stima: ~20/giorno
  a modello (da confermare).
- Gemma 26B: limite effettivo dopo 4 richieste *grandi* (il prompt di BMO) in
  circa 30 s, ma 9 richieste minuscole di fila in 21 s passano: il limite è
  sui token al minuto, non sulle richieste.
- I due lite hanno dato "quota esaurita su tutti i modelli" **una volta in
  ciascun banco** (frase 13 nel "prima", frase 31 nel "dopo"): il banco va a
  una frase ogni ~4 s (15-20 richieste/minuto), più dell'RPM dei lite.
  Con una conversazione vera non succede; la cascata ha ritentato dopo 30 s.

## Banco di frasi (`python -m bmo_core.prova_frasi`, 48 frasi italiane)

| Corsa | Corrette | Modelli che hanno risposto | Turno più lungo |
|---|---|---|---|
| **Prima** (cascata a 2) | **47/48 (98%)** — sbagliata «Abbassa la radio» (manca `canale`) | 3.5-lite 43, 3.1-lite 5 | 17,9 s (1 riepilogo forzato) |
| **Dopo** (cascata a 4) | **47/48 (98%)** — sbagliata «Che ore sono a Tokyo?» (ha cercato sul web) | 3.5-lite 45, 3.1-lite 3 | 18,2 s (ricerca web lenta, nessun riepilogo) |
| 3.1-lite da solo | 47/47 (100%), 1 errore escluso | — | 12,4 s (5 riepiloghi forzati) |
| 3.6-flash da solo | non completabile: 1/1, poi 429 giornaliero | — | — |
| 3.5-flash da solo | non completabile: 1/1, poi 429 giornaliero | — | — |

Il "dopo" **non esercita i due Flash in coda** (oggi hanno la quota giornaliera
esaurita): conferma solo che la lista nuova non peggiora il caso normale.

## Simulatore (`python -m bmo_core.simula_cascata --prove 400`)

400 conversazioni da 60 turni, una pausa media di 25 s fra i turni. Guasti
modellati a episodi (catena di Markov, minuti di durata) con parametri dalle
misure; `falliti` = turni senza risposta; `mediana`/`p95` sui soli turni riusciti.

**Guasti correlati** (un sovraccarico di Google colpisce tutti i modelli
insieme; calibrato a ~6,4% di turni falliti per la cascata di oggi, contro il
7,3% reale della #65):

| Variante | Falliti | Mediana | p95 | richieste/turno (oltre il 1°) |
|---|---|---|---|---|
| A attuale (2 lite) | 6,4% | 1,37 s | 7,2 s | 3.1-lite 0,09 |
| B + flash in coda (3.5-f, 3.6) | 5,3% | 1,38 s | 7,3 s | 3.1-lite 0,09 · flash 0,05 |
| **B2 + flash in coda (3.6, 3.5-f) — implementata** | **5,6%** | 1,38 s | 7,3 s | 3.1-lite 0,09 · flash 0,06 |
| C flash prima del 3.1-lite | 5,6% | 1,38 s | 7,1 s | 3.5-f 0,09 · 3.6 0,04 |
| D con 3.7/3.8 nella cascata | 5,7% | 1,37 s | 7,3 s | tempo perso (>8 s: 9,2%) |
| E C + timeout 10 s | 5,7% | 1,37 s | 7,3 s | — |
| F C + salto RPM + sospensione lunga (non implem.) | 6,0% | 1,41 s | 6,9 s | — |
| G C + hedging 3 s (non implem.) | 6,7% | 1,40 s | 6,1 s | flash 0,23 |
| H C + timeout 10 s + hedging (non implem.) | 6,7% | 1,39 s | 6,1 s | flash 0,23 |

**Guasti indipendenti** (estremo ottimistico): A 0,8% → B2 **0,1%**; D 1,4%
(peggio di A); E 1,0%; F/G/H 0,1-0,2% (con hedging p95 7,4 → 6,4 s).

Lettura: la coda dà **-0,8 punti** (correlati) o **-0,7 punti** (indipendenti) di
turni falliti senza toccare la mediana; fra B e B2, C è rumore. 3.7/3.8 fanno
peggio che non averli. I meccanismi nuovi (F, G, H) non valgono la complessità:
il collo di bottiglia è il guasto comune a tutti i modelli, non l'ordine.
**Limite:** la correlazione fra modelli non è misurabile con i dati della #65
(solo il totale dei turni falliti); i due scenari sono il minimo e il massimo.

## Come ripetere

```bash
cd bmo-core
python -m bmo_core.misura_modelli compat       --modelli gemini-3.6-flash --pausa 14
python -m bmo_core.misura_modelli latenza      --modelli gemini-3.6-flash --ripetizioni 5 --pausa 30
python -m bmo_core.misura_modelli affidabilita --modelli gemini-3.5-flash-lite --ripetizioni 25 --pausa 60
python -m bmo_core.misura_modelli limite       --modelli gemini-3.7-flash --raffica 8 --tentativi 2
BMO_GEMINI_MODELLI=gemini-3.6-flash python -m bmo_core.prova_frasi --pausa 30
python -m bmo_core.simula_cascata --guasti correlati   # e: indipendenti
```

I modelli a 5 RPM vogliono `--pausa 30`; con la quota giornaliera di ~20
richieste bastano una o due prove al giorno per modello.
