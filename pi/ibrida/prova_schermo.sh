#!/usr/bin/env bash
# Prova di schermo, faccia e camera sul Pi (issue #77), senza audio né Gemini.
# Da lanciare SUL PI, sulla copia in ~/bmo-test/albero (la porta `avvia_ibrida.sh`
# o un rsync a mano). Avvia la faccia sul display SPI e cicla gli stati.
#
#   ssh clanker_home@clanker.local 'bash ~/bmo-test/albero/pi/ibrida/prova_schermo.sh'
set -euo pipefail

BASE="$HOME/bmo-test"
ALBERO="$BASE/albero"
PYTHON="$HOME/bmo-pi/venv/bin/python"
RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
SOCKET="$RUNTIME/bmo-test/bmo.sock"
SISTEMA_PY=/usr/lib/python3/dist-packages
mkdir -p "$BASE/extra" "$RUNTIME/bmo-test"

for modulo in spidev.cpython-313-aarch64-linux-gnu.so RPi lgpio.py _lgpio.cpython-313-aarch64-linux-gnu.so; do
  [ -e "$SISTEMA_PY/$modulo" ] && ln -sfn "$SISTEMA_PY/$modulo" "$BASE/extra/$modulo"
done

export PYTHONPATH="$ALBERO/bmo-core/src:$ALBERO/bmo-face/src:$BASE/extra"
export BMO_ENV=pi BMO_FACCIA=socket BMO_SOCKET="$SOCKET" BMO_CAMERA=grezza
export BMO_CAMERA_RUOTA="${BMO_CAMERA_RUOTA:-180}"

pkill -f "bmo_face.pannello --assets assets/ --uscita spi" 2>/dev/null || true
sleep 0.5
(cd "$ALBERO/bmo-face" && exec "$PYTHON" -m bmo_face.pannello --assets assets/ --uscita spi --socket "$SOCKET") &
PANNELLO=$!
trap 'kill -TERM "$PANNELLO" 2>/dev/null || true; wait "$PANNELLO" 2>/dev/null || true; rm -f "$SOCKET"' EXIT

for _ in $(seq 1 50); do [ -S "$SOCKET" ] && break; sleep 0.1; done
[ -S "$SOCKET" ] || { echo "la faccia non ha aperto il socket" >&2; exit 1; }

"$PYTHON" "$ALBERO/pi/ibrida/prova_faccia.py" "$@"
