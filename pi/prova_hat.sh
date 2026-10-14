#!/usr/bin/env bash
# Prova dal vivo del HAT WM8960 (issue #79): routing dei mixer, bip, 5 s di voce registrati, livelli
# per canale e riascolto sull'altoparlante. Da lanciare SUL PI. Strumento di prova, il servizio non lo usa.
#
#   ssh clanker_home@clanker.local 'bash ~/prova_hat.sh'
#   VOLUME=50 CAPTURE=45 bash ~/prova_hat.sh      # volume altoparlante in %, guadagno di cattura 0-63
set -euo pipefail
SCHEDA=wm8960soundcard
DEV="hw:CARD=$SCHEDA,DEV=0"
PY="$HOME/bmo-pi/venv/bin/python"
M="amixer -c $SCHEDA -q"
# Routing: all'avvio l'ingresso (Input Mixer Boost) e il volume LINPUT1/RINPUT1 sono a zero.
$M cset name="Left Input Mixer Boost Switch" on
$M cset name="Right Input Mixer Boost Switch" on
$M cset name="Left Input Boost Mixer LINPUT1 Volume" 2
$M cset name="Right Input Boost Mixer RINPUT1 Volume" 2
$M cset name="Left Output Mixer PCM Playback Switch" on
$M cset name="Right Output Mixer PCM Playback Switch" on
$M sset Playback 200
$M sset Speaker "${VOLUME:-70}%"
$M sset "Speaker AC" 5
$M sset "Speaker DC" 5
if [ -n "${CAPTURE:-}" ]; then $M sset Capture "$CAPTURE"; fi
f="$(mktemp --suffix=.raw)"
trap 'rm -f "$f"' EXIT
echo ">> bip, poi PARLA per 5 secondi (a ~1 m dal HAT)"
"$PY" -c "
import sys, numpy as np
t = np.arange(24000) / 48000
x = (0.2 * np.sin(2 * np.pi * 880 * t) * 32767).astype('<i2')
sys.stdout.buffer.write(np.repeat(x[:, None], 2, axis=1).tobytes())" |
  aplay -q -D "plug$DEV" -t raw -f S16_LE -r 48000 -c 2
arecord -q -D "$DEV" -f S32_LE -r 48000 -c 2 -d 5 -t raw "$f"
echo ">> livelli:"
"$PY" - "$f" <<'PY'
import sys
import numpy as np
a = np.fromfile(sys.argv[1], dtype="<i4").reshape(-1, 2).astype(float)
for nome, c in zip(("sinistro", "destro"), a.T):
    r = np.sqrt(np.mean((c - c.mean()) ** 2))
    p = np.abs(c).max()
    print(f"{nome:9s} rms {20 * np.log10(max(r, 1) / 2**31):6.1f} dBFS  picco {20 * np.log10(max(p, 1) / 2**31):6.1f} dBFS")
PY
echo ">> riascolto"
aplay -q -D "plug$DEV" -t raw -f S32_LE -r 48000 -c 2 "$f"
