#!/usr/bin/env bash
# Wrapper d'avvio di bmo-core per systemd (issue #16).
#
# I modelli di wake word nel repo sono bmo1.onnx e bmo2.onnx. Un modello personale in più si aggiunge
# copiandolo come bmo-core/modelli-wake-word/bmo3.onnx (ignorato da git): viene caricato se c'è.
set -euo pipefail

RADICE=/home/clanker_home/bmo-pi/bmo-diy
VENV=/home/clanker_home/bmo-pi/venv
MODELLI="$RADICE/bmo-core/modelli-wake-word"
BMO3="$MODELLI/bmo3.onnx"

MODELLI_WAKE=(--modello-wake-word "$MODELLI/bmo1.onnx" --modello-wake-word "$MODELLI/bmo2.onnx")
if [ -f "$BMO3" ]; then MODELLI_WAKE+=(--modello-wake-word "$BMO3"); fi

# Messa a punto col microfono del HAT, tutta sovrascrivibile da /etc/bmo/env:
#   BMO_SILENZIO_MS      silenzio che chiude l'ascolto
#   BMO_VOCE_MINIMA_MS   voce minima prima che il silenzio possa chiudere (scarta la coda di «Hey BMO»)
#   BMO_SOGLIA_WAKE_WORD soglia di rilevamento: 0.20 (richiamo da 3 m e oltre: 90% da 0.05 a 0.25, 70% a 0.5;
#                        0.20 ha margine sotto il minimo misurato di «Hey BMO», vedi docs/misure.md)
export BMO_VOCE_MINIMA_MS="${BMO_VOCE_MINIMA_MS:-400}"

exec "$VENV/bin/python" -m bmo_core.macchina --wake-word --voce-tts \
  --silenzio-ms "${BMO_SILENZIO_MS:-1500}" \
  --soglia-wake-word "${BMO_SOGLIA_WAKE_WORD:-0.20}" \
  "${MODELLI_WAKE[@]}"
