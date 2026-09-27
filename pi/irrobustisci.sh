#!/usr/bin/env bash
# Irrobustimento del Raspberry Pi per il 24/7 (issue #25, fase 2.1 del piano).
#
# Da lanciare SUL PI, come root. Idempotente: rilanciarlo non cambia niente
# che sia già a posto, quindi va bene anche dopo un re-flash.
#
#   sudo bash irrobustisci.sh servizi   # blocco 1: solo systemd, nessun file di avvio
#   sudo bash irrobustisci.sh avvio     # blocco 2: cmdline.txt e config.txt (backup .bak-25)
#   sudo bash irrobustisci.sh verifica  # stampa i numeri del criterio di uscita, non cambia nulla
#
# Dopo `servizi` e dopo `avvio` serve un riavvio (`sudo reboot`) — lo script
# non riavvia da solo: sul Pi senza schermo, fra un blocco e l'altro bisogna
# controllare che SSH torni su prima di andare avanti.
#
# Scritto per Raspberry Pi OS trixie (Debian 13). Rispetto al piano §2.1,
# scritto per bookworm, qui NON si fa:
#   - niente `dphys-swapfile` (non esiste più) e niente `zram-tools`: lo swap
#     è già zram, gestito da `rpi-swap` + `systemd-zram-generator`; un secondo
#     gestore zram litigherebbe col primo;
#   - niente `Storage=volatile` a mano: è già nel drop-in di sistema
#     /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf.
# Resta attivo apposta:
#   - avahi-daemon: senza, `clanker.local` non si risolve più e SSH dal PC
#     andrebbe fatto per IP (che cambia sulla rete Lambrate);
#   - NetworkManager, ssh, timesyncd, lambrate-login.timer (captive portal);
#   - cloud-init (vedi docs/decisioni-issue-25.md).
set -euo pipefail

BOOT=/boot/firmware
MARCATORE="# bmo-diy #25"

# Servizi del desktop e di periferiche che BMO non usa. Solo `disable`, mai
# `purge`: tornare indietro è un `systemctl enable`, i pacchetti restano.
UNITA_DA_SPEGNERE=(
  cups.service cups.socket cups.path cups-browsed.service
  bluetooth.service
  wayvnc-control.service wayvnc.service
  rpcbind.service rpcbind.socket nfs-blkmap.service nfs-client.target
  udisks2.service
  accounts-daemon.service
  glamor-test.service rp1-test.service
)

# Righe aggiunte in coda a config.txt, in una sezione [all] nuova: una sezione
# condizionale precedente ([pi5], [cm5]...) non le può catturare.
RIGHE_CONFIG=(
  "dtparam=spi=on"
  "dtparam=watchdog=on"
  "gpu_mem=16"
  # Niente Bluetooth: toglie dal kernel lo stack bluetooth + hci_uart e
  # libera la UART buona del Pi 3.
  "dtoverlay=disable-bt"
)

# Lo stack grafico KMS (vc4 + drm) serve solo a un monitor HDMI. La faccia di
# BMO va sul display SPI via spidev (§2.11), che non passa di lì. Commentato,
# non cancellato: per riavere l'HDMI basta togliere il #.
RIGA_KMS="dtoverlay=vc4-kms-v3d"

serve_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "serve root: sudo bash $0 $*" >&2
    exit 1
  fi
}

esiste_unita() {
  systemctl list-unit-files --no-legend "$1" 2>/dev/null | grep -q .
}

servizi() {
  serve_root servizi
  echo "== target predefinito"
  if [ "$(systemctl get-default)" != "multi-user.target" ]; then
    systemctl set-default multi-user.target
  else
    echo "già multi-user.target"
  fi

  echo "== servizi da spegnere"
  for unita in "${UNITA_DA_SPEGNERE[@]}"; do
    if ! esiste_unita "$unita"; then
      echo "  $unita: non installata, salto"
      continue
    fi
    stato="$(systemctl is-enabled "$unita" 2>/dev/null || true)"
    case "$stato" in
      enabled|enabled-runtime)
        systemctl disable "$unita" >/dev/null 2>&1
        echo "  $unita: disabilitata"
        ;;
      *)
        echo "  $unita: già $stato"
        ;;
    esac
  done

  echo "== login automatico sulla console tty1"
  # L'immagine col desktop fa entrare da solo l'utente sulla console. Senza
  # desktop quel login resta lì: tiene in piedi il gestore utente di systemd
  # con pipewire e wireplumber (~35-50 MB misurati), e chiunque attacchi una
  # tastiera al Pi si ritrova dentro senza password. Rinominato, non
  # cancellato: systemd ignora i drop-in che non finiscono in .conf.
  local autologin=/etc/systemd/system/getty@tty1.service.d/autologin.conf
  if [ -f "$autologin" ]; then
    mv "$autologin" "$autologin.bak-25"
    echo "  disattivato (rimesso a posto con: mv $autologin.bak-25 $autologin)"
  else
    echo "  già disattivato"
  fi

  echo "== watchdog di systemd a 15 s (il piano; il default del Pi è 1 min)"
  mkdir -p /etc/systemd/system.conf.d
  cat > /etc/systemd/system.conf.d/50-bmo-watchdog.conf <<'EOF'
# bmo-diy #25: se il sistema si pianta per più di 15 s, il watchdog hardware
# del BCM2837 riavvia il Pi. Il Pi resta in casa acceso 24/7 senza nessuno
# che lo stacchi e riattacchi.
[Manager]
RuntimeWatchdogSec=15
RebootWatchdogSec=2min
EOF
  echo "  scritto /etc/systemd/system.conf.d/50-bmo-watchdog.conf"

  echo
  echo "Fatto. Ora: sudo reboot, poi controllare che SSH torni su."
}

avvio() {
  serve_root avvio
  local cmdline="$BOOT/cmdline.txt" config="$BOOT/config.txt"

  for f in "$cmdline" "$config"; do
    if [ ! -f "$f.bak-25" ]; then
      cp -p "$f" "$f.bak-25"
      echo "backup: $f.bak-25"
    fi
  done

  echo "== cmdline.txt: cgroup_enable=memory"
  # Il firmware del Pi 3 aggiunge da solo `cgroup_disable=memory` alla riga
  # di comando del kernel. Senza questo contrordine i MemoryMax= delle unit
  # (fase 2.2) e systemd-cgtop (fase 2.3) non misurano né limitano niente.
  # cmdline.txt DEVE restare di una riga sola: una seconda riga = niente
  # boot = niente SSH. Per questo sed sulla riga 1, mai `echo >>`.
  if [ "$(wc -l < "$cmdline")" -gt 1 ]; then
    echo "ERRORE: $cmdline ha più di una riga, non tocco niente" >&2
    exit 1
  fi
  if grep -qw "cgroup_enable=memory" "$cmdline"; then
    echo "  già presente"
  else
    sed -i '1 s/[[:space:]]*$/ cgroup_enable=memory/' "$cmdline"
    echo "  aggiunto"
  fi
  if [ "$(wc -l < "$cmdline")" -gt 1 ]; then
    echo "ERRORE: dopo la modifica $cmdline ha più righe: ripristino il backup" >&2
    cp -p "$cmdline.bak-25" "$cmdline"
    exit 1
  fi

  echo "== config.txt"
  if ! grep -qF "$MARCATORE" "$config"; then
    printf '\n[all]\n%s — vedi pi/irrobustisci.sh e docs/decisioni-issue-25.md\n' "$MARCATORE" >> "$config"
    echo "  aggiunta la sezione [all] $MARCATORE in coda"
  fi
  # La sezione nostra è per costruzione l'ultima del file: le righe nuove
  # si accodano, e restano dentro il suo [all].
  for riga in "${RIGHE_CONFIG[@]}"; do
    if grep -qxF "$riga" "$config"; then
      echo "  $riga: già presente"
    else
      echo "$riga" >> "$config"
      echo "  $riga: aggiunta"
    fi
  done
  if grep -qx "$RIGA_KMS" "$config"; then
    sed -i "s|^$RIGA_KMS\$|#$RIGA_KMS  $MARCATORE: niente HDMI, la faccia va su SPI|" "$config"
    echo "  $RIGA_KMS: commentata"
  else
    echo "  $RIGA_KMS: già commentata o assente"
  fi

  echo
  echo "Fatto. Ora: sudo reboot, poi controllare che SSH torni su."
  echo "Se il Pi non torna: togliere la microSD e, dal PC, rimettere"
  echo "cmdline.txt.bak-25 e config.txt.bak-25 al posto degli originali."
}

verifica() {
  echo "== target predefinito: $(systemctl get-default)"
  echo "== memoria (criterio di uscita: ~90 MB usati, niente swap su disco)"
  free -m
  echo "== swap attivi"
  cat /proc/swaps
  echo "== CMA"
  grep -E '^(MemTotal|MemAvailable|CmaTotal|CmaFree)' /proc/meminfo
  echo "== throttling (criterio di uscita: 0x0)"
  vcgencmd get_throttled
  vcgencmd get_mem arm
  vcgencmd get_mem gpu
  echo "== controller cgroup (deve comparire 'memory')"
  cat /sys/fs/cgroup/cgroup.controllers
  echo "== watchdog"
  systemctl show -p RuntimeWatchdogUSec -p RebootWatchdogUSec
  echo "== journald"
  journalctl --disk-usage
  echo "== da non rompere"
  for u in ssh.service NetworkManager.service avahi-daemon.service systemd-timesyncd.service lambrate-login.timer; do
    printf '  %-28s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || true)"
  done
  echo "== sessioni aperte (in produzione: nessuna, a parte chi è in SSH)"
  loginctl list-sessions --no-legend || true
  echo "== unità fallite"
  systemctl --failed --no-legend || true
  echo "== processi più grossi (RSS, kB)"
  ps -eo rss,comm --sort=-rss | head -12
}

case "${1:-}" in
  servizi) servizi ;;
  avvio) avvio ;;
  verifica) verifica ;;
  *)
    echo "uso: sudo bash $0 servizi|avvio|verifica" >&2
    exit 2
    ;;
esac
