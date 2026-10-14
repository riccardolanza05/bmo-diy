#!/usr/bin/env bash
# All'avvio del Pi (issue #83): aspetta la scheda del HAT WM8960 e imposta il mixer, PRIMA di bmo-core.
# Lo lancia `bmo-hat-audio.service` (oneshot, utente clanker_home), non va lanciato a mano.
#
# Perché serve oltre ad `alsactl store`: lo stato salvato viene ripristinato da `alsa-restore.service`,
# ma bmo-core può partire prima che la scheda sia pronta, e un riavvio improvviso (corrente staccata)
# non passa dallo spegnimento pulito che salva lo stato. Qui i valori sono quelli misurati il 14/10/2026
# (stessi di `pi/abilita-hat.sh`; se si cambia uno, va cambiato anche l'altro).
set -uo pipefail

SCHEDA=wm8960soundcard
ATTESA_S="${BMO_ATTESA_SCHEDA_S:-60}"

for _ in $(seq 1 "$ATTESA_S"); do
  if grep -q "$SCHEDA" /proc/asound/cards 2>/dev/null && amixer -c "$SCHEDA" scontrols >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! amixer -c "$SCHEDA" scontrols >/dev/null 2>&1; then
  echo "bmo-hat-audio: la scheda $SCHEDA non è comparsa in ${ATTESA_S} s (overlay in config.txt? HAT montato?)" >&2
  exit 1
fi

M="amixer -c $SCHEDA -q"
# ingresso: i due MEMS, boost 2, cattura 40
$M cset name="Left Input Mixer Boost Switch" on
$M cset name="Right Input Mixer Boost Switch" on
$M cset name="Left Input Boost Mixer LINPUT1 Volume" 2
$M cset name="Right Input Boost Mixer RINPUT1 Volume" 2
$M sset Capture 40
# uscita: DAC verso l'altoparlante
$M cset name="Left Output Mixer PCM Playback Switch" on
$M cset name="Right Output Mixer PCM Playback Switch" on
$M sset Playback 255
$M sset Speaker 85%
$M sset "Speaker AC" 5
$M sset "Speaker DC" 5

echo "bmo-hat-audio: scheda $SCHEDA pronta, mixer impostato (Capture 40, boost 2, Speaker 85%)"
