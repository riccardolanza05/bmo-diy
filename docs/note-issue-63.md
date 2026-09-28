# Note — issue #63 (bmo-face senza schermo sul Pi)

Informazioni utili, non decisioni da prendere (quelle sono in
[`decisioni-issue-63.md`](decisioni-issue-63.md)).

## Cosa fa `bmo_face.pannello`

Punto d'ingresso alternativo a `finestra.py` (che resta il tool di sviluppo
su GTK, invariato). Avvia `ServitoreFaccia` (il socket Unix di sempre) e un
`Renderer`, poi gira un loop che a ogni tick:

1. legge lo stato corrente (`ServitoreFaccia.comando_snapshot()` — spostato
   qui da `finestra.py`, era una funzione privata duplicabile solo lì);
2. chiama `Renderer.disegna(comando, t)`;
3. manda il fotogramma a `UscitaPannello.disegna_frame()` **solo se è
   diverso dall'ultimo inviato** (confronto byte a byte del fotogramma
   intero, non ancora un dirty-rect per regioni — quello è compito
   dell'implementazione SPI quando arriverà, vedi `UscitaPannello` in
   `pannello.py`).

Verificato dal vivo (non solo test unitari): asset placeholder generati con
`build_face.costruisci`, `pannello.py --uscita nulla` lanciato in
background, comandi `state`/`level`/`timer` mandati sul socket Unix da un
client Python vero, poi fermato con lo stesso segnale (`SIGTERM`) che userà
systemd — il gestore del segnale ha chiuso il servitore e ripulito il file
del socket come previsto.

## Perché `UscitaPannello.disegna_frame` prende un fotogramma intero

L'issue chiede "i fotogrammi solo quando cambia qualcosa (blit sulle
regioni cambiate)". Le due cose sono separate qui apposta: il loop di
`pannello.py` decide **quando** ridisegnare (fotogramma intero diverso dal
precedente); **cosa** mandare fisicamente al bus SPI (l'intero fotogramma o
solo le regioni cambiate) resta una scelta interna della futura
`UscitaSpi`, che può tenersi il fotogramma precedente e calcolare da sola il
dirty-rect — l'interfaccia attuale non la esclude né la impone.

## Perché non serve una modalità "carta di prova" qui

`finestra.py --carta-prova` esiste per il criterio di leggibilità (b) della
#23: guardare tre righe a mezzo metro su uno schermo vero. Un pannello senza
schermo non ha niente da guardare, quindi `pannello.py` non la replica — il
criterio (b) resta verificato con `finestra.py` sul PC di sviluppo (o più
avanti, sul display SPI vero).
