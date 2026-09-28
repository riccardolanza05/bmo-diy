import pytest

from bmo_face.animazione import Renderer
from bmo_face.build_face import costruisci
from bmo_face.pannello import UscitaNulla, UscitaPannello, UscitaSpi, crea_uscita, esegui_pannello
from bmo_face.servitore import ServitoreFaccia


def _renderer(larghezza=16, altezza=16):
    dati, manifesto = costruisci(larghezza, altezza)
    return Renderer(manifesto, dati)


def _servitore(tmp_path, orologio=lambda: 0.0):
    return ServitoreFaccia(percorso=tmp_path / "bmo.sock", orologio=orologio)


def test_crea_uscita_nulla():
    assert isinstance(crea_uscita("nulla"), UscitaNulla)


def test_crea_uscita_spi_non_implementata():
    # L'interfaccia esiste già (issue #63); l'hardware no (fase 4.5/4.7).
    with pytest.raises(NotImplementedError, match="fase 4.5/4.7"):
        crea_uscita("spi")


def test_crea_uscita_sconosciuta():
    with pytest.raises(ValueError):
        crea_uscita("hdmi")


def test_uscita_pannello_di_base_non_implementata():
    with pytest.raises(NotImplementedError):
        UscitaPannello().disegna_frame(object())


def test_esegui_pannello_disegna_un_fotogramma_per_tick(tmp_path):
    renderer = _renderer()
    servitore = _servitore(tmp_path)
    uscita = UscitaNulla()

    contatore = {"t": 0.0}

    def orologio() -> float:
        contatore["t"] += 1.0  # ogni lettura avanza: ogni tick vede un tempo diverso dal precedente
        return contatore["t"]

    tick = {"n": 0}

    def ancora() -> bool:
        tick["n"] += 1
        return tick["n"] <= 3

    esegui_pannello(renderer, servitore, uscita, orologio=orologio, dormi=lambda s: None, ancora=ancora)

    # Stato "idle" fermo, ma il tempo passa: il battito irregolare può far
    # cambiare o no il fotogramma da un tick all'altro. Verifichiamo invece
    # il comportamento che conta: mai più fotogrammi dei tick eseguiti.
    assert uscita.fotogrammi_inviati <= 3
    assert uscita.fotogrammi_inviati >= 1  # il primo fotogramma va sempre inviato


def test_esegui_pannello_salta_i_fotogrammi_identici(tmp_path):
    renderer = _renderer()
    servitore = _servitore(tmp_path, orologio=lambda: 0.0)
    # Stato "parlato" senza inviluppo: `disegna` restituisce sempre lo stesso
    # fotogramma per lo stesso tempo, e qui il tempo passato a `disegna` è
    # sempre 0.0 (vedi orologio sotto) -> il fotogramma non cambia mai.
    servitore.comando.stato = "parlato"
    uscita = UscitaNulla()

    tick = {"n": 0}

    def ancora():
        tick["n"] += 1
        return tick["n"] <= 5

    # orologio() usato da esegui_pannello per il tempo del fotogramma resta
    # fisso a 0.0: il fotogramma calcolato è sempre identico byte per byte.
    esegui_pannello(renderer, servitore, uscita, orologio=lambda: 0.0, dormi=lambda s: None, ancora=ancora)

    assert uscita.fotogrammi_inviati == 1


def test_esegui_pannello_ridisegna_quando_il_livello_cambia(tmp_path):
    renderer = _renderer()
    servitore = _servitore(tmp_path, orologio=lambda: 0.0)
    servitore.comando.stato = "ascolto"
    uscita = UscitaNulla()

    # 5 livelli di pupille (arte_placeholder.overlay_pupille): 0.0 e 0.9
    # cadono su fotogrammi diversi, 0.9 ripetuto sullo stesso -> non deve
    # ridisegnare due volte di fila.
    livelli = iter([0.0, 0.9, 0.9, 0.1])

    def prossimo_tick() -> bool:
        try:
            servitore.comando.livello = next(livelli)
            return True
        except StopIteration:
            return False

    esegui_pannello(renderer, servitore, uscita, orologio=lambda: 0.0, dormi=lambda s: None, ancora=prossimo_tick)

    assert uscita.fotogrammi_inviati == 3  # inviati a 0.0, 0.9, 0.1 — non ripetuto a 0.9
