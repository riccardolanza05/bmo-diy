import pytest

from bmo_core.config import Ambiente, rileva_ambiente


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
