# Decisioni da prendere — issue #83 (avvio automatico dopo lo stacco della corrente)

Numeri e metodo in [`note-issue-83.md`](note-issue-83.md). Il codice di BMO non è stato toccato: solo unit
e uno script di avvio.

## 1. Stacco della corrente e scheda SD

**Opzioni:** (a) lasciare il root `ext4 rw` com'è (journal di ext4 + `fsck` all'avvio); (b) root in sola
lettura con overlay (`overlayroot`): la SD non si corrompe, ma niente cambia più su disco senza passare da
un comando.

**Implementato: (a).**

**Conseguenza:** (a) uno stacco mentre il Pi scrive (memoria della sessione, dati, `apt`) può lasciare un
file corrotto o, raramente, un filesystem da riparare: `fsck` all'avvio lo ripara di solito, ma un
avvio con `fsck` lungo ritarda BMO di decine di secondi. Il carico normale di BMO scrive poco. (b)
elimina il rischio, ma timer, radio salvate e memoria della sessione si perderebbero a ogni riavvio
(servirebbe una partizione di dati a parte): è un cambiamento strutturale, non l'ho fatto.

## 2. Mixer: `alsactl store` oppure lo script all'avvio

**Opzioni:** (a) solo `alsactl store` (stato salvato, ripristinato da `alsa-restore`); (b) anche lo script
`bmo-hat-audio` all'avvio, che reimposta i valori.

**Implementato: (b)**, perché lo stato salvato si scrive allo spegnimento pulito: se stacchi la corrente
dopo aver cambiato il mixer a mano, al riavvio tornano i valori del kernel (cattura +30 dB, ingresso e
uscita spenti).

**Conseguenza:** (b) i valori sono scritti in due posti (`abilita-hat.sh` e `bmo-hat-audio.sh`): se li
cambi, vanno cambiati tutti e due; il vantaggio è che ogni avvio parte dagli stessi valori misurati.

## 3. Se la scheda audio non compare

**Opzioni:** (a) `bmo-core` parte comunque e riprova (`Restart=always`, `Wants=`); (b) `Requires=` e non
parte finché non c'è la scheda.

**Implementato: (a).** Con (a) la faccia c'è e BMO prova a sentire; senza HAT non risponde e continua a
riprovare ogni 2 s (ogni tentativo carica la wake word, ~100 MB: CPU al 100% per qualche secondo e
log a raffica). (b) lascerebbe `bmo-core` fermo con un messaggio chiaro, ma senza ripartire da solo se la
scheda arriva dopo.
