# Sintesi della distinta rev. 3

> **Superata.** Vedi [Panoramica](../00-panoramica.md) per lo stato corrente e il [Piano attuale, rev. 5.1](../02-piano-attuale.md) per il piano in vigore (BOM ~68 €, tutto UE, HAT WM8960). Il documento completo di questa revisione è in [Distinta base rev. 3](rev3-hardware-bom.md).

Documento d'acquisto. Componenti 86,40 €, ~96 € con spedizioni. Ordine A Europa 41,90 € (Pi 3 A+, alim. 5V 2.5A, microSD 32GB A1). Ordine B AliExpress 44,50 €: display SPI 3.2" ILI9341 240x320 no touch; camera OV5647 5MP fuoco regolabile + cavo CSI; MAX98357A; speaker 40mm 4Ω 3W; INMP441; dissipatori; Dupont F-F + M2.5 + fascette; minuteria 8 € (cond. 1000µF 10V x2, LED bianchi 5mm x2 + R 220Ω x5, pulsanti 6x6x5 x4, R 10k x5, filo silicone AWG24 1m rosso+nero, guarnizione schiuma 2mm, viti M2.5x6 + termorestringente, cavo micro-USB angolato).

Regole: display solo ILI9341/ST7789 240x320 no touch; camera fuoco regolabile; no risparmio su alim/microSD. Pin: BL su GPIO12 (non 18), MISO non collegato, massa a stella, config.txt con googlevoicehat-soundcard + gpio-shutdown + watchdog + gpu_mem=16. Driver spidev diretto, no fbcp. PETG, 39mm stack, USB-A sul fianco.
