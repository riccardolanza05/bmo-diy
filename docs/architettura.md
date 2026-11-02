# Architettura

Come funziona BMO e perché è fatto così. L'idea di fondo: un Raspberry Pi 3 A+ ha 512 MB di RAM, quindi sul dispositivo
gira solo ciò che deve per forza stare lì. Il ragionamento è in cloud, su Gemini.

## Principi

- **Cheap ma affidabile.** Il criterio per ogni scelta: il software può essere complicato da scrivere, ma non fragile
  da mantenere.
- **Solo overlay in-tree.** La scheda audio usa `dtoverlay=wm8960-soundcard`, che è nel kernel di Raspberry Pi: nessun
  driver esterno da ricompilare dopo un `apt upgrade`. Il display si pilota da `spidev`, senza moduli del kernel.
- **Niente modelli linguistici a bordo.** Un solo modello in cloud fa trascrizione, ragionamento e visione nella stessa
  chiamata.
- **Interazione a voce.** Unica eccezione, il pulsante del HAT: un richiamo manuale per quando la wake word non basta.
- **La faccia dice cosa succede.** A ogni cambio di stato cambia la faccia, così un BMO che pensa non sembra guasto.

## Componenti

```
 2 microfoni MEMS ──► bmo-core ──HTTPS──► Gemini (audio, testo, foto)
 pulsante GPIO17 ───►    │     ──HTTPS──► edge-tts (voce)
 fotocamera CSI ────►    │     ──HTTPS──► DuckDuckGo, radio-browser, YouTube
                         │
              /run/bmo/bmo.sock (un JSON per riga)
              socket datagram dei fotogrammi video
                         │
                         ▼
                     bmo-face ──SPI──► display ILI9341

 bmo-core ──► mpv, ffmpeg ──► ALSA dmix ──► WM8960 ──► altoparlante
```

Sono processi separati per isolare i guasti: se `bmo-core` si ferma, systemd lo riavvia in due secondi e la faccia
continua a sbattere le palpebre.

| Dove | Cosa | Perché |
|---|---|---|
| Sul Pi | Wake word (openWakeWord, ONNX) | L'alternativa sarebbe mandare il microfono in cloud 24/7. Nulla esce di casa prima del richiamo |
| Sul Pi | Rilevamento del silenzio (`webrtcvad`) | Serve subito, a costo quasi zero |
| Sul Pi | Faccia e suoni | Un'animazione non può aspettare la rete |
| In cloud | Trascrizione, ragionamento, visione | Gemini li fa nella stessa chiamata |
| In cloud | Sintesi vocale (edge-tts) | ~0,6 s per una frase breve, con cache su disco |
| Misto | Ricerca sul web | Risultati da DuckDuckGo, ragionamento su Gemini |

## La macchina a stati

```
ATTESA ──richiamo──► ASCOLTO ──► PENSIERO ──► PARLATO ──► ATTESA
   ▲                                                         │
   └──────── PAUSA · ERRORE · CONFERMA ──────────────────────┘
```

1. **Attesa.** La wake word ascolta in locale. Il richiamo arriva dalla voce o dal pulsante.
2. **Ascolto.** Suono di conferma e faccia in ascolto, poi BMO registra fino al silenzio.
3. **Pensiero.** L'audio va a Gemini con il prompt e gli strumenti. Il loop agentico fa al massimo 4 giri con strumenti
   e l'intero turno ha un tetto di 20 secondi; gli ultimi 6 sono riservati a un riepilogo forzato, senza strumenti, così
   BMO risponde con quello che ha trovato.
4. **Parlato.** Il testo diventa voce e la bocca segue l'inviluppo reale dell'audio. Il microfono è chiuso: BMO non si
   interrompe mentre parla.

**Conferma** è un sotto-dialogo: BMO fa una domanda e riascolta senza chiedere il richiamo. **Pausa** ferma l'ascolto
a comando, con la faccia assonnata, mentre i timer continuano a suonare. **Errore** segnala che la rete o Gemini non
rispondono, con un suono e una faccia dedicata.

## Il prompt

Il prompt ha tre strati:

1. **Fisso** (`brain.PROMPT_FISSO`): personalità, regole per il parlato, uso degli strumenti. Il banco di prova
   `bmo_core.prova_frasi` lo verifica su 43 frasi.
2. **Dinamico**, ricostruito a ogni turno: ora locale, timer attivi, diario delle preferenze, persone di casa.
3. **Riepilogo**, aggiunto solo quando il loop deve chiudere senza strumenti.

La risposta inizia con due etichette che non vengono lette ad alta voce: `[it][felice] Sette per otto fa cinquantasei.`
La prima sceglie la voce, la seconda l'espressione. BMO è bilingue: se gli parli in inglese, risponde in inglese.

## Gli strumenti

| Strumento | Cosa fa |
|---|---|
| `scatta_foto` | Scatta, mostra la foto sullo schermo e la passa a Gemini nello stesso turno |
| `cerca_sul_web` | Tre risultati da DuckDuckGo |
| `imposta_timer`, `annulla_timer`, `elenca_timer` | Timer persistenti su disco |
| `riproduci_musica`, `controllo_riproduzione` | Radio via internet, scorrimento delle stazioni, pausa |
| `salva_stazione`, `elenca_stazioni` | Stazioni preferite |
| `riproduci_video` | Video di YouTube sullo schermo |
| `regola_volume` | Volumi indipendenti: radio, voce, timer, sistema |
| `metti_in_pausa_l_ascolto` | Smette di ascoltare per qualche minuto |
| `ricorda` | Propone una voce nel diario, che viene scritta solo dopo un sì a voce |

## Memoria

- **Sessione.** Lo storico recente resta in RAM. Dopo 5 minuti di silenzio la sessione si chiude e al più un paio di
  fatti utili passano al diario. A 60.000 token la conversazione viene compressa in un riassunto.
- **Diario.** `memoria.json` contiene frasi in linguaggio naturale. Le voci scritte a mano non vengono mai sfrattate da
  quelle automatiche.
- **Timer.** Si salva la scadenza assoluta, con scrittura atomica e lock. Un timer scaduto mentre BMO era spento suona
  lo stesso al riavvio.

## Cascata dei modelli

Se un modello risponde con quota esaurita o sovraccarico, `modelli.py` passa subito al successivo e lo sospende per un
po'. L'ordine è `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`: prima i modelli lite, i più
affidabili alle misure, poi il più forte ma con meno quota.

## Audio

Il driver I2S del Pi condivide il formato fra riproduzione e cattura, e la WM8960 ha un solo sottodispositivo di
riproduzione. Per questo `/etc/asound.conf`, generato da `pi/asound.conf.modello`, usa:

- `dmix` in `S32_LE` a 48 kHz, per mescolare voce e video mantenendo il formato del microfono;
- un volume software `Video`, per abbassare il video mentre BMO parla.

Niente PipeWire: costerebbe 35-50 MB di RAM.

## Faccia

`bmo_face.build_face` converte i disegni in `faces.bin`, fotogrammi RGB565 grezzi, più il manifesto `faces.json`.
`bmo_face.pannello` li mappa in memoria e scrive sul bus SPI solo il rettangolo cambiato, così l'animazione costa
pochissima CPU. La stessa logica di disegno alimenta anche una finestra sul PC.

Video e foto arrivano sullo stesso pannello. Il video resta in pausa mentre BMO ascolta e riprende dopo.

## Servizi

| Unit | Ruolo | Limite di memoria |
|---|---|---|
| `bmo-hat-audio.service` | Attende la scheda audio e imposta il mixer, una volta all'avvio | — |
| `bmo-face.service` | Faccia su SPI; parte prima della rete, così il display si accende subito | 80 MB |
| `bmo-core.service` | Il cervello | 280 MB |

## Avvio automatico

All'accensione il Pi avvia i tre servizi senza intervento. `Restart=always` con `StartLimitIntervalSec=0` fa sì che
systemd non smetta mai di riprovare, anche se rete o scheda audio ci mettono più del previsto. Il watchdog hardware
riavvia il Pi se il sistema si blocca per più di 15 secondi.

Il filesystem resta `ext4` in lettura e scrittura, con i log in RAM: uno stacco della corrente è gestito dal journal
di `ext4` e da `fsck`, e BMO scrive poco.

## Privacy

- Nulla lascia il Pi prima del richiamo: la wake word gira in locale.
- Dopo il richiamo, l'audio e le foto vanno a Google e il testo delle risposte a Microsoft, per la voce.
- Sul piano gratuito di Gemini, Google può usare i dati inviati.
- `metti_in_pausa_l_ascolto` è una pausa software: non c'è un interruttore fisico del microfono.
- La chiave API resta in `/etc/bmo/env` e i nomi delle persone in un file privato, fuori dal repository.

## Dipendenze fragili

| Dipendenza | Rischio | Cosa fare |
|---|---|---|
| `edge-tts` | Client non ufficiale, senza garanzie | Aggiornarlo; se sparisce, Azure Speech serve la stessa voce `it-IT-DiegoNeural` |
| `yt-dlp` | YouTube lo rompe spesso | `deploy.sh` lo aggiorna sempre |
| Modelli Gemini | Vengono ritirati spesso | Aggiornare `BMO_GEMINI_MODELLI` |
