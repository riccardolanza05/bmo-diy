import pytest

from bmo_core.volumi import CANALI, leggi_volume, regola_volume


def test_leggi_volume_predefinito_senza_file(tmp_path):
    assert leggi_volume("voce", tmp_path / "volumi.json") == 100
    assert leggi_volume("timer", tmp_path / "volumi.json") == 100


def test_regola_volume_radio_chiama_solo_imposta_radio(tmp_path):
    chiamati = {"radio": None, "sistema": None}
    risultato = regola_volume(
        55,
        "radio",
        imposta_radio=lambda p: chiamati.__setitem__("radio", p),
        imposta_sistema=lambda p: chiamati.__setitem__("sistema", p),
        percorso_file=tmp_path / "volumi.json",
    )
    assert risultato == {"stato": "ok", "percentuale": 55, "canale": "radio"}
    assert chiamati == {"radio": 55, "sistema": None}


def test_regola_volume_sistema_chiama_solo_imposta_sistema(tmp_path):
    chiamati = {"radio": None, "sistema": None}
    regola_volume(
        30,
        "sistema",
        imposta_radio=lambda p: chiamati.__setitem__("radio", p),
        imposta_sistema=lambda p: chiamati.__setitem__("sistema", p),
        percorso_file=tmp_path / "volumi.json",
    )
    assert chiamati == {"radio": None, "sistema": 30}


def test_regola_volume_predefinito_e_sistema(tmp_path):
    chiamati = []
    regola_volume(20, imposta_sistema=chiamati.append, percorso_file=tmp_path / "volumi.json")
    assert chiamati == [20]


def test_regola_volume_voce_e_timer_persistono_nel_file_non_chiamano_niente(tmp_path):
    percorso = tmp_path / "volumi.json"
    chiamato = []
    regola_volume(45, "voce", imposta_radio=chiamato.append, imposta_sistema=chiamato.append, percorso_file=percorso)
    regola_volume(80, "timer", imposta_radio=chiamato.append, imposta_sistema=chiamato.append, percorso_file=percorso)
    assert chiamato == []  # né radio né sistema toccati
    assert leggi_volume("voce", percorso) == 45
    assert leggi_volume("timer", percorso) == 80


def test_i_due_canali_del_file_sono_indipendenti(tmp_path):
    percorso = tmp_path / "volumi.json"
    regola_volume(45, "voce", percorso_file=percorso)
    assert leggi_volume("voce", percorso) == 45
    assert leggi_volume("timer", percorso) == 100  # non toccato, resta il predefinito


def test_fuori_range_solleva(tmp_path):
    with pytest.raises(ValueError):
        regola_volume(101, percorso_file=tmp_path / "volumi.json")
    with pytest.raises(ValueError):
        regola_volume(-1, percorso_file=tmp_path / "volumi.json")


def test_canale_sconosciuto_solleva(tmp_path):
    with pytest.raises(ValueError):
        regola_volume(50, "musica", percorso_file=tmp_path / "volumi.json")


def test_file_rotto_non_blocca_la_lettura(tmp_path):
    percorso = tmp_path / "volumi.json"
    percorso.write_text("{non e' json valido", encoding="utf-8")
    assert leggi_volume("voce", percorso) == 100


def test_canali_dichiarati():
    assert set(CANALI) == {"radio", "voce", "timer", "sistema"}
