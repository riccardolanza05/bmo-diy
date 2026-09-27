import json

from bmo_core.persone import carica_persone


def _scrivi(percorso, righe):
    percorso.write_text(json.dumps(righe, ensure_ascii=False), encoding="utf-8")


def test_file_mancante_da_lista_vuota(tmp_path):
    assert carica_persone(tmp_path / "persone.json") == []


def test_file_rotto_da_lista_vuota(tmp_path):
    percorso = tmp_path / "persone.json"
    percorso.write_text("{non e' json valido", encoding="utf-8")
    assert carica_persone(percorso) == []


def test_legge_i_nomi(tmp_path):
    percorso = tmp_path / "persone.json"
    _scrivi(percorso, ["Finn", "Jake"])
    assert carica_persone(percorso) == ["Finn", "Jake"]


def test_non_e_una_lista_da_lista_vuota(tmp_path):
    percorso = tmp_path / "persone.json"
    _scrivi(percorso, {"nome": "Finn"})
    assert carica_persone(percorso) == []


def test_voci_non_stringa_o_vuote_vengono_scartate(tmp_path):
    percorso = tmp_path / "persone.json"
    _scrivi(percorso, ["Finn", "", "  ", 42, "  Jake  "])
    assert carica_persone(percorso) == ["Finn", "Jake"]
