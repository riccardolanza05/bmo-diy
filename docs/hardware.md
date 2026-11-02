# Hardware

Tutti i componenti di BMO, come si collegano e come va configurato il Raspberry Pi. Non servono saldature:
il HAT audio si innesta sull'header, il display si collega con cavetti Dupont e la fotocamera con il suo flat.

## Distinta base

| Componente | Modello | Negozio | Prezzo | A cosa serve |
|---|---|---|---|---|
| Computer | **Raspberry Pi 3 Model A+** (512 MB) | rivenditore ufficiale | — | Esegue BMO. Una sola porta USB-A, connettore CSI, header a 40 pin |
| Alimentatore | 5 V, 2,5 A, micro-USB | rivenditore ufficiale | — | Acceso 24/7, niente batterie |
| microSD | 32 GB, classe A1, di marca | qualsiasi | ~8 € | Sistema operativo e dati |
| Scheda audio | **Waveshare WM8960 Audio HAT** con altoparlante 8 Ω incluso | [BerryBase](https://www.berrybase.de/) | 20,50 € | Codec, due microfoni MEMS, amplificatore, pulsante |
| Display | **Waveshare 2.4" LCD Module**: ILI9341, 240×320, senza touch | [Welectron](https://www.welectron.com/Waveshare-18366-24inch-LCD-Module_1) (cod. 18366) | 12,90 € | La faccia |
| Fotocamera | **OV5647 5 MP** Groundmicro, messa a fuoco a pinza, flat CSI 15 pin 150 mm incluso | [Welectron](https://www.welectron.com/Groundmicro-OV5647-5-MP-Kameramodul-fuer-Raspberry-Pi) | 5,90 € | Lo strumento `scatta_foto` |
| Header | **Stacking header 2×20 extra-tall**, 17 mm | BerryBase | 1,60 € | Fa sporgere i pin sopra il HAT, per i fili del display |
| Dissipatori | Kit generico | Welectron | 1,30 € | Facoltativi: si montano solo se il collaudo nel guscio chiuso li richiede |
| Cablaggio | Dupont femmina-femmina, 20 cm | qualsiasi | ~3 € | I segnali del display |
| Viteria | Viti autofilettanti M2.5×6, ~20 pezzi | qualsiasi | ~2,50 € | Torrette del telaio stampato |
| Magneti | Neodimio 5×2 mm, ×20 | qualsiasi | ~6 € | Faceplate apribile senza viti a vista |
| Filamento | **PETG**, ~200 g | qualsiasi | ~5 € | Guscio e telaio, vedi [stampa 3D](stampa-3d.md) |

Totale oltre a Pi e alimentatore: **circa 68 €** con le spedizioni, filamento escluso.

Quando compri il display, controlla che nel titolo dell'inserzione ci siano **ILI9341**, **240×320** e **senza touch**.

## Collegamenti

Il HAT si innesta sul Pi attraverso lo stacking header. Occupa I2S (GPIO18-21), I2C (GPIO2 e 3) e il pulsante
(GPIO17). I fili del display vanno sui pin che sporgono **sopra** il HAT. Fai passare il flat della fotocamera
sotto o attraverso il HAT senza forzare il connettore.

| Segnale del display | Pin fisico | BCM | Note |
|---|---|---|---|
| CLK | 23 | GPIO11 | SPI0 |
| DIN (MOSI) | 19 | GPIO10 | SPI0 |
| CS | 24 | GPIO8 | CE0 |
| DC | 22 | GPIO25 | |
| RST | 13 | GPIO27 | |
| BL | **32** | **GPIO12** | **Non** usare il pin 12 |
| GND | un GND libero | — | |
| VCC | un 3,3 V libero | — | Vedi l'avviso qui sotto |
| MISO | — | — | Non collegare |

Il cablaggio di fabbrica di Waveshare mette il backlight sul pin **12**, cioè GPIO18, che con il HAT è il clock
audio. BMO lo pilota invece dal pin **32**, GPIO12. Con il filo sul pin 12 il display si accende, ma il clock
dell'audio resta caricato e la luminosità non si controlla.

**Alimentazione del display.** Guarda il modulo prima di dare tensione: se ha un regolatore a bordo vuole 5 V,
se non ce l'ha vuole 3,3 V e 5 V lo distruggono. Nel dubbio usa 3,3 V: al peggio non si accende.

Gli altri GPIO liberi sono 5, 6, 13, 16, 22, 23, 24 e 26. I pin del display si cambiano con le variabili `BMO_SPI_*`,
vedi [configurazione](configurazione.md#display).

## Fotocamera

Il modulo esce tarato all'infinito, mentre BMO fotografa a circa 30 cm. Va regolato una volta: sblocca la ghiera con
la pinzetta, ruotala fino a mettere a fuoco un bersaglio a 30 cm e fissala con una goccia di smalto. Non mettere
finestrelle trasparenti davanti alla lente.

Con `gpu_mem=16` libcamera e `rpicam` non vedono la fotocamera, quindi BMO la legge direttamente in V4L2 (Bayer
`pGAA` a 1296×972, sviluppato in software a 648×486) e regola da solo esposizione e guadagno.
`pi/abilita-hat.sh` imposta `BMO_CAMERA=grezza`. L'immagine va ruotata di 180° se il modulo è montato
capovolto, con `BMO_CAMERA_RUOTA=180`.

## Configurazione del Pi

Gli script di [installazione](installazione-pi.md) scrivono tutto da soli. Alla fine `/boot/firmware/config.txt`
contiene, nella sezione `[all]`:

```ini
dtparam=spi=on
dtparam=watchdog=on
gpu_mem=16
dtoverlay=disable-bt
dtoverlay=wm8960-soundcard
camera_auto_detect=1
#dtoverlay=vc4-kms-v3d
```

E `/boot/firmware/cmdline.txt`, sempre su una riga sola, contiene `cgroup_enable=memory`: senza, i limiti di memoria
dei servizi non hanno effetto.

Il jack analogico resta attivo come scheda 0 e il HAT è la scheda 1. Per questo BMO indirizza il microfono per nome,
`hw:CARD=wm8960soundcard,DEV=0`, e mai come `hw:0,0`.

## Mixer della WM8960

All'avvio il kernel lascia ingresso e uscita spenti. `bmo-hat-audio.service` imposta a ogni accensione questi valori,
gli stessi di `pi/abilita-hat.sh`:

| Controllo | Valore |
|---|---|
| `Left/Right Input Mixer Boost Switch` | on |
| `Left/Right Input Boost Mixer LINPUT1/RINPUT1 Volume` | 2 |
| `Capture` | 40 |
| `Left/Right Output Mixer PCM Playback Switch` | on |
| `Playback` | 255 |
| `Speaker` | 85% |
| `Speaker AC`, `Speaker DC` | 5 |

Se cambi uno di questi valori, cambialo in entrambi gli script.

## Alimentazione e spegnimento

BMO non ha un interruttore: si accende attaccando il cavo e riparte da solo, vedi
[avvio automatico](architettura.md#avvio-automatico). La porta USB-A resta libera per diagnostica o per un microfono
USB di riserva.

Con il HAT e il display collegati, tutta l'alimentazione passa dall'header. Un contatto debole sui 5 V si presenta
come un riavvio improvviso del Pi: se succede, ricontrolla che header e connettori siano ben inseriti.
