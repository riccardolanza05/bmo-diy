#!/usr/bin/env bash
# Il lato Pi della prova ibrida (issue #77). Lo lancia `avvia_ibrida.sh` dal PC
# via SSH (`ssh -t`, serve il terminale per Invio e Ctrl-D): da solo non fa
# niente di utile, perché il microfono e gli altoparlanti stanno sul PC.
#
# Gira TUTTO sul Pi: bmo-core (cervello, wake word, VAD, voce, strumenti), la
# faccia sul display SPI, la camera del Pi, mpv/ffmpeg per radio e video, e i
# campionatori di RAM. Sul PC restano solo il microfono, gli altoparlanti e il
# tunnel SSH.
#
# Non tocca il clone di produzione (~/bmo-pi/bmo-diy) né i servizi systemd:
# lavora su una copia in ~/bmo-test/albero, con il venv di produzione solo come
# interprete, e con dati e socket suoi.
#
# Uso (da `avvia_ibrida.sh`): pi_avvia.sh [--senza-wake-word] [--senza-misura] [--pulsante-tastiera]
set -euo pipefail

SENZA_WAKE_WORD=0
MISURA=1
PULSANTE_TASTIERA=0
for argomento in "$@"; do
  case "$argomento" in
    --senza-wake-word) SENZA_WAKE_WORD=1 ;;
    --senza-misura) MISURA=0 ;;
    --pulsante-tastiera) PULSANTE_TASTIERA=1 ;;
    *) echo "[pi] opzione sconosciuta: $argomento" >&2; exit 2 ;;
  esac
done

BASE="$HOME/bmo-test"
ALBERO="$BASE/albero"
PYTHON="$HOME/bmo-pi/venv/bin/python"
RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
SOCKET="$RUNTIME/bmo-test/bmo.sock"
CHIAVE="$RUNTIME/bmo-test.env"
SISTEMA_PY=/usr/lib/python3/dist-packages
mkdir -p "$BASE/dati" "$BASE/extra" "$BASE/misure" "$RUNTIME/bmo-test"

[ -x "$PYTHON" ] || { echo "[pi] manca il venv di produzione $PYTHON" >&2; exit 1; }
[ -f "$CHIAVE" ] || { echo "[pi] manca la chiave Gemini ($CHIAVE): la porta avvia_ibrida.sh" >&2; exit 1; }
[ -d "$ALBERO/bmo-core/src" ] || { echo "[pi] manca la copia del codice in $ALBERO: la porta avvia_ibrida.sh" >&2; exit 1; }

# La chiave sta in un file 600 sulla tmpfs: la si legge qui e nessun comando la contiene.
set -a
# shellcheck disable=SC1090
. "$CHIAVE"
set +a

# Il terzo modello della wake word non è nel repo: lo si prende dal clone di produzione.
mkdir -p "$ALBERO/bmo-core/modelli-wake-word"
if [ ! -f "$ALBERO/bmo-core/modelli-wake-word/bmo3.onnx" ] && [ -f "$HOME/bmo-pi/bmo-diy/bmo-core/modelli-wake-word/bmo3.onnx" ]; then
  cp "$HOME/bmo-pi/bmo-diy/bmo-core/modelli-wake-word/bmo3.onnx" "$ALBERO/bmo-core/modelli-wake-word/bmo3.onnx"
fi

# spidev e RPi.GPIO ci sono solo nel Python di sistema, non nel venv di produzione (che non va
# toccato): si espongono al test con dei link, e solo loro (non anche il numpy di sistema).
for modulo in spidev.cpython-313-aarch64-linux-gnu.so RPi lgpio.py _lgpio.cpython-313-aarch64-linux-gnu.so; do
  [ -e "$SISTEMA_PY/$modulo" ] && ln -sfn "$SISTEMA_PY/$modulo" "$BASE/extra/$modulo"
done

export PATH="$ALBERO/pi/ibrida/bin:$PATH"          # `arecord` e `mpv` finti: audio dal PC
export PYTHONPATH="$ALBERO/bmo-core/src:$ALBERO/bmo-face/src:$BASE/extra"
export BMO_ENV=pi
export BMO_FACCIA=socket
export BMO_SOCKET="$SOCKET"
export BMO_DATI="$BASE/dati"
export BMO_CAMERA=grezza
export BMO_CAMERA_RUOTA="${BMO_CAMERA_RUOTA:-180}"  # la camera è montata a testa in giù
export PULSE_SERVER="tcp:127.0.0.1:${BMO_PORTA_PULSE:-4713}"
export BMO_VIDEO_AUDIO=pulse                       # ffmpeg (video) suona sul PC, come mpv

# Controllo che il tunnel con il PC sia su, prima di partire: meglio fermarsi qui che a metà.
for porta in "${BMO_PORTA_MICROFONO:-5001}" "${BMO_PORTA_PULSE:-4713}"; do
  if ! (exec 3<>"/dev/tcp/127.0.0.1/$porta") 2>/dev/null; then
    echo "[pi] la porta $porta del tunnel verso il PC non risponde (lo apre avvia_ibrida.sh)" >&2
    exit 1
  fi
done

# Una faccia rimasta da una prova interrotta terrebbe occupato il display.
pkill -f "bmo_face.pannello --assets $ALBERO" 2>/dev/null || true
sleep 0.5

PIDS=()
chiudi() {
  trap - EXIT
  for pid in "${PIDS[@]:-}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${PIDS[@]:-}"; do wait "$pid" 2>/dev/null || true; done
  rm -f "$SOCKET" "$RUNTIME/bmo-test/bmo-video.sock"
  echo "[pi] fermato. Misure in $BASE/misure/" >&2
}
trap chiudi EXIT

echo "[pi] avvio la faccia sul display SPI..." >&2
(cd "$ALBERO/bmo-face" && exec "$PYTHON" -m bmo_face.pannello --assets assets/ --uscita spi --socket "$SOCKET") &
PIDS+=($!)

for _ in $(seq 1 50); do [ -S "$SOCKET" ] && break; sleep 0.1; done
[ -S "$SOCKET" ] || { echo "[pi] la faccia non ha aperto il socket $SOCKET (vedi sopra)" >&2; exit 1; }

if [ "$MISURA" = 1 ]; then
  BASE_MISURA="$BASE/misure/$(date +%Y-%m-%d_%H%M%S)"
  "$PYTHON" -m bmo_core.misura_ram --radice $$ --intervallo 1 \
    --csv "$BASE_MISURA.csv" --riepilogo "$BASE_MISURA.txt" &
  PIDS+=($!)
  # Temperatura, throttling, zram e la unit di produzione di bmo-face (che resta accesa: è la base).
  "$PYTHON" "$ALBERO/pi/misura_sistema_24h.py" --unita bmo-face.service --intervallo 2 \
    --csv "$BASE_MISURA-sistema.csv" >/dev/null 2>&1 &
  PIDS+=($!)
  echo "[pi] misuro la RAM (PSS) di tutti i processi e il sistema: $BASE_MISURA*" >&2
fi
sleep 1

MODELLI=()
for modello in bmo1 bmo2 bmo3; do
  [ -f "$ALBERO/bmo-core/modelli-wake-word/$modello.onnx" ] && MODELLI+=(--modello-wake-word "$ALBERO/bmo-core/modelli-wake-word/$modello.onnx")
done

RICHIAMO=(--wake-word "${MODELLI[@]}")
if [ "$SENZA_WAKE_WORD" = 1 ]; then
  RICHIAMO=()
  echo "[pi] richiamo a Invio (--senza-wake-word)." >&2
elif [ "$PULSANTE_TASTIERA" = 1 ]; then
  RICHIAMO+=(--pulsante-tastiera)
  echo "[pi] BMO acceso — di' «Hey BMO» o premi Invio. Ctrl-C per uscire." >&2
else
  echo "[pi] BMO acceso — di' «Hey BMO» (microfono del PC). Ctrl-D per uscire." >&2
fi

(cd "$ALBERO/bmo-core" && "$PYTHON" -m bmo_core.macchina --voce-tts "${RICHIAMO[@]}") || true
