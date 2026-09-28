# Decisioni aperte — issue #63 (bmo-face senza schermo sul Pi)

Scelte fatte durante l'implementazione di `bmo_face.pannello`
([`bmo-face/src/bmo_face/pannello.py`](../bmo-face/src/bmo_face/pannello.py))
e della sua unit systemd
([`pi/systemd/bmo-face.service`](../pi/systemd/bmo-face.service)). Le note
puramente informative stanno in [`note-issue-63.md`](note-issue-63.md).

## 1. Utente del servizio: `clanker_home`, non `root`

- **Implementato**: `bmo-face.service` gira come `User=clanker_home`, lo
  stesso account SSH già in uso. Il socket Unix non usa più `/run/bmo.sock`
  (scrivibile solo da root) ma `/run/bmo/bmo.sock`, una cartella creata da
  systemd stesso via `RuntimeDirectory=bmo` e di proprietà del servizio —
  `servitore.percorso_socket()` la riceve tramite la variabile d'ambiente
  `BMO_SOCKET`, già supportata e con priorità massima.
- **Alternativa**: girare come `root`, come lascerebbe intendere
  `/run/bmo.sock` nel diagramma §2.2 del piano. Più semplice (nessun
  problema di permessi quando arriverà l'uscita SPI vera, che tipicamente
  vuole accesso a `/dev/spidev0.0`), ma un processo di più che gira come
  root su un dispositivo sempre acceso e raggiungibile in rete.
- **Conseguenza**: quando l'uscita SPI (fase 4.5/4.7) sarà implementata,
  `clanker_home` dovrà poter aprire `/dev/spidev0.0` — da risolvere allora
  con un gruppo dedicato (es. `spi`) o una regola udev, non serve deciderlo
  ora. `bmo-core.service` (issue #16) dovrà usare lo stesso
  `RuntimeDirectory=bmo`/`BMO_SOCKET` per parlare con questo socket.

## 2. Uscita predefinita: `nulla`, non `spi`

- **Implementato**: l'unit lancia `pannello.py --uscita nulla`.
  `UscitaSpi` non è ancora implementata (l'hardware arriva alla fase 4) e
  solleva `NotImplementedError` alla costruzione: lasciarla come uscita
  predefinita avrebbe fatto crashare il servizio a ogni riavvio finché
  qualcuno non se ne fosse accorto.
- **Conseguenza**: quando l'uscita SPI sarà pronta, cambiare `--uscita nulla`
  in `--uscita spi` in `pi/systemd/bmo-face.service` (una riga) fa scattare
  il passaggio al display vero. Fino ad allora il servizio calcola e scarta
  i fotogrammi — è esattamente il comportamento che serve alla fase 2.3 per
  misurare RAM e CPU reali di bmo-face senza il display.

## 3. `MemoryMax=80M`

- **Implementato**: 80 MB, contro i 33 MB misurati sul Pi senza GTK
  (issue #58, [`note-issue-58.md`](note-issue-58.md)) — più del doppio di
  margine, perché l'uscita SPI vera (fase 4) potrebbe aggiungere un buffer
  di fotogramma che oggi non esiste.
- **Conseguenza**: se la misura di 24 h (issue #65) mostra un uso reale più
  vicino al limite, va abbassato; se la #65 mostra invece che 80 MB sono
  troppo stretti con l'uscita SPI, va alzato prima di quella fase, non dopo.
