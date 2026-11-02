# Note informative — issue #15 (persone di casa nel prompt)

Cose utili da sapere, ma che non richiedono una decisione: a differenza di
`decisioni-issue-15.md`, qui non c'è niente in sospeso.

## Il file non viene mai deduplicato o validato oltre "è una stringa non vuota"

`carica_persone` scarta voci non-stringa o vuote (già coperto dai test), ma
non toglie duplicati né corregge maiuscole/minuscole incoerenti. A differenza
del diario (#14), che cresce nel tempo con voci proposte dal modello e per
questo ha un tetto (`MAX_VOCI`) e un confronto case-insensitive contro i
doppioni, `persone.json` è un file piccolo scritto a mano una volta per
deploy: un eventuale doppione è un errore di battitura da correggere a mano,
non un problema che vale la pena risolvere nel codice.

## L'esempio nel README usa nomi di fantasia, di proposito

`bmo-core/README.md` mostra `["Finn", "Jake"]` come esempio del file — i
personaggi di Adventure Time, non nomi reali di chi vive in casa. Il file
vero (`persone.json`) non va mai versionato né incollato in issue, PR o
commit: sta solo in `config.percorso_dati()`, fuori dal repository per
costruzione (nessuna riga di `.gitignore` in più necessaria, quella cartella
non è mai stata dentro il repo).

## Ordine dei nomi: quello del file, non alfabetico

`_riga_persone` unisce i nomi con `", "` nell'ordine in cui compaiono in
`persone.json`, senza ordinarli. Chi scrive il file decide l'ordine in cui
compaiono nel prompt (irrilevante per il comportamento del modello, ma
comodo da sapere se si vuole un ordine particolare per leggibilità propria
del file).
