#!/usr/bin/env bash
# Prova ibrida di BMO (issue #77): microfono e altoparlanti del PC, camera e
# schermo del Pi. Tutto il resto gira sul Pi (cervello, wake word, voce, faccia,
# camera, radio, video) e si misura la RAM del Pi mentre si prova.
#
# Sul PC restano soli: il tunnel SSH, un `socat` (e, per ogni connessione, un
# `parec`) che passa il microfono, e il modulo TCP di PulseAudio, aperto solo
# su 127.0.0.1, che fa suonare mpv/ffmpeg del Pi sugli altoparlanti del PC.
#
# Uso: pi/ibrida/avvia_ibrida.sh [--senza-wake-word] [--senza-misura] [--pulsante-tastiera] [--solo-audio]
# `--solo-audio` controlla soltanto microfono e altoparlanti del PC attraverso il Pi (10 secondi),
# prima della prova vera. `--testo="frase"` fa un solo turno scritto (Gemini, strumenti, camera e
# faccia sul display) senza voce. (Dal worktree demo, `./avvia_demo.sh --pi` fa la stessa cosa.) Ctrl-D per uscire.
#
# Non tocca il clone di produzione sul Pi né i suoi servizi: copia il codice in
# ~/bmo-test/albero e usa dati e socket suoi. Alla fine fa ripulire tutto.
set -euo pipefail
cd "$(dirname "$0")/../.."

PI="${BMO_PI:-clanker_home@clanker.local}"
PORTA_PULSE="${BMO_PORTA_PULSE:-4713}"
PORTA_MICROFONO="${BMO_PORTA_MICROFONO:-5001}"
OPZIONI_PI=()
for argomento in "$@"; do
  case "$argomento" in
    --senza-wake-word | --senza-misura | --pulsante-tastiera | --solo-audio) OPZIONI_PI+=("$argomento") ;;
    --testo=*) OPZIONI_PI+=("$(printf '%q' "$argomento")") ;;
    *) echo "[ibrida] opzione sconosciuta: $argomento (uso: avvia_ibrida.sh [--senza-wake-word] [--senza-misura] [--pulsante-tastiera] [--solo-audio] [--testo=\"frase\"])" >&2; exit 2 ;;
  esac
done

for comando in ssh rsync socat parec pactl; do
  command -v "$comando" >/dev/null || { echo "[ibrida] manca '$comando' sul PC" >&2; exit 1; }
done
ssh -o ConnectTimeout=8 -o BatchMode=yes "$PI" true 2>/dev/null \
  || { echo "[ibrida] non riesco a collegarmi al Pi ($PI): è acceso e sulla stessa rete?" >&2; exit 1; }

# La chiave si legge come in avvia_demo.sh e viaggia solo dentro SSH (stdin), mai in una riga di comando.
GEMINI_API_KEY="$(grep -oP "(?<=^export GEMINI_API_KEY=)['\"]?[^'\"[:space:]]+" ~/.bashrc | head -1 | tr -d "'\"")"
[ -n "$GEMINI_API_KEY" ] || { echo "[ibrida] GEMINI_API_KEY non trovata in ~/.bashrc" >&2; exit 1; }

INIZIO="$(date +%s)"
MODULO_PULSE=""
PID_SOCAT=""
PID_TUNNEL=""
chiudi() {
  trap - EXIT
  [ -n "$PID_TUNNEL" ] && kill "$PID_TUNNEL" 2>/dev/null || true
  if [ -n "$PID_SOCAT" ]; then
    pkill -P "$PID_SOCAT" 2>/dev/null || true
    kill "$PID_SOCAT" 2>/dev/null || true
  fi
  # Il modulo si scarica solo se l'ho caricato io: un listener TCP anonimo non deve restare dopo la prova.
  [ -n "$MODULO_PULSE" ] && pactl unload-module "$MODULO_PULSE" 2>/dev/null || true
  ssh -o ConnectTimeout=8 -o BatchMode=yes "$PI" 'rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bmo-test.env"' 2>/dev/null || true
  mkdir -p misure_ram/ibrida
  rsync -a "$PI:bmo-test/misure/" misure_ram/ibrida/ 2>/dev/null || true
  # Solo le misure di QUESTA prova: i file più vecchi restano nella cartella ma non si ristampano.
  ULTIMO="$(find misure_ram/ibrida -name '*.txt' -newermt "@$INIZIO" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2- || true)"
  if [ -n "$ULTIMO" ]; then
    echo "[ibrida] misure del Pi salvate in misure_ram/ibrida/ — riepilogo:" >&2
    cat "$ULTIMO" >&2
  fi
}
trap chiudi EXIT

# La faccia è sempre quella VERA di BMO, costruita dall'arte del riferimento esterno
# (brenpoly/be-more-agent, issue #23: sta fuori dal repo per licenza), come fa avvia_demo.sh.
# Mai gli asset di produzione del Pi e mai il placeholder geometrico: se manca l'arte, ci si ferma.
ARTE_RIFERIMENTO="$HOME/.local/share/bmo-face-arte-riferimento"
if [ ! -f bmo-face/assets/faces.bin ]; then
  if [ -d "$ARTE_RIFERIMENTO" ] && [ -x bmo-face/.venv/bin/python ]; then
    echo "[ibrida] costruisco gli asset con l'arte vera del riferimento ($ARTE_RIFERIMENTO)..." >&2
    (cd bmo-face && .venv/bin/python -m bmo_face.build_face --sorgente "$ARTE_RIFERIMENTO" --destinazione assets/)
  else
    echo "[ibrida] manca l'arte vera: serve $ARTE_RIFERIMENTO e bmo-face/.venv, oppure bmo-face/assets già costruito." >&2
    echo "[ibrida] non uso il placeholder né gli asset di produzione del Pi: mi fermo." >&2
    exit 1
  fi
fi
echo "[ibrida] faccia: bmo-face/assets/faces.bin ($(stat -c %s bmo-face/assets/faces.bin) byte, impronta $(sha256sum bmo-face/assets/faces.bin | cut -c1-8))" >&2

echo "[ibrida] copio il codice sul Pi (~/bmo-test/albero)..." >&2
ssh "$PI" 'mkdir -p ~/bmo-test/albero'
rsync -aR --delete --exclude '.venv' --exclude '__pycache__' --exclude '*.egg-info' --exclude 'bmo3.onnx' \
  ./bmo-core/src ./bmo-core/prompt ./bmo-core/modelli-wake-word ./bmo-face/src ./bmo-face/assets \
  ./pi/ibrida ./pi/misura_sistema_24h.py "$PI:bmo-test/albero/"

echo "[ibrida] apro l'audio del PC verso il Pi (solo su 127.0.0.1, tunnel SSH)..." >&2
if pactl list short modules | grep -q "module-native-protocol-tcp.*port=$PORTA_PULSE"; then
  echo "[ibrida] il modulo TCP di PulseAudio era già caricato: lo lascio com'è." >&2
else
  MODULO_PULSE="$(pactl load-module module-native-protocol-tcp listen=127.0.0.1 port="$PORTA_PULSE" auth-anonymous=1)"
fi
# Un parec per ogni connessione del Pi: wake word, ascolto e ripartenze si aprono quando vogliono.
socat "TCP-LISTEN:$PORTA_MICROFONO,bind=127.0.0.1,fork,reuseaddr" \
  "EXEC:parec --format=s32le --rate=48000 --channels=2 --device=@DEFAULT_SOURCE@ --latency-msec=20" 2>/dev/null &
PID_SOCAT=$!
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 \
  -R "$PORTA_PULSE:127.0.0.1:$PORTA_PULSE" -R "$PORTA_MICROFONO:127.0.0.1:$PORTA_MICROFONO" "$PI" &
PID_TUNNEL=$!
for _ in $(seq 1 30); do
  if ssh -o ConnectTimeout=5 -o BatchMode=yes "$PI" "exec 3<>/dev/tcp/127.0.0.1/$PORTA_MICROFONO" 2>/dev/null; then
    TUNNEL_OK=1
    break
  fi
  sleep 0.5
done
[ "${TUNNEL_OK:-0}" = 1 ] || { echo "[ibrida] il tunnel verso il Pi non si apre (porte $PORTA_PULSE/$PORTA_MICROFONO già occupate sul Pi?)" >&2; exit 1; }

# Chiave sul Pi: file 600 sulla tmpfs, cancellato all'uscita (qui sopra).
printf 'GEMINI_API_KEY=%q\n' "$GEMINI_API_KEY" \
  | ssh "$PI" 'umask 077; cat > "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bmo-test.env"'

echo "[ibrida] avvio BMO sul Pi — microfono e altoparlanti del PC, camera e schermo del Pi." >&2
ssh -t "$PI" "BMO_PORTA_PULSE=$PORTA_PULSE BMO_PORTA_MICROFONO=$PORTA_MICROFONO bash ~/bmo-test/albero/pi/ibrida/pi_avvia.sh ${OPZIONI_PI[*]:-}"
