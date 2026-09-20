import pytest


@pytest.fixture(autouse=True)
def dati_in_cartella_temporanea(tmp_path, monkeypatch):
    """Nessun test deve scrivere i timer nella cartella vera dell'utente.

    `percorso_dati()` guarda BMO_DATI prima di tutto il resto: spostandola
    qui, anche un `Cervello` costruito senza archivio esplicito finisce in
    una cartella usa e getta.
    """
    monkeypatch.setenv("BMO_DATI", str(tmp_path / "bmo"))
