# Decisioni aperte — issue #25 (irrobustimento del Pi per il 24/7)

Scelte fatte durante l'implementazione, applicate sul Pi il 27/9 con
[`pi/irrobustisci.sh`](../pi/irrobustisci.sh). Ognuna ha un valore
predefinito già in vigore: cambiarla vuol dire modificare una riga dello
script e rilanciarlo. Le note puramente informative (misure, cose scoperte)
stanno in [`note-issue-25.md`](note-issue-25.md).

## 1. `gpu_mem=16` e la fotocamera della fase 4.8

- **Implementato**: `gpu_mem=16`, come dice il piano. Restituisce 48 MB a
  Linux (`MemTotal` da 415 a 463 MB): è la singola voce che vale di più.
- **Il rischio**: la documentazione ufficiale di `config.txt` (sezione *Boot
  Options*) dice che `gpu_mem=16` è l'unico modo per attivare il firmware
  ridotto (`start_cd.elf`), che *«removes support for codecs, 3D and debug
  logging»*. La fotocamera non è citata esplicitamente, ma sul Pi 3 l'ISP che
  elabora le immagini della OV5647 gira proprio sul firmware del
  VideoCore: è possibile che `libcamera-still` non funzioni.
- **Alternativa**: `gpu_mem=32` o `64` fin da subito. Si evita la sorpresa
  alla fase 4.8, al prezzo di 16–48 MB in meno per tutte le misure della
  fase 2.

**Conseguenza della scelta**: per ora nessuna, perché la fotocamera non è
ancora comprata. Alla fase 4.8, se `libcamera-still` fallisce, si alza
`gpu_mem` al minimo valore con cui funziona e si **rifanno i conti della
§2.8** con quei MB in meno. Se invece si preferisce che le misure della fase
2 riflettano già il sistema definitivo, conviene alzarlo adesso.

## 2. Pacchetti del desktop: disabilitati, non disinstallati

- **Implementato**: `multi-user.target` e `systemctl disable` dei servizi
  (cups, bluetooth, wayvnc, rpcbind/NFS, udisks2, accounts-daemon, due
  servizi di test del firmware). Chromium, Firefox, labwc e lightdm restano
  installati ma non partono.
- **Alternativa**: `apt purge` del desktop, o riflashare con Raspberry Pi OS
  Lite.

**Conseguenza della scelta**: la RAM a riposo è identica nei due casi, perché
un pacchetto che non parte non occupa memoria. Si perdono ~3–4 GB di microSD,
che ha 22 GB liberi. In cambio si può tornare al desktop con un comando
(`systemctl set-default graphical.target`), utile per il debug. Il riflash
Lite diventa interessante solo insieme a un ripensamento più ampio del
sistema operativo (vedi la issue sulla RAM).

## 3. Dimensione della zram: il default del sistema, non i 256 MB del piano

- **Implementato**: nessuna modifica. `rpi-swap` dimensiona la zram sulla RAM
  (oggi ~462 MB di swap virtuale, zstd).
- **Alternativa**: fissarla a 256 MB in `/etc/rpi/swap.conf`, come il piano.

**Conseguenza della scelta**: la dimensione della zram è un tetto, non una
prenotazione: finché non si usa non occupa niente. Un tetto più alto lascia
al kernel più spazio per spostare in swap compresso le pagine fredde prima
di arrivare all'OOM killer; il rischio è che un processo che perde memoria
venga ucciso più tardi, dopo aver rallentato tutto. Il piano aveva scelto 256
MB senza una misura dietro. La fase 2.3 (24 h con `systemd-cgtop`) è il posto
giusto per decidere.

## 4. avahi resta acceso

- **Implementato**: avahi-daemon attivo.
- **Alternativa**: spegnerlo, come assume il bilancio della §2.8, e
  raggiungere il Pi per indirizzo IP (o con una voce fissa in `/etc/hosts`
  del PC).

**Conseguenza della scelta**: ~3–5 MB in più a riposo, in cambio di
`ssh clanker.local` che funziona anche quando la rete Lambrate cambia
l'indirizzo del Pi. Spegnerlo ha senso solo se un giorno serve davvero ogni
MB, e a quel punto conviene prima prenotare un IP fisso sul router.

## 5. Niente HDMI e niente Bluetooth

- **Implementato**: `dtoverlay=vc4-kms-v3d` commentato e
  `dtoverlay=disable-bt` aggiunto. Non erano nel piano: li ho aggiunti
  perché, dopo i primi due blocchi, la RAM era ancora lontana dal criterio
  di uscita, e il kernel teneva caricati lo stack grafico (vc4 + drm) e lo
  stack Bluetooth senza che nessuno li usasse. Misurato: +9 MB disponibili,
  CMA da 256 a 64 MB, moduli del kernel da 60 a 43.
- **Alternativa**: lasciarli, per poter collegare un monitor HDMI al Pi in
  caso di problemi o usare un accessorio Bluetooth.

**Conseguenza della scelta**: un monitor collegato all'HDMI mostra solo la
console del firmware, niente desktop (che comunque non parte più). Il
display di BMO non è toccato: va su SPI tramite `spidev`, non passa da KMS.
L'audio del jack ora è la scheda ALSA numero 0, perché la scheda HDMI
(`vc4hdmi`) non esiste più. Il HAT WM8960 (fase 4.1) si aggiungerà come
scheda nuova. Per tornare indietro: togliere il `#` davanti a
`dtoverlay=vc4-kms-v3d` e la riga `dtoverlay=disable-bt`, poi riavviare.

## 6. cloud-init resta installato e attivo

- **Implementato**: nessuna modifica.
- **Alternativa**: `touch /etc/cloud/cloud-init.disabled`.

**Conseguenza della scelta**: cloud-init gira solo all'avvio (qualche secondo
e qualche MB, poi esce) e non riapplica la configurazione del primo avvio,
perché l'identificativo dell'istanza nella `cmdline.txt` resta lo stesso. Le
connessioni di rete `netplan-*` sono state generate da lui: disabilitarlo non
le cancella, ma è un cambiamento sulla rete di un Pi raggiungibile solo via
Wi-Fi, per un guadagno piccolo. Lasciato com'è finché non c'è un motivo
misurato.

## 7. Niente login automatico sulla console

- **Implementato**: il drop-in `getty@tty1.service.d/autologin.conf`
  dell'immagine col desktop è rinominato in `.bak-25`, quindi ignorato.
- **Alternativa**: lasciarlo, come faceva l'immagine.

**Conseguenza della scelta**: chi collega tastiera e monitor al Pi deve
inserire la password di `clanker_home`, invece di ritrovarsi già dentro.
In cambio, a riposo non gira nessuna sessione utente, quindi niente pipewire
e wireplumber: circa 18 MB disponibili in più, misurati. BMO girerà come
servizio di sistema, quindi non ha bisogno di nessun login.
