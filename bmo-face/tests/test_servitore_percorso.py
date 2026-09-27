"""`percorso_socket()` qui deve seguire esattamente la stessa regola di
`bmo_core.config.percorso_socket()` (calcolata in modo indipendente, i due
pacchetti non si importano a vicenda): se uno dei due cambia senza l'altro,
bmo-core e bmo-face finiscono in ascolto su socket diversi senza che nessuno
se ne accorga (`FacciaSocket` fallisce in silenzio)."""
from pathlib import Path

from bmo_face.servitore import percorso_socket


def test_bmo_socket_ha_sempre_la_precedenza(monkeypatch):
    monkeypatch.setenv("BMO_SOCKET", "/tmp/qualcosa.sock")
    assert percorso_socket() == Path("/tmp/qualcosa.sock")


def test_run_scrivibile_ha_la_precedenza_su_xdg_runtime_dir(monkeypatch):
    monkeypatch.delenv("BMO_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr("os.access", lambda percorso, modo: True)
    assert percorso_socket() == Path("/run/bmo.sock")


def test_run_non_scrivibile_usa_xdg_runtime_dir(monkeypatch):
    monkeypatch.delenv("BMO_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr("os.access", lambda percorso, modo: False)
    assert percorso_socket() == Path("/run/user/1000/bmo.sock")


def test_senza_run_ne_xdg_usa_tmpdir(monkeypatch):
    monkeypatch.delenv("BMO_SOCKET", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", "/tmp/prova")
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    assert percorso_socket() == Path("/tmp/prova/bmo.sock")
