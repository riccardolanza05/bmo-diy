#!/usr/bin/env bash
# Prova di BMO sul Pi con il microfono e l'altoparlante VERI del HAT WM8960 (issue #79).
# Come `avvia_ibrida.sh`, ma senza tunnel né audio del PC: dal PC restano solo la copia del codice
# e la chiave (via SSH, su un file 600 della tmpfs del Pi, cancellato all'uscita).
#
# Uso: pi/ibrida/avvia_hat.sh [--senza-wake-word] [--senza-misura] [--pulsante-tastiera] [--testo="frase"]
# Ctrl-D per uscire. Non tocca il clone di produzione né i servizi: lavora in ~/bmo-test/albero.
#
# La faccia è quella che c'è già in ~/bmo-test/albero/bmo-face/assets (l'arte vera del riferimento): se
# l'impronta di faces.bin non è quella attesa ci si ferma, come in `avvia_ibrida.sh`.
set -euo pipefail
cd "$(dirname "$0")/../.."

PI="${BMO_PI:-clanker_home@clanker.local}"
IMPRONTA_ATTESA=aa9f95d1
OPZIONI_PI=(--hat)
for argomento in "$@"; do
  case "$argomento" in
    --senza-wake-word | --senza-misura | --pulsante-tastiera) OPZIONI_PI+=("$argomento") ;;
    --testo=*) OPZIONI_PI+=("$(printf '%q' "$argomento")") ;;
    *) echo "[hat] opzione sconosciuta: $argomento" >&2; exit 2 ;;
  esac
done

ssh -o ConnectTimeout=8 -o BatchMode=yes "$PI" true 2>/dev/null \
  || { echo "[hat] non riesco a collegarmi al Pi ($PI)" >&2; exit 1; }

GEMINI_API_KEY="$(grep -oP "(?<=^export GEMINI_API_KEY=)['\"]?[^'\"[:space:]]+" ~/.bashrc | head -1 | tr -d "'\"")"
[ -n "$GEMINI_API_KEY" ] || { echo "[hat] GEMINI_API_KEY non trovata in ~/.bashrc" >&2; exit 1; }

chiudi() {
  trap - EXIT
  ssh -o ConnectTimeout=8 -o BatchMode=yes "$PI" 'rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bmo-test.env"' 2>/dev/null || true
  mkdir -p misure_ram/hat
  rsync -a "$PI:bmo-test/misure/" misure_ram/hat/ 2>/dev/null || true
}
trap chiudi EXIT

IMPRONTA="$(ssh "$PI" "sha256sum ~/bmo-test/albero/bmo-face/assets/faces.bin | cut -c1-8")"
if [ "$IMPRONTA" != "$IMPRONTA_ATTESA" ]; then
  echo "[hat] faces.bin sul Pi ha impronta $IMPRONTA, non $IMPRONTA_ATTESA (arte vera): mi fermo." >&2
  exit 1
fi

echo "[hat] copio il codice sul Pi (~/bmo-test/albero)..." >&2
rsync -aR --exclude '.venv' --exclude '__pycache__' --exclude '*.egg-info' --exclude 'bmo3.onnx' \
  ./bmo-core/src ./bmo-core/prompt ./bmo-core/modelli-wake-word ./bmo-face/src \
  ./pi/ibrida ./pi/misura_sistema_24h.py "$PI:bmo-test/albero/"

printf 'GEMINI_API_KEY=%q\n' "$GEMINI_API_KEY" \
  | ssh "$PI" 'umask 077; cat > "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bmo-test.env"'

echo "[hat] avvio BMO sul Pi — microfono e altoparlante del HAT." >&2
ssh -t "$PI" "bash ~/bmo-test/albero/pi/ibrida/pi_avvia.sh ${OPZIONI_PI[*]}"
