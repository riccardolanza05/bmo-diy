# Decisioni da prendere — issue #77 (prova ibrida)

Per ogni voce: le opzioni, cosa è implementato di default e la conseguenza concreta
di scegliere l'una o l'altra. Numeri e metodo in [`note-issue-77.md`](note-issue-77.md).
Il codice che gira sul Pi non è stato ristrutturato (vincolo tuo): sono aggiunte.

## 1. `gpu_mem=16` e la camera

**Opzioni:**
- (a) Tenere `gpu_mem=16` e usare la **cattura grezza** V4L2 con sviluppo in Python.
- (b) Alzare `gpu_mem` (per esempio a 64) e usare `rpicam`/libcamera, con ISP e auto-esposizione.

**Implementato: (a)**, opt-in con `BMO_CAMERA=grezza`; `LibcameraAdapter` resta il predefinito del Pi.

**Conseguenze:**
- (a): nessuna RAM in più; scatto in 1,4-1,8 s; immagine a 648×486 con bilanciamento del bianco e
  curva semplici (qualità inferiore a quella dell'ISP, ma sufficiente per Gemini e per lo schermo).
  Costa codice da mantenere (`CameraGrezzaV4L2`) e non c'è auto-esposizione vera.
- (b): ~48 MB di RAM in meno per il sistema (oggi 462 MB totali, ~280 MB disponibili a riposo; nella
  prova a voce `MemAvailable` è scesa a 110 MB), in cambio di una camera «normale». **Non è verificato
  che alzare `gpu_mem` basti** a far vedere la camera a libcamera: è la causa più probabile, non l'ho provato.

## 2. Pin del display: quelli del piano o quelli di fabbrica

**Opzioni:** (a) DC=GPIO25, RST=GPIO27 (pin di fabbrica, come è cablato adesso); (b) DC=GPIO23,
RST=GPIO24, come scritto nel piano originale.

**Implementato: (a)**, piano aggiornato (§1.4) e valori predefiniti di `bmo_face.spi`; il backlight è
su GPIO12 (pin 32) in tutti e due i casi.

**Conseguenza:** (a) non richiede di toccare i fili e, secondo il wiki Waveshare, 25 e 27 sono liberi
anche con il HAT (che usa solo GPIO2/3, 17 e 18-21). (b) obbliga a spostare due fili senza nessun
vantaggio. Resta da **confermare con il HAT montato**.

## 3. Camera a testa in giù

**Opzioni:** (a) ruotare l'immagine di 180° via software (`BMO_CAMERA_RUOTA=180`); (b) cambiare
il montaggio fisico, o impostare `vertical_flip` + `horizontal_flip` nel sensore; (c) lasciare
com'è.

**Implementato: (a) solo nel launcher della prova** (il predefinito dell'adapter è 0): non decido io
come sarà montata la camera nel guscio. **Conseguenza:** con (a) la rotazione costa pochi ms in
Python; con (b) non costa nulla ma va deciso insieme alla meccanica (fase 5). Senza nessuna delle
due, Gemini e lo schermo ricevono foto capovolte.

## 4. Come arriva la chiave Gemini al Pi nella prova

**Opzioni:** (a) dal PC, dentro SSH (stdin), in un file `600` sulla tmpfs del Pi cancellato all'uscita;
(b) niente chiave dal PC: lanciare la prova da un'unit systemd, con `sudo` e la chiave già in
`/etc/bmo/env`.

**Implementato: (a).** **Conseguenza:** (a) funziona senza password sudo e senza toccare i servizi di
produzione, ma la chiave passa (cifrata) dal PC al Pi e resta per qualche minuto in memoria e in un
file riservato; (b) non sposta la chiave ma richiede la tua password sudo a ogni prova.

## 5. La prova gira su una copia, non sul clone di produzione

**Opzioni:** (a) copia in `~/bmo-test/albero` con i dati in `~/bmo-test/dati`, e il venv di produzione
usato solo come interprete; (b) `deploy.sh` sul clone di produzione.

**Implementato: (a).** **Conseguenza:** (a) non tocca `~/bmo-pi/bmo-diy`, né i servizi, né i timer veri,
e si cancella senza lasciare tracce; (b) proverebbe il percorso di produzione vero (unit systemd,
`MemoryMax=280M`) ma richiede `sudo`, e `bmo-core` senza microfono andrebbe in ciclo di crash.

## 6. Velocità dell'SPI

**Opzioni:** (a) 20 MHz di predefinito (`BMO_SPI_HZ`), (b) 16 MHz, usati nei test a mano, o meno.

**Implementato: (a).** **Conseguenza:** a 20 MHz una schermata intera (150 kB) costa ~60 ms, e si
scrive solo la parte che cambia; più veloce con i jumper volanti può dare pixel sbagliati. Se vedi
rumore sullo schermo, abbassala con `BMO_SPI_HZ=10000000`.

## 7. `pillow` tra le dipendenze di `bmo-core`

**Implementato:** aggiunta in `pyproject.toml` (serve al JPEG della camera grezza); sul Pi c'è già
perché il venv è condiviso con `bmo-face`. **Conseguenza:** sul PC di sviluppo va reinstallata la
dipendenza (`pip install -e ./bmo-core`); nessun peso nuovo sul Pi.
