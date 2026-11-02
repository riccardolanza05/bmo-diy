# Note informative sull'issue #64

Cose emerse lavorando che Riccardo deve sapere, ma che non sono decisioni
da prendere: non richiedono una scelta fra opzioni.

- **Il Pi oggi non ha nessun dispositivo di cattura audio.** `arecord -l`
  (verificato dal vivo il 28/9/2026) restituisce la lista vuota: la scheda
  `bcm2835 Headphones` è playback-only (jack di uscita), non microfono.
  Questo conferma quanto già scritto nel prompt di ripresa: il punto 2
  dell'issue non era testabile con un microfono vero neanche in parte, solo
  con dati sintetici, com'era già previsto.

- **`amixer scontrols` sul jack del Pi 3 A+ restituisce un solo controllo:
  `'PCM'`, non `'Master'`.** Confermato dal vivo (non solo dedotto
  dall'issue): `amixer sget 'PCM'` mostra `[78%]`, un volume regolabile
  vero. Questo era già il sospetto scritto nel testo dell'issue ("per il
  jack è probabilmente PCM"), qui verificato.

- **Il file `~/.asoundrc` di `docs/02-piano-attuale.md` §2.10 non è mai
  stato distribuito** da nessuno script di provisioning del repo (cercato
  in tutta la cartella `pi/`, non c'è). Se in futuro (fase 4, con il HAT
  montato) si decide di usarlo per gestire la condivisione del microfono fra
  più lettori (`dsnoop`) o per semplificare `crea_audio_input`, va scritto
  ex novo e distribuito da `pi/deploy.sh` o simile — non c'è nulla da
  "riattivare".

- **Suite di test**: ho potuto far girare l'intera suite di bmo-core sul Pi
  reale? No — il venv di produzione (`~/bmo-pi/venv`) non ha `pytest`
  installato (è un venv di runtime, non di sviluppo), e non l'ho installato
  per non toccare le dipendenze del servizio in produzione. Ho invece
  eseguito a mano, sul Pi reale, i pezzi di codice veri (rilevamento del
  controllo volume contro l'`amixer` reale, conversione di un tono
  sintetico attraverso `ArecordConvertitoreAdapter` vero, e
  `registra_fino_al_silenzio` con un flusso di silenzio finto) — tutti e tre
  passati. La suite pytest completa (372 test, incluso tutto quanto scritto
  per questa issue) è stata eseguita sul portatile omarchy, non sul Pi.

- **Cartella di prova temporanea**: ho clonato il branch `issue-64-adapter-audio-pi`
  in `~/prova-issue-64` sul Pi per la verifica dal vivo, poi l'ho rimossa
  (`rm -rf`) a fine prova. Non ha toccato `~/bmo-pi/bmo-diy` (il clone su
  master usato da `bmo-core.service`/`bmo-face.service`) né `~/bmo-pi/venv`.
