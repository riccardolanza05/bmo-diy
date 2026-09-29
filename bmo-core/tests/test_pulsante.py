"""issue #70: il pulsante extra del HAT audio, letto via GPIO o assente."""
import sys
import types

from bmo_core.adapters.pulsante import PulsanteAssente, PulsanteGpio


def test_pulsante_assente_non_scatta_mai():
    assert PulsanteAssente().premuto() is False


def test_pulsante_gpio_delega_a_gpiozero_button(monkeypatch):
    """`gpiozero` non è fra le dipendenze del progetto (Pi-only, import
    pigro dentro PulsanteGpio.__init__, come onnxruntime in wake_word.py):
    un modulo finto in sys.modules evita di doverlo installare per far
    girare questo test sul PC di sviluppo."""
    catturato = {}

    class ButtonFinto:
        def __init__(self, pin, pull_up=True):
            catturato["pin"] = pin
            catturato["pull_up"] = pull_up
            self.is_pressed = False

    modulo_finto = types.ModuleType("gpiozero")
    modulo_finto.Button = ButtonFinto
    monkeypatch.setitem(sys.modules, "gpiozero", modulo_finto)

    pulsante = PulsanteGpio(17)
    assert catturato == {"pin": 17, "pull_up": True}
    assert pulsante.premuto() is False

    pulsante._bottone.is_pressed = True
    assert pulsante.premuto() is True


def test_pulsante_gpio_pull_up_falso_si_passa_a_button(monkeypatch):
    catturato = {}

    class ButtonFinto:
        def __init__(self, pin, pull_up=True):
            catturato["pull_up"] = pull_up
            self.is_pressed = False

    modulo_finto = types.ModuleType("gpiozero")
    modulo_finto.Button = ButtonFinto
    monkeypatch.setitem(sys.modules, "gpiozero", modulo_finto)

    PulsanteGpio(17, pull_up=False)
    assert catturato["pull_up"] is False
