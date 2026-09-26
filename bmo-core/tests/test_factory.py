from bmo_core.adapters.audio_input import ArecordAdapter
from bmo_core.adapters.audio_output import MpvAdapter
from bmo_core.adapters.camera import LibcameraAdapter, WebcamV4L2Adapter
from bmo_core.adapters.faccia import FacciaMuta, FacciaSocket, FacciaTerminale
from bmo_core.adapters.factory import crea_audio_input, crea_audio_output, crea_camera, crea_faccia
from bmo_core.config import Ambiente, percorso_socket


def test_crea_camera_pi():
    assert isinstance(crea_camera(Ambiente.PI), LibcameraAdapter)


def test_crea_camera_dev_linux():
    assert isinstance(crea_camera(Ambiente.DEV_LINUX), WebcamV4L2Adapter)


def test_crea_audio_input_pi_usa_hat():
    adapter = crea_audio_input(Ambiente.PI)
    assert isinstance(adapter, ArecordAdapter)
    assert adapter.dispositivo == "hw:0,0"


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


def test_registra_passa_campioni_interi(monkeypatch, tmp_path):
    comandi = []
    monkeypatch.setattr("subprocess.run", lambda comando, check: comandi.append(comando))
    ArecordAdapter(frequenza=48000).registra(tmp_path / "a.wav", 1.5)
    assert comandi[0][-3:] == ["-s", "72000", str(tmp_path / "a.wav")]
    assert "-d" not in comandi[0]
