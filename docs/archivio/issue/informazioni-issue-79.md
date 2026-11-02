# Informazioni — issue #79 (WM8960 Audio HAT)

Cose solo informative: niente da decidere. Numeri in [`note-issue-79.md`](note-issue-79.md).

- **Il HAT funziona**: codec riconosciuto (card 1 `wm8960soundcard`, I2C `0x1a`), due microfoni MEMS
  vivi e bilanciati, altoparlante 8 Ω udito, pulsante GPIO17 attivo-basso.
- **Le tre trappole del kernel**: ingresso e uscita del mixer sono spenti all'avvio; la cattura è a
  +30 dB (satura la voce); il volume iniziale dell'altoparlante è troppo basso per sentire qualcosa.
  `abilita-hat.sh` li imposta e li salva. Dopo un riavvio senza `alsactl store` tornano ai valori
  del kernel.
- **dmix e il formato**: il driver I2S del Pi condivide formato fra riproduzione e cattura. Il mixer
  software va tenuto in S32_LE come il microfono, altrimenti dopo la voce di BMO il microfono non
  si riapre.
- **`edge-tts` è un client non ufficiale**: il 14/10 la 7.2.8 prendeva 403 su tutto Internet; la
  7.3.1 funziona. Se riammutolisce, controllare prima `pip index versions edge-tts`.
- **`lgpio` su PyPI è inutilizzabile sul Pi** (ruota `0.0.0.2`): si usa quello di apt.
- **Un riavvio improvviso del Pi** è comparso un paio di volte all'inizio della sessione (uptime
  0-3 min fra una lettura e l'altra) mentre si maneggiava l'header; con `throttled=0x0`. Non si è
  ripetuto. Con il HAT in testa e il display collegato, l'alimentazione passa tutta dall'header: un
  contatto debole sul 5 V si vedrebbe così.
- **`/etc/bmo/env`** ora contiene, oltre alla chiave, `BMO_AUDIO_DISPOSITIVO`, `BMO_PULSANTE_PIN`,
  `BMO_CAMERA`, `BMO_CAMERA_RUOTA` (nomi e valori non segreti).
- **«Buonanotte» nel journal** è la stampa all'uscita di `macchina`: alle 21:57:57 il servizio è uscito
  da solo e systemd l'ha riavviato dopo 4 s (`Restart=always`). **Causa probabile, non provata:** il
  flusso del microfono della wake word è caduto per lo stesso difetto del formato (dmix in S16_LE
  tiene la scheda mentre `arecord` chiede S32_LE), il richiamo ha restituito «finito» e `macchina`
  è uscita. Con dmix in S32_LE non si è più ripetuto in otto turni.
- **edge-tts e Gemini TTS**: il motore predefinito è `edge`; i modelli TTS di Gemini preview
  chiudono il 17/11/2026 (vedi #80).
