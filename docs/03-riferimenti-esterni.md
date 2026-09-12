# Riferimenti esterni

Il progetto usa due riferimenti tecnici esterni per l'architettura hardware e software. Le note di analisi dettagliata di questi riferimenti (confronto voce per voce con le scelte fatte qui) vivono nella memoria di lavoro locale del progetto e non sono incluse in questo repository. Restano invece qui i link pubblici alle fonti, così chi vuole ricostruire BMO può risalire agli stessi materiali.

## Il riferimento principale — Pi 5 + Ollama, tutto in locale

Un progetto pubblico che costruisce un BMO con inferenza interamente locale su un Raspberry Pi 5 da 16 GB (Whisper per lo STT, Gemma 3 come LLM, Moondream come modello vision, Piper per il TTS). È il riferimento principale per **l'architettura software** di questo progetto: macchina a stati, faccia che cambia a ogni transizione, clip vocali pre-generate per coprire l'attesa, wake word custom, loop agentico con tool. Il [Piano attuale](02-piano-attuale.md) (§0) descrive nel dettaglio cosa di questo riferimento sopravvive nel passaggio a un Pi 3 A+ con inferenza in cloud, e cosa no.

- Video: [brenpoly — "I made a real BMO local AI agent with a Raspberry Pi and Ollama"](https://youtu.be/l5ggH-YhuAw)
- Modello 3D e PCB del progetto di riferimento: [Printables — BMO from Adventure Time](https://www.printables.com/model/1582055-bmo-from-adventure-time)

## Un secondo riferimento — PolyMO

Un progetto con architettura "split-brain": un ESP32-S3 tutto-in-uno più un telefono Android usato come nodo di calcolo per l'inferenza locale. Citato nel [BOM rev. 4](revisioni-precedenti/rev4-bom-senza-dazi.md) (§4, opzione C) come termine di paragone quando si è valutato — e scartato — un dispositivo integrato ESP32 al posto del Raspberry Pi.

## Modello 3D del guscio (usato in questo progetto)

- [Printables — Adventure Time BMO Figure (Interactive)](https://www.printables.com/model/1139445-adventure-time-bmo-figure-interactive) — il modello di partenza per il guscio esterno.
- [Printables — BMO come case per Raspberry Pi](https://www.printables.com/model/468112-raspberry-pi-4-case-bmo-adventure-time) — alternativa più semplice da adattare se il modello sopra fallisse i cinque criteri di validazione (vedi [Piano di progetto rev. 2/3](revisioni-precedenti/rev3-piano-progetto.md), §3).

## Normativa doganale UE citata nell'analisi dei dazi

- [Altalex — dazio UE da 3 € sui piccoli pacchi, in vigore dal 1° luglio 2026](https://www.altalex.com/documents/news/2026/07/03/unione-europea-stretta-piccoli-pacchi-via-dazio-3-euro-come-funziona)
- [Euronews — l'UE chiude l'esenzione sotto i 150 €](https://www.euronews.com/my-europe/2026/06/30/eu-ends-tax-loophole-exploited-by-shein-temu-and-aliexpress)

Per l'elenco completo delle fonti tecniche (datasheet, overlay del kernel, documentazione Gemini API, negozi) vedi la sezione "Fonti" in fondo a [Piano attuale](02-piano-attuale.md) e ai documenti in [revisioni precedenti](revisioni-precedenti/).
