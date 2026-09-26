from pathlib import Path

import pytest

from bmo_core.config import Ambiente, percorso_socket, rileva_ambiente


def test_bmo_env_esplicito(monkeypatch):
    monkeypatch.setenv("BMO_ENV", "dev-linux")
    assert rileva_ambiente() is Ambiente.DEV_LINUX


def test_bmo_env_non_valido(monkeypatch):
    monkeypatch.setenv("BMO_ENV", "windows")
    with pytest.raises(ValueError):
        rileva_ambiente()


def test_rilevamento_automatico_pi(monkeypatch, tmp_path):
    monkeypatch.delenv("BMO_ENV", raising=False)
    device_tree = tmp_path / "model"
    device_tree.write_text("Raspberry Pi 3 Model A Plus Rev 1.0")
    monkeypatch.setattr("bmo_core.config._DEVICE_TREE_MODEL", device_tree)
    assert rileva_ambiente() is Ambiente.PI


def test_rilevamento_automatico_dev_linux(monkeypatch, tmp_path):
    monkeypatch.delenv("BMO_ENV", raising=False)
    monkeypatch.setattr("bmo_core.config._DEVICE_TREE_MODEL", tmp_path / "assente")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert rileva_ambiente() is Ambiente.DEV_LINUX


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
    # Il caso vero di un servizio systemd senza RuntimeDirectory=: /run
    # esiste ma non è scrivibile da chi non è root. Stessa regola di
    # `bmo_face.servitore.percorso_socket()`: la parità fra i due pacchetti è
    # quello che questo test protegge.
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
