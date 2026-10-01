#!/usr/bin/env bash
# Installa /etc/asound.conf (dmix + volume software «Video») per far suonare insieme la voce di BMO e i video.
#
#   ~/bmo-pi/bmo-diy/pi/installa-audio.sh            # usa la scheda trovata da sé
#   ~/bmo-pi/bmo-diy/pi/installa-audio.sh --scheda wm8960soundcard
#
# Serve `sudo` (scrive in /etc). Lo lancia anche `pi/deploy.sh`, ma da solo non fa nulla finché non c'è la
# WM8960: sul Pi 3 A+ senza l'HAT la scheda analogica ha 8 sottodispositivi (voce e video suonano insieme
# già così) e il suo driver non supporta l'accesso mmap che `dmix` richiede (provato: «unable to open slave»).
# Il modello è pi/asound.conf.modello; il perché è scritto lì dentro.
set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELLO="$RADICE/pi/asound.conf.modello"
DESTINAZIONE=/etc/asound.conf
SCHEDA=""
if [ "${1:-}" = "--scheda" ]; then SCHEDA="${2:?manca l id della scheda}"; fi

if [ -z "$SCHEDA" ]; then
  # Id della scheda da `aplay -l` («card 1: wm8960soundcard [wm8960-soundcard], ...»).
  if aplay -l 2>/dev/null | grep -q "wm8960soundcard"; then
    SCHEDA=wm8960soundcard
  else
    echo "== audio: nessuna scheda WM8960 trovata (aplay -l): /etc/asound.conf non serve ancora."
    echo "   Con la scheda analogica del Pi voce e video suonano insieme senza mixer."
    echo "   Dopo aver montato l'HAT: ~/bmo-pi/bmo-diy/pi/installa-audio.sh"
    exit 0
  fi
fi

echo "== audio: scheda $SCHEDA -> $DESTINAZIONE"
TEMPORANEO="$(mktemp)"
trap 'rm -f "$TEMPORANEO"' EXIT
sed "s/@SCHEDA@/$SCHEDA/g" "$MODELLO" > "$TEMPORANEO"
if [ -f "$DESTINAZIONE" ] && cmp -s "$TEMPORANEO" "$DESTINAZIONE"; then
  echo "   già aggiornato"
  exit 0
fi
if [ -f "$DESTINAZIONE" ]; then
  sudo cp "$DESTINAZIONE" "$DESTINAZIONE.bak-bmo"
  echo "   copia del file precedente in $DESTINAZIONE.bak-bmo"
fi
sudo install -m 0644 "$TEMPORANEO" "$DESTINAZIONE"

echo "== audio: prova dmix (due flussi insieme per 2 secondi)"
PROVA="$(mktemp --suffix=.wav)"
trap 'rm -f "$TEMPORANEO" "$PROVA"' EXIT
ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=440:duration=2" -ar 48000 "$PROVA"
aplay -q -D default "$PROVA" &
sleep 0.5
if aplay -q -D video_out "$PROVA"; then
  wait
  echo "   ok: voce (default) e video (video_out) suonano insieme; controllo volume: amixer sget Video"
else
  echo "   ATTENZIONE: i due flussi insieme non funzionano. Rimetti il file precedente:" >&2
  echo "   sudo mv $DESTINAZIONE.bak-bmo $DESTINAZIONE  (oppure sudo rm $DESTINAZIONE)" >&2
  exit 1
fi
