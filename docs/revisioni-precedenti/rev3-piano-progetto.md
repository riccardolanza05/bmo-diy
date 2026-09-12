# Piano di progetto rev. 2/3 (superato)

> **Stato: superato** dal [piano attuale, rev. 5.1](../02-piano-attuale.md) dove in conflitto. **Restano validi e sono qui l'unica fonte**: la strategia meccanica senza CAD (§3), i cinque criteri di validazione del modello Printables, la termica, i parametri di stampa, l'ordine di montaggio.

---

# BMO in cantiere — piano di progetto e roadmap

> Telaio parametrico: `bmo_chassis.scad` (OpenSCAD)
> Base: [distinta base rev. 2/3](rev3-hardware-bom.md)

**Tre correzioni al BOM rev. 2, in ordine di impatto:**

1. **La fotocamera non serve a nessuno dei quattro obiettivi dichiarati.** Conversazione, cucina, musica, faccia animata: nessuno la richiede. Sono 9 € di capacità futura, e il connettore CSI resta libero per aggiungerla dopo.
2. **`fbcp-ili9341` non serve affatto.** Con il blit su regioni cambiate si passa da 153,6 kB a 24,7 kB per fotogramma. Sparisce l'unica dipendenza fuori dall'albero del kernel, e con lei la ragione d'essere della variante HDMI da 92,40 €.
3. **Mancano ~8 € di minuteria**, di cui un condensatore da 30 centesimi che protegge esattamente il rischio che veniva messo al primo posto.

| | |
|---|---|
| Costo reale componenti | **86,40 €** (78,40 BOM + 8,00 minuteria) |
| Minimo per i 4 obiettivi | **77,40 €** (senza camera) |
| Costo Gemini/mese | **~0,9 $** (pipeline classica + TTS locale, 10 min/g) |
| Tempo a BMO funzionante | **5–6 settimane**, di cui 2–3 di sola attesa |

---

## 1 — Analisi critica del BOM

### Necessario vs sufficiente

*Necessario*: senza quel componente la funzione è impossibile. *Sufficiente*: l'insieme raggiunge la funzione al livello di qualità richiesto.

| Obiettivo | Necessari | Sufficiente? |
|---|---|---|
| **1 · Conversazione** | Pi 3 A+, Wi-Fi, INMP441, MAX98357A, speaker, alimentatore, microSD | **Sì**, con riserva: in V1 il dialogo è half-duplex (mic chiuso mentre BMO parla). È software, non hardware. |
| **2 · Cucina** | Come sopra **+ display** (il countdown e il passo si guardano) | **Sì con vincolo acustico.** 40 mm in 0,5 L fa ~78–84 dB a 1 m; una cappa ne fa 65. La sveglia va progettata a **2,5–3 kHz** con pattern crescente, non con un beep grave. |
| **3 · Musica** | MAX98357A, speaker | **Necessario sì, sufficiente no.** f₃ a 400–600 Hz: per voce/podcast/radio è perfetto, per musica è una radiolina. Uscite: camera di compressione chiusa (gratis, nel file OpenSCAD); Bluetooth A2DP verso cassa vera (gratis, il Pi 3 A+ ha BT 4.2); stereo con 2° MAX98357A + 2° speaker (+5 €). |
| **4 · Schermo animato** | Display 240×320, SPI0 | **Sì, a condizione** di abbandonare `fbcp-ili9341`. |
| **5 · (implicito) Reggere 24/7** | Alimentatore ✓, microSD ✓, **termica ✗**, **spegnimento pulito ✗**, watchdog | **No.** È il quinto obiettivo che nessuno scrive e che decide se il progetto arriva in fondo. |

### La correzione sul driver del display

`fbcp-ili9341` copia l'intero framebuffer HDMI su SPI, 153,6 kB per fotogramma, indipendentemente da quanti pixel cambino. È giusto per RetroPie, sbagliato per una faccia.

BMO ha due occhi e una bocca su sfondo piatto: fra due fotogrammi cambiano ~12 000 pixel su 76 800. Scrivendo solo quelli (2 finestre 64×44 + 1 da 120×56):

| | Schermo intero | Dirty rect |
|---|---|---|
| Pixel | 76 800 | 12 352 |
| Byte | 153,6 kB | **24,7 kB** |
| Bus (clock 50 MHz, ~44 utili) | 28,0 ms | **4,5 ms** |
| Massimo teorico | 36 fps | oltre 200 fps |
| Occupazione a 25 fps | — | **11% del bus, <8% di un core** |

Si pilota il pannello direttamente da `spidev`, che è in-tree e funziona su qualsiasi Pi, Pi 5 compreso.

### Le voci mancanti dal BOM

| Voce | Perché | € |
|---|---|---|
| **Condensatore 1000 µF / 10 V** | Serbatoio ai morsetti del MAX98357A. Un class-D su 4 Ω chiede corrente a impulsi: senza serbatoio i transienti fanno crollare il rail 5 V e il Pi va in undervoltage. Va montato **a 2 cm dall'ampli**, non sul Pi. | 0,30 |
| LED bianco 5 mm + resistenza 220 Ω | Solo se si prende la camera. | 0,60 |
| 2 × pulsante momentaneo 6×6 mm | Spegnimento pulito (`dtoverlay=gpio-shutdown`) + muta microfono. Senza pulsante l'unico modo di spegnere è staccare la spina, ed è così che si corrompono le SD. BMO ha già i fori. | 0,40 |
| Filo siliconico AWG24, 1 m rosso + 1 m nero | I Dupont sono AWG28: ok per SPI e I2S, non per alimentare 3 W di picco. | 1,50 |
| Guarnizione schiuma adesiva 2 mm | Sigilla il cestello dello speaker alla camera. Senza, corto acustico sotto i 500 Hz. | 0,50 |
| Viti M2.5×6 autofilettanti (×20) + termorestringente | Le torrette stampate sono per autofilettanti: niente inserti. | 2,50 |
| Cavo micro-USB angolato o passacavo | Altrimenti servono 25 mm in più solo per il connettore. | 2,00 |
| 2 × resistenza 10 kΩ | Pull-up esterni sui pulsanti. | 0,20 |
| | **Totale** | **8,00** |

**Non servono:** cavo HDMI per il primo avvio (Raspberry Pi Imager preconfigura Wi-Fi + SSH); ventola (da decidere con una misura, §6).

---

## 2 — Le due varianti: i 13 € non comprano prestazioni

| Voce | 78,40 € | 65,40 € | Δ | Effetto su prestazioni/fluidità |
|---|---|---|---|---|
| Display | ILI9341 3,2″ 240×320 | ST7789 2,4″ 240×320 | −4,00 | **Nessuno, semmai favorevole al 65.** Stessa risoluzione → stesso framebuffer, stessi byte, stessi asset. L'ST7789 regge un clock SPI più alto. Cambia solo la faccia fisica: 48,8×36,6 vs 64,8×48,6 mm, −43% di superficie. |
| Camera | OV5647 fuoco regolabile | OV5647 fisso | −2,50 | Nessuno. Rischio: molti moduli fissi escono tarati a ~30 cm. |
| Alimentatore | 2,5 A di marca | generico | −3,00 | **Questo sì, ed è l'unico.** Sag → undervoltage → throttling + Wi-Fi che perde pacchetti. Si manifesta come "ogni tanto ci mette due secondi in più". |
| microSD | 32 GB A1 marca | generica | −2,50 | 1500 IOPS random vs poche centinaia. Non tocca il regime, allunga l'avvio e accorcia la vita su un 24/7. |
| Cavetteria | completa | ridotta | −1,00 | Nessuno diretto; peggiora l'affidabilità meccanica. |

**Verdetto: 5,50 € dei 13 sono un taglio sull'affidabilità, 4 € sulla dimensione della faccia, 2,50 € sulla messa a fuoco. Zero euro comprano potenza di calcolo.** Stesso SoC, stessi 512 MB, stesso Wi-Fi, stesso bus, stessi quattro core.

**Regola d'acquisto per la variante 65 — critica:** l'ST7789 pilota due famiglie di pannelli, 240×240 (1,3″–1,54″, i più venduti) e 240×320 (2,0″–2,4″). Un 240×240 manda all'aria asset e proporzioni. Nel titolo dell'inserzione deve comparire **240×320**, non solo "ST7789".

---

## 3 — Modellazione 3D e esoscheletro

### Il modello base è quello giusto?

*Adventure Time BMO Figure (Interactive)* è 58 STL e oltre 60 parti con interni fedeli: vano batterie con contatti, molle, lettore di dischi, pulsanti su molla. È ottimizzato per **essere una figura fedele**; l'obiettivo qui è opposto — un guscio che ospiti 0,15 L di elettronica e si riapra. Usarne il guscio, ignorando gli interni. Ma verificare prima cinque cose:

| # | Criterio | Come, in 10 minuti | Soglia |
|---|---|---|---|
| 1 | È un guscio o una figura? | Aprire gli STL nello slicer: nervature, sedi per molle, pareti interne occupano già il volume. | Vano libero unico |
| 2 | Profondità interna netta | Tagliare il corpo a metà altezza nello slicer e misurare fra le pareti. | **≥ 39 mm** (78) / ≥ 36 mm (65) |
| 3 | Si riapre? | Due mezzi gusci con viti/incastri, o pensato per essere incollato? Un 24/7 va riaperto. | Viti o incastri, mai colla |
| 4 | La faccia è piana? | Guardarla di profilo. Bombata o testurizzata → finestra netta impossibile. | Piano ±0,3 mm |
| 5 | Quanti triangoli? | Sopra 300k TinkerCAD rifiuta l'import e lo slicer rallenta. | < 300 000 |

Se fallisce 1–3, esistono BMO nati **come case** per Raspberry Pi: meno belli come figure, infinitamente più semplici da adattare perché il vano c'è già.

> **Regola che fa risparmiare due giorni:** prima di stampare qualsiasi cosa che duri più di un'ora, stampa il **provino della sola interfaccia**. Ogni interfaccia meccanica del progetto — finestra schermo, torrette Pi, sede speaker — ha un provino da dieci minuti che la valida.

### Strategia: tre pezzi, zero CAD

| Pezzo | Cosa fa | Come lo produci | Competenza |
|---|---|---|---|
| Guscio BMO | L'estetica. Invariato salvo finestra e aperture. | STL scaricato + *negative volume* nello slicer | Nessuna, 20 min |
| Telaio interno | Porta Pi, display, speaker, moduli audio. Si sfila dal retro. | `bmo_chassis.scad` (OpenSCAD) | Nessuna, cambi numeri e premi F6 |
| Mascherina | Copre la cornice del PCB, definisce la finestra della faccia. | Stesso file | Nessuna |

#### a) Finestra dello schermo, senza CAD

PrusaSlicer, Bambu Studio e OrcaSlicer sottraggono un solido dal modello al momento del taglio. Per un foro rettangolare millimetrico è più affidabile di TinkerCAD e non degrada la mesh.

1. Caricare il guscio frontale → click destro → **Add negative volume → Box**.
2. Dimensioni a mano: **63,6 × 47,4 × 10 mm** (variante 78 — area attiva meno 0,6 mm per lato, nasconde la fila di pixel di bordo). Variante 65: **47,6 × 35,4 × 10**.
3. Posizionare **numericamente**, non a mano.
4. Anteprima, correggere, ripetere. L'STL non viene toccato: reversibile anche fra sei mesi.

Serve anche un **gradino d'appoggio**: un secondo negative volume più largo e meno profondo (~90×57×3,4 mm per la 78, ~70×46×3,2 per la 65) dove il modulo si appoggia da dentro. Due box e la meccanica del display è finita.

#### b) Telaio interno — `bmo_chassis.scad`

OpenSCAD è gratuito e non richiede di disegnare: in cima al file c'è una sezione PARAMETRI con le misure di ogni componente. Si misurano i pezzi col calibro, si correggono i numeri, F6, si esporta STL.

Il telaio porta: 4 torrette Pi (interasse 58×49, viti autofilettanti M2.5, nessun inserto), 4 torrette display, la **camera di compressione dello speaker** con sfiato accordato, sedi a incastro per MAX98357A e INMP441, reticolo di alleggerimento che è anche canale di convezione, passaggio cavi con raggio minimo 6 mm.

La camera dello speaker è l'unico pezzo che migliora il suono a costo zero: un driver da 40 mm su parete aperta cortocircuita acusticamente fronte e retro e sotto i 500 Hz non produce nulla. Chiuso in ~12 cm³ con sfiato calibrato diventa un piccolo altoparlante.

#### c) Griglie, microfono, camera, LED

- **Speaker**: fori esagonali Ø 3,2 mm, muri 1,0 mm → ~55% di superficie aperta. Fori da 1 mm sembrano più fini e suonano molto peggio (fischiano e attenuano gli acuti).
- **Microfono**: **un foro solo, Ø 4 mm**, allineato alla porta del MEMS a meno di 1 mm. Al contrario dello speaker, più fori peggiorano: risonanze di cavità e S/N più basso. Il mic va montato *contro* la parete con un anello di schiuma, non sospeso dietro una griglia.
- **Distanza mic/speaker**: il più lontani possibile e mai sulla stessa parete rigida — la vibrazione si trasmette per via strutturale e nessun algoritmo la toglie. Speaker in basso a sinistra, mic in alto a destra, disaccoppiato con due rondelle di schiuma.
- **Camera**: foro Ø 8 mm con tasca 8×8×1 che tiene la lente a filo. **Nessuna finestrella trasparente**: davanti a una lente da 3 € peggiora l'immagine più di quanto la protegga.
- **LED**: foro Ø 5 mm a 15 mm dalla camera. Punta **avanti**, non verso la lente: il flare cancella il soggetto.
- **Pulsanti**: i fori del D-pad ci sono già. Due tastini 6×6 dietro due di quei fori con un cappuccio stampato che sporge 1,5 mm.

#### Parametri di stampa

- **PETG** per guscio e telaio. Non è preferenza: la Tg del PLA è ~60 °C e in una scatola sigillata con 4 W dentro, d'estate, ci si arriva. PETG sta a ~80 °C.
- Layer 0,2 mm; 0,12 solo per la mascherina.
- 3 perimetri sul guscio, 4 sul telaio. Riempimento 15% gyroid / 25%.
- **Ordine**: mascherina (10 min) → provino finestra (10) → provino torrette (15) → telaio (~3 h) → guscio (10–14 h). Il guscio per ultimo, quando ogni interfaccia è verificata.

**Δ variante:** 78 → guscio 110×125×45, 180–220 g, 10–14 h. 65 → guscio 95×110×42, 130–160 g, 7–10 h; **attenzione**: con 90 mm interni, Pi (56) + speaker (40) sommano 96 mm contro ~105 disponibili in altezza. Entra, ma i cavi vanno pianificati prima.

---

## 4 — Il cervello: Live API o pipeline classica

**Scelta: pipeline classica come spina dorsale, Live API come modalità opzionale.**

### Le due architetture

- **Live API** — WebSocket persistente verso `gemini-3.1-flash-live-preview`, PCM 16 bit 16 kHz in / 24 kHz out. Function calling e barge-in nativi.
- **Pipeline classica** — audio catturato dopo la wake word, mandato **come allegato audio** a `gemini-3.8-flash` con una normale `generateContent`. **Non serve un motore STT separato**: Flash è multimodale, trascrizione e ragionamento sono la stessa chiamata. La voce si sintetizza con Gemini TTS remoto o **Piper locale**.

### I numeri

| | Latenza al primo suono | Costo/mese a 10 min/g |
|---|---|---|
| Live API | **≈ 0,85 s** | 4,20 $ |
| Classica + TTS Gemini | ≈ 2,0 s | 5,40 $ |
| Classica + **Piper locale** | ≈ 2,0 s | **0,90 $** |

La sintesi vocale domina il conto in entrambe le architetture remote: **il TTS locale, non la scelta di pipeline, è la leva sul costo.**

### Perché la classica, in ordine di peso

1. **Con il TTS locale si conosce l'intera forma d'onda prima di riprodurla** — e questo riguarda l'obiettivo 4. Piper restituisce un WAV completo: si calcola l'inviluppo RMS a 25 Hz in due millisecondi e lo si manda al processo della faccia insieme all'ordine di parlare. La bocca si muove *esattamente* sull'audio, perché si conosce il futuro. **La sincronizzazione labiale gratis vale più di un secondo di latenza.**
2. **Costa 4,7× meno**, e sul free tier di `gemini-3.8-flash` tende a zero.
3. **È ispezionabile.** Ogni turno lascia su disco un WAV, un JSON di richiesta, uno di risposta con le chiamate a funzione, un WAV sintetizzato.
4. **Non richiede AEC per funzionare.** Half-duplex: mentre BMO parla il mic è chiuso. È una rinuncia reale, ma ritirabile dopo.
5. **Il free tier vede i dati inviati.** Si sviluppa sul free tier, si passa al piano a pagamento (~1 $/mese) quando BMO smette di essere un prototipo.

### Dove la Live API entra comunque

L'obiettivo 1 chiede conversazione fluida ed empatica, ed è precisamente ciò in cui la Live API è migliore. Entra come **modalità**: sessione aperta da una frase («parliamo un po'») o dal tasto verde, chiusa dopo 30 s di silenzio o al tetto di budget. Condizione tecnica per non pagarla due volte: progettare da subito un'interfaccia `Brain` con `ascolta()`, `rispondi()`, `strumenti()` e due implementazioni dietro.

### Wake word

**openWakeWord** con modello «hey BMO» addestrato con dati sintetici nel notebook Colab del progetto. Gira in ONNX, l'inferenza rilascia il GIL, e un core di Pi 3 ne fa girare 15–20: il consumo reale sarà sotto il 10% di un core. Apache 2.0 sul codice, CC-BY-NC-SA sui modelli preaddestrati.

Porcupine è più accurato ma richiede una AccessKey che si convalida online: su un dispositivo che deve svegliarsi anche col router giù, è una dipendenza che si preferisce evitare. In sviluppo si usa `hey_jarvis` preaddestrato: l'addestramento è rifinitura, non prerequisito.

### Le ricette sono una modalità, non una funzione

Se BMO legge la ricetta tutta d'un fiato, le mani restano sporche e ci si perde al terzo ingrediente. Il modello restituisce una ricetta **strutturata** via function calling; `bmo-core` la tiene in stato; lo schermo entra in `RECIPE` con la faccia rimpicciolita in alto e il passo corrente sotto; «avanti», «ripeti», «quanto manca» navigano senza rifare chiamate. Quando un passo contiene una durata, BMO propone il timer da solo. A 320×240 su 64,8 mm ci stanno tre righe da ~20 caratteri leggibili a mezzo metro.

---

## 5 — Architettura software: tre processi, non tre thread

```
        INMP441 ──dsnoop──►┌─────────────────────────────────┐
                           │ bmo-core   processo 1 · asyncio │──HTTPS──► Gemini 3.8 Flash
                           │  thread: wake word (openWakeWord)│           (audio in, tool out)
                           │  task:   dialogo (VAD→cattura)   │
                           │  task:   strumenti (timer/musica)│
                           │  task:   sintesi → piper + RMS   │
                           └──────────────┬──────────────────┘
                              /run/bmo.sock (JSON per riga)
                    ┌─────────────────────┴───────────────┐
        ┌───────────▼──────────┐              ┌───────────▼──────────┐
        │ bmo-face  proc 2     │              │ mpv       proc 3     │
        │ nice −5 · 25 fps     │              │ nice +5 · decode in C │
        │ blit RGB565 dirty    │              │ --input-ipc-server    │
        │ possiede spidev0.0   │              └───────────┬──────────┘
        └───────────┬──────────┘                          │
                 SPI0 → display              ALSA dmix ──► MAX98357A ──► speaker
```

### Perché processi, se il GIL quasi non c'entra

La risposta abituale — "per aggirare il GIL" — qui è quasi sbagliata: openWakeWord gira in ONNX Runtime, le scritture SPI passano da una `ioctl`, Piper è un binario esterno, le chiamate a Gemini sono I/O di rete. *Tutte queste cose rilasciano già il GIL.* La separazione serve a due cose più importanti:

- **Isolamento dei guasti.** Se `bmo-core` va in eccezione, systemd lo riavvia in due secondi e la faccia non se ne accorge: BMO resta lì a sbattere le palpebre. Stesso processo → ogni bug del dialogo produce uno schermo nero, il sintomo più allarmante possibile per un oggetto che deve sembrare vivo.
- **Priorità di scheduling indipendenti.** La faccia a `nice −5` perché il jitter si vede; `mpv` a `nice +5` perché ha mezzo secondo di buffer.

### Bus di messaggi

Socket Unix `/run/bmo.sock`, un oggetto JSON per riga. Nessuna dipendenza, e si ispeziona con `socat` da SSH mentre BMO funziona.

```
# bmo-core → bmo-face
{"cmd":"state",      "value":"listening"}
{"cmd":"speak",      "envelope":[0.10,0.42,0.71,...], "fps":25}
{"cmd":"expression", "value":"felice", "ttl":3.0}
{"cmd":"timer",      "remaining":312, "label":"pasta"}
{"cmd":"recipe",     "step":3, "of":8, "text":"Soffriggi la cipolla 5 minuti"}
# bmo-face → bmo-core
{"ev":"button", "id":"verde"}
```

### Strumenti per Gemini

Pochi, con nomi in italiano (riduce gli errori quando l'utente parla italiano), effetti collaterali sempre reversibili.

```python
imposta_timer(durata_secondi: int, etichetta: str)
annulla_timer(etichetta: str | None)
elenca_timer()
riproduci_musica(query: str, sorgente: "locale" | "radio")
controllo_riproduzione(azione: "pausa"|"riprendi"|"stop"|"volume", valore: int|None)
avvia_ricetta(titolo: str, ingredienti: list[str], passi: list[Passo])
imposta_espressione(stato: "felice"|"pensieroso"|"sorpreso"|"triste"|"assonnato")
scatta_foto()   # solo se monti la camera
```

`imposta_espressione` costa meno e rende di più: si lascia al modello il controllo della faccia, e una risposta triste arriva con gli occhi tristi senza una riga di logica emotiva. Da mettere nel primo prototipo, non nell'ultimo.

### Timer che sopravvivono al riavvio

È la funzione col costo di errore più alto: se BMO si riavvia mentre la pasta bolle e il timer sparisce in silenzio, la fiducia nel dispositivo si perde in un colpo.

- In `timers.json` si salva la **scadenza assoluta**, mai i secondi rimanenti.
- Riscrittura a ogni modifica con temporaneo + `rename` atomica. Su microSD, un file mezzo scritto è la norma.
- All'avvio, un timer scaduto durante il downtime **suona lo stesso**, con messaggio diverso: «il timer della pasta è scaduto due minuti fa». Il silenzio è la risposta sbagliata.

### Audio: un codec, due flussi

Con `googlevoicehat-soundcard` riproduzione e cattura sono due PCM distinti sullo stesso codec: bastano i plugin di serie.

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

Il codec gira a 48 kHz; il ricampionamento a 16 kHz per wake word e Gemini è in software e trascurabile. Il *ducking* è un comando IPC a `mpv`.

**Barge-in:** in V1 il mic si chiude mentre BMO parla. È la ragione per cui il BOM insisteva su BCLK e LRCLK condivisi: mic e ampli sono campione-sincroni, quindi il giorno del barge-in basta abilitare `module-echo-cancel` di PipeWire senza deriva di clock.

### Bilancio della memoria

Prima cosa: `gpu_mem=16` in `config.txt` — senza HDMI, restituisce quasi 50 MB.

| Voce | RAM | Nota |
|---|---|---|
| Raspberry Pi OS Lite a riposo | ~45 MB | senza desktop, avahi, bluetooth |
| `bmo-face` | ~35 MB | Python + framebuffer + asset mappati (~2 MB) |
| `bmo-core` | ~110 MB | Python + ONNX Runtime + modelli wake word — la voce più grossa |
| `piper` (a raffica) | ~40 MB | voce `x_low`/`low`; le `medium` pesano 60–150 MB, su 512 non sono desiderabili |
| `mpv` | ~30 MB | solo quando suona |
| **Picco** | **~260 MB** | restano ~230 MB di margine |

**32 o 64 bit:** su 512 MB il 32 bit (armhf) consuma meno. Ma **verificare prima che ONNX Runtime e `tflite-runtime` abbiano ruote armv7l aggiornate**; se hanno solo aarch64, meglio 64 bit Lite e recuperare con `gpu_mem=16`, swap disabilitato e journald volatile. Decisione da prendere **prima** di scrivere la scheda. *(Nota: il piano attuale ha chiuso questa decisione su arm64 — vedi [piano attuale, §2.6](../02-piano-attuale.md).)*

### Pipeline asset della faccia — gira su computer esterno

Le GIF non si decodificano sul Pi. Si convertono una volta su un altro computer in un `.bin` di fotogrammi RGB565 grezzi + un manifesto JSON con le regioni; il Pi lo mappa in memoria e fa `write()` sul bus. Decodifica a runtime: zero. Memoria: ~2 MB per una faccia completa.

```python
# build_face.py — sul computer esterno, una volta
from PIL import Image
def rgb565(im):
    px = im.convert("RGB").tobytes()
    return b"".join(
        ((px[i]&0xF8)<<8 | (px[i+1]&0xFC)<<3 | px[i+2]>>3).to_bytes(2,"little")
        for i in range(0,len(px),3))
# → faces.bin + faces.json  {stato: {regione:[x,y,w,h], frames:N, offset:B}}
```

---

## 6 — Assemblaggio hardware

### Mappa dei pin

*(identica alla rev. 3 — vedi [rev. 3, hardware-bom](rev3-hardware-bom.md); le correzioni introdotte dal HAT WM8960 sono nel [BOM rev. 4](rev4-bom-senza-dazi.md))*

### Alimentazione

Il rail 5 V arriva dal micro-USB con in mezzo un polyfuse. L'ampli lo preleva dal pin 2, a valle di quel fusibile e di tutta la pista: quando un colpo di grancassa chiede un ampere per due millisecondi, la tensione scende e il SoC registra undervoltage.

1. **Condensatore 1000 µF ai morsetti dell'ampli**, reofori corti — non sul Pi, non a metà cavo.
2. **Alimentazione ampli in AWG24 siliconico**, dedicata, non un Dupont in catena. Due fili da 10 cm intrecciati.
3. **Massa a stella.** Tutte le masse a due pin GND vicini, mai a catena. Una massa in serie fra ampli e mic mette il ritorno dello speaker dentro il riferimento del microfono: è il ronzio che poi si insegue per giorni.
4. **Alimentazione display**: guardare il modulo. Regolatore a bordo (SOT-23 vicino a VCC) → vuole 5 V; senza → vuole 3,3 V e 5 V lo distrugge. Nel dubbio 3,3 V: al peggio non si accende.

### Termica — la voce che il BOM non affronta

Scatola sigillata da ~0,5 L con dentro 1,5–4 W; a convezione naturale la resistenza termica è dell'ordine di 8–15 °C/W. A 1,5 W di regime: +12÷22 °C sull'ambiente. Con 28 °C in casa d'estate si arriva a 40–50 °C di aria interna, e il SoC con dissipatore sta 10–15 °C sopra. Sotto la soglia di throttling (80 °C), ma **sopra la Tg del PLA**.

Tre contromisure a costo zero:
- **Feritoie passanti**, ≥300 mm² in basso e ≥300 in alto su pareti opposte, per l'effetto camino. Nel modello di BMO ci sono già griglie stilizzate: renderle passanti.
- **PETG invece di PLA.**
- **Non tenere aperto lo stream.** Con wake word locale e sessioni brevi il regime è ~1,5 W, non 4. È l'architettura software che tiene fresco l'hardware.

**Criterio di accettazione:** `vcgencmd measure_temp` ogni minuto per 24 h a BMO chiuso e in uso normale. **< 65 °C: nessuna ventola.** 65–75: allargare le feritoie e rimisurare. > 75: ventola 25 mm a tensione ridotta in aspirazione dall'alto — ma è una sorgente di rumore a 8 cm dal microfono, e quel rumore lo si paga in accuratezza di trascrizione per sempre.

### Ordine di montaggio

1. Cablaggio completo **fuori dal guscio**, su un tavolo, tutto acceso e funzionante. Nessun cavo si salda dentro BMO.
2. Elettronica sul telaio: prima lo speaker con la guarnizione (non si raggiunge più dopo), poi i moduli audio, poi il Pi, per ultimo il display.
3. Prova a telaio nudo, fuori dal guscio.
4. Mascherina, telaio nel guscio frontale, cavi verso il lato USB.
5. Guscio posteriore, viti. **USB-A e microSD affacciate su un fianco**: la USB vuole 45 mm liberi in linea e nel guscio ce ne sono 45 in tutto.

---

## 7 — Roadmap (superata dalla rev. 5.1)

Questa roadmap è storica; la roadmap in vigore è nel [piano attuale, §3](../02-piano-attuale.md).

**Regola che governa la pianificazione: nulla del lavoro software dipende dall'arrivo dei componenti.**

```
        S0        S1        S2        S3        S4        S5
ORDINI  [ordine]
        [Pi in transito──]
        [moduli AliExpress in transito─────────]
SOFTW.  [F4 · cervello sul computer esterno──────────]
              [asset faccia · tool · wake word────]
MECC.   [F6a provini]              [F6b telaio e guscio────]
HARDW.        [F1 bring-up]  ▲     [F2 audio][F3 display] ▲
                          arriva Pi        arrivano moduli
INTEGR.                              [F7 integrazione + burn-in 72 h]
```

### Fase 0 — Decidere e ordinare *(giorno 1)*

- **0.1 Congelare la configurazione.** La domanda che decide è una sola: **si vuole la visione ora o fra sei mesi?**
- **0.2 Due ordini, non cinque.** Ordine A (europeo, 3–5 gg): Pi 3 A+, alimentatore, microSD. Ordine B (AliExpress, 2–3 settimane, stesso venditore): tutto il resto. *Criterio di uscita*: due numeri di tracking, e il condensatore da 1000 µF nel carrello.
- **0.3 Chiave API e primo contatto con Gemini.** Venti righe: tre secondi di audio → `gemini-3.8-flash` con una dichiarazione di funzione `imposta_timer`. *Criterio di uscita*: «Metti un timer di dieci minuti» produce `imposta_timer(durata_secondi=600)`.

### Fase 1 — Bring-up del Pi *(una sera)*

- **1.1 Sistema headless.** Raspberry Pi Imager, OS Lite, hostname `bmo`, chiave SSH, Wi-Fi. Mai collegato un monitor.
- **1.2 Irrobustimento 24/7.** `systemctl disable dphys-swapfile`; `Storage=volatile` in `journald.conf`; `dtparam=watchdog=on` + `RuntimeWatchdogSec=15`; `gpu_mem=16`; `dtoverlay=gpio-shutdown`. *Uscita*: `free -m` ~45 MB, `vcgencmd get_throttled` = `0x0`.

### Fase 2 — Audio *(una sera)*

> L'audio va prima del display per gestione del rischio: è l'unico sottosistema che può risultare irrecuperabile con l'hardware comprato.

- **2.1 Uscita audio.** *Uscita*: rumore rosa all'80% per due minuti con `get_throttled = 0x0`.
- **2.2 Ingresso audio.** INMP441 VDD al pin 1 (3,3 V, **non** 5 V). Picco a voce normale a 1,5 m fra −18 e −6 dBFS. *Uscita*: trascrivi `test.wav` con Gemini, testo corretto.
- **2.3 Convivenza dei flussi.** Il `~/.asoundrc` della §5; `mpv` che suona mentre `aplay` spara un beep sopra, e due `arecord` contemporanei.

### Fase 3 — Display e faccia *(due sere)*

- **3.1 Primo pixel.** Un rettangolo rosso valida cablaggio, tensione e init insieme. Ricordare `gpio_LIGHT=12`.
- **3.2 Misurare il bus prima di progettarci sopra.** *Uscita*: ≥30 fps a schermo pieno e >150 blit/s sulla finestra della bocca.
- **3.3 Pipeline asset e processo `bmo-face`.** 25 fps sotto il 10% di un core.

### Fase 4 — Il cervello *(settimane 0–3)*

- **4.1 Il giro completo, senza hardware.** *Uscita*: venti frasi di prova, sotto 18/20 il problema è il prompt di sistema.
- **4.2 Strumenti e stato.** Test brutale: far partire un timer, uccidere il processo, riavviarlo, verificare che suoni all'ora giusta.
- **4.3 Wake word.** «Hey BMO» a 3 m, meno di un falso positivo al giorno. Soglia tarata nella stanza vera, con la TV accesa.
- **4.4 Portare tutto sul Pi.** *Uscita*: picco RSS totale < 300 MB, zero OOM in 24 h.

### Fase 5 — Camera e LED *(saltabile)*

`libcamera-still` con il LED acceso 200 ms prima dello scatto. Taratura una tantum a 1,5 m con un giornale, poi una goccia di smalto sulla ghiera.

### Fase 6 — Meccanica *(provini alla S0, resto alle 4–5)*

- **6.1 Provini prima di tutto** — anche prima dei componenti.
- **6.2 Telaio parametrico** — calibro alla mano, correzione dei parametri, F6, esportazione. Stampa prima il provino delle torrette: quindici minuti che evitano tre ore buttate.
- **6.3 Guscio**: finestra, tasca, griglia speaker, foro mic da 4 mm, feritoie.
- **6.4 Assemblaggio** — l'ordine della §6.

### Fase 7 — Integrazione *(settimane 5–6)*

- **7.1 Avvio automatico e resilienza.** La faccia deve accendersi **prima** che la rete sia pronta, con uno stato "assonnato".
- **7.2 Burn-in di 72 ore.** *Criteri, tutti e cinque*: temp max < 65 °C · `get_throttled = 0x0` per 72 h · zero riavvii dei servizi · zero disconnessioni Wi-Fi · RSS stabile entro il 5%.
- **7.3 Rifinitura del carattere.** Personalità nel prompt, `imposta_espressione`, un suono di avvio, il battito di palpebre a intervalli **irregolari**.

### Fase 8 — V2

**8.1 Modalità Live** · **8.2 Barge-in** (PipeWire + `module-echo-cancel`, possibile perché mic e ampli condividono BCLK e LRCLK) · **8.3 Domotica** via Home Assistant.

---

## 8 — Rischi, in ordine di probabilità

| Rischio | Quando | Contromisura |
|---|---|---|
| **Si compra il pannello sbagliato** | alta, alla consegna | ILI9341 o ST7789 **e** 240×320 nel titolo |
| **Il modello 3D non ha volume interno utile** | alta, settimana 0 | I cinque criteri della §3, nello slicer, in dieci minuti, prima di stampare |
| Undervoltage sotto i picchi audio | media, fase 2 | Condensatore 1000 µF ai morsetti, AWG24, massa a stella |
| Backlight su GPIO18 che rompe l'I2S | media, fase 3 | È il default di `luma.lcd`, quindi ci si casca facilmente. `gpio_LIGHT=12`. Sintomo indiretto: il display funziona e l'audio smette |
| Il calore ammorbidisce il guscio in PLA | media, estate | PETG + feritoie passanti |
| L'overlay I2S non riconosce la coppia | media, fase 2 | Microfono USB da 8 € nella porta USB-A. Motivo per cui la fase audio va per prima |
| Leak di memoria che matura in settimane | media, mese 2 | RSS monitorato nel burn-in + `MemoryMax=` nelle unit |
| Consumo di quota Gemini | bassa | Contatore giornaliero con un tetto |
| Il microfono sente lo speaker | bassa in V1 | Non esiste in V1 (half-duplex) |

---

## In tre righe

**Ordinare la configurazione senza camera, cominciare il software subito, e non stampare niente che duri più di un'ora prima di aver stampato il provino che lo valida.**

Il progetto non è rischioso tecnicamente: ogni pezzo è documentato e collaudato da altri. È rischioso nella **sequenza**. La roadmap è ordinata per una sola regola: **ogni fase mette alla prova l'ipotesi che, se fosse sbagliata, invaliderebbe più lavoro a valle.** Per questo l'audio viene prima del display, i provini prima delle stampe, e il giro completo di Gemini nel primo pomeriggio, quando ancora non si è comprato niente.

---

## Fonti

- [Gemini API — listino prezzi](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Live API — audio, WebSocket, tool use, barge-in](https://ai.google.dev/gemini-api/docs/live)
- [openWakeWord](https://github.com/dscripka/openWakeWord)
- [juj/fbcp-ili9341 — benchmark dei controller SPI](https://github.com/juj/fbcp-ili9341)
- [luma.lcd — hardware e pin di default](https://luma-lcd.readthedocs.io/en/latest/hardware.html)
- [Adafruit — microfono MEMS I2S e overlay googlevoicehat](https://learn.adafruit.com/adafruit-i2s-mems-microphone-breakout/raspberry-pi-wiring-test)
- [Printables — BMO Figure (Interactive)](https://www.printables.com/model/1139445-adventure-time-bmo-figure-interactive)
- [Printables — BMO come case per Raspberry Pi](https://www.printables.com/model/468112-raspberry-pi-4-case-bmo-adventure-time)
- [Piper TTS su Raspberry Pi](https://pidiylab.com/text-to-speech-raspberry-pi-piper/)
- [BerryBase — Raspberry Pi 3 Model A+](https://www.berrybase.de/en/raspberry-pi-3-model-a)
