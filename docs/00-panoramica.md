# Panoramica del progetto

## Scopo

Costruire un assistente vocale domestico con le sembianze di **BMO**, il personaggio di *Adventure Time*: scocca stampata in 3D, acceso 24/7 alla corrente (niente batterie). Priorità dichiarata fin dall'inizio: **"cheap ma affidabile"**. Un'architettura complicata da programmare è accettabile, perché la parte di programmazione la fa un assistente AI (Claude); non è accettabile un'architettura fragile da mantenere.

**Funzioni da mantenere (piano corrente, rev. 5.1):** conversazione vocale, foto analizzate da un modello vision, risposte che richiedono ricerca sul web, timer da cucina, riproduzione musicale.

Le funzioni sono cambiate nel tempo — vedi [Storia del progetto](01-storia-del-progetto.md) per come si è arrivati da quattro obiettivi iniziali (chatbot, aiutante da cucina, musica, faccia animata) a questa lista.

## Premesse consolidate (settembre 2026)

1. **Raspberry Pi 3 Model A+ (512 MB) + alimentatore già comprati**, da rivenditori ufficiali. Non è una variabile: è il vincolo che filtra tutto il resto del progetto.
2. **Nessun modello in locale** — 512 MB di RAM lo escludono. Il ragionamento sta su **Gemini in cloud**.
3. **Interazione unicamente vocale**: niente pulsanti, niente D-pad, niente PCB custom, niente microcontrollore.
4. Guscio da Printables (*Adventure Time BMO Figure (Interactive)*), stampa in **PETG** (non PLA: temperatura di transizione vetrosa ~60 °C contro i 37–48 °C interni stimati in una scatola sigillata).
5. **Nessuna esperienza di CAD** e nessuna intenzione di acquisirne: fori come *negative volume* nello slicer, telaio interno parametrico in OpenSCAD (`bmo_chassis.scad`) cambiando numeri.

## Stato del progetto (13 settembre 2026)

| Voce | Stato |
|---|---|
| Raspberry Pi 3 Model A+ | ✅ comprato |
| Alimentatore 5V 2.5A | ✅ comprato |
| microSD, HAT audio, display, camera, minuteria | ⬜ da comprare (~68 €, tutta UE) |
| Bring-up del Pi | ⬜ non iniziato |
| Software (`bmo-core`, `bmo-face`, wake word, tool) | ⬜ non iniziato |
| Meccanica (provini, telaio, guscio) | ⬜ niente ancora stampato |
| Piano in vigore | **rev. 5.1 "cloud-first, solo voce"** — vedi [Piano attuale](02-piano-attuale.md) |

Il piano corrente è la **rev. 5.1**, ma è la quinta iterazione di una distinta base che è cambiata parecchio: vale la pena capire *perché* prima di seguirla alla lettera. Vedi la tabella qui sotto e la [Storia del progetto](01-storia-del-progetto.md).

## Il filo dei documenti — come si è arrivati qui

| Rev. | Documento | Cosa cambia |
|---|---|---|
| 1 | *(non conservata)* | 132,10 € — Camera Module 3, display HDMI |
| 2 | *(non conservata)* | 78,40 € — OV5647, `fbcp-ili9341` |
| 3 | [Distinta base rev. 3](revisioni-precedenti/rev3-hardware-bom.md) + [Piano di progetto](revisioni-precedenti/rev3-piano-progetto.md) | 86,40 € — rientra la camera, censita la minuteria, **cade `fbcp-ili9341`** in favore di `spidev` diretto con blit su dirty rect |
| 4 | [BOM rev. 4 — senza dazi](revisioni-precedenti/rev4-bom-senza-dazi.md) | ~76 € tutto UE — **i dazi UE da 3 €/riga doganale (dal 1º luglio 2026) uccidono l'ordine AliExpress**: ~59 € di oneri su 44,50 € di merce. I moduli audio discreti diventano un HAT WM8960 |
| **5.1** | [Piano attuale — cloud-first](02-piano-attuale.md) | **~68 €** — premesse "Pi già comprato / niente modelli locali / solo voce"; display 2.4", camera OV5647 economica, musica su microSD, cinque voci tagliate dal BOM |

## Le decisioni tecniche che reggono il progetto

- **Solo overlay in-tree.** È la disciplina che ha fatto cadere `fbcp-ili9341` (fuori dall'albero del kernel) e scartare il ReSpeaker 2-Mics (driver `seeed-voicecard`, rotture documentate a ogni `apt upgrade`). Il WM8960 passa perché `dtoverlay=wm8960-soundcard` è in `raspberrypi/linux`.
- **Blit sulle sole regioni cambiate**, non copia dell'intero framebuffer: 24,7 kB invece di 153,6 kB per fotogramma, 11% del bus SPI a 25 fps.
- **Cloud-first non è un ripiego dei 512 MB**: è ciò che rende il progetto *più semplice* del riferimento tecnico usato come base. RAM di picco stimata ~295 MB su ~495 disponibili, contro i 4–8 GB di un'architettura locale.
- **La wake word è l'unica cosa che deve restare locale** (openWakeWord/ONNX, ~110 MB): l'alternativa sarebbe streammare il microfono 24/7 al cloud.
- **Tre processi, non tre thread** — `bmo-core`, `bmo-face`, `mpv`, socket Unix `/run/bmo.sock` con un JSON per riga. Non per il GIL di Python (ONNX, `ioctl` SPI e la rete lo rilasciano già) ma per isolamento dei guasti e priorità di scheduling opposte.
- **Senza pulsanti, la faccia è l'unico canale di conferma**: transizione WAIT → LISTEN visibile entro 150 ms, altrimenti l'utente ripete "Hey BMO" e rompe la cattura.

## Preferenze emerse discutendo la rev. 5.1

- Niente LED/illuminatore per la camera: cucina sempre ben illuminata, scatti sempre a ~30 cm.
- Dissipatori rimandati al post burn-in, non eliminati: si decide con una misura di temperatura reale, non con una stima.
- Usare la porta USB-A libera del Pi invece di lasciarla inutilizzata.
- Musica sulla microSD di sistema, non su chiavetta USB; radio via internet o Spotify Connect come estensioni future.
- Per la minuteria, evitare kit assortiti che costringono a comprare più unità del necessario.

## Riferimenti tecnici esterni

Il progetto usa due riferimenti tecnici esterni per architettura hardware e software (un video "brenpoly" con Pi 5 + Ollama in locale, e il progetto PolyMO con ESP32-S3). Le note di analisi di questi riferimenti vivono su disco locale e non sono incluse in questo repository; i link alle fonti pubbliche citate nei documenti sono raccolti in [Riferimenti esterni](03-riferimenti-esterni.md).
