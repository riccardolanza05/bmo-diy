# Stampa 3D e assemblaggio

Questa è l'unica parte del progetto ancora da realizzare: l'elettronica è completa e funziona fuori dal guscio. Qui
trovi il metodo previsto; il telaio `bmo_chassis.scad` è ancora da scrivere e dimensioni e parametri vanno confermati
con i provini.

## La strategia: tre pezzi, zero CAD

| Pezzo | Cosa fa | Come si produce |
|---|---|---|
| Guscio | L'estetica di BMO | STL scaricato, con i fori sottratti nello slicer |
| Telaio interno | Porta Pi, HAT, display e altoparlante; si sfila dal retro | OpenSCAD parametrico: si cambiano numeri, non si disegna |
| Mascherina | Copre il bordo del display e definisce la finestra della faccia | Stesso file del telaio |

Il modello di partenza è
[Adventure Time BMO Figure (Interactive)](https://www.printables.com/model/1139445-adventure-time-bmo-figure-interactive).
Se non passa i controlli qui sotto, un'alternativa più semplice è il
[case BMO per Raspberry Pi](https://www.printables.com/model/468112-raspberry-pi-4-case-bmo-adventure-time).

## 1. Controlla il modello nello slicer

Dieci minuti, prima di stampare qualsiasi cosa.

| # | Controllo | Soglia |
|---|---|---|
| 1 | È un guscio o una figura piena di nervature e sedi? | Un unico vano libero |
| 2 | Profondità interna netta, tagliando il corpo a metà altezza | Almeno 50 mm; il guscio finito ne richiede 55 |
| 3 | Si riapre? | Viti o incastri, mai colla |
| 4 | La faccia è piana? | ±0,3 mm |
| 5 | Quanti triangoli? | Meno di 300.000 |

I 55 mm vengono da: parete 2,5 + display 5 + aria 3 + Pi 20 + HAT 11 + raggio dei cavi 6 + parete 2,5, più margine.

**Regola:** prima di stampare qualcosa che dura più di un'ora, stampa il provino della sola interfaccia. Finestra del
display, torrette del Pi e sede dell'altoparlante hanno ciascuna un provino da dieci minuti.

## 2. Ritaglia il guscio senza CAD

PrusaSlicer, Bambu Studio e OrcaSlicer sottraggono un solido dal modello: click destro, **Add negative volume → Box**.
Inserisci dimensioni e posizione a mano, così l'STL resta intatto e la modifica è reversibile.

| Foro | Misure |
|---|---|
| Finestra del display | 47,6 × 35,4 × 10 mm, passante |
| Tasca d'appoggio del display | ~72 × 45 × 3,4 mm (il PCB misura 70,5 × 43,3 mm) |
| Griglia dell'altoparlante | Fori esagonali Ø 3,2 mm, muri 1 mm, ~55% di superficie aperta |
| Microfoni | **Un solo foro** Ø 4 mm, allineato alle porte MEMS |
| Fotocamera | Foro Ø 8 mm, tasca 8 × 8 × 1 mm con la lente a filo, nessuna finestrella |
| Ventilazione | Almeno 300 mm² in basso e 300 mm² in alto, su pareti opposte, passanti |
| Magneti | 16-20 tasche per magneti 5 × 2 mm |

Note che contano:

- Per l'altoparlante servono fori grandi: quelli da 1 mm fischiano e attenuano gli acuti. Per il microfono vale il
  contrario: più fori peggiorano.
- Tieni microfoni e altoparlante il più lontano possibile e mai sulla stessa parete rigida. La vibrazione passa nel
  guscio e nessun software la toglie.
- USB-A e microSD devono affacciarsi su un fianco, con circa 45 mm liberi in linea per la USB.

## 3. Telaio

`bmo_chassis.scad` è il file OpenSCAD da scrivere, con una sezione di parametri in cima: si misurano i pezzi con il
calibro, si correggono i numeri e si esporta l'STL. Deve portare:

- 4 torrette per il Pi, interasse 58 × 49 mm, per viti autofilettanti M2.5;
- 4 torrette per il display;
- una camera di compressione per l'altoparlante, ~12 cm³ con sfiato e guarnizione di schiuma sul cestello: su una
  parete aperta un driver da 40 mm quasi non produce bassi;
- passaggi per i cavi con raggio minimo 6 mm.

Idee a costo zero da mantenere: faceplate a magneti, sportello posteriore modulare e arti a innesto per cambiare posa.

## 4. Parametri di stampa

| Parametro | Valore |
|---|---|
| Materiale | **PETG**. La Tg del PLA è ~60 °C e in una scatola chiusa d'estate si può raggiungere; il PETG regge ~80 °C |
| Altezza layer | 0,2 mm; 0,12 mm per la mascherina |
| Perimetri | 3 sul guscio, 4 sul telaio |
| Riempimento | 15% gyroid sul guscio, 25% sul telaio |
| Filamento totale | ~200 g |

**Ordine di stampa:** mascherina → provino della finestra → provino delle torrette → telaio → guscio. Il guscio va
per ultimo, quando ogni interfaccia è verificata.

## 5. Assemblaggio

1. Collega tutto **fuori dal guscio** e verifica che BMO funzioni.
2. Monta sul telaio l'altoparlante con la guarnizione: dopo non lo raggiungi più.
3. Monta il Pi con il HAT, poi per ultimo il display.
4. Riprova tutto a telaio nudo, fuori dal guscio.
5. Metti mascherina e telaio nel guscio, poi chiudi il retro.

## 6. Collaudo finale, a guscio chiuso

Il guscio cambia acustica e temperatura, quindi queste prove vanno ripetute a BMO chiuso.

| Prova | Criterio | Se non passa |
|---|---|---|
| Temperatura, 72 h di uso normale | Sotto i 65 °C | 65-75 °C: allarga le feritoie e monta i dissipatori. Oltre 75 °C: ventola da 25 mm, ma il suo rumore finisce nel microfono |
| Throttling | `vcgencmd get_throttled` sempre `0x0` | Controlla l'alimentatore |
| Stabilità | Nessun riavvio dei servizi, memoria stabile entro il 5% | Controlla i log |
| Volume | Almeno 78 dB a 1 m con rumore rosa all'80% | Secondo altoparlante, poi camera di compressione |
| Wake word | Almeno 9 richiami su 10 a 3 m con la TV accesa, meno di un falso positivo al giorno | Ricalibra con `pi/strumenti/calibra_wake_word.py` |

`pi/strumenti/misura_sistema_24h.py` registra temperatura, throttling e memoria per tutta la prova.
