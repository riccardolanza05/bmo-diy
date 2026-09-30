# Informazioni — video di YouTube (cose da sapere, non da decidere)

- **Nessuna dipendenza da computer accesi.** Ricerca, risoluzione e decodifica girano sul Pi. Le API
  pubbliche provate (Piped, Invidious) non reggono (0 su 10 video); la YouTube Data API ufficiale farebbe
  solo la ricerca (~100 al giorno, con chiave) e i suoi termini vietano di estrarre lo stream: non serve.
- **Il primo test «9 su 9» era falso**: contava gli indirizzi restituiti, ma quelli dei client leggeri
  davano 403 a ffmpeg. Vale solo il test in cui ffmpeg decodifica davvero (`pi/peso_video_pi.py`,
  `pi/prova_video_e2e.py`).
- **Il Pi di produzione non è stato aggiornato.** Sul Pi ho installato `yt-dlp` nel venv `~/bmo-pi/venv`
  (è anche una dipendenza di `bmo-core`, quindi `deploy.sh` lo installa) e ho usato copie temporanee in
  `/tmp` (poi cancellate). Dopo il merge: `~/bmo-pi/bmo-diy/pi/deploy.sh` (ha bisogno di `sudo`).
- **Pulizia fatta**: sul Pi `~/bin/node`, `qjs`, il `yt-dlp` zipapp, `~/bmo-pi/yt-venv` e i cookie esportati
  (anonimi) sono stati rimossi; i cookie sono stati cancellati anche dal laptop.
- **Quota di Gemini**: la validazione del prompt ha fatto comparire «quota esaurita su tutti i modelli»
  una volta (è ripartita da sola dopo 30 s). Le prossime corse di `prova_frasi` (il banco storico intero
  è ~48 frasi) conviene farle distanziate.
- **L'invariante «Di' di aver fatto un'azione solo se stato ok»**: con l'avvio in background
  `riproduci_video` risponde `ok` *prima* che il video suoni (porta `"nota": "sta partendo"`); se poi
  non parte nessun risultato lo segnala il suono di errore. Nel prompt c'è «non dire metto il video se
  riproduci_video non ha risposto ok» e lo STATO dice «Video: sta partendo…» finché non suona.
- **`prova_frasi`**: il banco storico resta di 48 frasi; `video` è una categoria a parte
  (`--categoria video`, 22 frasi, 21/21 alla prima corsa). Le due frasi storiche di musica che ora vanno a
  YouTube (Bohemian Rhapsody, Gangnam Style) sono state spostate lì.
