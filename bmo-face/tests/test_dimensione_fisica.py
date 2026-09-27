from bmo_face.dimensione_fisica import PRESET_PANNELLI, e_sottocampionato, px_per_dimensione_fisica


def test_preset_2_4_pollici_dal_piano():
    assert PRESET_PANNELLI["2.4"] == (48.96, 36.72)


def test_px_per_dimensione_fisica_pitch_piu_fine_del_pannello():
    # Un monitor con pitch 0.10 mm/px (più fine del pannello 0.153 mm/px del
    # 2.4"): servono PIÙ pixel di 320×240 per lo stesso ingombro fisico.
    px = px_per_dimensione_fisica(48.96, 36.72, pitch=(0.10, 0.10))
    assert px == (490, 367)


def test_px_per_dimensione_fisica_pitch_piu_grosso_del_pannello():
    # Un laptop FHD tipico: 0.177 mm/px, più grosso dello 0.153 del 2.4".
    px = px_per_dimensione_fisica(48.96, 36.72, pitch=(0.177, 0.177))
    assert px == (277, 207)


def test_e_sottocampionato():
    pannello_px = (320, 240)
    assert e_sottocampionato((277, 207), pannello_px) is True
    assert e_sottocampionato((490, 367), pannello_px) is False
    assert e_sottocampionato((320, 240), pannello_px) is False
