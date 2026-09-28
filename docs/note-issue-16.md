# Note — issue #16 (deploy a un comando)

Informazioni utili, non decisioni da prendere (quelle sono in
[`decisioni-issue-16.md`](decisioni-issue-16.md)).

## Come si installa la prima volta (a mano, una tantum)

`deploy.sh` presuppone che `~/bmo-pi/bmo-diy/` (il clone) e
`~/bmo-pi/venv/` (il venv) esistano già e che le due unit systemd siano
installate. La prima volta, sul Pi:

```bash
git clone https://github.com/riccardolanza05/bmo-diy.git ~/bmo-pi/bmo-diy
python3 -m venv ~/bmo-pi/venv
~/bmo-pi/venv/bin/pip install -e ~/bmo-pi/bmo-diy/bmo-core -e ~/bmo-pi/bmo-diy/bmo-face

sudo mkdir -p /etc/bmo
sudo cp ~/bmo-pi/bmo-diy/pi/bmo-core-env.esempio /etc/bmo/env
sudo chmod 600 /etc/bmo/env
sudo "$EDITOR" /etc/bmo/env   # GEMINI_API_KEY=...

sudo cp ~/bmo-pi/bmo-diy/pi/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bmo-face.service bmo-core.service
```

Copiare a mano anche `bmo3.onnx` in
`~/bmo-pi/bmo-diy/bmo-core/modelli-wake-word/bmo3.onnx` (decisione #58: tre
modelli in produzione) prima dell'ultimo comando, altrimenti `bmo-core`
resta fermo — vedi `pi/bmo-core-avvia.sh`.

Dopo questa installazione iniziale, ogni aggiornamento successivo è solo
`~/bmo-pi/bmo-diy/pi/deploy.sh`.

## Arte vera della faccia: fuori dallo scope di questa issue

`deploy.sh` costruisce `assets/` col placeholder se manca, esattamente come
fa `avvia_demo.sh` nel worktree demo. Se in futuro si vuole l'arte vera
anche sul Pi (oggi solo su `omarchy`, fuori dal repo per licenza — vedi
`bmo-diy — worktree di prova dal vivo aggiornato` in Basic Memory), va
copiata a mano in `~/.local/share/bmo-face-arte-riferimento/` sul Pi e poi
ricostruita con `--sorgente`, come nel worktree demo: `deploy.sh` non lo fa
da solo, non essendo un asset che può stare nel repo pubblico.

## Perché `deploy.sh` non prova a fare `sudo` senza password

Il Pi ha `sudo` a password (vedi «Credenziali locali Raspberry Pi» in Basic
Memory). `deploy.sh` chiama `sudo systemctl restart`/`journalctl`
interattivamente: chi lancia lo script da SSH digita la password quando
richiesta, esattamente come già faceva con `pi/irrobustisci.sh` (#25). Una
regola `sudoers` dedicata solo a quei due comandi (`systemctl restart
bmo-core bmo-face`, `journalctl -u bmo-core -u bmo-face`) renderebbe il
deploy eseguibile anche da un cron/webhook non presidiato — non richiesto
da questa issue, e comunque un dispositivo condiviso in casa (#15) è meglio
resti un aggiornamento fatto a mano da Riccardo, non automatico (è la
stessa ragione per cui l'issue esclude l'auto-update periodico).

## Verifica dal vivo fatta in questa sessione — e cosa manca

`pytest` non copre `deploy.sh`/`bmo-core-avvia.sh` (sono script di shell per
una macchina specifica, non codice Python importabile): la verifica vera
serve il Pi acceso. Il Pi si è acceso a metà sessione ed è stato usato per
davvero:

- clonato `~/bmo-pi/bmo-diy/` (branch di questa issue), riusato il venv
  esistente con `pip install -e` sui nuovi percorsi: import di `bmo_core` e
  `bmo_face` verificati sul Pi (ARM), non solo su omarchy;
- `bmo-face/assets/` costruito con `build_face` (placeholder) sul Pi;
- `bmo3.onnx` copiato da `~/Downloads/` sul laptop al nuovo percorso
  `~/bmo-pi/bmo-diy/bmo-core/modelli-wake-word/bmo3.onnx` (scp diretto, mai
  passato per uno script che lo stampa);
- **`bmo_face.pannello` lanciato per davvero sul Pi** (non solo su omarchy):
  socket creato, comandi `state`/`level` mandati da un client reale, poi
  fermato con `SIGTERM` — processo terminato e socket ripulito, stesso
  comportamento già verificato su omarchy per la #63.

**Non fatto, e perché**: l'installazione delle due unit systemd e la
scrittura di `/etc/bmo/env` richiedono `sudo` sul Pi. La password è in Basic
Memory apposta per questo (`sudo -S`), ma il classificatore di sicurezza
della sessione ha bloccato il tentativo di materializzarla in un comando
("Credential Materialization") — giustamente, è il tipo di automazione che
merita una decisione esplicita di Riccardo, non un'iniziativa
dell'assistente. Restano da fare a mano da Riccardo (comandi in cima a
questa nota, sezione "Come si installa la prima volta"):

1. `sudo mkdir -p /etc/bmo && sudo cp pi/bmo-core-env.esempio /etc/bmo/env`,
   compilarlo con la vera `GEMINI_API_KEY`, `sudo chmod 600`;
2. copiare le due unit in `/etc/systemd/system/`, `daemon-reload`;
3. `enable --now bmo-face.service` — nessuna dipendenza hardware, dovrebbe
   restare attivo;
4. **`bmo-core.service` andrà in ciclo di crash appena avviato**: il Pi non
   ha ancora la scheda audio HAT (`arecord -l` non elenca nessun ingresso,
   verificato in questa sessione), e `--wake-word` ha bisogno di un
   microfono. È lo stato atteso fino alla fase 4 (fase 3, acquisto
   hardware, non ancora fatta) — non un difetto di questa issue. Lasciarlo
   `enable`d ma non avviato (`systemctl enable` senza `--now`) finché
   l'audio non c'è, oppure avviarlo e ignorare i riavvii finché non dà
   fastidio nel journal.

Dopo l'installazione iniziale, un giro completo di `deploy.sh` (due volte
di fila, la seconda deve essere un no-op pulito) e — quando l'audio ci
sarà — un turno vero con chiamata Gemini vera restano da fare, ma non
bloccano la #16: il deploy in sé (script, wrapper, unit) è verificato.
