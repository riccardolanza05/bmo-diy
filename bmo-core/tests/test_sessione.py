from google.genai import types

from bmo_core.sessione import StoricoSessione


def test_sessione_vuota_non_e_mai_scaduta():
    sessione = StoricoSessione()
    assert sessione.scaduta(10_000.0, inattivita_s=1.0) is False


def test_scaduta_solo_dopo_linattivita_indicata():
    sessione = StoricoSessione()
    sessione.aggiungi("Ciao", "Ciao!", adesso=0.0, token_prompt=10)
    assert sessione.scaduta(299.0, inattivita_s=300.0) is False
    assert sessione.scaduta(300.0, inattivita_s=300.0) is True


def test_oltre_tetto_confronta_lultimo_conteggio():
    sessione = StoricoSessione()
    sessione.aggiungi("Ciao", "Ciao!", adesso=0.0, token_prompt=59_999)
    assert sessione.oltre_tetto(60_000) is False
    sessione.aggiungi("Ancora", "Sì!", adesso=1.0, token_prompt=60_000)
    assert sessione.oltre_tetto(60_000) is True


def test_svuota_azzera_tutto():
    sessione = StoricoSessione()
    sessione.aggiungi("Ciao", "Ciao!", adesso=5.0, token_prompt=100)
    sessione.svuota()
    assert sessione.turni == []
    assert sessione.riassunto is None
    assert sessione.ultimo_turno is None
    assert sessione.token_prompt == 0
    assert sessione.attiva is False


def test_sostituisci_con_riassunto_non_chiude_la_sessione():
    sessione = StoricoSessione()
    sessione.aggiungi("Ciao", "Ciao!", adesso=5.0, token_prompt=60_000)
    sessione.sostituisci_con_riassunto("  Si parlava di timer.  ")
    assert sessione.turni == []
    assert sessione.riassunto == "Si parlava di timer."
    # Non è una chiusura: l'ultimo turno resta quello vero, la sessione può
    # ancora scadere per inattività allo stesso modo di prima.
    assert sessione.ultimo_turno == 5.0
    assert sessione.attiva is True


def test_sostituisci_con_riassunto_vuoto_lascia_nessun_riassunto():
    sessione = StoricoSessione()
    sessione.aggiungi("Ciao", "Ciao!", adesso=5.0, token_prompt=60_000)
    sessione.sostituisci_con_riassunto("   ")
    assert sessione.riassunto is None
    assert sessione.attiva is False


def test_testo_per_estrazione_include_riassunto_e_turni_nellordine():
    sessione = StoricoSessione(riassunto="Si parlava di cena.")
    sessione.aggiungi("Che ore sono?", "Le sette.", adesso=0.0, token_prompt=10)
    testo = sessione.testo_per_estrazione()
    righe = testo.splitlines()
    assert righe[0] == "[Riassunto di prima] Si parlava di cena."
    assert righe[1] == "Persona: Che ore sono?"
    assert righe[2] == "BMO: Le sette."


def test_contenuti_vuoti_per_una_sessione_appena_creata():
    assert StoricoSessione().contenuti() == []


def test_contenuti_non_includono_mai_il_riassunto():
    """Due `Content` di seguito con `role="user"` non è una forma garantita
    dall'API multi-turno: il riassunto va nello strato STATO, non qui."""
    sessione = StoricoSessione(riassunto="Si parlava di timer.")
    sessione.aggiungi("Metti anche la sveglia", "Fatto.", adesso=0.0, token_prompt=10)
    contenuti = sessione.contenuti()
    assert len(contenuti) == 2  # solo il turno, il riassunto non c'è
    assert contenuti[0] == types.Content(role="user", parts=[types.Part.from_text(text="Metti anche la sveglia")])
    assert contenuti[1] == types.Content(role="model", parts=[types.Part.from_text(text="Fatto.")])
