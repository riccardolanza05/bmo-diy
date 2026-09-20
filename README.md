# BMO DIY

Un assistente vocale domestico con le sembianze di **BMO**, il personaggio di *Adventure Time*: scocca stampata in 3D, acceso 24/7 alla corrente. Conversazione vocale, foto analizzate da un modello vision, ricerca sul web, timer da cucina, riproduzione musicale. Cervello su Gemini in cloud, wake word locale, ~68 € di componenti oltre al Raspberry Pi.

> 🇮🇹 **Repository in italiano.** Il progetto è nato ed è documentato in italiano; una versione in inglese arriverà solo quando il progetto sarà considerato definitivo.

## Stato del progetto

| | |
|---|---|
| **Piano in vigore** | rev. 5.1 "cloud-first, solo voce" — [`docs/02-piano-attuale.md`](docs/02-piano-attuale.md) |
| **Hardware comprato** | Raspberry Pi 3 Model A+, alimentatore 5V 2.5A, microSD (bring-up fatto, raggiungibile via SSH) |
| **Hardware da comprare** | HAT audio, display, camera, minuteria (tutto UE, zero dazi) — **ultima fase** della roadmap |
| **Software** | `bmo-core` in sviluppo sul PC: cervello con cascata di modelli e loop agentico, timer persistenti, macchina a stati, radio — vedi [`bmo-core/`](bmo-core/); wake word e TTS ancora da collegare (issue #21, #22) |
| **Meccanica** | non iniziata (niente ancora stampato) |
| **Fase corrente della roadmap** | Fase 1 — software su PC con `bmo-core`, usando webcam, microfono e casse del computer (vedi [roadmap](docs/02-piano-attuale.md#3--roadmap), software-first dal 2026-09-19) |

Il progetto è arrivato a questo punto passando per cinque revisioni della distinta base e tre premesse di fondo che ne hanno riscritto l'architettura (niente modelli locali, solo interazione vocale, hardware già in parte comprato). La storia completa, comprese le decisioni scartate e perché, è in [`docs/01-storia-del-progetto.md`](docs/01-storia-del-progetto.md).

## Struttura del repository

```
docs/
├── 00-panoramica.md                  Scopo, premesse, stato, decisioni tecniche di fondo
├── 01-storia-del-progetto.md         Come si è arrivati al piano attuale, revisione per revisione
├── 02-piano-attuale.md               IL PIANO IN VIGORE: BOM, architettura software, roadmap, rischi
├── 03-riferimenti-esterni.md         Link ai progetti di riferimento e alle fonti
└── revisioni-precedenti/             Distinte base superate — non sono scartate: ognuna
    ├── rev3-hardware-bom.md          resta l'UNICA fonte per una parte del progetto (vedi i
    ├── rev3-piano-progetto.md        banner in cima a ciascun file)
    ├── rev4-bom-senza-dazi.md
    └── rev3-sintesi-bom.md

bmo-core/                             Logica di dialogo, in sviluppo sul PC (omarchy) prima
└── src/bmo_core/                     ancora di comprare HAT/display/camera — vedi bmo-core/README.md
    ├── brain.py                       il cervello: prompt, cascata di modelli, loop agentico
    ├── macchina.py                    la macchina a stati (attesa/ascolto/pensiero/parlato)
    ├── modelli.py                     cascata dei modelli Gemini con ripiego automatico
    ├── strumenti.py                   le dichiarazioni degli strumenti per Gemini
    ├── timer.py / sveglia.py          timer persistenti su disco e il processo che li fa suonare
    ├── radio.py / ricerca.py          radio via internet e ricerca sul web
    ├── prova_frasi.py                 il banco di prova a frasi del prompt di sistema
    ├── config.py                      rileva l'ambiente: PC di sviluppo o Raspberry Pi
    └── adapters/                      confine hardware: stessa logica, implementazione diversa
```

## Per chi vuole ricostruire BMO da zero

Il piano attuale ([`docs/02-piano-attuale.md`](docs/02-piano-attuale.md)) è il documento tecnico principale ed è pensato per essere seguito in ordine, ma **tre sezioni della rev. 2/3 restano l'unica fonte** e non sono ripetute nel piano attuale — leggerle quando la roadmap ci arriva:

1. **Fase 1 (software su PC)** → architettura software completa in [`02-piano-attuale.md` §2](docs/02-piano-attuale.md#2--architettura-software) e adapter hardware in [`bmo-core/`](bmo-core/).
2. **Fase 3 (acquisto)** → BOM in [`02-piano-attuale.md` §1](docs/02-piano-attuale.md#1--hardware-da-comprare).
3. **Fase 4 (audio, display, camera)** → [`02-piano-attuale.md` §1.4](docs/02-piano-attuale.md#14-mappa-dei-pin) per la mappa dei pin; driver `spidev` e blit su dirty rect spiegati in [`revisioni-precedenti/rev3-hardware-bom.md`](docs/revisioni-precedenti/rev3-hardware-bom.md) (sezione "Correzione della rev. 2").
4. **Fase 5 (meccanica)** → **qui la fonte è [`revisioni-precedenti/rev3-piano-progetto.md`](docs/revisioni-precedenti/rev3-piano-progetto.md) §3**: la strategia "tre pezzi, zero CAD", i cinque criteri per validare un modello Printables, i parametri di stampa e l'ordine di montaggio non sono ripetuti altrove.
5. **Fase 6 (integrazione, burn-in)** → criteri di accettazione in [`02-piano-attuale.md` §3, Fase 6](docs/02-piano-attuale.md#fase-6--integrazione-e-messa-in-esercizio).

I riferimenti tecnici esterni usati come base per l'architettura sono elencati in [`docs/03-riferimenti-esterni.md`](docs/03-riferimenti-esterni.md).

## Decisioni ancora aperte

Le domande implementative ancora senza risposta (display 2.4" vs 3.5", secondo altoparlante, interruttore fisico per il microfono, funzioni V2 come barge-in o Spotify Connect...) sono tracciate come **Issue** di questo repository, non sepolte in un documento. Chi ha un'opinione o vuole proporre un'alternativa è benvenuto a commentare lì.

## Una nota sulla privacy

Il prompt di sistema, sia l'esempio in [`02-piano-attuale.md` §2.3](docs/02-piano-attuale.md#23-il-prompt-di-sistema-e-liniezione-di-contesto) sia quello vero in `bmo-core/src/bmo_core/brain.py`, include la città del proprietario del progetto: è il profilo per cui BMO viene configurato, non un dato di terzi, ed è lasciato intenzionalmente com'è.

## Licenza

Nessuna licenza è stata ancora scelta per questo repository. I riferimenti a modelli e librerie di terze parti (openWakeWord, Piper, i modelli STL su Printables, ecc.) restano soggetti alle rispettive licenze originali, linkate nei documenti.
