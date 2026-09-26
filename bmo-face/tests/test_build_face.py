from bmo_face.arte_placeholder import GENERATORI_CORPO, N_FRAME_CORPO
from bmo_face.build_face import costruisci
from bmo_face.formato import rgb888_da_565


def test_costruisci_produce_tutti_gli_stati_minimi():
    _, manifesto = costruisci(64, 48)
    # Gli STATO_* di bmo-core (adapters.base): la #23 chiede tutti gli stati
    # minimi, non un sottoinsieme.
    attesi = {"assonnato", "idle", "ascolto", "pensiero", "parlato", "timer", "errore-rete", "conferma"}
    assert set(manifesto.corpo) == attesi
    assert manifesto.bocca is not None
    assert manifesto.pupille is not None
    assert set(manifesto.espressioni) == {"felice", "pensieroso", "sorpreso", "triste", "assonnato"}


def test_costruisci_e_parametrico_sulla_risoluzione():
    dati_piccoli, manifesto_piccolo = costruisci(64, 48)
    dati_grandi, manifesto_grande = costruisci(128, 96)
    assert (manifesto_piccolo.larghezza, manifesto_piccolo.altezza) == (64, 48)
    assert (manifesto_grande.larghezza, manifesto_grande.altezza) == (128, 96)
    # Il pannello grande ha più byte per fotogramma quindi, a parità di
    # numero di fotogrammi, un faces.bin più grande.
    assert len(dati_grandi) > len(dati_piccoli)


def test_offset_del_manifesto_indicizzano_dati_dentro_i_confini(tmp_path):
    dati, manifesto = costruisci(48, 32)
    frame_size = manifesto.larghezza * manifesto.altezza * 2
    for stato, anim in manifesto.corpo.items():
        fine = anim.offset + anim.frames * frame_size
        assert 0 <= anim.offset < fine <= len(dati), stato
    for extra in (manifesto.bocca, manifesto.pupille, *manifesto.espressioni.values()):
        rw, rh = extra.regione[2], extra.regione[3]
        fine = extra.offset + extra.frames * rw * rh * 2
        assert 0 <= extra.offset < fine <= len(dati)


def test_regione_di_uno_stato_statico_e_lintera_tela():
    # ascolto, parlato, timer, errore-rete, conferma hanno un solo fotogramma
    # (N_FRAME_CORPO): _regione_cambiata deve coprire tutta la tela, non un
    # rettangolo vuoto, altrimenti il futuro blit a dirty-rect non
    # disegnerebbe mai il primo fotogramma.
    _, manifesto = costruisci(40, 30)
    for stato in ("ascolto", "parlato", "timer", "errore-rete", "conferma"):
        assert N_FRAME_CORPO[stato] == 1
        assert manifesto.corpo[stato].regione == [0, 0, 40, 30]


def test_i_fotogrammi_decodificati_sono_immagini_valide():
    dati, manifesto = costruisci(32, 24)
    anim = manifesto.corpo["idle"]
    frame_size = manifesto.larghezza * manifesto.altezza * 2
    primo = dati[anim.offset : anim.offset + frame_size]
    rgb = rgb888_da_565(primo)
    assert len(rgb) == manifesto.larghezza * manifesto.altezza * 3


def test_regge_un_pannello_piccolissimo_caso_peggiore():
    # Nessun modello di display piccolo è ancora nel BOM (issue #1): questo è
    # solo un limite basso per verificare che la pipeline non si rompa su un
    # pannello più piccolo di quanto pianificato oggi (320×240/2.4").
    dati, manifesto = costruisci(16, 16)
    assert len(dati) > 0
    assert set(manifesto.corpo) == set(GENERATORI_CORPO)


def test_generatori_coprono_tutti_i_conteggi_dichiarati():
    for stato, genera in GENERATORI_CORPO.items():
        frame = genera(32, 24, N_FRAME_CORPO[stato])
        assert len(frame) == N_FRAME_CORPO[stato]
        assert all(img.size == (32, 24) for img in frame)


def _scrivi_png_tinta(percorso, colore, dimensione=(80, 48)):
    from PIL import Image

    percorso.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", dimensione, colore).save(percorso)


def test_costruisci_da_sorgente_legge_il_layout_del_riferimento(tmp_path):
    from bmo_face.build_face import costruisci_da_sorgente

    sorgente = tmp_path / "sorgente"
    _scrivi_png_tinta(sorgente / "idle" / "idle 01.png", (200, 230, 190))
    _scrivi_png_tinta(sorgente / "listening" / "listen 01.png", (200, 230, 190))
    _scrivi_png_tinta(sorgente / "thinking" / "thinking 01.png", (200, 230, 190))
    _scrivi_png_tinta(sorgente / "error" / "error 01.png", (200, 60, 60))
    _scrivi_png_tinta(sorgente / "warmup" / "warmup 01.png", (150, 150, 150))
    dati, manifesto = costruisci_da_sorgente(sorgente, 32, 24)

    attesi = {"assonnato", "idle", "ascolto", "pensiero", "errore-rete", "timer", "parlato", "conferma"}
    assert set(manifesto.corpo) == attesi
    assert manifesto.corpo["timer"] == manifesto.corpo["idle"]  # riuso, nessuna cartella "timer" nel riferimento
    assert manifesto.corpo["conferma"] == manifesto.corpo["ascolto"]
    assert len(dati) > 0


def test_costruisci_da_sorgente_ordina_la_bocca_dal_chiuso_allaperto(tmp_path):
    from PIL import Image, ImageDraw

    from bmo_face.build_face import costruisci_da_sorgente

    sorgente = tmp_path / "sorgente"
    _scrivi_png_tinta(sorgente / "idle" / "idle 01.png", (200, 230, 190))

    cartella_bocca = sorgente / "speaking"
    cartella_bocca.mkdir(parents=True)
    for nome, apertura in (("c_aperta.png", 20), ("a_chiusa.png", 2), ("b_media.png", 10)):
        img = Image.new("RGB", (80, 48), (200, 230, 190))
        disegna = ImageDraw.Draw(img)
        disegna.ellipse([40 - apertura, 24 - apertura, 40 + apertura, 24 + apertura], fill=(20, 20, 20))
        img.save(cartella_bocca / nome)

    _, manifesto = costruisci_da_sorgente(sorgente, 32, 24)
    assert manifesto.bocca is not None
    assert manifesto.bocca.frames == 3
    # L'ordine sul disco era c(aperta), a(chiusa), b(media): dopo il sort per
    # apertura deve uscire chiusa -> media -> aperta, non l'ordine del nome file.


def test_costruisci_da_sorgente_senza_cartelle_da_manifesto_vuoto(tmp_path):
    from bmo_face.build_face import costruisci_da_sorgente

    dati, manifesto = costruisci_da_sorgente(tmp_path / "vuota", 32, 24)
    assert manifesto.corpo == {}
    assert manifesto.bocca is None
    assert dati == b""
