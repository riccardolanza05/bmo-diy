# Note — issue #25 (irrobustimento del Pi per il 24/7)

Note informative, non decisioni: quelle stanno in
[`decisioni-issue-25.md`](decisioni-issue-25.md). Misure prese sul Pi vero
(Raspberry Pi 3 Model A+ Rev 1.1, Raspberry Pi OS trixie, kernel
6.18.50+rpt-rpi-v8) il 27/9/2026, con
[`pi/irrobustisci.sh`](../pi/irrobustisci.sh) `verifica`.

## Prima e dopo

| | prima | dopo |
|---|---|---|
| target | `graphical.target` (desktop) | `multi-user.target` |
| `MemTotal` | 415 MB | **462 MB** (`gpu_mem` da 64 a 16) |
| `MemAvailable` | 227 MB | **331 MB** |
| «used» di `free -m` (= `MemTotal − MemAvailable`) | 188 MB | **130 MB** |
| «used» classico (`totale − libera − buffer/cache`) | 128 MB | **77 MB** |
| swap in uso (zram) | 93 MB | 0 |
| swap su microSD | nessuno | nessuno |
| CMA riservata | 256 MB | 64 MB |
| moduli del kernel | 60 | 43 |
| `vcgencmd get_throttled` | `0x0` | `0x0` |
| controller cgroup `memory` | assente | presente |
| watchdog di systemd | 1 min | 15 s |
| login automatico su tty1 | sì | no |

Il «dopo» è misurato 5 minuti dopo l'avvio **senza nessuno collegato** (una
unit `systemd-run` programmata prima di scollegarsi): è il Pi come sarà in
casa. Collegati in SSH si aggiungono ~30 MB della sessione utente (pipewire,
wireplumber, systemd --user).

## Il criterio di uscita

Il piano chiede «`free -m` intorno a 90 MB usati». Il numero dipende dalla
versione di `free`: quella di trixie (procps-ng 4) calcola «used» come
`MemTotal − MemAvailable` e dà **130 MB**; la definizione classica, con cui
è stato presumibilmente scritto il piano, dà **77 MB**. Il numero che conta
per il bilancio della §2.8 è un altro: **331 MB disponibili per BMO**,
contro i ~200 MB di margine che il piano si aspettava dopo il picco di ~295
MB — cioè ~30 MB meno di quanto il piano immaginava (§2.8 dava ~495 MB
visibili, sono 462). Swap su microSD: zero. `get_throttled`: `0x0`.

## Dove sono finiti i 104 MB in più

Misurati un passo alla volta, sempre a sistema assestato:

1. **Desktop spento e servizi disabilitati** (blocco `servizi`): da 227 a
   ~259 MB disponibili subito dopo l'avvio.
2. **`gpu_mem=16`**: +48 MB di `MemTotal`, da 415 a 463.
3. **Niente KMS né Bluetooth**: +9 MB disponibili, CMA da 256 a 64 MB.
4. **Niente login automatico su tty1**: la sessione che teneva in piedi
   pipewire e wireplumber anche senza desktop — circa +18 MB disponibili.

## Cosa resta

A riposo i processi utente occupano appena ~20 MB di memoria anonima
(NetworkManager ~20 MB RSS, systemd, wpa_supplicant, journald, avahi). Il
grosso del resto è il kernel: slab ~37 MB, vmalloc ~13 MB. Da qui in giù i
guadagni sono piccoli e costano (vedi la issue sulla RAM): la partita vera
si gioca su quanto occupa `bmo-core`.

## Se il Pi non si riavvia

Lo script fa un backup dei file di avvio prima di toccarli. Dal PC, con la
microSD nel lettore, nella partizione `bootfs`:

```bash
cp cmdline.txt.bak-25 cmdline.txt
cp config.txt.bak-25 config.txt
```

Le modifiche a systemd si annullano invece dal Pi stesso:
`systemctl set-default graphical.target`, `systemctl enable <unità>`,
`rm /etc/systemd/system.conf.d/50-bmo-watchdog.conf`, e rinominare
`autologin.conf.bak-25` in `autologin.conf`.
