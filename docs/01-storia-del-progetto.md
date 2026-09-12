# Storia del progetto

> **Natura di questo documento.** Non è un transcript delle conversazioni originali. Questo è l'arco delle discussioni ricostruito a posteriori dai documenti di progetto — la sostanza c'è, le parole esatte no.

## L'arco, in ordine

### 1 · Il brief iniziale

Il progetto parte da un brief semplice: costruire un piccolo assistente vocale domestico con le sembianze di BMO, scocca stampata in 3D. Requisiti posati subito: Wi-Fi, ascolto audio, riproduzione vocale, display per espressioni facciali animate, microfono, altoparlante con ampli, mini fotocamera per computer vision. Query e immagini via API a un LLM — probabilmente Gemini, per i limiti di token generosi. Il dispositivo resta collegato alla corrente 24/7: niente batterie.

Priorità dichiarata: **"cheap ma affidabile"**. Un'architettura complicata da programmare è accettabile, perché la parte di programmazione la fa un assistente AI.

Richiesta concreta iniziale: una selezione hardware con prezzi, link agli store e stima degli ingombri interni del guscio.

### 2 · I quattro obiettivi funzionali

La discussione si stringe su quattro obiettivi: chatbot conversazionale/culturale, aiutante da cucina (ricette + timer), riproduzione audio/musica, display animato non touch (faccia statica in idle, animata mentre parla). La camera **non serve a nessuno dei quattro** — resta a distinta esplicitamente come capacità futura per modelli vision.

### 3 · Rev. 1 → rev. 2 → rev. 3 della distinta

Da 132,10 € (Camera Module 3, display HDMI) a 78,40 € (OV5647, `fbcp-ili9341`) a 86,40 €. La rev. 3 ([hardware-bom](revisioni-precedenti/rev3-hardware-bom.md)) fa tre correzioni:

- la camera rientra a distinta, per la visione futura;
- **`fbcp-ili9341` viene eliminato**: copia l'intero framebuffer HDMI su SPI, 153,6 kB per fotogramma indipendentemente da quanti pixel cambino. Una faccia BMO cambia ~12.000 pixel su 76.800 → 24,7 kB con il blit sulle sole regioni cambiate. Sparisce l'unica dipendenza fuori dall'albero del kernel, e con lei la variante HDMI da 92,40 €;
- vengono censite ~8 € di minuteria mancante, fra cui il condensatore da 1000 µF che protegge il rischio numero uno del progetto (undervoltage sotto i picchi audio).

Emergono i vincoli d'acquisto: display **ILI9341 o ST7789, 240×320, no touch** (un 240×240 manda all'aria asset e proporzioni), camera a fuoco regolabile, **nessun risparmio su alimentatore e microSD**.

### 4 · Il piano di progetto e la meccanica senza CAD

Discussione sulla strategia meccanica, senza esperienza di CAD né intenzione di acquisirne. Ne esce una strategia a tre pezzi con zero modellazione — guscio scaricato da Printables con i fori fatti come *negative volume* nello slicer, telaio interno generato da `bmo_chassis.scad` cambiando numeri in OpenSCAD, mascherina dallo stesso file. Dettagli completi in [Piano di progetto rev. 2/3](revisioni-precedenti/rev3-piano-progetto.md).

Cinque criteri per validare il modello Printables *prima* di stampare (è un guscio o una figura? profondità interna netta? si riapre? faccia piana? meno di 300k triangoli?), e la regola che governa tutta la fase meccanica: **prima di stampare qualsiasi cosa che duri più di un'ora, stampa il provino della sola interfaccia**.

Si decide anche l'architettura del cervello: **pipeline classica** (audio → `generateContent` multimodale → function calling → TTS) invece della Live API, perché con un TTS non-streaming si conosce l'intera forma d'onda prima di riprodurla e la sincronizzazione labiale viene gratis. La Live API resta come *modalità* opzionale dietro la stessa interfaccia `Brain`.

### 5 · Gli acquisti, e il muro dei dazi

Vengono comprati **Raspberry Pi 3 Model A+ e alimentatore** da rivenditori ufficiali. Per il resto si punta su AliExpress, con due vincoli: tetto ~57 € spedizione inclusa, e solo venditori con almeno 100 vendite.

L'ordine si rivela molto più caro del previsto: **~60 € di dazi doganali** sul carrello dei moduli. La causa è il regime UE entrato in vigore il **1º luglio 2026** — abolita l'esenzione sotto i 150 €, sostituita da un dazio fisso di **3 € per riga doganale** più IVA al 22%. Il dazio non è proporzionale al valore ma al **numero di articoli diversi**: un BOM fatto di minuteria da 30 centesimi (15 categorie merceologiche su 44,50 € di merce) è il caso peggiore possibile.

### 6 · Rev. 4 — uscire dai dazi

Quattro opzioni valutate (dettagli completi in [BOM rev. 4 — senza dazi](revisioni-precedenti/rev4-bom-senza-dazi.md)):

- **A (raccomandata)**: tutto UE, audio su **Waveshare WM8960 Audio HAT** — ~76 €, zero dazi, 3–5 giorni. Il HAT integra codec, due MEMS e ampli: spariscono MAX98357A, INMP441, condensatore, filo siliconico, massa a stella, 12 Dupont, e con loro due rischi interi della lista.
- **B**: Raspberry Pi Codec Zero HAT ufficiale — supporto eterno, ma **un solo microfono** e audio mono.
- **C**: split-brain con ESP32-S3-BOX-3 — è più economico dell'ordine AliExpress con i dazi, ma rende inutile il Pi appena comprato e butta via tutto il piano software. Nel riferimento tecnico esterno lo split-brain ha senso perché un telefono Android fa da acceleratore per LLM/Whisper/Piper in locale; qui BMO usa Gemini in cloud, quindi quel motivo non si applica.
- **D**: restare su AliExpress comprimendo le righe doganali da 15 a 3–4. Sei euro di risparmio teorico contro tre settimane di attesa e cloni WM8960 senza certezza sull'overlay in-tree.

Scartato il **ReSpeaker 2-Mics Pi HAT v2.0** nonostante sia il più economico: richiede `seeed-voicecard`, fuori dall'albero del kernel, con rotture documentate a ogni aggiornamento. *"2,50 € di risparmio non valgono un `apt upgrade` che ammutolisce BMO."*

### 7 · Le note dai riferimenti esterni

Vengono raccolte due fonti di riferimento tecnico (vedi [Riferimenti esterni](03-riferimenti-esterni.md)):

- **PolyMO** — ESP32-S3 tutto-in-uno + telefono Android come nodo di calcolo.
- **Un Pi 5 + Ollama** — un BMO con inferenza interamente locale su Pi 5 da 16 GB. Diventa il **riferimento principale** per hardware e architettura software.

### 8 · Rev. 5 — cloud-first, solo voce

Vengono poste tre premesse nuove che riscrivono il progetto: Pi 3 A+ e alimentatore già comprati; **niente modelli in locale** (i 512 MB lo escludono); **interazione unicamente vocale**, nessun pulsante.

Il piano rev. 5 filtra il riferimento voce per voce. Del BOM del riferimento sopravvive poco — cadono Pi 5 16 GB, SSD NVMe, HAT M.2, acceleratore AI, UPS + batteria (~250 €), più un microcontrollore Feather 32u4 con PCB custom KiCad e sette switch (~40 € e un intero sottoprogetto). Dell'**architettura software** invece sopravvive quasi tutto: macchina a stati WAIT/LISTEN/THINK/SPEAK, faccia che cambia a ogni transizione, **clip vocali pre-generate per coprire l'attesa** (l'idea migliore del riferimento), openWakeWord custom, loop agentico con tool.

Si copiano tre idee meccaniche dal riferimento: faceplate a magneti 5×2 mm, sportello posteriore modulare, arti a innesto.

### 9 · Rev. 5.1 — il giro di taglio del BOM

Cinque voci vengono messe in discussione, una per una. Ne esce un BOM da **~68 €** (−23 €), con la motivazione scritta accanto a ciascun taglio:

| Voce | Esito | Perché |
|---|---|---|
| LED + resistenza per la camera | **tagliata** | Cucina sempre ben illuminata, scatti sempre a ~30 cm |
| Camera a fuoco motorizzato (12 €) | **declassata** a OV5647 regolabile a pinza (5,90 €) | La taratura una tantum è identica; il meccanismo micrometrico serve a chi cambia fuoco spesso |
| Dissipatori adesivi | **rimandati**, non eliminati | In una scatola chiusa l'aria interna sta 12–22 °C sopra la stanza, non 25–26 °C — ma 37–48 °C restano sotto throttling e sotto la Tg del PETG. Lo decide il burn-in di 72 h, non una stima; 4 € e 5 minuti se servirà |
| Cavo USB con interruttore | **tagliata** | Sul Pi 3 A+ la porta USB-A e l'ingresso micro-USB sono circuiti separati: la USB non può tagliare né erogare corrente. E l'alimentatore già comprato ha un suo cavo da staccare |
| Chiavetta USB per la musica | **tagliata** | La libreria vive sulla microSD di sistema in `/home/bmo/musica/` — zero costo, un componente in meno, USB-A libera davvero |
| Fascette e termorestringente | **tagliate** | Il termorestringente è *obsoleto*, non opzionale: con il HAT non c'è più nessuna giunzione saldata in tutto il progetto |
| Kit minuteria assortito (12 €) | **ridotto a ~5,50 €** | Restano solo viti M2.5 autofilettanti e Dupont F-F, gli unici due elementi senza alternativa. La schiuma si compra in ferramenta, non da un venditore di elettronica |

Dettagli completi nel [Piano attuale](02-piano-attuale.md).

## Cosa è rimasto aperto

- **Display 2.4" o 3.5"** — è l'unica decisione d'acquisto ancora aperta. Il 2.4" è quello per cui è dimensionato tutto il resto; il 3.5" è un upgrade legittimo che non rompe niente (con il blit su dirty rect costa il 50% in più, non il 400% della vecchia "trappola del 3,5 pollici" misurata con `fbcp`).
- **Secondo altoparlante per lo stereo** (~5 €) — da decidere dopo la misura di pressione sonora.
- **Interruttore a slitta sull'alimentazione dei MEMS** — l'unica garanzia hardware di muta del microfono. Proposto, lasciato come scelta aperta.
- **Spotify Connect via `raspotify`** — idea V2, richiede un account Premium.

Queste voci aperte sono tracciate come issue nel repository — vedi la scheda Issues.

## Il prossimo passo concreto

Comprare la microSD e fare il bring-up del Pi (Pi e alimentatore ci sono già); fare il giro completo di Gemini per validare l'architettura del cervello; ordinare il resto in UE in un colpo solo.
