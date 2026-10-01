#!/usr/bin/env bash
# Deploy a un comando di bmo-core/bmo-face sul Pi (issue #16, §2.2 del piano).
#
# Via di mezzo decisa nella #16 fra niente auto-update (rischio di un
# aggiornamento che rompe qualcosa senza preavviso, su un dispositivo che
# altri usano, vedi #15) e comandi manuali uno per uno via SSH: uno script
# lanciato a mano che fa tutto in un colpo solo.
#
# Da lanciare SUL PI (via SSH), non dal PC di sviluppo:
#
#   ssh clanker_home@clanker.local
#   ~/bmo-pi/bmo-diy/pi/deploy.sh
#
# Si aspetta il layout deciso in docs/decisioni-issue-16.md:
#   ~/bmo-pi/bmo-diy/   clone git di questo repo, sul branch di produzione
#   ~/bmo-pi/venv/      un solo venv condiviso da bmo-core e bmo-face
#
# In un colpo solo: git pull (fast-forward, mai un merge a sorpresa) ->
# dipendenze aggiornate -> assets di bmo-face costruiti se mancano ->
# avviso se manca bmo3.onnx (non versionato, §2.6/#58) -> restart dei due
# servizi -> verifica che siano ripartiti puliti. Esce con codice diverso da
# zero, e NON considera il deploy riuscito, se un passo fallisce.
set -euo pipefail

RADICE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$HOME/bmo-pi/venv"
ASSETS="$RADICE/bmo-face/assets"
BMO3="$RADICE/bmo-core/modelli-wake-word/bmo3.onnx"

cd "$RADICE"

echo "== git pull (fast-forward)"
git fetch origin
git merge --ff-only "@{upstream}"

echo "== dipendenze (pip)"
"$VENV/bin/pip" install --upgrade --quiet -e ./bmo-core -e ./bmo-face

echo "== yt-dlp (aggiornato sempre)"
# `pip install --upgrade -e ./bmo-core` NON aggiorna una dipendenza già soddisfatta e senza versione
# fissata: yt-dlp resterebbe quello vecchio. YouTube rompe spesso le versioni vecchie («il video non
# parte»), quindi lo si aggiorna a ogni deploy, esplicitamente.
"$VENV/bin/pip" install --upgrade --quiet yt-dlp
"$VENV/bin/python" -c "import yt_dlp; print('-- yt-dlp', yt_dlp.version.__version__)"
if ! command -v ffmpeg >/dev/null; then
  echo "ATTENZIONE: ffmpeg non è installato: i video non partiranno (sudo apt install ffmpeg)." >&2
fi

echo "== unit di systemd (copiate solo se cambiate)"
ricarica=0
for unit in bmo-face.service bmo-core.service; do
  if ! cmp -s "$RADICE/pi/systemd/$unit" "/etc/systemd/system/$unit"; then
    sudo cp "$RADICE/pi/systemd/$unit" "/etc/systemd/system/$unit"
    echo "-- $unit aggiornata"
    ricarica=1
  fi
done
if [ "$ricarica" -eq 1 ]; then sudo systemctl daemon-reload; fi

echo "== audio (dmix + volume del video, solo con la WM8960)"
"$RADICE/pi/installa-audio.sh"

echo "== assets di bmo-face"
if [ ! -f "$ASSETS/faces.bin" ]; then
  echo "-- faces.bin mancante: lo costruisco (placeholder, a meno che non esista"
  echo "   già un riferimento d'arte vero — vedi docs/note-issue-16.md)"
  "$VENV/bin/python" -m bmo_face.build_face --destinazione "$ASSETS"
fi

echo "== modello wake word bmo3 (non versionato)"
if [ ! -f "$BMO3" ]; then
  echo "ATTENZIONE: $BMO3 manca." >&2
  echo "bmo-core non partirà (tre modelli in produzione è la decisione della" >&2
  echo "#58, docs/decisioni-issue-58.md): copialo a mano prima di continuare," >&2
  echo "o il restart qui sotto farà entrare bmo-core in un ciclo di crash." >&2
fi

echo "== restart servizi"
sudo systemctl restart bmo-face.service bmo-core.service

echo "== verifica post-restart"
sleep 2
fallito=0
for servizio in bmo-face.service bmo-core.service; do
  if sudo systemctl is-active --quiet "$servizio"; then
    echo "-- $servizio: attivo"
  else
    echo "-- $servizio: NON attivo" >&2
    sudo journalctl -u "$servizio" -n 20 --no-pager >&2
    fallito=1
  fi
done

if [ "$fallito" -ne 0 ]; then
  echo "DEPLOY FALLITO: almeno un servizio non è ripartito pulito." >&2
  exit 1
fi
echo "== deploy riuscito"
