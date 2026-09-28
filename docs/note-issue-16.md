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

## Verifica dal vivo fatta in questa sessione

`pytest` non copre `deploy.sh`/`bmo-core-avvia.sh` (sono script di shell
per una macchina specifica, non codice Python importabile): la verifica
vera richiede il Pi acceso, non ancora fatta in questa sessione (era
spento). Prima di considerare la #16 chiusa per davvero: eseguire
l'installazione iniziale qui sopra sul Pi reale, poi `deploy.sh` due volte
di fila (la seconda deve essere un no-op pulito, "già aggiornato"), poi un
giro vero con chiamata Gemini vera per confermare che `bmo-core.service`
parla davvero con `bmo-face.service` sul socket condiviso.
