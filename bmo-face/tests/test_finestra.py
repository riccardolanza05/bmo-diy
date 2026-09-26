import pytest

from bmo_face.animazione import ComandoFaccia
from bmo_face.finestra import _comando_snapshot, _host_px
from bmo_face.servitore import ServitoreFaccia


class _Argomenti:
    def __init__(self, **kw):
        self.pixel = False
        self.mm_larghezza = None
        self.mm_altezza = None
        self.pitch_mm = None
        self.monitor = None
        self.pannello = "2.4"
        self.__dict__.update(kw)


def test_host_px_modalita_pixel_ignora_le_mm():
    assert _host_px(_Argomenti(pixel=True), (320, 240)) == (320, 240)


def test_host_px_con_pitch_a_mano():
    # Stesso calcolo di dimensione_fisica, verificato lì: qui basta
    # controllare che _host_px lo colleghi correttamente al preset scelto.
    host = _host_px(_Argomenti(pitch_mm=[0.177, 0.177]), (320, 240))
    assert host == (277, 207)


def test_host_px_mm_esplicite_sostituiscono_il_preset():
    host_preset = _host_px(_Argomenti(pitch_mm=[0.15, 0.15]), (320, 240))
    host_custom = _host_px(
        _Argomenti(pitch_mm=[0.15, 0.15], mm_larghezza=20.0, mm_altezza=15.0), (320, 240)
    )
    assert host_custom != host_preset
    assert host_custom == (133, 100)


def test_host_px_senza_pitch_disponibile_solleva_con_un_messaggio_chiaro():
    with pytest.raises(SystemExit, match="hyprctl"):
        _host_px(_Argomenti(monitor="non-esiste-di-sicuro"), (320, 240))


def test_comando_snapshot_e_una_copia_indipendente(tmp_path):
    servitore = ServitoreFaccia(percorso=tmp_path / "bmo.sock")
    servitore.comando.stato = "ascolto"
    servitore.comando.livello = 0.5
    copia = _comando_snapshot(servitore)
    assert copia == ComandoFaccia(stato="ascolto", livello=0.5)
    copia.stato = "pensiero"
    assert servitore.comando.stato == "ascolto"  # la copia non muta l'originale
