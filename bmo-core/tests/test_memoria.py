import json

from bmo_core.memoria import MAX_VOCI, Voce, carica_diario


def _scrivi(percorso, righe):
    percorso.write_text(json.dumps(righe, ensure_ascii=False), encoding="utf-8")


def test_file_mancante_da_diario_vuoto(tmp_path):
    assert carica_diario(tmp_path / "memoria.json") == []


def test_file_rotto_da_diario_vuoto(tmp_path):
    percorso = tmp_path / "memoria.json"
    percorso.write_text("{non e' json valido", encoding="utf-8")
    assert carica_diario(percorso) == []


def test_legge_le_voci_scritte_a_mano(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(percorso, [{"testo": "non gli piacciono i funghi", "aggiunta_il": "2026-09-14"}])
    [voce] = carica_diario(percorso)
    assert voce == Voce("non gli piacciono i funghi", "2026-09-14", "manuale")


def test_fonte_esplicita_rispettata(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(percorso, [{"testo": "ceno alle 20", "aggiunta_il": "2026-09-20", "fonte": "modello"}])
    [voce] = carica_diario(percorso)
    assert voce.fonte == "modello"


def test_righe_malformate_non_bloccano_le_altre(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [
            {"testo": "voce buona", "aggiunta_il": "2026-09-20"},
            {"aggiunta_il": "senza testo"},
            "una stringa invece di un oggetto",
            42,
        ],
    )
    [voce] = carica_diario(percorso)
    assert voce.testo == "voce buona"


def test_un_oggetto_invece_di_una_lista_da_diario_vuoto(tmp_path):
    percorso = tmp_path / "memoria.json"
    percorso.write_text(json.dumps({"testo": "non e' una lista"}), encoding="utf-8")
    assert carica_diario(percorso) == []


def test_oltre_il_tetto_restano_solo_le_voci_piu_recenti(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(percorso, [{"testo": f"voce {i}", "aggiunta_il": "2026-09-20"} for i in range(MAX_VOCI + 5)])
    voci = carica_diario(percorso)
    assert len(voci) == MAX_VOCI
    assert [v.testo for v in voci] == [f"voce {i}" for i in range(5, MAX_VOCI + 5)]


def test_tetto_personalizzabile(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(percorso, [{"testo": f"voce {i}", "aggiunta_il": "2026-09-20"} for i in range(10)])
    voci = carica_diario(percorso, tetto=3)
    assert [v.testo for v in voci] == ["voce 7", "voce 8", "voce 9"]
