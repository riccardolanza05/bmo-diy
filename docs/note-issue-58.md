# Note — issue #58 (RAM sul Pi)

Misure del 27/9/2026. L'analisi e gli spunti stanno nel testo della issue
#58; qui ci sono i numeri grezzi e come ripeterli.

## Come sono state prese

- **Pi**: Raspberry Pi 3 A+, Raspberry Pi OS trixie, dopo l'irrobustimento
  della #25 (331 MB disponibili a riposo). Python 3.13.5, dipendenze di
  bmo-core installate con `pip` in un venv (`numpy 2.5.3`, `onnxruntime
  1.30.0`, `openwakeword 0.4.0`, `google-genai 2.25.0`), bmo-core e bmo-face
  copiati dal master del 27/9.
- **Script**: [`pi/peso_bmo_core.py`](../pi/peso_bmo_core.py) e
  [`pi/peso_bmo_face.py`](../pi/peso_bmo_face.py), che leggono RSS e PSS
  del proprio processo dopo ogni tappa. Nessuna chiamata di rete: il client
  Gemini viene solo costruito, con una chiave finta.
- **PC** (omarchy, x86_64, Python 3.14): [`bmo_core.misura_ram`](../bmo-core/src/bmo_core/misura_ram.py)
  su `python -m bmo_core.macchina --wake-word` vero, microfono aperto.

## bmo-core sul Pi, com'è oggi

| tappa | RSS | Δ | PSS | tempo |
|---|---|---|---|---|
| Python nudo | 10 | | 8 | |
| numpy + onnxruntime | 44 | +34 | 41 | 0,8 s |
| `import openwakeword` | 136 | **+92** | 130 | 7,1 s |
| `import google.genai` | 170 | +34 | 164 | 4,2 s |
| `bmo_core.macchina` (edge_tts, ddgs, …) | 173 | +3 | 167 | 0,3 s |
| 3 modelli wake word caricati | 248 | **+75** | 242 | 3,8 s |
| 50 finestre di ascolto (4 s di audio) | 249 | +1 | 243 | 1,7 s |
| `Cervello` costruito | 251 | +2 | 245 | 0,4 s |
| altre 250 finestre (20 s di audio) | 254 | +3 | **248** | 9,5 s |

## bmo-core sul Pi, alleggerito (`--leggero`)

| tappa | RSS | Δ | PSS |
|---|---|---|---|
| numpy + onnxruntime | 44 | +34 | 41 |
| `import openwakeword` senza verificatore | 46 | **+2** | 44 |
| `import google.genai` | 89 | +43 | 83 |
| 3 modelli caricati, ONNX senza arena | 108 | **+18** | 102 |
| dopo 24 s di ascolto e `Cervello` | 114 | | **108** |
| — con 1 modello invece di 3 | 112 | | 106 |

I punteggi della wake word sulla stessa finestra audio sono identici con e
senza alleggerimento (verificato sul PC: `bmo1` 0,000709, `bmo2` 0,000853,
`bmo3` 0,000732 in entrambi i casi).

## bmo-face sul Pi (senza GTK)

| tappa | RSS | PSS |
|---|---|---|
| Python nudo | 10 | 8 |
| numpy + PIL + animazione + socket | 36 | 31 |
| asset mappati (`faces.bin`, 2,3 MB, `mmap`) | 36 | 31 |
| dopo 100 fotogrammi | 39 | **33** |

Manca l'uscita SPI (`spidev`/`luma.lcd`, fase 4.7), che aggiungerà qualche MB.

## Sul PC

`bmo_core.macchina --wake-word` con tre modelli, a riposo per 40 s:
**bmo-core 276 MB PSS**, arecord 3 MB. Con un modello solo: ~279 MB RSS,
quasi uguale: il costo non sta nei modelli dei classificatori ma in
openwakeword + le arene ONNX. I numeri del PC sono più alti di quelli del
Pi (Python 3.14 contro 3.13, x86_64 contro aarch64, librerie diverse): per
il budget valgono **le misure sul Pi**, il PC serve per confrontare prima e
dopo una modifica.

## CPU della wake word

Sul Pi, 250 finestre da 80 ms (20 s di audio) richiedono ~9,5 s di calcolo,
con 1 o con 3 modelli: ~47% di un core, sempre, finché BMO ascolta.

## Alpine e onnxruntime

Verificato il 27/9: su PyPI `onnxruntime 1.30.0` pubblica 6 ruote
`manylinux` per aarch64 e **nessuna** `musllinux`, mentre numpy e scipy le
hanno. Su Alpine il pacchetto `py3-onnxruntime` esiste **solo nel ramo
`edge`** (community, aarch64), in nessuna versione stabile.
