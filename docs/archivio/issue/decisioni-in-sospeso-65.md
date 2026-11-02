# Decisioni in sospeso dopo la sessione del 29/9/2026 (#65)

Non ho scelto io per queste: sono decisioni di Riccardo, con le opzioni e
cosa comporta scegliere l'una o l'altra. Le informazioni che deve solo
conoscere (non decidere) stanno invece in
[`informazioni-dalla-sessione-65.md`](informazioni-dalla-sessione-65.md).

## 1. Chiudere a mano le issue #16 e #63?

Le PR che le risolvevano (#67, #66) sono mergiate in master da giorni, ma
restano "open" su GitHub perché i testi delle PR non contenevano la keyword
"Closes #N" — GitHub non le ha chiuse da solo.

- **Chiuderle ora, a mano** (`gh issue close 16 63` con un commento che
  rimanda alle PR): il board torna coerente con lo stato reale del lavoro;
  nessuna perdita di informazione, la issue resta comunque consultabile
  chiusa.
- **Lasciarle aperte**: il board mostra lavoro "da fare" che in realtà è già
  fatto — rischio di riguardarle per sbaglio o di doverci ripensare più
  avanti chiedendosi se manca qualcosa.

Non l'ho fatto io: nessuna delle due sessioni precedenti (28/9, 29/9) lo ha
fatto, sempre per lasciare la scelta a Riccardo.

## 2. Chiudere #1 (display 2.4" o 3.5") con un commento?

Riccardo ha comprato il Waveshare 2.4" il 29/9: la issue è di fatto
risolta, il preset relativo (`bmo_face/dimensione_fisica.py`, `"2.4":
(48.96, 36.72)` mm) è già nel codice, nessun lavoro in più.

- **Chiuderla con un commento** che spiega la scelta (2.4", perché, dove sta
  il preset nel codice): il board riflette la decisione presa, futuri
  lettori della issue vedono il motivo.
- **Lasciarla aperta finché il componente non è montato fisicamente**: più
  prudente se si vuole aspettare una conferma "dal vivo" che le dimensioni
  siano giuste prima di considerarla chiusa per davvero.

## 3. #13 (STT/TTS locale, Piper) dentro la #65: farlo o no?

Il testo della #65 lo include come misura opzionale ("solo se si vuole
Piper come rete di sicurezza per il TTS"), da fare dentro la stessa issue.
Non l'ho toccato in questa sessione: la #65 come issue di per sé si chiude
già con le misure di RAM/temperatura/zram/OOM.

- **Farlo ora, nella stessa PR**: risposta completa alla domanda "whisper.cpp
  tiny + Piper stanno nei 512 MB del Pi 3 A+?" prima di chiudere la #65 per
  sempre. Costo: altro lavoro di misura (whisper.cpp e Piper non sono
  ancora installati sul Pi), la PR di #65 cresce e si allontana la sua
  chiusura.
- **Farlo dopo, come issue separata** (o non farlo affatto se Piper non
  serve più come rete di sicurezza, es. se edge-tts continua a bastare):
  la #65 si chiude prima, la domanda su Piper resta aperta esplicitamente
  altrove invece di restare implicita dentro una issue già chiusa.

## 4. RPD reale del free tier Gemini per `gemini-3.5-flash-lite`

Non ho trovato un numero pubblico affidabile (cercato su
`ai.google.dev/gemini-api/docs/rate-limits` e sul web, vedi
`note-issue-65.md`): la pagina ufficiale rimanda al pannello personale
`aistudio.google.com/rate-limit`, che richiede il login di Riccardo e non è
raggiungibile da questa sessione.

- **Se Riccardo controlla il numero vero** (probabilmente in pochi minuti,
  loggato nel suo account Google AI Studio): posso aggiustare
  `--pausa-minuti` della unit `bmo-carico.service` con un dosaggio preciso
  invece che prudente — più richieste al giorno se il tetto vero è più
  alto, oppure conferma che 24 giri/giorno (~480 richieste) è già al
  sicuro.
- **Se resta com'è** (dosaggio prudente, non confermato): nessun problema
  finché non arrivano errori 429 nel log della unit — in quel caso va
  semplicemente aumentato `--pausa-minuti` e riavviata la prova.

## 5. Pulizia dei worktree stantii (spazio disco)

In `~/Work/bmo-diy/.claude/worktrees/` ci sono 16 worktree, la maggior parte
per issue le cui PR sono già mergiate da giorni (#15, #16, #22, #23, #24,
#25, #29, #51, #54 — due copie —, #60, #63, #64, più `misura-ram` e
`wake-word-modelli-bmo`): ciascuno ha una propria venv da ~1 GiB, coerente
con la nota "Piano spazio disco Omarchy" (crescita non necessaria del
disco). Solo `demo-live-pr-non-mergiate` (il test dal vivo persistente) e
questo stesso worktree (`issue-65-24h-carico-pi`) servono ancora.

- **Rimuoverli** (`git worktree remove` per ciascuno, poi eventualmente
  `git branch -D` sui branch locali corrispondenti se già mergiati): libera
  probabilmente diversi GiB di spazio. Nessuna perdita: il codice di
  ciascuno è già in master via le rispettive PR.
- **Lasciarli**: nessun rischio immediato, solo spazio disco occupato senza
  motivo.

Non ho toccato nessuno di questi: sono azioni distruttive (rimozione di
worktree/branch) che vanno confermate prima, come da istruzioni.

## 6. Quando aprire la PR di questa issue

Il branch `issue-65-24h-carico-pi` è già pushato, ma la PR non è ancora
aperta.

- **Aprirla subito come draft**: visibile da ora sul board, si può seguire
  l'avanzamento della prova di 24 h direttamente dai commit che arriveranno
  (uno a fine corsa, con i risultati completi).
- **Aprirla solo a fine prova**, con già dentro i risultati completi:
  meno rumore sul board nel frattempo, ma nessuna visibilità intermedia se
  la sessione che la scrive finisce prima che la prova sia finita.

**Scelto (a) per non bloccarmi**: la prova di 24 h probabilmente supera la
durata di questa sessione, quindi ho aperto la PR come draft subito, per
non perdere continuità — se preferivi (b), la si può sempre convertire o
richiudere e riaprire più avanti.

