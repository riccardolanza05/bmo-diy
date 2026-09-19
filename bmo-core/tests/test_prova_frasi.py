from bmo_core.brain import ChiamataStrumento, Risposta
from bmo_core.prova_frasi import FRASI, _f, nessuno, usa, valuta


def _risposta(*chiamate, testo="ok"):
    return Risposta(testo, [ChiamataStrumento(nome, argomenti, {}) for nome, argomenti in chiamate])


def test_quaranta_frasi_con_attesi():
    assert len(FRASI) == 40
    assert all(f.attesi for f in FRASI)
    assert len({f.testo for f in FRASI}) == 40


def test_numeri_esatti_e_testi_contenuti():
    frase = _f("musica", "Metti Radio Deejay", usa("riproduci_musica", sorgente="radio", query="deejay"))
    assert valuta(frase, _risposta(("riproduci_musica", {"sorgente": "radio", "query": "Radio DEEJAY"})))
    assert not valuta(frase, _risposta(("riproduci_musica", {"sorgente": "libreria", "query": "deejay"})))

    timer = _f("timer", "dieci minuti", usa("imposta_timer", durata_secondi=600))
    assert valuta(timer, _risposta(("imposta_timer", {"durata_secondi": 600.0, "etichetta": "x"})))
    assert not valuta(timer, _risposta(("imposta_timer", {"durata_secondi": 60, "etichetta": "x"})))
    assert not valuta(timer, _risposta())


def test_imposta_espressione_non_conta():
    frase = _f("conversazione", "Ciao", nessuno())
    assert valuta(frase, _risposta(("imposta_espressione", {"stato": "felice"}), testo="Ciao!"))
    foto = _f("foto", "Cosa vedi?", usa("scatta_foto"))
    assert valuta(foto, _risposta(("imposta_espressione", {"stato": "sorpreso"}), ("scatta_foto", {"motivo": "m"})))


def test_esiti_alternativi_e_chiamate_in_piu():
    frase = _f("web", "Che ore sono a Tokyo?", nessuno(), usa("cerca_sul_web", query="tokyo"))
    assert valuta(frase, _risposta(testo="Sono le sei del mattino."))
    assert valuta(frase, _risposta(("cerca_sul_web", {"query": "ora attuale Tokyo"})))
    timer = _f("timer", "dieci minuti", usa("imposta_timer", durata_secondi=600))
    assert not valuta(timer, _risposta(("imposta_timer", {"durata_secondi": 600}), ("imposta_timer", {"durata_secondi": 600})))


def test_nessuno_strumento_richiede_testo():
    assert not valuta(_f("conversazione", "Ciao", nessuno()), _risposta(testo=""))
