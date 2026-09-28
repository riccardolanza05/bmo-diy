"""issue #64: il controllo volume ALSA va rilevato, non fisso a "Master"
(che non esiste né sul jack del Pi 3 né, secondo la documentazione, sul
WM8960)."""
from bmo_core.adapters.volume import (
    VARIABILE_AMBIENTE_CONTROLLO,
    VolumeAlsa,
    controlli_con_volume,
    rileva_controllo,
)

_SCONTROLS_JACK_PI3 = "Simple mixer control 'PCM',0\n"
_SCONTROLS_WM8960 = (
    "Simple mixer control 'Left Output Mixer PCM',0\n"
    "Simple mixer control 'Speaker',0\n"
    "Simple mixer control 'Playback',0\n"
    "Simple mixer control 'Auto Mute Mono',0\n"
)
_SGET_CON_VOLUME = "  Mono: Playback -1988 [78%] [-19.88dB] [on]\n"
_SGET_SENZA_VOLUME = "  Mono: Playback [on]\n"


def _finto_esegui(risposte: dict[tuple, str]):
    def _esegui(comando):
        return risposte.get(tuple(comando))

    return _esegui


def test_controlli_con_volume_filtra_gli_switch_puri(monkeypatch):
    risposte = {
        ("amixer", "scontrols"): _SCONTROLS_WM8960,
        ("amixer", "sget", "Left Output Mixer PCM"): _SGET_CON_VOLUME,
        ("amixer", "sget", "Speaker"): _SGET_CON_VOLUME,
        ("amixer", "sget", "Playback"): _SGET_SENZA_VOLUME,
        ("amixer", "sget", "Auto Mute Mono"): _SGET_SENZA_VOLUME,
    }
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", _finto_esegui(risposte))
    assert controlli_con_volume() == ["Left Output Mixer PCM", "Speaker"]


def test_rileva_controllo_preferisce_speaker_su_wm8960(monkeypatch):
    risposte = {
        ("amixer", "scontrols"): _SCONTROLS_WM8960,
        ("amixer", "sget", "Left Output Mixer PCM"): _SGET_CON_VOLUME,
        ("amixer", "sget", "Speaker"): _SGET_CON_VOLUME,
        ("amixer", "sget", "Playback"): _SGET_CON_VOLUME,
        ("amixer", "sget", "Auto Mute Mono"): _SGET_SENZA_VOLUME,
    }
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", _finto_esegui(risposte))
    monkeypatch.delenv(VARIABILE_AMBIENTE_CONTROLLO, raising=False)
    assert rileva_controllo() == "Speaker"


def test_rileva_controllo_trova_pcm_sul_jack_del_pi3(monkeypatch):
    """Il caso confermato dal vivo il 28/9/2026 sul Pi reale: un solo
    controllo, 'PCM', non fra i preferiti ma l'unico regolabile."""
    risposte = {
        ("amixer", "scontrols"): _SCONTROLS_JACK_PI3,
        ("amixer", "sget", "PCM"): _SGET_CON_VOLUME,
    }
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", _finto_esegui(risposte))
    monkeypatch.delenv(VARIABILE_AMBIENTE_CONTROLLO, raising=False)
    assert rileva_controllo() == "PCM"


def test_variabile_ambiente_ha_sempre_precedenza(monkeypatch):
    risposte = {
        ("amixer", "scontrols"): _SCONTROLS_WM8960,
        ("amixer", "sget", "Speaker"): _SGET_CON_VOLUME,
    }
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", _finto_esegui(risposte))
    monkeypatch.setenv(VARIABILE_AMBIENTE_CONTROLLO, "NomeForzato")
    assert rileva_controllo() == "NomeForzato"


def test_nessun_controllo_trovato_restituisce_none_e_avvisa(monkeypatch, capsys):
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", lambda comando: None)
    monkeypatch.delenv(VARIABILE_AMBIENTE_CONTROLLO, raising=False)
    assert rileva_controllo() is None
    volume = VolumeAlsa()
    assert volume.imposta(50) is False
    assert "ATTENZIONE" in capsys.readouterr().err


def test_volume_alsa_con_controllo_esplicito_non_rileva(monkeypatch):
    chiamate = []
    monkeypatch.setattr("bmo_core.adapters.volume._esegui", lambda c: chiamate.append(c) or "ok")
    volume = VolumeAlsa(controllo="PCM")
    assert volume.imposta(60) is True
    assert chiamate == [["amixer", "-q", "sset", "PCM", "60%"]]


def test_volume_alsa_rileva_una_sola_volta(monkeypatch):
    chiamate_scontrols = []

    def _esegui(comando):
        if comando[-1] == "scontrols":
            chiamate_scontrols.append(comando)
            return _SCONTROLS_JACK_PI3
        if comando[:2] == ["amixer", "sget"]:
            return _SGET_CON_VOLUME
        return "ok"

    monkeypatch.setattr("bmo_core.adapters.volume._esegui", _esegui)
    monkeypatch.delenv(VARIABILE_AMBIENTE_CONTROLLO, raising=False)
    volume = VolumeAlsa()
    volume.imposta(10)
    volume.imposta(20)
    volume.leggi()
    assert len(chiamate_scontrols) == 1  # rilevato una volta sola, non a ogni chiamata
