#!/usr/bin/env bash
# Abilita la Waveshare WM8960 Audio HAT sul Pi (issue #79). Da lanciare SUL PI, con sudo, una volta sola:
#
#   sudo ~/bmo-pi/bmo-diy/pi/abilita-hat.sh
#   sudo reboot
#
# Fa due cose, entrambe idempotenti (rilanciarlo non cambia niente):
#   1. aggiunge `dtoverlay=wm8960-soundcard` in fondo a /boot/firmware/config.txt, nella sezione [all]
#      (lascia stare gpu_mem, dtparam=audio e tutto il resto: sono decisioni a parte, vedi
#      docs/decisioni-issue-79.md);
#   2. fissa in /etc/bmo/env il microfono PER NOME, `BMO_AUDIO_DISPOSITIVO=hw:CARD=wm8960soundcard,DEV=0`:
#      con `dtparam=audio=on` il jack bcm2835 è la scheda 0 e il HAT diventa la 1, quindi il predefinito
#      `hw:0,0` di factory.py punterebbe al jack (che non ha cattura). Il nome non cambia con l'ordine.
# Non stampa mai il contenuto di /etc/bmo/env (contiene la chiave).
set -euo pipefail

CONFIG=/boot/firmware/config.txt
ENV_FILE=/etc/bmo/env
OVERLAY="dtoverlay=wm8960-soundcard"
DISPOSITIVO="BMO_AUDIO_DISPOSITIVO=hw:CARD=wm8960soundcard,DEV=0"

if [ "$(id -u)" -ne 0 ]; then
  echo "serve sudo: sudo $0" >&2
  exit 1
fi

echo "== overlay"
if grep -qx "$OVERLAY" "$CONFIG"; then
  echo "-- già presente in $CONFIG"
else
  ultima="$(grep -E '^\[.*\]$' "$CONFIG" | tail -1)"
  if [ "$ultima" != "[all]" ]; then
    # La riga finirebbe in una sezione condizionale (cm4, pi5…) e il Pi 3 la ignorerebbe in silenzio.
    echo "ERRORE: l'ultima sezione di $CONFIG è '$ultima', non [all]: non scrivo, sistemalo a mano." >&2
    exit 1
  fi
  cp -a "$CONFIG" "$CONFIG.prima-hat"
  printf '\n# bmo-diy #79 — Waveshare WM8960 Audio HAT\n%s\n' "$OVERLAY" >> "$CONFIG"
  echo "-- aggiunto (copia di sicurezza: $CONFIG.prima-hat)"
fi

echo "== dispositivo di cattura"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERRORE: $ENV_FILE non esiste (vedi pi/bmo-core-env.esempio)." >&2
  exit 1
fi
if grep -q '^BMO_AUDIO_DISPOSITIVO=' "$ENV_FILE"; then
  sed -i "s|^BMO_AUDIO_DISPOSITIVO=.*|$DISPOSITIVO|" "$ENV_FILE"
  echo "-- BMO_AUDIO_DISPOSITIVO aggiornato"
else
  printf '%s\n' "$DISPOSITIVO" >> "$ENV_FILE"
  echo "-- BMO_AUDIO_DISPOSITIVO aggiunto"
fi

echo "== fatto: ora 'sudo reboot'. Dopo il riavvio: cat /proc/asound/cards deve elencare wm8960soundcard."
