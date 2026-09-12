# Distinta base rev. 3 (superata)

> **Stato: superato.** L'Ordine B è sostituito dalla [rev. 4](rev4-bom-senza-dazi.md) e l'intero impianto dal [piano attuale, rev. 5.1](../02-piano-attuale.md). **Restano validi**: la mappa dei pin del display, gli ingombri, il bilancio energetico, le regole d'acquisto.

---

**Documento d'acquisto.** Per il piano di progetto, l'architettura software e la roadmap di questa generazione: vedi [Piano di progetto rev. 2/3](rev3-piano-progetto.md).

**Rev. 3** — la camera rientra a distinta (visione per implementazioni future), e si aggiungono le 8 voci di minuteria che mancavano alla rev. 2. Da **78,40 €** a **86,40 €** di componenti, ~96 € con spedizioni.

| | rev. 1 | rev. 2 | **rev. 3** |
|---|---|---|---|
| Componenti | 132,10 € | 78,40 € | **86,40 €** |
| Con spedizioni | ~145 € | ~88 € | **~96 €** |
| Camera | Camera Module 3 | OV5647 | **OV5647 fuoco regolabile** |
| Minuteria elettrica | non censita | non censita | **censita, 8,00 €** |
| Driver display | fbcp-ili9341 | fbcp-ili9341 | **spidev diretto, blit su dirty rect** |

---

## Ordine A — Europa (BerryBase / Amazon.it) · 3–5 giorni

| Componente | Scelta | Qtà | € |
|---|---|---|---|
| SBC | Raspberry Pi 3 Model A+ | 1 | 26,90 |
| Alimentazione | 5 V 2,5 A micro-USB, marca nota | 1 | 8,00 |
| Memoria | microSD 32 GB classe A1, marca vera | 1 | 7,00 |
| | | **Subtotale A** | **41,90** |

> **Verifica prima di ordinare**: se il computer usato per il setup non ha lo slot SD, aggiungere un **lettore microSD USB-C, ~8 €**, altrimenti la microSD non si scrive e il progetto si ferma al primo passo.

---

## Ordine B — AliExpress, stesso venditore dove possibile · 2–3 settimane

### Moduli

| Componente | Scelta | Qtà | € |
|---|---|---|---|
| Display | SPI 3,2″ **ILI9341** 240×320, **no touch** | 1 | 11,00 |
| Camera | **OV5647 5 MP, lente a fuoco regolabile** + cavo CSI 15 pin | 1 | 9,00 |
| Ampli + DAC | MAX98357A I2S breakout | 1 | 2,50 |
| Altoparlante | Full-range 40 mm, 4 Ω 3 W | 1 | 2,50 |
| Microfono | INMP441 MEMS I2S | 1 | 3,50 |
| Raffreddamento | Set dissipatori adesivi | 1 | 2,00 |
| Cavetteria | Dupont F-F 20 cm, distanziali M2.5, fascette | 1 | 6,00 |
| | | **Subtotale moduli** | **36,50** |

### Minuteria elettrica — mancava alla rev. 2

| Componente | Qtà | € | Perché |
|---|---|---|---|
| **Condensatore elettrolitico 1000 µF 10 V low-ESR** | 2 | 0,30 | **La voce singola più importante di tutto il BOM.** Serbatoio locale ai morsetti del MAX98357A: un class-D su 4 Ω chiede corrente a impulsi e senza serbatoio i transienti fanno crollare il rail 5 V → undervoltage sul Pi. Va montato **a 2 cm dall'ampli**, non sul Pi. |
| LED bianco 5 mm alta efficienza + resistenza 220 Ω | 2 + 5 | 0,60 | Illuminatore per gli scatti della camera. Vale più di 20 € di sensore migliore, e dà a BMO un modo visibile di dire «sto guardando». |
| Pulsante momentaneo 6×6×5 mm | 4 | 0,40 | Spegnimento pulito (`dtoverlay=gpio-shutdown` su GPIO3, che riaccende anche da halt) + muta microfono. Senza pulsante l'unico modo di spegnere è staccare la spina, ed è così che si corrompono le microSD. I fori del D-pad di BMO ci sono già. |
| Resistenza 10 kΩ 1/4 W | 5 | 0,20 | Pull-up esterni sui pulsanti, se non ci si fida di quelli interni. |
| Filo siliconico AWG24, 1 m rosso + 1 m nero | 1 | 1,50 | I Dupont sono AWG28: ok per SPI e I2S, insufficienti per alimentare 3 W di picco. |
| Guarnizione in schiuma adesiva 2 mm | 1 | 0,50 | Sigilla il cestello dello speaker alla camera di compressione stampata. Senza, corto acustico fra fronte e retro del cono e i medio-bassi spariscono. |
| Viti M2.5×6 autofilettanti + termorestringente assortito | 20 | 2,50 | Le torrette del telaio stampato sono per autofilettanti: niente inserti a caldo, niente saldatore per la meccanica. |
| Cavo micro-USB angolato 1 m o passacavo | 1 | 2,00 | Ingresso alimentazione a filo del guscio: altrimenti servono 25 mm di profondità in più solo per il connettore. |
| | | **8,00** | |

**Subtotale B: 44,50 €**

---

## Totale

| | € |
|---|---|
| Ordine A (Europa) | 41,90 |
| Ordine B (AliExpress) | 44,50 |
| **Componenti** | **86,40** |
| Spedizioni (2 ordini) | ~10,00 |
| **Totale d'acquisto** | **~96,40** |
| Filamento PETG ~200 g | ~5,00 |
| **Tutto compreso** | **~101,40** |

Comprando tutto su Amazon.it con consegna in due giorni invece delle tre settimane di AliExpress si sale di circa 22 € (~118 €): è un premio di comodità, non un errore di stima.

---

## Opzionali e piani di riserva

| Voce | € | Quando |
|---|---|---|
| Lettore microSD USB-C | 8,00 | Se il computer usato per il setup non ha lo slot SD. **Verificarlo subito.** |
| Microfono USB | 8,00 | Piano B se l'overlay I2S non riconosce la coppia mic+ampli. Va nella porta USB-A, nessun'altra modifica al cablaggio. |
| 2° MAX98357A + 2° speaker 40 mm | 5,00 | Stereo. Solo se la musica conta davvero: il MAX98357A è mono, serve una coppia con L/R impostati diversamente. |
| Ventola 25 mm 5 V | 2,50 | **Solo se** il burn-in di 72 h supera i 75 °C. Attenzione: mette una sorgente di rumore a 8 cm dal microfono. |
| Inserti filettati M2.5 a caldo ×20 | 3,00 | Se si prevede di aprire e richiudere BMO molte volte. |

---

## Regole d'acquisto — le tre che fanno danno

**1 · Display.** Deve comparire nel titolo dell'inserzione: **controller ILI9341 o ST7789**, risoluzione **240×320**, **senza touch**, diagonale 2,4″–3,2″. Se dice ILI9486, o se su un 480×320 non dichiara il controller, passare oltre: l'ILI9486 è il più diffuso ed è misurato a 13 fps a schermo pieno. Se si sceglie l'ST7789 attenzione doppia — pilota anche i pannelli 240×240 (1,3″–1,54″), che sono i più venduti e manderebbero all'aria asset e proporzioni del guscio.

**2 · Camera.** Prendere la versione con **lente a fuoco regolabile**, non quella a fuoco fisso: parecchi moduli fissi escono tarati a ~30 cm, cioè inutilizzabili a distanza di stanza. Tarare una volta a ~1,5 m con un giornale come bersaglio, poi bloccare la ghiera con una goccia di smalto. Verificare che il cavo CSI 15 pin sia incluso.

**3 · Alimentatore e microSD.** Non sono la voce da cui risparmiare 5,50 €. L'alimentazione insufficiente è la prima causa dei Pi descritti come inaffidabili: sotto tensione il SoC va in throttling, il Wi-Fi cade in trasmissione e la microSD si corrompe agli sbalzi. Su un dispositivo acceso 24 ore su 24 è il taglio con il peggior rapporto fra risparmio e grattacapi.

---

## Collegamenti — mappa dei pin definitiva

SPI0 e I2S sono gruppi di pin separati e non confliggono; la camera passa dal CSI senza toccare l'header.

| Segnale | Pin fisico | BCM | Note |
|---|---|---|---|
| Display SCLK | 23 | GPIO11 | SPI0 |
| Display MOSI | 19 | GPIO10 | SPI0 |
| Display CS | 24 | GPIO8 | CE0 |
| Display DC | 16 | GPIO23 | |
| Display RST | 18 | GPIO24 | |
| **Display BL** | **32** | **GPIO12** | ⚠️ `luma.lcd` mette il backlight su GPIO18 di default, che qui è **BCLK dell'I2S**. Passare `gpio_LIGHT=12` — è ALT0 = PWM0, quindi la luminosità resta regolabile in hardware. Sintomo se sbagliato: il display funziona e l'audio smette. |
| Display MISO | — | — | **Non collegare.** Il pannello non va letto e alcuni moduli pilotano la linea a sproposito. |
| Display VCC | 17 o 4 | 3,3 V o 5 V | **Guardare il modulo**: regolatore a bordo (SOT-23 vicino a VCC) → 5 V; senza regolatore → 3,3 V, e 5 V lo distrugge. Nel dubbio 3,3 V: al peggio non si accende. |
| I2S BCLK | 12 | GPIO18 | condiviso ampli + microfono |
| I2S LRCLK | 35 | GPIO19 | condiviso |
| I2S DIN → ampli | 40 | GPIO21 | MAX98357A |
| I2S DOUT ← mic | 38 | GPIO20 | INMP441 SD; L/R a massa per il canale sinistro |
| MAX98357A VIN | 2 | 5 V | con filo siliconico AWG24 dedicato + condensatore 1000 µF ai morsetti |
| MAX98357A GND | 6 | GND | |
| Ampli SD/shutdown | 36 | GPIO16 | Facoltativo ma consigliato: spegne lo stadio di potenza in assenza di audio ed elimina il fruscio di fondo permanente. |
| INMP441 VDD | 1 | 3,3 V | **non 5 V** |
| INMP441 GND | 9 | GND | |
| LED camera | 29 | GPIO5 | + 220 Ω in serie |
| Pulsante spegnimento | 5 | GPIO3 | `dtoverlay=gpio-shutdown`. GPIO3 **riaccende il Pi da halt**: un pulsante solo fa entrambe le cose. |
| Pulsante muta mic | 37 | GPIO26 | pull-up interno, letto da `bmo-core` |
| Camera | CSI | — | connettore dedicato 15 pin, nessun GPIO |

**Massa a stella**: tutte le masse tornano a due pin GND del Pi vicini fra loro, mai a catena da un modulo all'altro. Una massa in serie fra ampli e microfono mette il ritorno di corrente dello speaker dentro il riferimento del mic, ed è il ronzio che poi si insegue per giorni.

### `/boot/firmware/config.txt`

```
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard
dtparam=spi=on
dtoverlay=gpio-shutdown
dtparam=watchdog=on
gpu_mem=16
```

L'overlay `googlevoicehat-soundcard` è **in-tree**: microfono e amplificatore condividono BCLK e LRCLK, quindi sono campione-sincroni e la cancellazione d'eco funzionerà davvero il giorno che servirà. `gpu_mem=16` restituisce quasi 50 MB su 512: senza HDMI non servono alla GPU.

---

## Correzione della rev. 2: `fbcp-ili9341` non serve

La rev. 2 dava per scontato `fbcp-ili9341` e ne segnalava il rischio (fuori dall'albero del kernel, non funziona su Pi 5, nessuna garanzia sui kernel futuri). Quel rischio è evitabile: fbcp copia l'intero framebuffer HDMI su SPI, **153,6 kB per fotogramma**, indipendentemente da quanti pixel siano cambiati.

BMO ha due occhi e una bocca su sfondo piatto: fra due fotogrammi cambiano ~12 000 pixel su 76 800. Scrivendo solo quelli (due finestre 64×44 + una 120×56) passano **24,7 kB per fotogramma**, cioè 4,5 ms di bus invece di 28 — l'11% del bus SPI a 25 fps.

**Conseguenze sulla distinta:**
- Si pilota il pannello direttamente da `spidev`, che è in-tree e funziona su qualsiasi Pi, Pi 5 compreso. Sparisce l'unica dipendenza fuori dall'albero del kernel dell'intero progetto.
- **La configurazione "senza fbcp" a 92,40 € con display HDMI perde ogni motivo di esistere** e va cancellata dalle alternative.

---

## Ingombri (variante 3,2″)

| | Valore |
|---|---|
| Guscio esterno | 110 × 125 × 45 mm |
| Volume interno | ~0,50 L, ~30% occupato |
| Profondità minima | 39 mm |
| Area faccia (attiva) | 64,8 × 48,6 mm |
| PCB del modulo display | ~88 × 55 mm — la cornice va coperta dalla mascherina stampata |
| Filamento | 180–220 g PETG |

Stack in profondità: 2,5 (parete) + 5 (modulo SPI) + 3 (gap) + 20 (Pi con header) + 6 (raggio cavi) + 2,5 = **39 mm**, su 45 esterni.

**La porta USB-A vuole ~45 mm liberi in linea**: deve affacciarsi su un fianco, non verso il retro. Stessa cosa per la fessura della microSD.

**Materiale: PETG, non PLA.** In una scatola sigillata da 0,5 L con 1,5–4 W dentro, d'estate a Milano si superano i 50 °C di aria interna. La Tg del PLA è ~60 °C, quella del PETG ~80. Servono anche feritoie passanti: ≥300 mm² in basso e ≥300 in alto, su pareti opposte, per innescare l'effetto camino.

---

## Bilancio energetico

| Carico | Potenza |
|---|---|
| Pi 3 A+ a riposo | ~1,2 W |
| Pi 3 A+ in picco, Wi-Fi in TX | ~4 W |
| Display SPI 3,2″ (retroilluminazione inclusa) | ~0,5 W |
| Audio, picchi brevi | fino a 3 W |
| Camera + LED, solo durante lo scatto | ~0,8 W |
| **Picco totale** | **~8 W** — l'alimentatore da 12,5 W resta la scelta giusta |

Regime reale con wake word locale e sessioni brevi: **~1,5 W**. È l'architettura software che tiene fresco l'hardware.

---

## Cosa la camera aggiunge, e cosa non aggiunge

La camera **non serve a nessuno dei quattro obiettivi funzionali** (conversazione, cucina, musica, faccia animata): rientra a distinta come capacità futura per modelli vision. Vale la pena essere onesti su cosa aspettarsi.

- **Il limite non sarà il sensore, sarà la luce.** Un OV5647 ha sensore piccolo, ottica lenta, niente HDR. In una stanza illuminata di sera produce foto scure e rumorose, e nessun modello vision recupera informazione che non è stata catturata. Il LED da 60 centesimi su GPIO è la contromisura che conta.
- **Un frame JPEG a 640×480 pesa ~50 kB**, mandato a Gemini Flash insieme alla domanda. A questa risoluzione i 512 MB non sono un problema e il costo per immagine è trascurabile.
- **Nessuna finestrella trasparente davanti alla lente**: qualsiasi cosa messa davanti a un'ottica da 3 € peggiora l'immagine più di quanto la protegga. Foro Ø 8 mm con tasca 8×8×1 mm che tiene la lente a filo.
- **Il LED punta avanti, non verso la lente.** Se illumina la propria ottica, il flare cancella il soggetto.
- Il connettore CSI resta libero se si decide di rimandare: aggiungere la camera più tardi non richiede di toccare nient'altro.
