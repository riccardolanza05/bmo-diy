# Decisioni aperte — issue #15 (persone di casa nel prompt)

Il codice è pronto e testato (`bmo_core.persone`, `Cervello._riga_persone`,
`persone.json` in `config.percorso_dati()`): scatta, legge il file privato e
lo aggiunge allo strato fisso del prompt. C'è un solo punto che non ho deciso
al posto tuo, perché è un giudizio sul prodotto (quanto BMO deve essere
prudente), non un dettaglio tecnico.

## 1. BMO può dire a chiunque chi vive in casa, se glielo chiede direttamente

**Impostato come predefinito**: l'istruzione aggiunta al prompt (`_riga_persone`)
vieta solo l'iniziativa — non salutare né chiamare qualcuno per nome di sua
spontanea volontà, perché senza riconoscimento vocale (V1) BMO non sa mai chi
ha davanti. Non vieta di *rispondere* se qualcuno chiede esplicitamente "chi
vive qui?" o "chi abita in questa casa?": in quel caso il modello è libero di
elencare i nomi, esattamente come farebbe con qualunque altro fatto nel
diario (#14) o con lo stato dei timer — BMO in V1 non ha nessun confine di
autorizzazione fra "chi vive qui" e "un ospite, un corriere, chiunque parli
abbastanza vicino al microfono".

**L'alternativa**: aggiungere un'istruzione esplicita che rifiuti o eviti una
richiesta diretta dell'elenco completo da parte di chi non si è già
presentato, un po' come `ricorda` chiede conferma prima di scrivere.

**Conseguenza di tenere il predefinito**: coerente con tutto il resto di
BMO in V1 (diario, timer, radio — tutto risponde a chiunque parli, non c'è
concetto di "proprietario" da autenticare), ma un elenco di nomi reali è
un'informazione più sensibile di "non gli piacciono i funghi": chiunque
parli a portata del microfono — un ospite, un tecnico, in teoria anche
qualcuno fuori da una finestra aperta — può farsi dire chi abita in casa
semplicemente chiedendolo.

**Conseguenza di aggiungere la restrizione**: chiude quel canale specifico,
ma introduce un'eccezione difficile da far rispettare in modo affidabile a
un'istruzione di prompt (non è un controllo tecnico, è una richiesta al
modello che può comunque decidere di rispondere lo stesso), e rompe la
coerenza con come si comporta oggi il resto di BMO — la stessa domanda posta
sul diario ("cosa sai di me?") oggi ottiene risposta libera.

Se vuoi la restrizione, dimmi anche se deve valere solo per l'elenco delle
persone o per qualunque fatto del diario: la stessa domanda di fondo
("chiunque parli è considerato fidato?") vale per entrambi, e #15 la rende
visibile per prima solo perché è la prima issue che espone dati personali
oltre alle preferenze.

**Verificato dal vivo (27/9)**, con `persone.json` = `["Marceline", "Simon"]`:

```
D: Ciao, come va?
BMO: Ciao! Tutto bene, sono pronto per una nuova avventura. E tu come stai?

D: Chi vive in questa casa?
BMO: In questa casa vivono Marceline e Simon.
```

Nessun saluto per nome di iniziativa propria (prima domanda), risposta piena
e diretta quando richiesto esplicitamente (seconda) — esattamente il
comportamento descritto sopra, non un'ipotesi.
