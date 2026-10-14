#!/usr/bin/env bash
# Wrapper d'avvio di bmo-core per systemd (issue #16).
#
# Tre modelli di wake word sono la decisione di produzione presa il 28/9
# (docs/decisioni-issue-58.md); bmo3.onnx non è nel repo (mai committato,
# solo sul BMO personale di Riccardo). Se manca, `python -m bmo_core.macchina`
# fallirebbe comunque (openwakeword non trova il file), ma con un
# `FileNotFoundError` generico due livelli sotto — qui l'errore è esplicito
# nel journal, e dice cosa fare, prima ancora di provare ad avviare Python.
set -euo pipefail

RADICE=/home/clanker_home/bmo-pi/bmo-diy
VENV=/home/clanker_home/bmo-pi/venv
MODELLI="$RADICE/bmo-core/modelli-wake-word"
BMO3="$MODELLI/bmo3.onnx"

if [ ! -f "$BMO3" ]; then
  echo "bmo3.onnx manca in $MODELLI: copialo a mano prima che bmo-core possa" >&2
  echo "partire (tre modelli in produzione, docs/decisioni-issue-58.md)." >&2
  exit 1
fi

# Messa a punto col microfono vero del HAT (issue #79, 14/10/2026), tutta sovrascrivibile da /etc/bmo/env:
#   BMO_SILENZIO_MS      silenzio che chiude l'ascolto (era 800: tagliava le pause a metà frase)
#   BMO_VOCE_MINIMA_MS   voce minima prima che il silenzio possa chiudere (scarta la coda di «Hey BMO»)
#   BMO_SOGLIA_WAKE_WORD soglia di rilevamento: 0.3 (richiesta del 14/10: più bassa, così parole simili a «Hey BMO»
#                        scattano più spesso; era 0.5)
export BMO_VOCE_MINIMA_MS="${BMO_VOCE_MINIMA_MS:-400}"

exec "$VENV/bin/python" -m bmo_core.macchina --wake-word --voce-tts \
  --silenzio-ms "${BMO_SILENZIO_MS:-1500}" \
  --soglia-wake-word "${BMO_SOGLIA_WAKE_WORD:-0.3}" \
  --modello-wake-word "$MODELLI/bmo1.onnx" \
  --modello-wake-word "$MODELLI/bmo2.onnx" \
  --modello-wake-word "$BMO3"
