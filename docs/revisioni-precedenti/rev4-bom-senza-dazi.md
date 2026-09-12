# BOM rev. 4 — uscire dai dazi (superato)

> **Stato: superato** dal [piano attuale, rev. 5.1](../02-piano-attuale.md), che ne eredita la scelta del HAT WM8960 e del display 2.4" ma taglia ulteriormente il BOM. Resta il documento di riferimento per **l'analisi dei dazi doganali UE** e per il confronto fra le quattro strategie d'acquisto — nessun documento successivo la ripete per intero.

---

**Sostituisce l'Ordine B** della [rev. 3](rev3-hardware-bom.md). Il resto di quel documento — mappa dei pin, ingombri, bilancio energetico, regole d'acquisto — resta valido salvo dove indicato qui.

## Stato acquisti al momento di questa revisione

| Voce | Stato |
|---|---|
| Raspberry Pi 3 Model A+ | **comprato**, rivenditore ufficiale |
| Alimentatore 5 V micro-USB | **comprato**, rivenditore ufficiale |
| microSD 32 GB A1 | da comprare |
| Tutto l'Ordine B | **da rifare** — vedi sotto |

---

## 1 · Perché l'ordine AliExpress è saltato

Dal **1° luglio 2026** l'UE ha abolito l'esenzione dai dazi sotto i 150 € e la sostituisce con un **dazio fisso di 3 € per riga doganale** (per codice HS presente in dichiarazione), più IVA al 22% su merce + spedizione + dazio.

**Il dazio non è proporzionale al valore: è proporzionale al numero di articoli diversi.** L'Ordine B della rev. 3 conteneva ~15 categorie merceologiche distinte (display, camera, ampli, speaker, microfono, dissipatori, cavetteria, condensatori, LED, pulsanti, resistenze, filo, guarnizione, viti, cavo USB) su 44,50 € di merce:

```
15 righe × 3 €        = 45,00 €
IVA 22% su ~62 €      ≈ 13,60 €
                        ─────────
                       ≈ 58,60 €  di oneri su 44,50 € di componenti
```

I ~60 € osservati tornano esattamente. **Un BOM fatto di tanta minuteria da 30 centesimi è il caso peggiore possibile per questo regime fiscale.**

Ne segue la regola che governa la rev. 4: *non si ottimizza il prezzo unitario, si ottimizza il numero di righe doganali* — e la via più diretta per averne zero è comprare dentro l'UE.

---

## 2 · Opzione A — Tutto UE, audio su HAT integrato ✅ *raccomandata*

L'architettura software non cambia di una riga. Cambia solo *come* il Pi vede l'audio: al posto di due breakout cablati a mano (MAX98357A + INMP441) va una scheda unica che li integra entrambi.

| Componente | Scelta | Fonte | € |
|---|---|---|---|---|
| Audio (ampli + 2 mic MEMS + codec) | **Waveshare WM8960 Audio HAT** | Welectron (DE) | 18,90 |
| Display | **Waveshare 2.4" LCD Module** — ILI9341, 240×320, no touch, PCB 70,5×43,3 mm | Welectron (DE) | 12,90 |
| Header stacking 2×20 extra-tall | per far sporgere i pin sopra il HAT | Welectron / Amazon.it | ~5,00 |
| Altoparlante 40 mm 8 Ω 2 W con JST | il WM8960 pilota 8 Ω, non 4 Ω | Amazon.it | ~8,00 |
| microSD 32 GB A1 di marca | | Amazon.it | ~8,00 |
| Dissipatori adesivi | | Amazon.it | ~4,00 |
| Minuteria (viti M2.5 autofilettanti, 2 pulsanti 6×6, schiuma 2 mm, termorestringente, fascette, Dupont F-F) | un solo kit misto | Amazon.it | ~12,00 |
| Spedizione Welectron | | | ~7,00 |
| | | **Totale** | **~76 €** |

**Consegna 3–5 giorni. Dazi: zero.**

### Confronto con il piano originale (spesa residua, Pi e alimentatore già pagati)

| | Rev. 3 via AliExpress | **Rev. 4 opzione A** |
|---|---|---|
| Componenti | 44,50 | ~69 |
| Spedizioni | ~5 | ~7 |
| Dazi + IVA | ~59 | **0** |
| microSD | 7 | inclusa |
| **Totale** | **~116 €** | **~76 €** |
| Attesa | 2–3 settimane | 3–5 giorni |

**Risparmio ~40 € e ~2,5 settimane.**

### Cosa sparisce dal BOM e dalla lista dei rischi

Il HAT non è solo più economico dopo i dazi: elimina i punti in cui il progetto poteva rompersi.

- **MAX98357A, INMP441, condensatore 1000 µF, filo siliconico AWG24, massa a stella, 12 cavetti Dupont** — tutto integrato sul PCB del HAT, con il piano di massa e il disaccoppiamento già progettati.
- **Rischio «undervoltage sotto i picchi audio»** (rev. 3, probabilità media): non è più a carico dell'utente.
- **Rischio «l'overlay I2S non riconosce la coppia mic + ampli»** (il motivo per cui la fase audio andava per prima): sparisce. Il WM8960 è **una scheda sola con un overlay in-tree** — `dtoverlay=wm8960-soundcard` è nell'albero ufficiale `raspberrypi/linux` (presente in `rpi-6.6.y` e `rpi-6.12.y`), quindi non serve il driver DKMS di Waveshare e non si rompe agli aggiornamenti di kernel. È la stessa disciplina che aveva già portato ad abbandonare `fbcp-ili9341`.
- **Fase 2 (audio) si riduce a**: infilare il HAT, aggiungere una riga a `config.txt`, `speaker-test`.

### I tre prezzi da pagare — tutti reali, tutti gestibili

**1 · La faccia diventa quella della "variante 65".**
Il 2,4" ha la stessa risoluzione 240×320 e gli stessi asset, ma area attiva 48,8×36,6 mm invece di 64,8×48,6. Finestra nello slicer: **47,6 × 35,4 × 10 mm**; guscio 95×110×42 nominali (poi vedi punto 3). Il PCB Waveshare è 70,5×43,3 mm, più piccolo degli 88×55 ipotizzati: la mascherina va riquotata e il gradino d'appoggio scende a ~72×45×3,4 mm.
*Verifica prima di stampare il guscio*: tre righe da 20 caratteri di una ricetta, lette a mezzo metro. Se non bastano, un 2,8"/3,2" in UE costa 20–28 € (+8÷15 €) e riporta la geometria alla variante 78.

**2 · La potenza audio scende: 1 W/canale su 8 Ω invece di 3 W su 4 Ω.**
Il WM8960 è però **stereo**: due driver da 40 mm su 8 Ω, dentro la camera di compressione già prevista, restano adeguati per la cucina. È comunque **il primo criterio di accettazione da misurare** — rumore rosa all'80%, fonometro a 1 m, obiettivo ≥ 78 dB. Se non basta: un MAX98357A esterno resta un piano B da 8 €, con l'ingresso line-out del HAT.

**3 · La profondità cresce.**
Stack con HAT impilato su header extra-tall: 2,5 (parete) + 5 (display) + 3 (gap) + 20 (Pi) + ~11 (HAT sopra header alto) + 6 (raggio cavi) + 2,5 = **~50 mm** contro i 45 esterni della rev. 3.
Rimedio: **portare la profondità del guscio a 55 mm** nel parametro corrispondente di `bmo_chassis.scad`. Su un guscio 110×125 (o 95×110) sono 10 mm che non si notano e ~40 g di PETG in più. L'alternativa — HAT affiancato al Pi con prolunga flat a 40 pin — è più compatta ma toglie i pin al display, quindi non conviene.

### Correzioni alla mappa dei pin (rev. 3)

Il codec si controlla via I2C, quindi **GPIO2 e GPIO3 sono occupati**.

| Riga della rev. 3 | Correzione |
|---|---|
| `Pulsante spegnimento — pin 5 / GPIO3` | **Non più possibile.** `dtoverlay=gpio-shutdown,gpio_pin=26` su GPIO26, e il pulsante muta microfono si sposta su GPIO6. Si perde la riaccensione da halt con lo stesso tasto: per riaverla, un secondo pulsante sui pad **RUN** del Pi 3 A+ (due piazzole, un tastino, zero costo). |
| `I2S BCLK/LRCLK/DIN/DOUT` | Gestiti dal HAT sull'header, nessun cablaggio manuale. |
| `MAX98357A VIN / GND / SD` | Righe cancellate. |
| `INMP441 VDD / GND` | Righe cancellate. |
| Display (SCLK, MOSI, CS, DC, RST, **BL su GPIO12**) | Invariate, ma i Dupont vanno sui **pin che sporgono sopra il HAT**, non sull'header del Pi. |

`/boot/firmware/config.txt`:

```
dtparam=spi=on
dtoverlay=wm8960-soundcard
dtoverlay=gpio-shutdown,gpio_pin=26
dtparam=watchdog=on
gpu_mem=16
```

Sparisce `dtoverlay=googlevoicehat-soundcard`. **Mic e ampli restano campione-sincroni** — sono sullo stesso codec — quindi la premessa che rendeva possibile l'AEC vale ancora, anzi è più solida di prima.

---

## 3 · Opzione B — Come A, ma con hardware ufficiale Raspberry Pi

Sostituisce il WM8960 con il **Raspberry Pi Codec Zero HAT** (ex IQaudio), 20,90 € da Welectron: codec Dialog DA7212, overlay in-tree `iqaudio-codec`, microfono MEMS a bordo, uscita speaker mono 1,2 W su 8 Ω a morsetti, ingressi line/mic esterni, 65×31 mm.

**Quando sceglierla**: se il criterio dominante è "supportato ufficialmente per sempre". È l'unica scheda audio del confronto che Raspberry Pi vende e documenta in proprio.

**Perché non è la prima scelta**:
- **un solo microfono**, pensato per il parlato ravvicinato; il WM8960 ne ha due, e a 1,5–3 m in cucina la differenza si sente in accuratezza di trascrizione;
- 2 € più cara e, da Welectron, con ~3 settimane di consegna — il che riporta l'attesa che l'opzione A elimina;
- audio mono.

Tutte le note su profondità, GPIO2/3 e header extra-tall dell'opzione A valgono identiche.

---

## 4 · Opzione C — Split-brain con un tutto-in-uno ESP32

L'unico vero "tutto-in-uno" del mercato a questo prezzo: **~45 € IVA inclusa**, a magazzino, spedizione in giorni. Un dispositivo come l'ESP32-S3-BOX-3 contiene display 2,4" 320×240 touch, **due microfoni digitali**, speaker, accelerometro, ESP32-S3 con 16 MB PSRAM e un guscio proprio. Zero cablaggi, zero dazi, zero rischi di alimentazione.

È la risposta letterale alla domanda "conviene un dispositivo integrato?" — ed è **più economico dell'ordine AliExpress con i dazi** (45 € contro 116 €). Ma:

- **rende inutile il Raspberry Pi appena comprato**, a meno di riciclarlo come nodo di calcolo in rete locale (che sul 3 A+ da 512 MB significa poco: non ci gira un LLM, e l'inferenza sta comunque su Gemini);
- **butta via il piano software** — `bmo-core`, `bmo-face`, i tre processi, Piper locale, `mpv`, il socket Unix. Sull'ESP32 si riscrive tutto in ESP-IDF/C, e la sincronizzazione labiale gratis (il primo motivo per cui era stata scelta la pipeline classica) va rifatta a mano;
- il guscio va smontato per entrare nella scocca BMO, e il display è saldato alla sua scheda: le quote della faccia le detta lui, non il file OpenSCAD;
- niente riproduzione musicale decente: speaker piccolo, nessun decoder come `mpv`.

Nel riferimento tecnico esterno lo split-brain ha senso perché **un telefono Android fa da acceleratore per LLM, Whisper e Piper in locale e ha accesso nativo a notifiche e screen time**. Nessuno di quei due motivi si applica qui: BMO usa Gemini in cloud e non deve leggere notifiche. Senza il telefono nel disegno, l'ESP32 resta solo un Pi più debole con lo schermo incollato sopra.

**Quando sceglierla comunque**: se in corsa si decide che BMO deve essere **portatile a batteria** (questi moduli gestiscono la LiPo; il Pi 3 A+ no) o se si vuole un secondo BMO da scrivania senza ricomprare nulla.

---

## 5 · Opzione D — Restare su AliExpress comprimendo le righe doganali

Se per qualche ragione l'ordine cinese deve partire lo stesso, la leva è ridurre le categorie merceologiche da 15 a 3–4: **un modulo display, un modulo audio integrato (clone WM8960/ReSpeaker), un altoparlante, un kit minuteria unico**. Dazio 12 € invece di 45, IVA ~10 €.

Resta comunque peggiore dell'opzione A: ~70 € di oneri e merce contro 76 € **ma con tre settimane di attesa, nessuna garanzia sul conteggio delle righe fatto in dogana, e i cloni WM8960 senza certezza sull'overlay in-tree**. Sei euro di risparmio teorico non pagano quel rischio.

---

## 6 · Scheda scartata e perché

**ReSpeaker 2-Mics Pi HAT v2.0** (~14,50 € IVA inclusa, 2 microfoni, uscita speaker, pulsante, 3 LED RGB): il più economico dei tre HAT audio e apparentemente il più adatto.
Il problema è il driver: la v2.0 monta un TLV320AIC3104 e richiede `seeed-voicecard`, **fuori dall'albero del kernel**, con una storia documentata di rotture a ogni aggiornamento di kernel. Su un dispositivo acceso 24/7 che deve ricevere aggiornamenti di sicurezza è esattamente la dipendenza che il progetto aveva già deciso di non avere quando ha eliminato `fbcp-ili9341`. **2,50 € di risparmio non valgono un `apt upgrade` che ammutolisce BMO.**

**Pirate Audio (Pimoroni)**: integra display e audio su un solo HAT, ma 240×240 su 1,3" e **nessun microfono**. Fuori specifica.

---

## 7 · Cosa fare, in ordine

1. **Comprare l'opzione A** (un ordine Welectron + un ordine Amazon.it). Il display 2,4" è a magazzino, il WM8960 dichiara 11–13 giorni lavorativi: se l'attesa dà fastidio, verificare prima la disponibilità dello stesso HAT su Amazon.it o Berrybase.
2. **Comprare subito la microSD** e fare la fase 1 (bring-up headless) mentre il resto viaggia — il Pi e l'alimentatore ci sono già, quindi la roadmap può partire questa settimana invece che fra tre.
3. **Portare la profondità del guscio a 55 mm** e riquotare finestra e mascherina sulle misure del 2,4" prima di stampare qualsiasi cosa lunga.
4. **Misurare la pressione sonora** all'arrivo del HAT, prima di chiudere la meccanica: è l'unico requisito che questa revisione mette davvero a rischio.

> **Nota:** la rev. 5.1 taglia ulteriormente il BOM di questa opzione A (~76 € → ~68 €) rimuovendo cinque voci — vedi [piano attuale, §1](../02-piano-attuale.md).

---

## Fonti

- [Altalex — dazio UE da 3 € sui piccoli pacchi, in vigore dal 1° luglio 2026](https://www.altalex.com/documents/news/2026/07/03/unione-europea-stretta-piccoli-pacchi-via-dazio-3-euro-come-funziona)
- [Euronews — l'UE chiude l'esenzione sotto i 150 €](https://www.euronews.com/my-europe/2026/06/30/eu-ends-tax-loophole-exploited-by-shein-temu-and-aliexpress)
- [Welectron — Waveshare WM8960 Audio HAT, 18,90 €](https://www.welectron.com/Waveshare-15668-WM8960-Audio-HAT_1)
- [Welectron — Waveshare 2.4" LCD Module ILI9341 240×320, 12,90 €](https://www.welectron.com/Waveshare-18366-24inch-LCD-Module_1)
- [Welectron — Raspberry Pi Codec Zero HAT, 20,90 €](https://www.welectron.com/Official-Raspberry-Pi-Codec-Zero-HAT)
- [raspberrypi/linux — overlay wm8960-soundcard in-tree (rpi-6.12.y)](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/wm8960-soundcard-overlay.dts)
- [Waveshare WM8960-Audio-HAT #23 — «basta aggiungere dtoverlay=wm8960-soundcard»](https://github.com/waveshareteam/WM8960-Audio-HAT/issues/23)
- [Kiwi Electronics — ReSpeaker 2-Mics Pi HAT v2.0, 11,99 € escl. IVA](https://www.kiwi-electronics.com/en/respeaker-2-mics-pi-hat-3140)
- [respeaker/seeed-voicecard — rotture ricorrenti del driver DKMS](https://github.com/respeaker/seeed-voicecard/issues/311)
- [Mouser Italia — ESP32-S3-BOX-3, 44,72 € IVA inclusa](https://www.mouser.it/ProductDetail/Espressif-Systems/ESP32-S3-BOX-3)
