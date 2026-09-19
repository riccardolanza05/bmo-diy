# Piano attuale — rev. 5.1: cloud-first, solo voce

> **Questo è il piano in vigore.** Sostituisce, dove in conflitto, il [Piano di progetto rev. 2/3](revisioni-precedenti/rev3-piano-progetto.md) e il [BOM rev. 4](revisioni-precedenti/rev4-bom-senza-dazi.md).
>
> **Documento di riferimento tecnico esterno**: un progetto con Pi 5 16 GB + Ollama, tutto in locale — vedi [Riferimenti esterni](03-riferimenti-esterni.md).
> **Restano validi** dai documenti precedenti: la pipeline asset della faccia, il blit su dirty rect, la disciplina "solo overlay in-tree", la termica e le regole di stampa (vedi [rev. 2/3](revisioni-precedenti/rev3-piano-progetto.md) e [rev. 3 BOM](revisioni-precedenti/rev3-hardware-bom.md) per i dettagli completi di queste sezioni).
> **Aggiornamento 2026-09-19 — roadmap software-first**: prima tutto il software sul PC di sviluppo, l'acquisto dei componenti per ultimo. Vedi [§3](#3--roadmap).
> **Rev. 5.1**: cinque modifiche al BOM per tagliare i costi. Totale: da ~91 € a **~68 €** (~73 € con lo stereo) — **−23 €**.

Questa revisione parte da tre premesse nuove:

1. **Raspberry Pi 3 Model A+ (512 MB) e alimentatore sono già comprati.** Non è più una variabile di progetto: è il vincolo che filtra tutto il resto.
2. **Nessun modello in locale.** Il ragionamento sta su Gemini in cloud.
3. **Interazione unicamente vocale.** Niente pulsanti, niente D-pad, niente PCB custom, niente microcontrollore.

Funzioni da mantenere: **conversazione vocale, foto analizzate da un modello vision, risposte che richiedono ricerca sul web, timer, riproduzione musicale.**

| | |
|---|---|
| Spesa residua (Pi e alimentatore già pagati) | **~68 €** (~73 € con il secondo altoparlante) |
| Fonte | tutta UE — **zero dazi**, consegna 3–5 giorni |
| RAM di picco stimata | **~295 MB su ~495 MB disponibili** |
| Latenza dalla fine della frase al primo suono | **~2,5–3,5 s**, coperti da una clip di attesa che parte a 0,2 s |
| Costo Gemini | **0 € sul free tier**; ~6 $/mese sul piano a pagamento, di cui l'80% è il TTS |
| Tempo a BMO funzionante | **~4 settimane**, di cui quasi zero di sola attesa |

---

## 0 · Cosa sopravvive del riferimento tecnico, e cosa no

Il riferimento è un progetto **eseguito su un Pi 5 da 16 GB con inferenza locale**: quasi metà delle sue scelte hardware esiste solo per far girare Whisper, Gemma 3 e Moondream in RAM. Togliere l'inferenza locale non è una variante: è la ragione per cui metà di quel BOM sparisce.

### 0.1 Le scelte hardware del riferimento, filtrate

| Scelta del riferimento | Perché c'era | Sopravvive? |
|---|---|---|
| **Pi 5, 16 GB** | tenere in RAM Whisper + Gemma 3 + Moondream | **No.** Con l'inferenza in cloud il carico a bordo è: una wake word, un blit SPI e una richiesta HTTPS |
| **SSD NVMe + HAT M.2 Pimoroni** | i modelli si caricavano da disco a ogni avvio | **No.** Non c'è nessun modello da caricare. Risparmi ~80 € e un HAT |
| **Acceleratore AI (2ª porta M.2)** | futuro LLM locale | **No** |
| **UPS shield Geekworm + batteria Li-ion** | far girare BMO a batteria | **No.** BMO sta attaccato alla corrente 24/7. L'autore del riferimento dice che il power management del Pi 5 gli ha dato "molti tentativi ed errori": è il sottosistema più rognoso del riferimento e sparisce gratis |
| **Feather 32u4 + PCB custom KiCad + 7 switch** | i pulsanti come tastiera USB HID | **No** (premessa 3). Sparisce un intero sottoprogetto |
| **Camera Module v2 su CSI** | tool "fotocamera" dell'agente | **Sì.** Il Pi 3 A+ ha il CSI a 15 pin. Un OV5647 regolabile a pinza da 5,90 € invece dei ~28 € dell'ufficiale |
| **Display per la faccia** | la faccia di BMO | **Sì, ma ridimensionato** (§1.3). Il 5" 800×480 DSI costa 45–55 € contro 13, e su 512 MB il framebuffer KMS non è gratis |
| **Microfono USB + speaker USB** | ingresso/uscita audio | **Sostituiti.** Il 3 A+ ha **una sola porta USB-A**. Una scheda audio HAT le sostituisce entrambe, lascia libera la USB e ha due microfoni invece di uno |
| **16 magneti 5×2 mm per la faceplate** | corpo apribile senza viti a vista | **Sì, e vale la pena copiarla** |
| **Sportello posteriore modulare** | cambiare il vano senza ristampare il corpo | **Sì.** Costa zero e salva una stampa da 10 ore fra sei mesi |
| **Arti a innesto** | pose intercambiabili | **Sì**, è gratis |

**Traduzione in euro:** delle voci hardware del riferimento, il cloud ne cancella circa 250 € e la premessa "solo voce" altre ~40 € più il PCB custom.

### 0.2 Le scelte software del riferimento, filtrate

Qui è l'opposto: **l'architettura del riferimento sopravvive quasi per intero.**

| Idea del riferimento | Sopravvive? |
|---|---|
| Macchina a stati WARM-UP → IDLE → LISTENING → THINKING → SPEAKING | **Sì**, con WARM-UP che si svuota (§2.1) |
| Faccia che cambia a **ogni** transizione di stato | **Sì, e diventa più importante**: senza pulsanti e senza LED, la faccia è l'unico canale di conferma |
| **Clip vocali pre-generate**, scelte a caso, per coprire l'attesa | **Sì — è l'idea migliore del riferimento.** Si pre-generano col TTS di Gemini sul PC di sviluppo e si spediscono come WAV. Zero motore TTS a bordo, zero RAM, latenza zero |
| Wake word **openWakeWord** custom "Hey BMO" col Colab ufficiale | **Sì.** È l'unica cosa che *deve* restare locale (§2.6) |
| **Loop agentico**: l'LLM decide se servono tool, emette JSON, l'output rientra nel loop | **Sì, invariato.** Con Gemini è function calling nativo invece che da parsare a mano |
| Tool **fotocamera** con re-iniezione dell'immagine nel loop | **Sì, e diventa 40× più veloce** (§2.4) |
| Tool **ricerca web DuckDuckGo** come RAG | **Sì, e non per pigrizia**: il grounding con Google Search *non è nel free tier* |
| Whisper locale per lo STT | **No** — Gemini è multimodale, trascrive e ragiona nella stessa chiamata |
| Ollama + Gemma 3 + Moondream 2, con model swap | **No** — un solo modello in cloud fa testo e immagini |
| Piper locale per il TTS | **No come motore**; resta come rete di sicurezza opzionale (§2.5) |
| Pulsanti come tastiera USB HID | **No** (premessa 3) |

---

## 1 · Hardware da comprare

### 1.1 La distinta

Tutto acquistabile in UE, due ordini, consegna 3–5 giorni, **nessun dazio**.

| # | Componente | Scelta concreta | A cosa serve | € |
|---|---|---|---|---|
| 1 | **Scheda audio** | **Waveshare WM8960 Audio HAT** (Welectron, cod. 15668) — altoparlante 8 Ω incluso | Sostituisce da sola il microfono USB *e* lo speaker USB del riferimento. Codec stereo WM8960, **due microfoni MEMS** a bordo, ampli **1 W/canale su 8 Ω**. Si infila sull'header a 40 pin: zero saldature, zero cablaggi | 18,90 |
| 2 | **2° altoparlante** *(opzionale)* | full-range 40 mm **8 Ω** con connettore JST | Il WM8960 è stereo e la confezione ne porta uno solo | ~5,00 |
| 3 | **Display** | **Waveshare 2.4" LCD Module** — ILI9341, **240×320**, **senza touch**, PCB 70,5×43,3 mm (Welectron, cod. 18366) | La faccia di BMO. SPI, pilotato da `spidev` con blit sulle sole regioni cambiate | 12,90 |
| 4 | **Header stacking 2×20 extra-tall** | passo 2,54 mm, corpo ≥ 11 mm — **in coppia, non in kit assortito** | Fa sporgere i pin **sopra** il HAT audio, così i sette fili del display si innestano lì. Senza questo, HAT e display non coesistono | ~5,00 |
| 5 | **Fotocamera** | **OV5647 5 MP "a fuoco fisso" regolabile a pinza** + flat CSI 15 pin incluso | Il tool `scatta_foto`. Esce tarata a fuoco infinito, ma la lente si sblocca con una pinzetta: **la stessa taratura una tantum a ~30 cm** della versione "regolabile", a meno della metà del prezzo (§1.1bis) | 5,90 |
| 6 | **microSD** | **32 GB classe A1 di marca** | Sistema **e libreria musicale sulla stessa scheda** (§1.2bis). **Già in uso**: il Pi ci fa il boot dal bring-up | ~8,00 |
| 7 | **Magneti al neodimio 5×2 mm** | ×20 | Faceplate apribile senza viti a vista | ~6,00 |
| 8 | **Minuteria essenziale** | viti M2.5×6 autofilettanti (~20 pz) + Dupont F-F 20 cm | Gli unici due elementi senza alternativa (§1.1ter) | ~5,50 |
| 9 | Spedizioni | Welectron + Amazon.it | | ~6,00 |
| | | | **Totale** | **~68 €** *(73 con il 2° altoparlante)* |

Più ~200 g di filamento **PETG** (~5 €). Il PLA non è una preferenza estetica: la sua Tg è ~60 °C e in una scatola chiusa con 1,5–4 W dentro, d'estate, ci si arriva.

**Non serve comprare:** hub USB, cavo HDMI, condensatore da 1000 µF, filo siliconico AWG24, pulsanti, resistenze di pull-up, microcontrollore, PCB. **La rev. 5.1 ne toglie altri cinque**: LED e resistenza, dissipatori adesivi (rimandati al post-burn-in, non eliminati), il cavo USB con interruttore, la chiavetta USB per la musica, fascette e termorestringente.

### 1.1bis · La fotocamera e i dissipatori, motivati

**La fotocamera.** Il modulo "a fuoco fisso" da 5,90 € esce tarato all'infinito, non a 30 cm: va comunque calibrato una volta, esattamente come la versione "regolabile" da 12 € — pinzetta, si sblocca la ghiera, si ruota fino a mettere a fuoco un bersaglio a 30 cm, si fissa con una goccia di smalto. La differenza non è il lavoro di taratura (identico) ma il meccanismo motorizzato a vite micrometrica, pensato per chi deve *cambiare* fuoco di frequente. BMO fotografa sempre dallo stesso punto, alla stessa distanza: quel meccanismo è capacità che non si userà mai.

**I dissipatori.** "In casa non si superano i 25-26 °C" è la temperatura dell'*aria della stanza*, non quella *dentro una scatola sigillata da 0,5 L*. Una scatola chiusa scambia calore solo per convezione naturale attraverso pareti e feritoie: resistenza termica tipica 8-15 °C/W, quindi anche a 1,5 W di regime l'aria interna può stare 12-22 °C sopra la stanza — 37-48 °C interni. **Questo però non contraddice la richiesta di risparmiare**: 37-48 °C sono ben sotto la soglia di throttling (80 °C) e sotto la Tg del PETG (~80 °C). "Serve o non serve il dissipatore" ha una risposta misurabile, non stimabile: il burn-in di 72 ore della Fase 6.2 registra la temperatura reale ogni minuto. **Quindi: non si compra ora.** Sotto i 65 °C non serve mai; se ci si avvicina, 4 € e cinque minuti senza riaprire la stampa.

### 1.1ter · La minuteria, voce per voce

- **Viti M2.5×6 autofilettanti — essenziali, nessuna alternativa.** Le torrette del telaio stampato sono disegnate per autofilettanti. Cercarle in un kit di sole viti M2.5, non in un kit "elettronica assortita".
- **Dupont F-F 20 cm — essenziali, nessuna alternativa.** Collegano i 7 segnali del display (SCLK, MOSI, CS, DC, RST, BL, GND) dall'header sporgente al modulo.
- **Schiuma adesiva 2 mm — utile, non essenziale**, e non va comprata da un venditore di elettronica: è una guarnizione da infissi, pochi centesimi in ferramenta.
- **Fascette — rimosse.** Pura estetica del cablaggio interno; dentro un involucro chiuso nessuno le vede.
- **Termorestringente — rimosso, con motivazione tecnica.** Serviva quando microfono e ampli erano moduli discreti cablati a mano. Con il HAT non c'è più nessuna giunzione saldata in tutto il progetto: la voce non è "opzionale", è **obsoleta**.

Dei 12 € originari, ~5,50 € sono l'essenziale.

### 1.2bis · Perché la musica va sulla microSD e non su una chiavetta USB

Una chiavetta aggiunge un file system rimovibile da montare, un punto in cui una rimozione a caldo può corrompere dati, un componente da procurarsi. La microSD di sistema (32 GB) ospita comodamente la libreria in `/home/bmo/musica/`, popolata via SSH/SCP dal PC di sviluppo. **Zero costo aggiuntivo, un componente fisico in meno, la porta USB-A resta genuinamente libera** — buona per una chiavetta di diagnostica o per un microfono USB di riserva.

### 1.2ter · Lo spegnimento: perché la USB non può sostituire il cavo, e perché non serve nessuno dei due

**Sul Pi 3 A+ la porta USB-A e l'ingresso di alimentazione micro-USB sono due circuiti completamente separati.** La USB-A è una porta host: può ricevere segnali, non può erogare né interrompere l'alimentazione. Qualsiasi cosa infili lì può al massimo far partire uno script (`shutdown -h now` via `udev`/`triggerhappy`), mai tagliare la corrente né riaccendere il Pi da spento, perché a Pi spento il controller USB non riceve energia.

Questo rende superfluo anche l'oggetto che sostituiva. Un power-cycle fisico serve solo in due casi rari: un blocco che il watchdog hardware non recupera, o una vacanza lunga. In entrambi, l'alimentatore già comprato ha un suo cavo: lo si stacca dalla presa. **Il cavo micro-USB con interruttore (~5 €) sparisce dal BOM.**

### 1.2 Perché una scheda audio HAT invece del mic USB + speaker USB del riferimento

1. **Il Pi 3 A+ ha una sola porta USB-A.** Il riferimento ne usa due su un Pi 5 che ne ha quattro. Qui servirebbe un hub: un componente in più, un punto di guasto in più.
2. **Senza pulsanti, il microfono diventa critico.** Nel riferimento il pulsante è il *fallback* quando la wake word non sente. Qui quel fallback non c'è: se BMO non sente, non c'è nessun altro modo di parlargli. Il WM8960 ha **due** MEMS; un mini-mic USB da 8 € ne ha uno.
3. **L'overlay è in-tree.** `dtoverlay=wm8960-soundcard` sta in `raspberrypi/linux`: non serve il DKMS di Waveshare e non si rompe agli `apt upgrade`. Stessa disciplina che ha fatto cadere `fbcp-ili9341` e scartare il ReSpeaker 2-Mics.
4. **La USB resta libera davvero** (§1.2bis).

In più, gratis: microfoni e amplificatore stanno sullo **stesso codec**, quindi campione-sincroni. È la precondizione perché la cancellazione d'eco funzioni il giorno del barge-in.

**Piano B**, se il HAT tarda: mini-mic USB (~10 €) + hub passivo (~5 €) + altoparlante amplificato sul jack 3,5 mm. Funziona, costa uguale, suona peggio.

### 1.3 Il display: tre opzioni, una raccomandazione

| | **2.4" SPI** ✅ | 3.5" SPI | 5" DSI (fedele al riferimento) |
|---|---|---|---|
| Controller / risoluzione | ILI9341, 240×320 | ILI9488, 320×480 | 800×480 |
| Area attiva | 48,8 × 36,6 mm | ~73 × 49 mm | ~108 × 65 mm |
| Prezzo UE | **12,90 €** | ~22 € | 45–55 € |
| Byte per pixel | 2 (RGB565) | **3** (l'ILI9488 in SPI vuole 18 bit) | — (framebuffer KMS) |
| Costo RAM | ~2 MB di asset | ~4 MB | **CMA ≥ 64 MB** su 512 totali |
| Occupazione bus a 25 fps | ~11% | ~25% | n/a |
| Impatto sul guscio | BMO da comodino | BMO medio | BMO grande, ~150 mm di larghezza |

**Raccomandazione: il 2.4".** Non per risparmiare 10 €, ma perché su 512 MB il framebuffer KMS del DSI si mangia in CMA più RAM di quanta ne usi tutto `bmo-core`, e perché gli asset e `bmo-face` sono già progettati per 240×320.

**Nota:** la vecchia "trappola del 3,5 pollici" (13 fps a schermo pieno) veniva da `fbcp`, che copia **tutto** il framebuffer. Con il blit su dirty rect un 3.5" costa il 50% in più del 2.4", non il 400%.

**Verifica prima di stampare il guscio**: scrivere tre righe da ~20 caratteri e leggerle a mezzo metro.

> Questa è l'unica decisione d'acquisto ancora aperta — vedi la relativa issue nel repository.

### 1.4 Mappa dei pin

Il HAT occupa **I2S** (GPIO18/19/20/21) e **I2C** (GPIO2/3); il display sta su **SPI0** più tre GPIO liberi; la fotocamera passa dal CSI. I fili del display vanno sui pin che sporgono **sopra** il HAT.

| Segnale | Pin | BCM | Note |
|---|---|---|---|
| Display SCLK | 23 | GPIO11 | SPI0 |
| Display MOSI | 19 | GPIO10 | SPI0 |
| Display CS | 24 | GPIO8 | CE0 |
| Display DC | 16 | GPIO23 | |
| Display RST | 18 | GPIO24 | |
| **Display BL** | **32** | **GPIO12** | ⚠️ `luma.lcd` mette il backlight su **GPIO18** di default, che qui è il BCLK dell'I2S. Passare `gpio_LIGHT=12` (ALT0 = PWM0). Il sintomo se sbagliato è indiretto e fa perdere una serata: il display funziona e **l'audio smette** |
| Display MISO | — | — | **Non collegare** |
| Display VCC | — | 3,3 V o 5 V | **Guardare il modulo**: regolatore a bordo → 5 V; senza → 3,3 V, e 5 V lo distrugge. Nel dubbio 3,3 V |
| I2S + I2C + alimentazione audio | — | GPIO18/19/20/21, GPIO2/3 | Gestiti dal HAT, nessun cablaggio manuale |
| Fotocamera | CSI | — | connettore dedicato 15 pin |
| GPIO liberi | | 5, 6, 13, 16, 17, 22, 26, 27 | Non serve niente |

`/boot/firmware/config.txt`:

```
dtparam=spi=on
dtoverlay=wm8960-soundcard
dtparam=watchdog=on
camera_auto_detect=1
gpu_mem=16
# opzionale: dtoverlay=disable-bt   (se si rinuncia all'uscita A2DP verso una cassa vera)
```

### 1.5 Meccanica: cosa copiare dal riferimento

Strategia invariata: guscio da Printables, fori come *negative volume* nello slicer, telaio da `bmo_chassis.scad`. Dal riferimento tecnico, tre idee a costo zero:

- **Faceplate a magneti** (16–20 magneti 5×2 mm in tasche stampate) invece delle viti.
- **Sportello posteriore modulare**: si cambia quello che c'è dietro senza ristampare il corpo.
- **Arti a innesto**: pose intercambiabili.

Aggiunte, che nel riferimento non ci sono:
- **Feritoie passanti** ≥300 mm² in basso e ≥300 in alto, su pareti opposte, per l'effetto camino.
- **Un solo foro Ø 4 mm per i microfoni**, allineato alle porte MEMS. Al contrario dell'altoparlante, più fori peggiorano.
- **Microfoni e altoparlante il più lontani possibile, mai sulla stessa parete rigida.**
- **Camera di compressione** per l'altoparlante (~12 cm³ con sfiato) e guarnizione di schiuma sul cestello.

**La regola che fa risparmiare due giorni:** prima di stampare qualsiasi cosa che duri più di un'ora, stampare il **provino della sola interfaccia**.

---

## 2 · Architettura software

### 2.1 La macchina a stati

**Lo stato WARM-UP si svuota**: con l'inferenza in cloud non c'è nessun modello da tenere caldo. Ne resta un'eco utile: **tenere aperta una connessione HTTPS keep-alive** verso Gemini, che risparmia l'handshake TLS a ogni turno (~200–400 ms).

```
   [BOOT ~2 s]
       │  carica il modello wake word, apre la sessione HTTPS, faccia "assonnata"
       ▼
 ┌─►[WAIT]──────────────────────────────────────────────────────┐
 │     │  openWakeWord su 16 kHz mono · ~1,3 W · zero traffico   │
 │     │  faccia idle, battito di palpebre a intervalli IRREGOLARI│
 │     ▼  "Hey BMO"                                              │
 │  [LISTEN]                                                     │
 │     │  entro 150 ms: faccia "ascolto" + chirp breve           │
 │     │  registra fino a endpoint (VAD, 800 ms di silenzio)     │
 │     │  cap 15 s · WAV 16 kHz mono in /dev/shm                 │
 │     ▼                                                         │
 │  [THINK]                                                      │
 │     │  a 0,2 s: clip di attesa pre-generata, scelta a caso    │
 │     │  audio + storico + tool → gemini-3.8-flash              │
 │     │  ┌── loop agentico, max 4 giri / 20 s ──┐               │
 │     │  │  functionCall → esegui → functionResponse │           │
 │     │  └───────────────────────────────────────┘               │
 │     ▼  testo finale (≤ 2 frasi, imposto dal prompt)           │
 │  [SPEAK]                                                      │
 │     │  testo → gemini-3.1-flash-tts-preview → PCM 24 kHz      │
 │     │  inviluppo RMS a 25 Hz calcolato PRIMA di riprodurre    │
 │     │  microfono chiuso (half-duplex in V1)                   │
 │     └──────────────────────────────────────────────────────►──┘
 │
 └── [ERRORE] rete giù / timeout → clip "non ci arrivo", faccia triste, → WAIT
```

**A ogni transizione cambia la faccia.** Con la premessa "solo voce" non è un tocco estetico: senza pulsanti e senza LED di stato, la faccia è l'**unico** modo di sapere che la wake word è stata sentita. Requisito preciso: **transizione WAIT → LISTEN visibile e udibile entro 150 ms**. Se ci mette mezzo secondo, l'utente ripete "Hey BMO" e rompe la cattura.

### 2.2 Tre processi

```
        2× MEMS ──dsnoop──►┌──────────────────────────────────────┐
        (WM8960)           │ bmo-core   processo 1 · asyncio      │
                           │  thread: openWakeWord (ONNX)         │──HTTPS──► gemini-3.8-flash
                           │  task:   VAD + cattura               │  keep-alive
                           │  task:   loop agentico + tool        │
                           │  task:   TTS → inviluppo RMS         │──HTTPS──► gemini-3.1-flash-tts
                           └──────────────┬───────────────────────┘
                              /run/bmo.sock (un JSON per riga)
                    ┌─────────────────────┴───────────────┐
        ┌───────────▼──────────┐              ┌───────────▼──────────┐
        │ bmo-face  proc 2     │              │ mpv       proc 3     │
        │ nice −5 · 25 fps     │              │ nice +5 · decode in C│
        │ blit RGB565 dirty    │              │ --input-ipc-server   │
        │ possiede spidev0.0   │              └───────────┬──────────┘
        └───────────┬──────────┘                         │
                 SPI0 → display            ALSA dmix ──► WM8960 ──► altoparlanti
```

La separazione in processi non serve ad aggirare il GIL (ONNX, le `ioctl` SPI e la rete lo rilasciano già). Serve a **isolamento dei guasti** (se `bmo-core` va in eccezione, systemd lo riavvia in due secondi e la faccia continua a sbattere le palpebre; nello stesso processo ogni bug del dialogo produrrebbe uno schermo nero) e a **priorità di scheduling opposte**.

Messaggi:

```
{"cmd":"state",      "value":"listening"}
{"cmd":"speak",      "envelope":[0.10,0.42,0.71,...], "fps":25}
{"cmd":"expression", "value":"felice", "ttl":3.0}
{"cmd":"timer",      "remaining":312, "label":"pasta"}
{"cmd":"level",      "value":0.34}          # durante LISTEN: le pupille reagiscono alla voce
```

### 2.3 Il prompt di sistema e l'iniezione di contesto

Due strati: una parte fissa e una **ricostruita a ogni turno** con lo stato reale del dispositivo. È il secondo strato a rendere affidabile il tool calling.

**Strato fisso** (`system_instruction`):

```
Sei BMO, la piccola console vivente di Adventure Time, e vivi in una casa a Milano.
Sei entusiasta, curioso e un po' ingenuo; ti preoccupi dei tuoi amici. Non sei servile.

REGOLE DI FORMA — sono vincolanti, il tuo testo va a un sintetizzatore vocale:
- Rispondi SEMPRE in italiano.
- Massimo 2 frasi. Se la risposta richiede più di 2 frasi, dai la sintesi e offri di continuare.
- Niente markdown, niente elenchi puntati, niente emoji, niente parentesi, niente sigle
  da leggere lettera per lettera. Scrivi i numeri come si pronunciano.
- Non descrivere quello che stai facendo ("sto cercando..."): lo dice già la faccia.

REGOLE SUGLI STRUMENTI:
- Usa uno strumento solo se la risposta lo richiede davvero. Una poesia sui dinosauri
  non richiede strumenti.
- scatta_foto SOLO se la domanda riguarda ciò che vedi o l'ambiente fisico intorno a te.
  Non scattare foto per curiosità e mai senza che qualcuno te l'abbia chiesto.
- cerca_sul_web per fatti che cambiano nel tempo: notizie, prezzi, orari, meteo, risultati.
  Se non sai una cosa, cercala invece di inventarla.
- Chiama imposta_espressione quando la tua risposta ha un tono preciso.
```

**Strato dinamico** (rigenerato a ogni turno):

```
[STATO ALLE 22:14 DI MARTEDÌ 8 SETTEMBRE 2026, Europe/Rome]
Timer attivi: "pasta" scade fra 4 minuti e 12 secondi.
Musica: in riproduzione, "Radio Deejay", volume 60 percento.
Fotocamera: presente, punta in avanti, illuminatore disponibile.
Rete: connessa.
Ultima cosa che hai detto: "Ho messo il timer per la pasta."
```

Tre dettagli che sembrano piccoli e non lo sono:

- **L'ora locale va iniettata sempre.** È la prima causa di risposte sbagliate su qualsiasi assistente: il modello non ha un orologio, e "fra dieci minuti" senza sapere che ore sono non significa niente.
- **"Massimo 2 frasi" è un requisito funzionale, non stilistico.** Senza pulsanti non si può interrompere BMO: una risposta di ottanta parole è ottanta parole da ascoltare fino in fondo.
- **"Niente markdown"** va ripetuto: un asterisco letto ad alta voce da un TTS diventa "asterisco".

### 2.4 Gli strumenti

```python
scatta_foto(motivo: str)
cerca_sul_web(query: str)
imposta_timer(etichetta: str, ore: int = 0, minuti: int = 0, secondi: int = 0)
annulla_timer(etichetta: str | None)
elenca_timer()
riproduci_musica(query: str, sorgente: "chiavetta" | "radio")
controllo_riproduzione(azione: "pausa"|"riprendi"|"stop"|"successivo")
regola_volume(percentuale: int)
imposta_espressione(stato: "felice"|"pensieroso"|"sorpreso"|"triste"|"assonnato")
metti_in_pausa_l_ascolto(minuti: int)
```

**`scatta_foto` — dove il cloud regala un ordine di grandezza.** Nel riferimento questo tool è il più lento: scatta, re-inietta l'immagine, **cambia modello** e l'insieme richiede **circa un minuto**. Con Gemini la foto è un'altra parte della stessa conversazione: **una chiamata in più, ~1,5 s**.

1. `libcamera-still -o /dev/shm/scatto.jpg --width 640 --height 480 -q 75 -n -t 800`. Un JPEG a 640×480 pesa ~50 kB. Nessun illuminatore: la cucina è sempre ben illuminata e BMO scatta sempre da ~30 cm.
2. Rispondere al `functionCall` con un `functionResponse` breve (`{"stato":"ok"}`) **e** accodare un nuovo `Content` di ruolo `user` con la parte `inlineData` che porta il JPEG.
3. Richiamare il modello. Risponde guardando la foto.

**`cerca_sul_web` — perché resta DuckDuckGo.** Il grounding con Google Search nativo sarebbe più pulito, ma **sul free tier non è disponibile** (sul piano a pagamento: 5.000 ricerche/mese incluse, poi 14 $ ogni 1.000), e combinare strumenti nativi con le proprie function declaration nella stessa richiesta è in Preview e solo sui modelli Gemini 3. Quindi V1 con `ddgs`, tre risultati con titolo, snippet e URL. Il giorno del passaggio al piano a pagamento si sostituisce con `google_search` senza toccare il resto — vedi la relativa issue V2.

**`riproduci_musica` — tre sorgenti, in ordine di affidabilità.**

1. **Libreria locale sulla microSD** (`/home/bmo/musica/`): istantaneo, funziona senza rete, zero dipendenze. È la sorgente predefinita.
2. **Radio via internet**: un JSON di stazioni curato a mano, `mpv` ci si attacca in un secondo.
3. **YouTube via `yt-dlp`**: su un Pi 3 A+ la risoluzione dell'URL richiede 5–10 s e ~100 MB di RSS transitorio. Rimandato alla V2.

**Un'idea per la V2 — Spotify Connect.** `raspotify` (servizio systemd attorno a `librespot`) farebbe comparire BMO come cassa fra i dispositivi dell'app Spotify: zero integrazione da programmare, il telefono resta il telecomando. ~30-50 MB solo mentre suona. **Serve un account Spotify Premium.**

`mpv` gira sempre con `--input-ipc-server=/run/mpv.sock`: pausa, volume e ducking sono comandi IPC.

**I timer sono la funzione col costo di errore più alto.** Tre regole: in `/var/lib/bmo/timers.json` si salva la **scadenza assoluta**, mai i secondi rimanenti; riscrittura con temporaneo + `rename` atomica; all'avvio, un timer scaduto durante il downtime **suona lo stesso**, con messaggio diverso.

### 2.5 Cosa resta in locale e cosa va in cloud

| Funzione | Dove | Perché |
|---|---|---|
| **Wake word** | **Locale, obbligatorio** | L'alternativa sarebbe streammare il microfono 24/7 verso il cloud: insostenibile per costo, banda e privacy. openWakeWord in ONNX: ~10 MB di modelli, <10% di un core. **Non è una concessione: è l'unico modo di avere un dispositivo cloud che non ascolti sempre** |
| **VAD / endpointing** | Locale, banale | `webrtcvad` |
| **STT** | **Cloud** | Gemini è multimodale: trascrizione e ragionamento sono la stessa chiamata. Whisper.cpp `tiny` su un 3 A+ impiegherebbe 5–10 s per 5 s di audio |
| **LLM + loop agentico** | **Cloud**, obbligato | 512 MB. Non c'è discussione |
| **Vision** | **Cloud** | Stesso modello, stessa conversazione: sparisce il model swap da ~1 minuto |
| **Ricerca web** | **Ibrido** | Funzione locale (DuckDuckGo) + ragionamento in cloud |
| **TTS** | **Cloud** | Vedi sotto |
| **Clip di attesa e di errore** | **Locale — ma sono file, non un motore** | Pre-generate col TTS di Gemini sul PC di sviluppo. Latenza zero, RAM zero |
| **Faccia** | Locale | Nessuna latenza di rete è accettabile per un'animazione |

**Sul TTS**: il piano precedente aveva scelto Piper in locale per la sincronizzazione labiale. Quell'argomento **non regge più**: la sincronia gratis viene dal conoscere l'intera forma d'onda prima di riprodurla, e questo vale per **qualsiasi TTS non in streaming**, cloud incluso. L'argomento colpiva la *Live API*, non il cloud in sé.

Quindi: **TTS in cloud come motore primario** (`gemini-3.1-flash-tts-preview`, PCM 24 kHz, italiano, ~30 voci), **non-streaming in V1** proprio per tenere la sincronia labiale gratis. **Piper resta come rete di sicurezza opzionale** (~40 MB solo mentre sintetizza), non come motore.

### 2.6 Wake word: le note pratiche che fanno perdere una serata

- **openWakeWord** con modello «Hey BMO» dal Colab ufficiale su dati sintetici. In sviluppo si usa `hey_jarvis` preaddestrato: l'addestramento è rifinitura, non prerequisito.
- **La soglia si tara nella stanza vera, con la TV accesa.** Tarata in silenzio è inutile.
- **Sistema a 64 bit** (Raspberry Pi OS Lite arm64). Il 32 bit consumerebbe ~30 MB in meno, ma `onnxruntime` non pubblica ruote ufficiali armv7l e le `tflite-runtime` per ARM 32 bit sono un campo minato. **Questa decisione è chiusa**: arm64 per la disponibilità delle ruote onnxruntime, non da riaprire.
- **`zram` invece di swap su SD.** `zram-tools` con 256 MB in zstd dà margine **senza scrivere un byte sulla scheda**.
- **Porcupine come piano B se la RAM stringe**: qualche MB invece di ~110. L'obiezione precedente ("BMO deve svegliarsi anche col router giù") **con questa architettura non esiste più**: col router giù BMO non può fare nulla comunque.

### 2.7 Le due conseguenze scomode del "solo voce"

**1 · Non si può interrompere BMO mentre parla.** In V1 il microfono è chiuso durante SPEAK.
- *Subito*: limite di 2 frasi nel prompt, e un tetto duro di ~15 s sull'audio sintetizzato lato codice. Il prompt è un'indicazione, il tetto è una garanzia.
- *V1.5*: microfono **aperto** durante SPEAK con wake word a soglia alzata; su rilevamento parziale abbassa il volume al 30% per un secondo.
- *V2*: barge-in con cancellazione d'eco. Funziona perché microfoni e amplificatore stanno sullo **stesso codec**. Su 512 MB conviene **speexdsp** (`SpeexEchoState`, pochi MB) al `module-echo-cancel` di PipeWire.

**2 · Nessun interruttore fisico del microfono.** Tre livelli:
- La wake word gira **in locale** e nulla lascia la casa finché non si dice «Hey BMO».
- Il comando vocale `metti_in_pausa_l_ascolto(minuti)`, con la faccia che dorme visibilmente. Onesto ma software.
- Un **interruttore a slitta** che apre l'alimentazione dei MEMS, nascosto sotto la base. È l'unica garanzia vera. Resta una scelta aperta — vedi la relativa issue.

Sul free tier **Google può usare i dati inviati**: si sviluppa sul free tier, si passa al piano a pagamento quando BMO smette di essere un prototipo.

### 2.8 Bilancio della RAM — il numero che decide tutto

| Voce | RAM | Nota |
|---|---|---|
| Raspberry Pi OS Lite arm64 a riposo | ~90 MB | senza desktop, senza avahi, journald volatile |
| `bmo-core` | ~120 MB | Python + ONNX Runtime + modelli wake word + client HTTPS |
| `bmo-face` | ~35 MB | Python + framebuffer + asset RGB565 mappati (~2 MB) |
| `mpv` | ~35 MB | solo mentre suona |
| transitori (`libcamera-still`, `aplay`, JPEG in `/dev/shm`) | ~15 MB | |
| **Picco** | **~295 MB** | su ~495 MB con `gpu_mem=16` → **~200 MB di margine** |

| | Riferimento tecnico (locale, Pi 5 16 GB) | **Questo piano (cloud, Pi 3 A+ 512 MB)** |
|---|---|---|
| STT | Whisper small, ~1 GB | 0 — è dentro la chiamata a Gemini |
| LLM | Gemma 3 quantizzato, 2–4 GB | 0 |
| VLM | Moondream 2, ~2 GB | 0 |
| TTS | Piper, ~150 MB | 0 — clip pre-generate + chiamata cloud |
| Wake word | openWakeWord, ~110 MB | ~110 MB — **l'unica voce identica** |
| Faccia, audio, sistema | ~200 MB | ~185 MB |
| **Totale** | **~4–8 GB** | **~295 MB** |

**È lo spostamento in cloud a rendere possibile il progetto su 512 MB, non il contrario.**

Regole per non perdere il margine: `MemoryMax=` nelle unit systemd, audio di scratch in `/dev/shm`, `Storage=volatile` in `journald.conf`, `zram` da 256 MB.

### 2.9 Latenza e costo

| Passo | Tempo |
|---|---|
| Endpoint VAD (silenzio di coda) | 0,8 s |
| Upload audio (5 s a 16 kHz mono, ~160 kB, Wi-Fi) | 0,2–0,4 s |
| `gemini-3.8-flash`, senza tool | 1,0–1,8 s |
| `gemini-3.1-flash-tts-preview` | 0,8–1,5 s |
| **Totale** | **~2,8–4,5 s** |
| *con un tool (ricerca o foto)* | *+1,5–3 s* |

Il numero che conta non è questo: è **0,2 s**, il tempo entro cui parte la clip di attesa pre-generata. **Un BMO muto per tre secondi è percepito come rotto.**

**Costo** per ~40 turni al giorno:

| | Free tier | Piano a pagamento |
|---|---|---|
| `gemini-3.8-flash` (audio in, testo out) | **0 €** | ~1,2 $/mese |
| `gemini-3.1-flash-tts-preview` | **0 €** | ~5 $/mese |
| Ricerca web (DuckDuckGo) | 0 € | 0 € |
| **Totale** | **0 €** | **~6 $/mese** |

**La sintesi vocale domina il conto.** La leva: le frasi ricorrenti pre-generate una volta diventano file. Da mettere dal primo giorno: un **contatore giornaliero con un tetto** in `bmo-core`.

### 2.10 Audio: un codec, due flussi

```
# ~/.asoundrc
pcm.!default { type asym  playback.pcm "out"  capture.pcm "in" }
pcm.out  { type plug slave.pcm "mixed"  }
pcm.in   { type plug slave.pcm "snooped" }
pcm.mixed   { type dmix   ipc_key 1024
              slave { pcm "hw:0,0" rate 48000 period_size 1024 buffer_size 8192 } }
pcm.snooped { type dsnoop ipc_key 2048
              slave { pcm "hw:0,0" rate 48000 channels 2 } }
```

Il codec gira a 48 kHz; il ricampionamento a 16 kHz è in software e trascurabile. Il `dsnoop` permette a wake word e cattura di leggere lo **stesso** microfono senza litigare. Niente PipeWire in V1.

### 2.11 Pipeline asset della faccia — gira sul PC di sviluppo

Le GIF non si decodificano sul Pi. Si convertono **una volta sul PC di sviluppo** (il portatile Linux) in un `.bin` di fotogrammi RGB565 grezzi più un manifesto JSON con le regioni; il Pi lo mappa in memoria e fa `write()` sul bus. Decodifica a runtime: zero. Memoria: ~2 MB.

```python
# build_face.py — sul PC di sviluppo, una volta
from PIL import Image
def rgb565(im):
    px = im.convert("RGB").tobytes()
    return b"".join(
        ((px[i]&0xF8)<<8 | (px[i+1]&0xFC)<<3 | px[i+2]>>3).to_bytes(2,"little")
        for i in range(0,len(px),3))
# → faces.bin + faces.json  {stato: {regione:[x,y,w,h], frames:N, offset:B}}
```

Stati minimi: `assonnato` (boot e pausa), `idle` (battito di palpebre a intervalli **irregolari** — la regolarità è ciò che fa sembrare morta un'animazione), `ascolto` (pupille che reagiscono al livello del microfono), `pensiero`, `parlato` (bocca pilotata dall'inviluppo RMS), `felice`, `triste`, `sorpreso`, `errore-rete`, `timer` (countdown grande).

Fra due fotogrammi cambiano ~12.000 pixel su 76.800: da 153,6 kB a **24,7 kB per fotogramma**, 4,5 ms di bus invece di 28 — l'11% del bus SPI a 25 fps e meno dell'8% di un core.

---

## 3 · Roadmap

> **Aggiornamento 2026-09-19 — roadmap software-first.** Questa sezione sostituisce la roadmap hardware-first della rev. 5.1, che partiva da "decidere il display e ordinare". Adesso **tutto il software si scrive prima**, sul PC di sviluppo (il portatile Linux omarchy), usando webcam, microfono e altoparlanti del computer. **Comprare i componenti elettronici è l'ultima fase.** Le analisi delle sezioni 1 e 2 restano valide: cambia solo l'ordine in cui si fanno le cose.

**Nessun pezzo del software aspetta l'hardware.** `bmo-core` è costruito attorno ad adapter intercambiabili ([`bmo-core/`](../bmo-core/)): webcam V4L2 al posto della camera CSI, microfono e casse del PC al posto del HAT WM8960. Il resto del codice dipende solo dalle interfacce, quindi il passaggio al Pi cambia un solo punto (`BMO_ENV=pi`). Il Pi è già in mano e raggiungibile via SSH: il software ci si sposta appena funziona sul PC. I componenti si comprano per ultimi, quando il software è finito e se ne conoscono i requisiti reali (RAM, leggibilità della faccia, sensibilità del microfono).

```
FASE 1  Software su PC    [giro Gemini][cervello: strumenti, stato, memoria ────────]
                                 [clip di attesa · wake word · faccia · foto ────]
FASE 2  Porting sul Pi                        [irrobustimento · deploy · misure RAM]
FASE 3  Acquisto                                                 [ordine UE]
FASE 4  Hardware                                                      [audio][display][camera]
FASE 5  Meccanica         [provini, quando capita]                    [telaio e guscio ──]
FASE 6  Integrazione                                                               [burn-in 72 h]
FASE 7  V2                (solo dopo due settimane di BMO in casa)
```

Le milestone su GitHub seguono questa divisione:

| Milestone | Fasi |
|---|---|
| **1 · Software su PC (bmo-core)** | Fase 1 |
| **2 · Porting sul Pi** | Fase 2 |
| **3 · Acquisto hardware e integrazione** | Fasi 3–6 |
| **4 · V2** | Fase 7 |

### Fase 1 — Software su PC *(bmo-core su omarchy)*

Tutto gira con `BMO_ENV=dev-linux`: `WebcamV4L2Adapter` per la foto, `ArecordAdapter` sul microfono del portatile, `MpvAdapter` sulle sue casse. Prima di cominciare, le verifiche del [README di bmo-core](../bmo-core/README.md) (`arecord -l`, `v4l2-ctl --list-devices`, `mpv` e `ffmpeg` installati).

**1.1 · Chiave API e primo contatto con Gemini** — *il singolo esperimento che vale di più di tutto il progetto*. Venti righe sul PC di sviluppo: tre secondi di audio dal microfono del portatile → `gemini-3.8-flash` con una `function_declaration` per `imposta_timer`. *Criterio di uscita*: «Metti un timer di dieci minuti» produce `imposta_timer(durata_secondi=600, etichetta="...")`. Provare anche «che ore sono» **senza** iniettare l'ora: si vedrà il modello inventare, dimostrazione pratica del perché §2.3 esiste.

**1.2 · Il giro completo.** `brain.py` con `ascolta()`, `rispondi()`, `strumenti()`, collegati agli adapter e mai alle classi concrete. *Uscita*: venti frasi di prova — **sotto 18 su 20 il problema è il prompt di sistema**. Qui entrano il fallback a un modello inferiore quando finisce la quota e il riepilogo forzato quando il loop agentico tocca il tetto di 4 giri/20 s.

**1.3 · Strumenti e stato.** Le dieci funzioni della §2.4, la macchina a stati della §2.1, la memoria persistente con conferma vocale obbligatoria (stato `CONFIRM`) e l'elenco configurabile delle persone di casa nel prompt di sistema. *Il test brutale che vale più di dieci unit test*: far partire un timer, uccidere il processo, riavviarlo, verificare che suoni all'ora giusta.

**1.4 · Le clip di attesa.** Una ventina di clip brevi in italiano generate col TTS di Gemini — attesa («ci penso!», «un attimo…», «vediamo…»), conferma, errore di rete, timer scaduto. Suonano sulle casse del PC tramite `MpvAdapter`. *Uscita*: BMO non resta mai muto per più di 0,3 s.

**1.5 · Wake word sul microfono del PC.** `pip install openwakeword onnxruntime`, modello `hey_jarvis`, collegata alla macchina a stati. La soglia tarata qui è **provvisoria**: il microfono del portatile non è il MEMS del HAT. Serve a scrivere e collaudare tutta la logica (rilevamento → ascolto → risposta → ritorno in attesa); il cancello vero, a 3 metri con la TV accesa, resta alla fase 4.4. *Uscita*: il giro completo parte a voce, senza toccare la tastiera, dal portatile a un metro.

**1.6 · La faccia in una finestra.** La pipeline asset della §2.11 gira sul PC di sviluppo; `bmo-face` disegna in una finestra 320×240 invece che sul bus SPI, con gli stati minimi della §2.11 pilotati da `bmo-core` sullo stesso socket Unix che userà sul Pi. *Uscita, due*: (a) tutti gli stati, battito di palpebre irregolare, bocca pilotata dall'inviluppo RMS; (b) la finestra mostrata **alle dimensioni fisiche del pannello** (48,96 × 36,72 mm per il 2.4") per una prima prova di leggibilità delle tre righe da 20 caratteri a mezzo metro. Il punto (b) dà un dato concreto per la scelta del display (§1.3) prima di comprarlo.

**1.7 · Foto con la webcam.** `scatta_foto` con `WebcamV4L2Adapter`, JPEG a Flash col pattern in due parti della §2.4. *Uscita*: «cosa vedi?» con qualcosa davanti alla webcam → descrizione corretta in meno di 6 s.

### Fase 2 — Porting sul Pi *(il Pi è già in mano)*

Il bring-up è fatto (settembre 2026): Raspberry Pi OS a 64 bit (Debian 13 trixie), SSH a sola chiave pubblica, Wi-Fi configurato. Senza HAT audio né display, il Pi basta già per misurare quello che conta davvero: RAM, stabilità, tempi.

**2.1 · Irrobustimento per il 24/7.** L'immagine installata è quella **con desktop** (`graphical.target`, ~187 MB occupati a riposo su 415 MB visibili): è la prima cosa da togliere. `sudo systemctl set-default multi-user.target` (oppure riflashare la versione Lite), poi `systemctl disable dphys-swapfile`; `apt install zram-tools` con 256 MB in zstd; `Storage=volatile` in `journald.conf`; `dtparam=watchdog=on` + `RuntimeWatchdogSec=15`; `gpu_mem=16`; `dtparam=spi=on`. *Uscita*: `free -m` intorno a 90 MB usati, 0 di swap su disco; `vcgencmd get_throttled` = `0x0`.

**2.2 · Deploy a un comando.** Uno script che dal PC di sviluppo sincronizza `bmo-core` e `bmo-face` sul Pi e riavvia i servizi. Socket Unix, due servizi systemd con `Restart=always` e `MemoryMax=`.

**2.3 · Misure sul Pi senza periferiche.** Il giro completo con l'audio letto da file WAV al posto del microfono e l'uscita sul jack da 3,5 mm (bastano degli auricolari). Qui si misura anche se STT/TTS locali (whisper.cpp tiny + Piper) stanno nei 512 MB, come riserva per quando manca la rete. `systemd-cgtop` per una giornata intera. *Uscita*: **picco RSS totale < 320 MB, zero eventi OOM in 24 h.**

### Fase 3 — Acquisto dei componenti *(l'ultima spesa)*

**3.1 · Congelare la configurazione.** La sola domanda aperta: display 2.4" o 3.5" (§1.3), ora con la prova di leggibilità della fase 1.6 in mano. Se non si riesce a decidere, prendere il 2.4". *Criterio di uscita*: nel titolo dell'inserzione devono comparire **ILI9341** *e* **240×320** *e* **senza touch**. È il rischio d'acquisto numero uno: gli ST7789 da 240×240 sono i più venduti.

**3.2 · Un solo ordine, tutto UE.** La distinta della §1.1. La microSD c'è già: il Pi ci fa il boot dal bring-up. Se le misure della fase 2 o la wake word provvisoria della fase 1.5 hanno cambiato qualcosa (per esempio un microfono USB direzionale come piano B), si corregge la distinta **prima** di ordinare.

### Fase 4 — Hardware: audio, display, fotocamera *(all'arrivo dell'ordine)*

Si passa a `BMO_ENV=pi` con le periferiche vere. Il software è già finito: questa fase valida l'hardware, non scrive codice nuovo.

> L'audio va **prima** del display: è il sottosistema su cui poggia l'intera interazione ora che non ci sono pulsanti.

**4.1 · Il HAT.** Infilare il HAT, aggiungere `dtoverlay=wm8960-soundcard`, riavviare, `aplay -l` e `arecord -l`. Poi `speaker-test -c2 -twav` con `watch -n1 vcgencmd get_throttled`. *Uscita*: rumore rosa all'80% per due minuti con `get_throttled = 0x0`.

**4.2 · Pressione sonora — il criterio che questa revisione mette a rischio.** Rumore rosa all'80%, fonometro (basta un'app) a 1 m. **Obiettivo ≥ 78 dB.** Se non basta: secondo altoparlante, poi camera di compressione, poi MAX98357A esterno sul line-out (~8 €). **Misurare prima di chiudere la meccanica.**

**4.3 · Ingresso e convivenza dei flussi.** `arecord -D hw:0,0 -f S32_LE -r 48000 -c2 test.wav`; picco a voce normale a **1,5 m** fra −18 e −6 dBFS. Poi il `~/.asoundrc` della §2.10, e la prova vera: `mpv` che suona mentre due `arecord` leggono contemporaneamente. *Uscita*: trascrizione corretta da Gemini **a 3 metri**.

**4.4 · Wake word sul dispositivo vero — il vero cancello della fase.** La soglia della fase 1.5 si ritara **nella stanza vera, con la TV accesa**, sul microfono del HAT. *Uscita*: **≥ 9 rilevamenti su 10 a 3 metri con la TV accesa, e meno di un falso positivo al giorno.**

**4.5 · Primo pixel.** `luma.lcd` con **`gpio_LIGHT=12`**. Prima di collegare VCC, cercare il regolatore sul modulo. *Uscita*: un rettangolo rosso — valida cablaggio, tensione e init insieme.

**4.6 · Misurare il bus prima di progettarci sopra.** Cento fotogrammi pieni cronometrati + mille blit di una finestra 120×56. Alzare il clock SPI finché non compaiono artefatti, poi tornare indietro di uno scalino (40–62,5 MHz con cavi corti). *Uscita*: ≥30 fps a schermo pieno e >150 blit/s.

**4.7 · `bmo-face` sul display vero.** Lo stesso `bmo-face` della fase 1.6, con l'uscita sul bus SPI invece che in una finestra. *Uscita, due*: (a) 25 fps sotto il 10% di un core; (b) **tre righe da 20 caratteri leggibili a mezzo metro**. Il punto (b) decide la dimensione del guscio: verificarlo **prima** di stampare.

**4.8 · Fotocamera.** `libcamera-still` al posto della webcam, stesso pattern della fase 1.7. **Taratura una tantum della lente a ~30 cm** (non 1,5 m) con un giornale: sbloccare la ghiera con una pinzetta, ruotare fino a fuoco netto, fissare con una goccia di smalto. Nessuna finestrella trasparente davanti alla lente. *Uscita*: «cosa vedi?» con qualcosa a ~30 cm → descrizione corretta in meno di 6 s.

### Fase 5 — Meccanica *(provini quando capita, telaio e guscio con l'hardware in mano)*

**5.1 · Provini, prima di tutto.** Non richiedono componenti e si possono fare in qualsiasi momento. I cinque criteri nello slicer (è un guscio o una figura? profondità interna netta ≥ 50 mm? si riapre? faccia piana? meno di 300k triangoli?), poi mascherina e provino della finestra. Dieci minuti ciascuno.

**5.2 · Telaio parametrico.** Calibro alla mano su display, HAT, altoparlanti. **Profondità del guscio: 55 mm** (stack con HAT su header extra-tall ~50 mm: 2,5 parete + 5 display + 3 gap + 20 Pi + 11 HAT + 6 raggio cavi + 2,5). Stampare prima il provino delle torrette.

**5.3 · Guscio: finestra, feritoie, griglie, magneti.** Tutto come *negative volume*, zero CAD: finestra passante **47,6 × 35,4 × 10 mm** (2.4"), tasca d'appoggio ~72 × 45 × 3,4 mm (PCB Waveshare 70,5 × 43,3), griglia altoparlante a fori esagonali Ø 3,2 mm con muri da 1 mm (~55% aperto), foro microfono Ø 4 mm singolo, feritoie ≥300 mm² in basso e in alto su pareti opposte, tasche per i magneti. *Stampa*: PETG, 0,2 mm (0,12 per la mascherina), 3 perimetri sul guscio e 4 sul telaio, 15% gyroid. **Ordine**: mascherina → provino finestra → provino torrette → telaio (~3 h) → guscio (7–10 h).

**5.4 · Assemblaggio.** Cablaggio completo **fuori dal guscio**, tutto acceso e funzionante. Poi l'altoparlante con la guarnizione (non si raggiunge più dopo), poi il Pi col HAT, per ultimo il display. Prova a telaio nudo. **USB-A e microSD affacciate su un fianco** (~45 mm liberi in linea).

### Fase 6 — Integrazione e messa in esercizio

**6.1 · Avvio automatico e resilienza.** `Restart=always`, `RestartSec=2`, `After=network-online.target` solo per core. Watchdog hardware attivo. *Il dettaglio che fa la differenza*: **la faccia deve accendersi prima che la rete sia pronta**, con lo stato "assonnato". *Aggiunta di questa revisione*: uno stato **`errore-rete`** esplicito — un BMO cloud senza rete è muto, e deve **dirlo con la faccia** invece di sembrare guasto.

**6.2 · Burn-in di 72 ore.** Script che ogni minuto registra temperatura, RSS, `get_throttled`, stato Wi-Fi, uptime dei servizi e conteggio delle chiamate API. *Criteri, tutti e sei*: temp max **< 65 °C** · `get_throttled = 0x0` per 72 h · zero riavvii dei servizi · zero disconnessioni Wi-Fi · RSS stabile entro il 5% · **zero falsi positivi della wake word durante la notte**. *Termica*: < 65 °C nessuna ventola; 65–75 allargare le feritoie; > 75 ventola 25 mm — ma è una sorgente di rumore a 8 cm dai microfoni, e quel rumore lo si paga in accuratezza per sempre. *Dissipatori*: se ci si avvicina ai 65 °C, 4 € e cinque minuti senza riaprire nulla.

**6.3 · Rifinitura del carattere.** Personalità nel prompt, `imposta_espressione` collegato agli stati della faccia, un suono di avvio, il battito di palpebre irregolare. La scelta della voce fra le ~30 di Gemini TTS va fatta qui, ascoltandone cinque di seguito sulla stessa frase.

### Fase 7 — V2 *(solo dopo due settimane di BMO in casa)*

**7.1 · Barge-in** — promosso a **funzione più importante della V2**: senza pulsanti è l'unico modo di interrompere BMO. `speexdsp` AEC sfruttando il codec condiviso.
**7.2 · Grounding nativo** — al passaggio al piano a pagamento, `google_search` al posto di `cerca_sul_web`.
**7.3 · Modalità Live** — `LiveBrain` dietro la stessa interfaccia. Latenza ~0,85 s invece di ~3, al prezzo dell'inviluppo calcolato al volo e di un costo 4–5× superiore.
**7.4 · Domotica** — una sola funzione che parla a Home Assistant, lasciando a lui il compito di conoscere i dispositivi.

---

## 4 · Rischi, in ordine di probabilità

| Rischio | Quando | Contromisura |
|---|---|---|
| **Si compra il pannello sbagliato** | alta, alla consegna | ILI9341 **e** 240×320 **e** no touch nel titolo |
| **Il modello 3D non ha volume interno utile** | alta, fase 5.1 | I cinque criteri nello slicer, dieci minuti, prima di stampare |
| **La wake word non regge a 3 m** | **media, il rischio nuovo di questa revisione** | Senza pulsanti non c'è fallback. Logica collaudata sul PC alla fase 1.5, cancello esplicito alla fase 4.4 con hardware ancora sul tavolo. Piano B: mic USB direzionale da 10 € |
| 1 W su 8 Ω non basta per la cucina | media, fase 4.2 | Misurare col fonometro **prima** di chiudere la meccanica |
| Backlight su GPIO18 che rompe l'I2S | media, fasi 4.5–4.7 | `gpio_LIGHT=12`. Sintomo indiretto: il display funziona e l'audio smette |
| `openwakeword` che non si installa | media, fase 4.4 | Sistema **arm64** e `onnxruntime` esplicito |
| Il calore ammorbidisce il guscio in PLA | media, estate | PETG + feritoie passanti |
| Il SoC va in throttling senza dissipatori | bassa | Il burn-in lo dice con certezza; si aggiungono dopo in 5 minuti |
| Foto ravvicinate sfocate | media, se ci si fida del preset di fabbrica | Il modulo esce tarato all'infinito: la taratura a pinza è un passo da 5 minuti, non opzionale |
| Risposte troppo lunghe che non si possono interrompere | media, dal primo giorno | Limite di 2 frasi nel prompt **e** tetto duro sull'audio sintetizzato |
| Leak di memoria | media, mese 2 | RSS nel burn-in + `MemoryMax=` nelle unit |
| Rete giù = BMO muto | bassa ma certa quando capita | Stato `errore-rete` con faccia dedicata; Piper `x_low` come voce di riserva |
| Consumo di quota Gemini | bassa | Contatore giornaliero con tetto, dal primo giorno |

---

## In tre righe

**Scrivere tutto il software sul PC di sviluppo con `bmo-core`, portarlo sul Pi che è già in mano e misurarlo lì; comprare i componenti per ultimi, in UE, in un colpo solo.**

Il passaggio al cloud non è un ripiego imposto dai 512 MB: è ciò che rende il progetto **più semplice** del riferimento tecnico esterno, non solo più economico. Sparisce l'inferenza locale, e con lei l'SSD, l'acceleratore, lo swap dei modelli, il minuto di attesa per una foto e i 250 € di hardware che esistevano solo per tenere i pesi in RAM. La premessa "solo voce" cancella un intero sottoprogetto — PCB in KiCad, microcontrollore, sette pulsanti — e in cambio chiede **una sola cosa in più**: che la wake word funzioni davvero, perché non c'è più nessun pulsante dietro cui ripararsi.

È per questo che nella fase hardware l'audio viene prima del display, e la wake word a 3 metri con la TV accesa è un criterio di uscita e non una nota a piè di pagina.

---

## Fonti

- [Gemini API — listino prezzi e free tier](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API — generazione vocale (TTS): modelli, voci, PCM 24 kHz, streaming da 3.1](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini API — combinare strumenti nativi e function calling (Preview, solo Gemini 3)](https://ai.google.dev/gemini-api/docs/tool-combination)
- [Gemini API — grounding con Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini API — limiti di frequenza](https://ai.google.dev/gemini-api/docs/rate-limits)
- [openWakeWord — 15–20 modelli in tempo reale su un core di Pi 3](https://github.com/dscripka/openWakeWord)
- [openWakeWord issue #322 — installazione su Raspberry Pi e ruote tflite-runtime](https://github.com/dscripka/openWakeWord/issues/322)
- [Welectron — Waveshare WM8960 Audio HAT, 18,90 €](https://www.welectron.com/Waveshare-15668-WM8960-Audio-HAT_1)
- [Waveshare Wiki — WM8960 Audio HAT](https://www.waveshare.com/wiki/WM8960_Audio_HAT)
- [Welectron — Waveshare 2.4" LCD Module ILI9341 240×320, 12,90 €](https://www.welectron.com/Waveshare-18366-24inch-LCD-Module_1)
- [Welectron — Groundmicro OV5647 5 MP, fuoco fisso regolabile a pinza, 5,90 €](https://www.welectron.com/Groundmicro-OV5647-5-MP-Kameramodul-fuer-Raspberry-Pi)
- [Pimoroni — GPIO Header extra-tall 2×20, venduto singolo](https://shop.pimoroni.com/en-us/products/gpio-header-for-raspberrypi-a-b-pi-2-tall-2x20-female-header)
- [raspberrypi/linux — overlay `wm8960-soundcard` in-tree](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/wm8960-soundcard-overlay.dts)
- [Raspberry Pi — Pi 3 Model A+ (512 MB, 1× USB-A, CSI, DSI, jack 3,5 mm)](https://www.raspberrypi.com/products/raspberry-pi-3-model-a-plus/)
- [Waveshare Wiki — 5inch DSI LCD, compatibile con Pi 3A+](https://www.waveshare.com/wiki/5inch_DSI_LCD)
- [juj/fbcp-ili9341 — benchmark dei controller SPI](https://github.com/juj/fbcp-ili9341)
- [luma.lcd — hardware e pin di default (backlight su GPIO18)](https://luma-lcd.readthedocs.io/en/latest/hardware.html)
- [Printables — BMO from Adventure Time (STL + PCB del progetto di riferimento)](https://www.printables.com/model/1582055-bmo-from-adventure-time)

Vedi anche [Riferimenti esterni](03-riferimenti-esterni.md) per il video di riferimento hardware/software.
