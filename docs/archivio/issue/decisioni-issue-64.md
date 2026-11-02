# Decisioni prese durante l'issue #64 (adapter audio del Pi)

Decisioni mie, prese per non bloccare il lavoro (issue scritta per essere
implementata e testata con dati sintetici, senza il HAT WM8960): opzioni
valutate, cosa è implementato di default, conseguenze concrete di scegliere
l'altra opzione. Da rivedere quando arriva l'hardware vero (fase 4.1/4.3).

## 1. Come si trova il nome del controllo volume ALSA

**Opzioni:**
- (a) *Rilevamento automatico* con `amixer scontrols`, filtrato ai controlli
  che espongono davvero un volume regolabile (non switch on/off puri come
  "Auto-Mute Mode"), con un ordine di preferenza fra i nomi noti
  (`Speaker`, `PCM`, `Master`, `Playback`) e una variabile d'ambiente
  (`BMO_VOLUME_ALSA_CONTROLLO`) per forzare un nome specifico.
- (b) *Nome fisso*, cambiato a mano nel codice quando si scopre quello giusto
  per ciascuna scheda (quello che faceva l'issue prima: `"Master"`, sbagliato
  per entrambe le schede viste finora).

**Implementato: (a).** Verificato dal vivo il 28/9/2026 sul Pi reale (jack
integrato, nessun HAT montato): `amixer scontrols` restituisce un solo
controllo, `'PCM'`, con `[78%]`, coerente con l'unica ipotesi che l'issue
avanzava per il jack. Il rilevamento lo trova senza bisogno della variabile
d'ambiente.

**Conseguenza di (a) invece di (b):** funziona senza modifiche sia oggi
(jack, `PCM`) sia — probabilmente, da riverificare — quando arriverà il
WM8960 (`Speaker`/`Playback` secondo la documentazione Waveshare, non
ancora confermato dal vivo). Il rischio è che se una scheda futura avesse
più uscite regolabili contemporaneamente (es. jack *e* HDMI insieme) il
rilevamento potrebbe scegliere quella sbagliata: per quel caso c'è la
variabile d'ambiente, ma il codice da solo non sa distinguere "quale altoparlante
sta davvero suonando" da "quale controllo ha un volume".

## 2. Cosa risponde lo strumento quando il volume di sistema non cambia davvero

**Opzioni:**
- (a) Solo un avviso su stderr (log), il risultato dello strumento resta
  `{"stato": "ok", ...}` come prima — il sintomo dell'issue ("BMO risponde
  ok ma non cambia niente") resterebbe identico dal punto di vista di chi
  parla con BMO, solo con una riga in più nei log del servizio.
- (b) Il risultato diventa `{"stato": "errore", ..., "motivo": "..."}` quando
  il comando ALSA fallisce davvero (non quando semplicemente non c'è nessuna
  funzione iniettata, quel caso resta "ok" come da `volumi.py` esistente).

**Implementato: (b).** `VolumeAdapter.imposta()` ora restituisce un booleano
(successo/fallimento) invece di `None`; `volumi.regola_volume` lo controlla
e cambia lo stato solo se il valore è esplicitamente `False` (un `None`,
come restituiscono le funzioni iniettate nei test esistenti, resta "ok":
nessun test esistente si è dovuto modificare per questo).

**Conseguenza di (b) invece di (a):** il risultato della function call
arriva a Gemini con il campo `motivo` quando il volume non è cambiato
davvero, quindi il modello *può* dirlo a voce invece di confermare un
cambiamento inesistente — ma questo non è stato verificato con un giro
vero attraverso Gemini (serve la chiave API e un turno completo, fuori
dallo scopo "dati sintetici" di questa issue): è verificato solo che il
dizionario Python contenga l'informazione giusta.

## 3. Dove avviene la conversione del microfono (S32 stereo 48 kHz -> S16 mono 16 kHz)

**Opzioni:**
- (a) *Nel dispositivo ALSA*: aprire `arecord` su `plughw:0,0` (o su un
  device `default` definito da un `~/.asoundrc` come quello abbozzato nel
  piano, §2.10) chiedendo direttamente il formato di destinazione, e
  lasciare che il plugin `plug` di ALSA faccia resample/downmix/troncamento
  in C, fuori dal processo Python.
- (b) *In Python, dentro bmo-core*: catturare al formato nativo
  (`hw:0,0`, S32_LE stereo 48 kHz) e convertire al volo con numpy
  (`ArecordConvertitoreAdapter`), prima di consegnare i byte al resto del
  codice (VAD, wake word).

**Implementato: (b).**

**Perché non (a):** il `~/.asoundrc` del piano (§2.10) non è mai stato
distribuito da nessuno script di provisioning (verificato: nessun
riferimento fuori dalla documentazione) — affidarsi a `plughw`/`default`
avrebbe reso la conversione dipendente da una configurazione di sistema non
ancora presente sul Pi reale, e il cui comportamento con il driver del
WM8960 non è verificabile senza il HAT montato: esattamente il tipo di
guasto silenzioso ("sembra configurato, in realtà non funziona") di cui si
lamenta il punto 1 di questa stessa issue. La versione Python è invece
interamente scrivibile e testabile ora con dati sintetici, come chiede il
testo dell'issue.

**Il criterio di scelta che l'issue chiedeva ("misurando la CPU sul Pi")
è stato misurato per davvero**, non solo ipotizzato: uno script di
benchmark (dati sintetici, buffer casuali da 4096 byte come li produce
`arecord`) eseguito sul Pi 3 A+ reale via SSH mostra un costo di ~2,4% di un
singolo core per 30 s di audio continuo elaborato; una seconda misura con un
tono sintetico reale (440 Hz, 2 s) attraverso il percorso di codice vero
(non solo lo script isolato) è scesa a ~1%. Su un quad-core con margine
enorme (bmo-core oggi usa ~108-250 MB di RAM e una piccola frazione di CPU
anche con ONNX della wake word attivo), è trascurabile: non c'è stato
bisogno di misurare anche il costo lato-C di `plughw` per dichiarare (b)
la scelta giusta.

**Conseguenza:** quando arriva il HAT WM8960, se il suo driver esponesse
nativamente un formato diverso da S32_LE stereo (da verificare con
`arecord --dump-hw-params -D hw:1,0` o simile, non ancora possibile), il
costruttore di `ArecordConvertitoreAdapter` solleva subito un `ValueError`
esplicito invece di convertire dati sbagliati in silenzio — il posto giusto
per aggiornare `formato_nativo`/estendere la conversione a un secondo
formato è quel momento, non ora.

Nota tecnica sulla conversione stessa: il downmix stereo->mono è la media
dei due canali (i due MEMS del WM8960 guardano punti diversi della stanza,
scartarne uno perderebbe informazione utile); la decimazione 48kHz->16kHz
usa un filtro anti-aliasing elementare (media di ogni gruppo di 3 campioni,
non un semplice `[::3]`) per non far rientrare come rumore le frequenze
sopra 8 kHz; da 32 a 16 bit si tiene la metà più significativa (`>> 16`),
non un troncamento che ignorerebbe il segno.

## 4. Non toccato: condivisione del microfono fra wake word e VAD (dsnoop)

Non è una decisione ma il motivo per cui il punto 3 non ne ha avuto
bisogno: leggendo `richiamo.py` e `macchina.py`, oggi il microfono non è
mai aperto due volte in contemporanea — `RichiamoWakeWord.ascolta_punteggio()`
chiude il proprio flusso (`flusso.close()`) *prima* che lo stato ASCOLTO
apra un nuovo `arecord` per `registra_fino_al_silenzio()`. Il `dsnoop`
del piano (§2.10, §4.3) serve per un caso che oggi non si presenta ancora
nel codice. Se in futuro si aggiunge un ascolto della wake word sempre
attivo in background mentre si registra, questo andrà rivisto — ma è
lavoro di un'altra issue, non di questa.
