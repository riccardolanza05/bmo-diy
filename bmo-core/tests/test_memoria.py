import json

from bmo_core.memoria import MAX_VOCI_AUTOMATICHE, Voce, aggiungi_voce, carica_diario, salva_diario


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


def test_oltre_il_tetto_restano_solo_le_voci_automatiche_piu_recenti(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [
            {"testo": f"voce {i}", "aggiunta_il": "2026-09-20", "fonte": "modello"}
            for i in range(MAX_VOCI_AUTOMATICHE + 5)
        ],
    )
    voci = carica_diario(percorso)
    assert len(voci) == MAX_VOCI_AUTOMATICHE
    assert [v.testo for v in voci] == [f"voce {i}" for i in range(5, MAX_VOCI_AUTOMATICHE + 5)]


def test_tetto_personalizzabile(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [{"testo": f"voce {i}", "aggiunta_il": "2026-09-20", "fonte": "modello"} for i in range(10)],
    )
    voci = carica_diario(percorso, tetto=3)
    assert [v.testo for v in voci] == ["voce 7", "voce 8", "voce 9"]


def test_le_voci_manuali_non_vengono_mai_sfrattate(tmp_path):
    """Decisione del 26/9: solo le voci "modello" contano per il tetto."""
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [{"testo": f"manuale {i}", "aggiunta_il": "2026-09-20", "fonte": "manuale"} for i in range(50)],
    )
    voci = carica_diario(percorso)
    assert len(voci) == 50  # tutte, ben oltre MAX_VOCI_AUTOMATICHE


def test_le_voci_manuali_restano_anche_con_tante_automatiche(tmp_path):
    percorso = tmp_path / "memoria.json"
    righe = [{"testo": "voce manuale", "aggiunta_il": "2026-09-01", "fonte": "manuale"}]
    righe += [
        {"testo": f"automatica {i}", "aggiunta_il": "2026-09-20", "fonte": "modello"}
        for i in range(MAX_VOCI_AUTOMATICHE + 5)
    ]
    _scrivi(percorso, righe)
    voci = carica_diario(percorso)
    assert "voce manuale" in [v.testo for v in voci]
    assert len(voci) == 1 + MAX_VOCI_AUTOMATICHE  # la manuale più le ultime automatiche


def test_salva_diario_scrive_leggibile_dopo(tmp_path):
    percorso = tmp_path / "memoria.json"
    salva_diario(percorso, [Voce("ceno alle 20", "2026-09-20", "manuale")])
    [voce] = carica_diario(percorso)
    assert voce == Voce("ceno alle 20", "2026-09-20", "manuale")


def test_salva_diario_crea_la_cartella_se_manca(tmp_path):
    percorso = tmp_path / "bmo" / "memoria.json"
    salva_diario(percorso, [Voce("ceno alle 20", "2026-09-20", "manuale")])
    assert percorso.exists()


def test_aggiungi_voce_su_file_mancante(tmp_path):
    percorso = tmp_path / "memoria.json"
    nuova = aggiungi_voce(percorso, "non gli piacciono i funghi", "2026-09-20")
    assert nuova == Voce("non gli piacciono i funghi", "2026-09-20", "modello")
    assert carica_diario(percorso) == [nuova]


def test_aggiungi_voce_si_accoda_alle_esistenti(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(percorso, [{"testo": "voce vecchia", "aggiunta_il": "2026-09-14"}])
    aggiungi_voce(percorso, "voce nuova", "2026-09-20")
    assert [v.testo for v in carica_diario(percorso)] == ["voce vecchia", "voce nuova"]


def test_aggiungi_voce_fonte_esplicita(tmp_path):
    percorso = tmp_path / "memoria.json"
    nuova = aggiungi_voce(percorso, "test", "2026-09-20", fonte="manuale")
    assert nuova.fonte == "manuale"


def test_aggiungi_voce_rispetta_il_tetto(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [{"testo": f"voce {i}", "aggiunta_il": "2026-09-20", "fonte": "modello"} for i in range(MAX_VOCI_AUTOMATICHE)],
    )
    aggiungi_voce(percorso, "voce nuova", "2026-09-20")
    voci = carica_diario(percorso)
    assert len(voci) == MAX_VOCI_AUTOMATICHE
    assert voci[0].testo == "voce 1"  # la più vecchia (voce 0) è caduta
    assert voci[-1].testo == "voce nuova"


def test_aggiungi_voce_manuale_non_fa_cadere_niente(tmp_path):
    percorso = tmp_path / "memoria.json"
    _scrivi(
        percorso,
        [{"testo": f"voce {i}", "aggiunta_il": "2026-09-20", "fonte": "modello"} for i in range(MAX_VOCI_AUTOMATICHE)],
    )
    aggiungi_voce(percorso, "voce manuale nuova", "2026-09-20", fonte="manuale")
    voci = carica_diario(percorso)
    assert len(voci) == MAX_VOCI_AUTOMATICHE + 1  # nessuna sfrattata: la nuova è manuale
    assert voci[0].testo == "voce 0"
    assert voci[-1].testo == "voce manuale nuova"
