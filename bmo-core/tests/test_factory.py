from bmo_core.adapters.audio_input import ArecordAdapter, ArecordConvertitoreAdapter
from bmo_core.adapters.audio_output import MpvAdapter
from bmo_core.adapters.camera import LibcameraAdapter, WebcamV4L2Adapter
from bmo_core.adapters.faccia import FacciaMuta, FacciaSocket, FacciaTerminale
from bmo_core.adapters.factory import (
    crea_audio_input,
    crea_audio_output,
    crea_camera,
    crea_faccia,
    crea_pulsante,
)
from bmo_core.adapters.pulsante import PulsanteAssente, PulsanteGpio
from bmo_core.config import Ambiente, percorso_socket


def test_crea_camera_pi():
    assert isinstance(crea_camera(Ambiente.PI), LibcameraAdapter)


def test_crea_camera_dev_linux():
    assert isinstance(crea_camera(Ambiente.DEV_LINUX), WebcamV4L2Adapter)


def test_crea_audio_input_pi_usa_hat():
    # issue #64: il Pi cattura nativo (S32_LE stereo 48 kHz) e converte al
    # volo — l'adapter restituito espone comunque il formato che VAD e wake
    # word vogliono, come sul PC di sviluppo.
    adapter = crea_audio_input(Ambiente.PI)
    assert isinstance(adapter, ArecordConvertitoreAdapter)
    assert adapter.dispositivo == "hw:0,0"
    assert (adapter.frequenza, adapter.canali, adapter.formato) == (16000, 1, "S16_LE")


def test_crea_audio_input_pi_rispetta_bmo_audio_dispositivo(monkeypatch):
    monkeypatch.setenv("BMO_AUDIO_DISPOSITIVO", "plughw:1,0")
    adapter = crea_audio_input(Ambiente.PI)
    assert adapter.dispositivo == "plughw:1,0"


def test_crea_audio_input_dev_linux_usa_default():
    adapter = crea_audio_input(Ambiente.DEV_LINUX)
    assert isinstance(adapter, ArecordAdapter)
    assert adapter.dispositivo == "default"
    assert (adapter.frequenza, adapter.canali, adapter.formato) == (16000, 1, "S16_LE")


def test_crea_audio_output_identico_su_entrambi():
    assert isinstance(crea_audio_output(Ambiente.PI), MpvAdapter)
    assert isinstance(crea_audio_output(Ambiente.DEV_LINUX), MpvAdapter)


def test_crea_faccia_muta_di_default():
    """Senza BMO_FACCIA=socket il predefinito resta muto: bmo-face (#23) è un
    processo a parte che va avviato a mano, non deve scriversi addosso da solo."""
    assert isinstance(crea_faccia(), FacciaMuta)
    assert isinstance(crea_faccia(Ambiente.PI), FacciaMuta)
    assert isinstance(crea_faccia(sul_terminale=True), FacciaTerminale)


def test_crea_faccia_socket_con_bmo_faccia_socket(monkeypatch):
    monkeypatch.setenv("BMO_FACCIA", "socket")
    faccia = crea_faccia(Ambiente.DEV_LINUX)
    assert isinstance(faccia, FacciaSocket)
    assert faccia.percorso == percorso_socket(Ambiente.DEV_LINUX)


def test_faccia_sul_terminale_scrive_lo_stato():
    import io

    uscita = io.StringIO()
    FacciaTerminale(uscita).mostra("pensiero")
    assert uscita.getvalue() == "[faccia: pensiero]\n"


def test_crea_pulsante_dev_linux_e_sempre_assente(monkeypatch):
    """Anche con BMO_PULSANTE_PIN impostata: sul PC di sviluppo non c'è
    nessun GPIO da leggere."""
    monkeypatch.setenv("BMO_PULSANTE_PIN", "17")
    assert isinstance(crea_pulsante(Ambiente.DEV_LINUX), PulsanteAssente)


def test_crea_pulsante_pi_senza_pin_resta_assente(monkeypatch):
    """Issue #70: il pin del bottone extra non è ancora tracciato — meglio
    inerte che indovinato."""
    monkeypatch.delenv("BMO_PULSANTE_PIN", raising=False)
    assert isinstance(crea_pulsante(Ambiente.PI), PulsanteAssente)


def test_crea_pulsante_pi_con_pin_sceglie_gpio(monkeypatch):
    catturato = {}

    class PulsanteGpioFinto:
        def __init__(self, pin):
            catturato["pin"] = pin

    monkeypatch.setattr("bmo_core.adapters.factory.PulsanteGpio", PulsanteGpioFinto)
    monkeypatch.setenv("BMO_PULSANTE_PIN", "27")
    pulsante = crea_pulsante(Ambiente.PI)
    assert isinstance(pulsante, PulsanteGpioFinto)
    assert catturato["pin"] == 27


def test_registra_passa_campioni_interi(monkeypatch, tmp_path):
    comandi = []
    monkeypatch.setattr("subprocess.run", lambda comando, check: comandi.append(comando))
    ArecordAdapter(frequenza=48000).registra(tmp_path / "a.wav", 1.5)
    assert comandi[0][-3:] == ["-s", "72000", str(tmp_path / "a.wav")]
    assert "-d" not in comandi[0]
