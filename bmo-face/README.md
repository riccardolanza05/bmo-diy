# bmo-face

La faccia di BMO (issue #23, piano §2.11 e §2.2): pipeline asset, motore di
animazione, server del socket Unix e finestra a schermo sul PC di sviluppo.
Gira come processo a sé rispetto a `bmo-core` — stesso isolamento dei guasti
del piano: se `bmo-core` va in eccezione, la faccia continua a sbattere le
palpebre.

## Pacchetto

```bash
cd bmo-face
python3 -m venv --system-site-packages .venv   # --system-site-packages: serve a GTK4 (vedi sotto)
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

`--system-site-packages` è necessario solo per la finestra a schermo: GTK4 e
PyGObject sono pacchetti di sistema (Arch: `python-gobject`, `gtk4`; Debian/
Raspberry Pi OS: `python3-gi`, `gir1.2-gtk-4.0`), non ruote pip affidabili.
Pipeline, motore di animazione e socket non hanno bisogno di GTK e girano
anche senza: il Pi non aprirà mai una finestra.

## 1. Generare gli asset

```bash
python -m bmo_face.build_face --destinazione assets/
```

Genera `assets/faces.bin` (fotogrammi RGB565 grezzi) e `assets/faces.json`
(il manifesto) dall'arte placeholder di `arte_placeholder.py` — geometrica,
disegnata a codice, **mai** un disegno vero di Adventure Time: quello resta
fuori dal repository pubblico, come già per l'audio di terzi (`suoni.py` di
bmo-core). `faces.bin` è un artefatto di build: non va committato, si
rigenera da qui.

Parametrico su risoluzione (`--larghezza`/`--altezza`, predefinito 320×240):
nessun pannello è ancora deciso (bmo-diy#1), e il formato deve reggere anche
un pannello più piccolo di quanto pianificato oggi — la pipeline è stata
provata fino a 16×16 senza rompersi. A 320×240 pesa circa 2 MB, in linea col
budget del piano (§2.11); un pannello più piccolo pesa proporzionalmente meno.

## 2. La finestra

```bash
python -m bmo_face.finestra --assets assets/                    # dimensione fisica, preset 2.4"
python -m bmo_face.finestra --assets assets/ --carta-prova       # criterio (b): tre righe da 20 caratteri
python -m bmo_face.finestra --assets assets/ --pixel             # 1 px pannello = 1 px schermo
python -m bmo_face.finestra --assets assets/ --pannello 3.5      # l'altro preset del BOM
```

**`--carta-prova`** è il comando che risponde davvero al criterio (b): mostra
tre righe da 20 caratteri (non la faccia) alla dimensione fisica del
pannello, quantizzate come `faces.bin` (RGB565), e ne salva anche una copia
in `assets/carta_prova.png` per un controllo rapido senza aprire la finestra.
Il "caso peggiore" della #23 è **il 2.4" stesso** (non c'è ancora un
pannello più piccolo nel BOM, §1.3): è quello il pannello da giudicare.

Apre un socket Unix (predefinito: `$XDG_RUNTIME_DIR/bmo.sock` sul PC,
`/run/bmo.sock` sul Pi, `BMO_SOCKET` sempre prioritario — stesso schema di
`percorso_dati()` in bmo-core) e ridisegna a 25 fps quel che riceve.

**Dimensione fisica** (predefinita, criterio (b) dell'issue #23): la finestra
occupa sullo schermo lo stesso ingombro in millimetri del pannello vero,
calcolato da `hyprctl monitors -j` (il pitch reale dello schermo di sviluppo).
Su un laptop con pitch più grosso di quello del pannello target (il caso di
questo portatile: ~0,177 mm/px contro lo 0,153 mm/px del 2.4"), la finestra
stampa un avviso e mostra l'immagine sottocampionata — **la prova risulta
quindi più severa del display reale, mai più ottimista**: se è leggibile così,
lo è a maggior ragione sul pannello vero. `--pitch-mm X Y` sostituisce
`hyprctl` a mano su una macchina diversa da questo laptop, o senza Hyprland.

**Modalità pixel** (`--pixel`): ignora le dimensioni fisiche, mostra ogni
pixel del pannello come un pixel reale dello schermo. Utile per giudicare
l'arte e le animazioni senza la densità dello schermo di sviluppo in mezzo.

## 3. Collegare bmo-core

```bash
BMO_FACCIA=socket python -m bmo_core.brain --testo "Metti un timer di dieci minuti"
```

`BMO_FACCIA=socket` fa scegliere a `crea_faccia()` (bmo-core) `FacciaSocket`,
il client vero del socket verso questa finestra, al posto delle
implementazioni provvisorie mute/da terminale. È un opt-in esplicito, non il
predefinito: senza una finestra già avviata ad ascoltare, `FacciaSocket`
scriverebbe a vuoto in silenzio (fallisce sempre in silenzio di proposito,
mai un turno di conversazione rotto perché la faccia non c'è).

Con `--voce-tts` (macchina.py, #42) la bocca durante `parlato` segue
l'inviluppo RMS vero della voce sintetizzata (`bmo_core.inviluppo`), calcolato
in un thread a parte per non aggiungere latenza percepita alla risposta.

## Struttura del pacchetto

| Modulo | Cosa fa |
|---|---|
| `formato.py` | Il formato di `faces.bin`/`faces.json`: RGB565, manifesto, `mmap` in lettura |
| `arte_placeholder.py` | L'arte geometrica placeholder, parametrica su risoluzione |
| `build_face.py` | La pipeline: arte → `faces.bin` + `faces.json` |
| `animazione.py` | `Renderer`: funzione pura del tempo e dei comandi → fotogramma |
| `protocollo.py` | I cinque messaggi del socket (§2.2): analisi e applicazione |
| `servitore.py` | Il server del socket Unix, un thread per connessione |
| `dimensione_fisica.py` | Il calcolo mm↔px per la finestra a dimensione fisica |
| `finestra.py` | La finestra GTK4 che lega tutto insieme |

## Cosa manca ancora

- **Arte vera**: al posto del placeholder geometrico, quando qualcuno la
  disegnerà. `build_face.py` è già pensato per un `--sorgente cartella/` che
  prenda il posto di `genera_placeholder()` senza toccare il resto.
- **Il criterio di leggibilità (b)**: tre righe da 20 caratteri leggibili a
  mezzo metro è un giudizio di chi guarda lo schermo, non del codice — vedi
  `docs/decisioni-issue-23.md` nel repository principale.
- **Il porting sul Pi**: oggi il renderer disegna in una finestra GTK4; sul
  Pi (§2.11) lo stesso `Renderer`/`ComandoFaccia` dovrà scrivere su SPI con
  `luma.lcd` invece che su una `Gtk.Picture`, e usare `regione` per il blit a
  dirty-rect invece di ridisegnare sempre il fotogramma intero.
