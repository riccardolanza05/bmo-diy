# Informazioni — issue #77 (cose da sapere, non da decidere)

Dettagli in [`note-issue-77.md`](note-issue-77.md).

## Cosa NON ho potuto verificare

- **Cosa mostra il display.** Da qui non lo vedo: i giri con `--uscita spi` finiscono senza errori, ma
  orientamento, colori e fluidità li può confermare solo chi guarda lo schermo. Il parametro da
  toccare se non vanno è `BMO_SPI_MADCTL` (predefinito `0x28`).
- **Che gli altoparlanti del PC suonino.** Ho visto sul PC il flusso `mpv` del Pi e i comandi finire
  senza errori, ma non lo sento.
- **Video di YouTube, radio e volume** attraverso la rete: non provati (il video passa da `ffmpeg`
  con `-f pulse`, che il Pi supporta; la radio da `mpv`, come i suoni). Il comando «alza il volume»
  agisce sull'ALSA **del Pi**, non sul PC: è atteso, non un difetto.
- **Il HAT audio e il suo microfono.** Nella prova il microfono è quello del PC, in S32 stereo 48 kHz
  per imitare il HAT: la conversione la fa il Pi come farà con la scheda vera, ma non è la scheda.
- **La velocità vera dell'SPI** (fotogrammi al secondo) e il comportamento a lungo termine.

## Cose da sapere

- **Le misure sono un po' pessimistiche per la CPU e fedeli per la RAM:** l'audio arriva in rete a
  384 kB/s e il Pi lo converte a 16 kHz mono (come con il HAT), in più c'è il tunnel SSH.
- **`bmo-face.service` di produzione resta acceso** (~19-20 MB, letti da `misura_sistema_24h.py`).
  Non interferisce: la prova usa un socket e una cartella dati propri (`/run/user/1000/bmo-test/`,
  `~/bmo-test/dati`) e la produzione non usa l'SPI. Le somme di PSS della prova **non** includono
  quel servizio.
- **Sul PC restano solo:** il tunnel SSH, `socat` e un `parec` per ogni connessione del microfono, e
  il modulo TCP di PulseAudio aperto su `127.0.0.1` senza autenticazione **solo durante la prova**
  (viene scaricato all'uscita; se lo trovi già caricato, il launcher non lo tocca).
- **Il launcher non stampa mai la chiave:** la legge da `~/.bashrc`, la manda dentro SSH e la cancella
  dal Pi all'uscita. Se la prova si interrompe in modo brusco (rete caduta, terminale chiuso), il
  file `/run/user/1000/bmo-test.env` può restare sulla tmpfs del Pi (si svuota al riavvio): cancellalo
  a mano.
- **Se la faccia sul display è sbagliata:** il launcher usa sempre l'arte vera del riferimento esterno
  (la costruisce da `~/.local/share/bmo-face-arte-riferimento` se `bmo-face/assets` manca) e stampa
  l'impronta di `faces.bin`; non ripiega mai sul placeholder né sugli asset di produzione. Il
  primo giro dell'issue usava per errore gli asset di produzione: corretto, e l'impronta `aa9f95d1`
  è quella dell'arte vera.
- **Se una prova si blocca**, `pkill -f bmo_face.pannello` sul Pi libera il display; la porta 4713 o
  5001 «già occupata» di solito è un tunnel di una prova precedente.
- **Il giro del 4/10** ha lasciato sul Pi `~/bmo-test/` (codice, dati, misure): si può cancellare.
