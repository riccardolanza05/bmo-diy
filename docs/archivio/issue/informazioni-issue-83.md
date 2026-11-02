# Informazioni — issue #83 (avvio automatico)

Cose solo informative: niente da decidere. Dettagli in [`note-issue-83.md`](note-issue-83.md).

- **Cosa riparte da solo all'accensione** (dopo `deploy.sh`): `bmo-hat-audio` (mixer), `bmo-face` (display
  SPI, faccia vera) e `bmo-core` (wake word, pulsante, Gemini). Servono rete (Wi-Fi già configurato) e la
  chiave in `/etc/bmo/env`, che c'è già.
- **Quanto ci mette** (stimato dai tempi visti oggi, non misurato dal vivo): ~30-60 s dallo stacco a «BMO è
  sveglio». Dopo, la wake word risponde subito.
- **Cosa non ripartirebbe da solo:** la camera grezza e il pulsante si leggono a ogni uso, niente da
  riavviare. La radio salvata riparte solo dal comando vocale (non si ricorda cosa suonava).
- **Se dopo lo stacco BMO è muto:** `journalctl -u bmo-core -b` (il journal è volatile, parte da
  quell'avvio) e `systemctl status bmo-hat-audio bmo-face bmo-core`. Il caso più probabile è la rete
  non ancora su; `bmo-core` riprova da solo.
- **Il journal di systemd è volatile**: dopo uno stacco i log del giro precedente non ci sono più.
