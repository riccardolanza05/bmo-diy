# Note — issue #83 (BMO riparte da solo dopo uno stacco dell'alimentazione)

Numeri grezzi. Decisioni in [`decisioni-issue-83.md`](decisioni-issue-83.md), cose informative in
[`informazioni-issue-83.md`](informazioni-issue-83.md). Tutto del 14/10/2026, Pi 3 A+ con HAT WM8960.

## Cosa c'è

| Pezzo | Dove | Cosa fa |
|---|---|---|
| `pi/bmo-hat-audio.sh` | Pi, all'avvio | aspetta fino a 60 s la scheda `wm8960soundcard`, imposta il mixer (Capture 40, boost 2, uscita accesa, Speaker 85%) |
| `pi/systemd/bmo-hat-audio.service` | Pi | oneshot (utente `clanker_home`), `Before=bmo-core.service`, `RemainAfterExit=yes` |
| `bmo-core.service` | Pi | `Wants=`/`After=bmo-hat-audio.service`, **`StartLimitIntervalSec=0`** |
| `bmo-face.service` | Pi | **`StartLimitIntervalSec=0`** |
| `pi/deploy.sh` | Pi | copia anche la nuova unit e fa `systemctl enable` delle tre |

## Verifiche fatte (sul Pi senza sudo)

- `bmo-hat-audio.sh` lanciato a mano: 0,24 s, rc 0, `Capture 40 [63%] [12,75 dB]`, `Speaker 85% [-13 dB]`.
- `bmo-face` e `bmo-core` risultano `enabled`; `NetworkManager-wait-online` abilitato; `alsa-restore`
  è `static` (lo tira `sound.target`).
- `bmo-core.service` aveva già `Wants=network-online.target` e `After=bmo-face.service`.
- `systemd-analyze verify` sulle tre unit: nessun errore fuori dai percorsi del Pi.

## Perché `StartLimitIntervalSec=0`

Con `Restart=always` e `RestartSec=2` systemd ferma i tentativi dopo 5 avvii in 10 s (valori predefiniti
`StartLimitBurst=5`, `StartLimitIntervalSec=10s`) e lascia l'unità in `failed` per sempre, finché non la
riavvii a mano. All'accensione, se il microfono o la rete ci mettono più di ~10 s, BMO resterebbe muto.

## Stato del filesystem (da `findmnt`)

- Root: `ext4 rw,noatime`, `fsck` a ogni avvio (`pass 1` in `/etc/fstab`). **Nessun overlay in sola lettura.**
- `/boot/firmware`: `vfat rw`, `errors=remount-ro`.
- Journal di systemd volatile (nessun boot precedente conservato): i log si perdono a ogni stacco.

## Non verificato

- **Il ciclo vero**: staccare e riattaccare la corrente. Serve il deploy (sudo) e poi lo stacco; non l'ho
  potuto fare io.
- Quanto ci mette la scheda audio a comparire all'accensione (il tetto è 60 s).
