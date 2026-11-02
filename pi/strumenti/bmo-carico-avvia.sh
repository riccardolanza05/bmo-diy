#!/usr/bin/env bash
# Wrapper d'avvio della prova di carico dosata (issue #65). Passa gli
# argomenti (--giri, --pausa-minuti, ...) così com'è: le due unit
# `bmo-carico-calibrazione.service` e `bmo-carico.service` differiscono solo
# in quelli, non in questo script.
#
# Stessi modelli di wake word di produzione (bmo-core-avvia.sh): bmo1 e bmo2,
# più bmo3.onnx se presente.
set -euo pipefail

RADICE=/home/clanker_home/bmo-pi/bmo-diy
VENV=/home/clanker_home/bmo-pi/venv
MODELLI="$RADICE/bmo-core/modelli-wake-word"
BMO3="$MODELLI/bmo3.onnx"

MODELLI_WAKE=(--modello-wake-word "$MODELLI/bmo1.onnx" --modello-wake-word "$MODELLI/bmo2.onnx")
if [ -f "$BMO3" ]; then MODELLI_WAKE+=(--modello-wake-word "$BMO3"); fi

cd "$RADICE/bmo-core"
exec "$VENV/bin/python" -m bmo_core.carico "$@" \
  "${MODELLI_WAKE[@]}"
