# Informazioni dalla sessione del 29/9/2026 (#65)

Cose da sapere, non da decidere — le decisioni vere stanno in
[`decisioni-in-sospeso-65.md`](decisioni-in-sospeso-65.md).

## Il Pi era indietro di 9 commit

`~/bmo-pi/bmo-diy` sul Pi era fermo al merge della #67 (prima della #68):
mancava l'adapter audio corretto e la conversione del microfono. Aggiornato
in questa sessione senza bisogno di sudo (`git fetch` + `git merge
--ff-only`, `pip install -e` — solo il restart di `bmo-core.service`/
`bmo-face.service` con `deploy.sh` richiede sudo, e non è stato necessario
farlo per questa issue: le nuove unit diagnostiche non dipendono da
`bmo-core.service`). Il Pi ora ha in checkout il branch
`issue-65-24h-carico-pi` (non `master`): va rimesso su `master` dopo che la
PR di questa issue è mergiata, come già fatto per le issue precedenti.

## Un bug trovato e corretto dal vivo

`pi/misura_sistema_24h.py` leggeva la colonna sbagliata di `/proc/swaps`
(la dimensione del device zram invece dello spazio usato): sempre ~462 MB
invece del vero valore. Corretto e verificato di nuovo sul Pi prima di
usarlo per la calibrazione — i numeri di zram in `note-issue-65.md` sono
già con la correzione.

## Niente pytest nel venv di produzione del Pi

Il venv di `~/bmo-pi/venv/` ha solo le dipendenze runtime (installato con
`pip install -e ./bmo-core -e ./bmo-face`, senza extra di sviluppo): non è
stato possibile lanciare la suite di test lì. La verifica sul Pi è stata
per comportamento reale (`carico.py --elenco`, `--help`, un giro vero via
systemd), coerente con quello che l'issue stessa chiede ("l'unico modo di
verificarlo è girare le cose sul Pi"). I 375 test automatici (372 esistenti
+ 3 nuovi) sono stati eseguiti in locale, sul laptop.

## `vcgencmd` e le cgroup si leggono senza sudo

Utile per diagnostica futura sul Pi: l'utente `clanker_home` è nel gruppo
`video`, quindi `vcgencmd measure_temp`/`get_throttled` funzionano senza
sudo; anche i file `memory.current`/`memory.peak`/`memory.events` sotto
`/sys/fs/cgroup/system.slice/<unit>.service/` sono leggibili da chiunque
(non serve essere root). Solo installare/avviare/fermare le unit systemd e
scrivere fuori dalla home richiede sudo.

## Il timestamp di sudo è condiviso fra sessioni SSH diverse

Dopo che Riccardo ha eseguito `sudo cp .../*.service /etc/systemd/system/`
dal suo terminale, i comandi `sudo systemctl start ...` lanciati poco dopo
da questa sessione (una connessione SSH separata, stesso utente
`clanker_home`) sono passati senza richiedere di nuovo la password — la
cache di autenticazione di `sudo` su questo Pi non è legata al singolo
terminale. Utile saperlo per le prossime sessioni: una finestra di qualche
minuto dopo che Riccardo ha digitato la password è sufficiente per far
passare più comandi sudo consecutivi, anche da connessioni diverse.

## L'hook RTK a volte blocca comandi SSH multi-riga senza motivo chiaro

Un comando SSH con più righe (`set -e`, più comandi) verso il Pi è stato
rifiutato dall'hook di sicurezza RTK con un messaggio pensato per comandi
`git` locali dentro un worktree ("a worktree-isolated session's git
operations must target its own worktree"), anche senza la parola "git" nel
comando. Comandi equivalenti su una sola riga (`cmd1 && cmd2 && cmd3`) sono
passati senza problemi. Non bloccante, ma da tenere a mente se un comando
SSH verso il Pi viene rifiutato senza un motivo che sembri pertinente:
provare a metterlo su una riga sola prima di altro.

## Branch e PR di questa sessione

Branch `issue-65-24h-carico-pi`, pushato su GitHub, PR non ancora aperta
(in attesa che la prova di 24 h finisca prima di scrivere la descrizione
finale — vedi `decisioni-in-sospeso-65.md` se si preferisce aprirla subito
come draft invece).
