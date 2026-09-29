#!/usr/bin/env bash
# Wrapper d'avvio della prova di carico dosata (issue #65). Passa gli
# argomenti (--giri, --pausa-minuti, ...) così com'è: le due unit
# `bmo-carico-calibrazione.service` e `bmo-carico.service` differiscono solo
# in quelli, non in questo script.
#
# Stessi tre modelli di wake word di produzione (bmo-core-avvia.sh,
# docs/decisioni-issue-58.md): bmo3.onnx non è nel repo, va copiato a mano
# sul Pi prima di lanciare una di queste unit (come già per bmo-core.service).
set -euo pipefail

RADICE=/home/clanker_home/bmo-pi/bmo-diy
VENV=/home/clanker_home/bmo-pi/venv
MODELLI="$RADICE/bmo-core/modelli-wake-word"
BMO3="$MODELLI/bmo3.onnx"

if [ ! -f "$BMO3" ]; then
  echo "bmo3.onnx manca in $MODELLI: copialo a mano prima che bmo-carico possa" >&2
  echo "partire (tre modelli in produzione, docs/decisioni-issue-58.md)." >&2
  exit 1
fi

cd "$RADICE/bmo-core"
exec "$VENV/bin/python" -m bmo_core.carico "$@" \
  --modello-wake-word "$MODELLI/bmo1.onnx" \
  --modello-wake-word "$MODELLI/bmo2.onnx" \
  --modello-wake-word "$BMO3"
