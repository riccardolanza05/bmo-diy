from bmo_core.brain import ChiamataStrumento, Risposta
from bmo_core.prova_frasi import CATEGORIE_A_PARTE, FRASI, _f, nessuno, usa, valuta


def _risposta(*chiamate, testo="ok"):
    return Risposta(testo, [ChiamataStrumento(nome, argomenti, {}) for nome, argomenti in chiamate])


def test_ogni_frase_ha_i_suoi_attesi_e_non_si_ripete():
    # 43 e' il banco storico della #19, quello su cui si misura il 90%: deve
    # restare stabile anche quando si aggiungono categorie a parte.
    storiche = [f for f in FRASI if f.categoria not in CATEGORIE_A_PARTE]
    assert len(storiche) == 43
    assert all(f.attesi for f in FRASI)
    assert len({f.testo for f in FRASI}) == len(FRASI)


def test_la_lingua_sbagliata_e_un_fallimento():
    """Una risposta corretta detta dalla voce sbagliata resta un difetto (#42)."""
    inglese = _f("inglese", "Set a timer for ten minutes", usa("imposta_timer", durata=600), lingua="en")
    giusta = _risposta(("imposta_timer", {"minuti": 10.0, "etichetta": "x"}))
    giusta.lingua = "en"
    assert valuta(inglese, giusta)

    in_italiano = _risposta(("imposta_timer", {"minuti": 10.0, "etichetta": "x"}))
    in_italiano.lingua = "it"
    assert not valuta(inglese, in_italiano)


def test_le_frasi_storiche_non_controllano_la_lingua():
    """Altrimenti il 40/40 della #19 cambierebbe significato."""
    storiche = [f for f in FRASI if f.categoria not in CATEGORIE_A_PARTE]
    assert all(f.lingua is None for f in storiche)
    assert all(f.lingua is not None for f in FRASI if f.categoria == "inglese")


def test_numeri_esatti_e_testi_contenuti():
    frase = _f("musica", "Metti Radio Deejay", usa("riproduci_musica", query="deejay"))
    assert valuta(frase, _risposta(("riproduci_musica", {"query": "Radio DEEJAY"})))
    assert not valuta(frase, _risposta(("riproduci_musica", {"query": "rai radio 2"})))

    timer = _f("timer", "dieci minuti", usa("imposta_timer", durata=600))
    assert valuta(timer, _risposta(("imposta_timer", {"minuti": 10.0, "etichetta": "x"})))
    assert not valuta(timer, _risposta(("imposta_timer", {"minuti": 1, "etichetta": "x"})))
    assert not valuta(timer, _risposta())


def test_contano_solo_le_chiamate_riuscite():
    """Caso reale: un parametro inventato, corretto al giro dopo (il tè, prova del 19/9)."""
    frase = _f("timer", "Timer di tre minuti per il tè", usa("imposta_timer", durata=180))
    risposta = Risposta("ok", [
        ChiamataStrumento("imposta_timer", {"minuti": 3, "durata_sec": 180}, {"errore": "argomento inatteso"}),
        ChiamataStrumento("imposta_timer", {"minuti": 3, "etichetta": "te"}, {"stato": "ok"}),
    ])
    assert valuta(frase, risposta)


def test_esiti_alternativi_e_chiamate_in_piu():
    frase = _f("web", "Che ore sono a Tokyo?", nessuno(), usa("cerca_sul_web", query="tokyo"))
    assert valuta(frase, _risposta(testo="Sono le sei del mattino."))
    assert valuta(frase, _risposta(("cerca_sul_web", {"query": "ora attuale Tokyo"})))
    timer = _f("timer", "dieci minuti", usa("imposta_timer", durata=600))
    assert not valuta(timer, _risposta(("imposta_timer", {"minuti": 10}), ("imposta_timer", {"minuti": 10})))


def test_nessuno_strumento_richiede_testo():
    assert not valuta(_f("conversazione", "Ciao", nessuno()), _risposta(testo=""))


def test_durata_valutata_comunque_sia_divisa():
    arrosto = _f("timer", "un'ora e un quarto", usa("imposta_timer", durata=4500))
    assert valuta(arrosto, _risposta(("imposta_timer", {"ore": 1, "minuti": 15, "etichetta": "arrosto"})))
    assert valuta(arrosto, _risposta(("imposta_timer", {"minuti": 75, "etichetta": "arrosto"})))
    assert not valuta(arrosto, _risposta(("imposta_timer", {"ore": 1, "etichetta": "arrosto"})))
