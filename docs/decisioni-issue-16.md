# Decisioni aperte — issue #16 (deploy a un comando)

Scelte fatte durante l'implementazione di [`pi/deploy.sh`](../pi/deploy.sh),
[`pi/bmo-core-avvia.sh`](../pi/bmo-core-avvia.sh) e
[`pi/systemd/bmo-core.service`](../pi/systemd/bmo-core.service). Le note
puramente informative stanno in [`note-issue-16.md`](note-issue-16.md).

## 1. Layout sul Pi: un solo clone, un solo venv

- **Implementato**: `~/bmo-pi/bmo-diy/` è un clone git dell'intero repo (sul
  branch di produzione, `master`), non due copie separate di `bmo-core` e
  `bmo-face` come nella misura di RAM della #58. `~/bmo-pi/venv/` è un solo
  venv condiviso: `deploy.sh` gli fa `pip install -e` di entrambi i
  pacchetti. La #63 (`bmo-face.service`) è stata corretta per usare questo
  stesso layout dopo essere stata scritta prima che questa decisione fosse
  presa.
- **Alternativa**: due venv separati (uno per pacchetto), più isolati ma il
  doppio delle dipendenze duplicate su una microSD già misurata stretta
  (piano spazio disco, §2.8).
- **Conseguenza**: `git pull` in `deploy.sh` aggiorna entrambi i pacchetti
  in un colpo solo, coerente con "un comando" del titolo dell'issue.

## 2. `pip install -e`, non `uv sync`

- **Implementato**: `deploy.sh` usa `pip install --upgrade -e` per
  aggiornare le dipendenze. Il testo dell'issue diceva `uv sync`, ma questo
  repo non usa `uv` da nessun'altra parte (nessun `uv.lock`, tutti i venv
  esistenti — anche quello del worktree demo — sono creati con
  `python -m venv` + `pip install -e`).
- **Perché**: adottare `uv` qui avrebbe voluto dire deciderne anche
  l'installazione sul Pi e la strategia di lock (quali extra, quanto
  pinning) — una decisione più grande di questa issue, non necessaria per
  avere un deploy a un comando funzionante.
- **Conseguenza**: se in futuro il progetto adotta `uv` per i venv di
  sviluppo, cambiare `deploy.sh` è una riga sola (`uv sync` al posto di
  `pip install -e`).

## 3. `bmo3.onnx` mancante: bmo-core non parte, non degrada a due modelli

- **Implementato**: [`pi/bmo-core-avvia.sh`](../pi/bmo-core-avvia.sh)
  controlla che `bmo3.onnx` esista **prima** di avviare Python e si ferma
  con un messaggio chiaro nel journal se manca. `deploy.sh` avvisa già
  prima del restart, ma non blocca il deploy: bmo-face può comunque
  aggiornarsi anche se bmo-core resta giù.
- **Alternativa**: far partire bmo-core solo con `bmo1`/`bmo2` se `bmo3`
  manca, silenziosamente.
- **Perché no**: la decisione del 28/9 è "tre modelli in produzione" — un
  BMO che riconosce il richiamo con soglie diverse da quelle previste senza
  che nessuno se ne accorga è peggio di un servizio fermo con un errore
  esplicito nel journal (`journalctl -u bmo-core.service`).

## 4. `GEMINI_API_KEY` via `/etc/bmo/env`, non nell'unit versionata

- **Implementato**: `bmo-core.service` ha `EnvironmentFile=/etc/bmo/env`
  (permessi 600, root:root — creato una volta a mano da
  [`pi/bmo-core-env.esempio`](../pi/bmo-core-env.esempio), mai committato
  con la chiave vera). systemd legge quel file come processo root, prima di
  abbassare i privilegi a `clanker_home`: resta leggibile dal servizio
  anche se `clanker_home` stesso non potrebbe aprirlo.
- **Conseguenza**: dopo il primo `deploy.sh`, se `/etc/bmo/env` non esiste
  ancora, `bmo-core.service` non parte (`EnvironmentFile=` senza `-` davanti
  fa fallire l'unit se il file manca — voluto, meglio bloccarsi subito che
  partire senza chiave). Il setup di quel file è un passo manuale, una
  tantum, descritto nel commento in cima all'unit.

## 5. Ceiling di `MemoryMax=`, non riserva

- **Implementato**: `bmo-core.service` → 280 MB, `bmo-face.service`
  (issue #63) → 80 MB. Il primo è calibrato sul caso peggiore misurato
  dalla #58 (~237 MB, bmo-core + entrambi gli `mpv` figli, che il cgroup
  conta insieme al genitore) con un margine del 18%.
- **Attenzione**: la somma (360 MB) supera i 331 MB "disponibili" misurati
  dopo l'irrobustimento (#25). Non è un errore: sono due tetti indipendenti
  pensati contro una singola perdita di memoria che scappa, non una
  riserva — l'uso reale combinato gira intorno ai 270 MB. Se la misura di
  24 h (#65) mostra i due servizi avvicinarsi entrambi al loro tetto nello
  stesso momento, è già un sintomo di OOM prima ancora di toccare questi
  numeri, e i tetti vanno rivisti insieme a quel punto.
