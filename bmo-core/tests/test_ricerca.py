from bmo_core.ricerca import LUNGHEZZA_ESTRATTO, cerca


def _finto(risultati):
    def cercatore(query, quanti):
        return risultati[:quanti]

    return cercatore


def test_tre_risultati_con_titolo_estratto_e_url():
    trovati = [
        {"title": f"Titolo {n}", "body": f"Testo {n}", "href": f"https://esempio.it/{n}"}
        for n in range(5)
    ]
    esito = cerca("meteo Torino domani", cercatore=_finto(trovati))
    assert esito["stato"] == "ok"
    assert len(esito["risultati"]) == 3  # non di più: ogni risultato costa token
    assert esito["risultati"][0] == {
        "titolo": "Titolo 0",
        "estratto": "Testo 0",
        "url": "https://esempio.it/0",
    }


def test_estratto_accorciato_senza_tagliare_le_parole():
    lungo = {"title": "T", "body": "parola " * 100, "href": "u"}
    [risultato] = cerca("x", cercatore=_finto([lungo]))["risultati"]
    assert len(risultato["estratto"]) <= LUNGHEZZA_ESTRATTO + 1
    assert risultato["estratto"].endswith("…")


def test_nessun_risultato_lo_dice():
    assert cerca("qualcosa", cercatore=_finto([]))["stato"] == "nessun_risultato"


def test_la_ricerca_rotta_non_fa_morire_bmo():
    def esplode(query, quanti):
        raise ConnectionError("rete giù")

    esito = cerca("meteo", cercatore=esplode)
    assert esito["stato"] == "errore"
    assert "ConnectionError" in esito["motivo"]


def test_senza_la_libreria_lo_dice_invece_di_sbagliare():
    def manca(query, quanti):
        raise ImportError("no module named ddgs")

    assert cerca("meteo", cercatore=manca)["stato"] == "non_disponibile"


def test_query_vuota():
    assert "errore" in cerca("   ", cercatore=_finto([]))
