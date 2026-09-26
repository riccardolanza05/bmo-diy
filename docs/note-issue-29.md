# Note informative — issue #29 (memoria di sessione)

Cose da sapere su questa implementazione, non decisioni da prendere (quelle
sono in `docs/decisioni-issue-29.md`).

- **Non provato dal vivo.** Questa sessione non aveva una `GEMINI_API_KEY`
  disponibile: tutto è verificato con la suite offline (251 test, inclusi
  `tests/test_sessione.py` e i casi di sessione in `tests/test_brain.py`),
  non con una conversazione vera. Il criterio di uscita dell'issue ("una
  conversazione di almeno cinque scambi in cui BMO usa ciò che è stato detto
  prima") va ancora verificato con `python -m bmo_core.brain --conversazione`.
- **`dopo_il_turno()` va chiamato da chi usa `Cervello` direttamente.**
  `Macchina.turno()` lo fa già (dopo `self.voce(...)`), ma chi scrive un
  altro punto di ingresso (uno script, una prova) e dimentica di chiamarlo
  perde silenziosamente lo storico di quel turno — nessun errore, la
  conversazione funziona lo stesso, semplicemente BMO non si ricorda più
  niente di quel turno al giro dopo. Vale la pena grepparlo se in futuro
  spunta un altro punto che chiama `rispondi()`.
- **Mitigazioni sull'estrazione, già applicate nel codice** (non decisioni,
  sono già dentro `Cervello._estrai_verso_diario`): il diario attuale entra
  nel prompt ("Voci già nel diario"), righe con punti elenco o numerazione
  ripulite invece di scartate, un sentinel (`NIENTE`) per "niente da
  ricordare" invece di contare su una riga vuota, niente doppioni di voci
  già nel diario (confronto case-insensitive, un secondo controllo lato
  codice oltre al prompt), al massimo 3 voci nuove per chiamata. Restano
  euristiche: se il modello risponde in un formato abbastanza diverso da
  quello richiesto, o riformula un fatto già noto invece di ripeterlo
  identico, una voce può comunque finire nel diario duplicata o più sporca
  del previsto. Vale la pena rileggere `memoria.json` dopo le prime
  conversazioni vere.
- **Le richieste silenziose di `dopo_il_turno()` non bloccano mai la voce**:
  girano tutte dopo che `Macchina.turno()` ha già chiamato `self.voce(...)`
  (verificato da `tests/test_macchina.py::test_dopo_il_turno_gira_solo_dopo_che_la_voce_ha_parlato`),
  e non sollevano mai — anche un `OSError` dalla scrittura del diario (es.
  filesystem in sola lettura sul Pi) resta dentro `dopo_il_turno()`. Un solo
  budget di tempo condiviso (`BUDGET_DOPO_IL_TURNO_S`, 8 s) copre l'intera
  catena di richieste di un turno, così un sovraccarico del modello non
  tiene BMO sordo per il tempo di quattro tentativi pieni.
- **`memoria.md` (#14) non era ancora documentato nel README** di `bmo-core`
  prima di questa issue: la nuova sezione "Memoria di sessione" lo introduce
  di striscio (stesso file `memoria.json`, `fonte="modello"`) ma non
  documenta lo strumento `ricorda` né la conferma vocale dell'#17. Non è
  stato ampliato oltre perché fuori dallo scopo della #29.
- **La tabella `Struttura` in cima al README di `bmo-core`** era già
  disallineata prima di questa modifica (non elenca `brain.py`, `memoria.py`,
  `modelli.py`, `strumenti.py`, `tts.py`, `vad.py`, `prova_frasi.py`): non
  l'ho toccata per non allargare lo scopo di questo PR, ma è un buon
  candidato per un piccolo PR di sola documentazione.
