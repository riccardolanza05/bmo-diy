import pytest

from bmo_core.richiamo import BYTE_PER_FRAME, RichiamoWakeWord, attendi_wake_word


class RilevatoreFinto:
    """Sostituto di openwakeword.Model: restituisce punteggi preparati in ordine."""

    def __init__(self, punteggi):
        self._punteggi = list(punteggi)

    def predict(self, x):
        return self._punteggi.pop(0)


def _frame(n):
    return [b"\x00" * BYTE_PER_FRAME for _ in range(n)]


def test_attendi_wake_word_si_ferma_al_primo_superamento():
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.1}, {"hey_jarvis": 0.2}, {"hey_jarvis": 0.9}, {"hey_jarvis": 0.9}])
    punteggio = attendi_wake_word(_frame(4), rilevatore, soglia=0.5)
    assert punteggio == 0.9
    # Il quarto frame non doveva essere consultato: si ferma al terzo.
    assert rilevatore._punteggi == [{"hey_jarvis": 0.9}]


def test_attendi_wake_word_nessun_superamento_restituisce_none():
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.1}, {"hey_jarvis": 0.2}])
    assert attendi_wake_word(_frame(2), rilevatore, soglia=0.5) is None


def test_attendi_wake_word_prende_il_massimo_fra_piu_modelli():
    """Più modelli caricati insieme: basta che uno solo superi la soglia."""
    rilevatore = RilevatoreFinto([{"alexa": 0.3, "hey_jarvis": 0.8}])
    assert attendi_wake_word(_frame(1), rilevatore, soglia=0.5) == 0.8


def test_attendi_wake_word_soglia_esatta_conta_come_superamento():
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.5}])
    assert attendi_wake_word(_frame(1), rilevatore, soglia=0.5) == 0.5


class MicrofonoFinto:
    """AudioInputAdapter minimo: `flusso_pcm` è l'unico metodo che serve qui."""

    def __init__(self, pezzi):
        self._pezzi = pezzi
        self.chiuso = False

    def flusso_pcm(self):
        return _FlussoFinto(self._pezzi, self)


class _FlussoFinto:
    def __init__(self, pezzi, microfono):
        self._iter = iter(pezzi)
        self._microfono = microfono

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iter)

    def close(self):
        self._microfono.chiuso = True


def test_richiamo_wake_word_call_restituisce_booleano_e_chiude_il_flusso():
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.1}, {"hey_jarvis": 0.9}])
    microfono = MicrofonoFinto(_frame(2))
    richiamo = RichiamoWakeWord(microfono=microfono, rilevatore=rilevatore)
    assert richiamo() is True
    assert microfono.chiuso is True


def test_richiamo_wake_word_non_rilevata_restituisce_false():
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.1}])
    microfono = MicrofonoFinto(_frame(1))
    richiamo = RichiamoWakeWord(microfono=microfono, rilevatore=rilevatore, soglia=0.5)
    assert richiamo() is False


def test_carica_rilevatore_normalizza_una_stringa_in_lista(monkeypatch):
    """Più file possono essere caricati insieme: basta che uno solo superi la soglia."""
    import openwakeword.model as modulo_model

    import bmo_core.richiamo as modulo

    catturato = {}

    class ModelFinto:
        def __init__(self, wakeword_model_paths):
            catturato["paths"] = wakeword_model_paths

    monkeypatch.setattr(modulo_model, "Model", ModelFinto)
    monkeypatch.setattr(modulo, "_percorso_modello", lambda nome: f"/finto/{nome}.onnx")

    modulo._carica_rilevatore("hey_jarvis")
    assert catturato["paths"] == ["/finto/hey_jarvis.onnx"]

    modulo._carica_rilevatore(["hey_jarvis", "alexa"])
    assert catturato["paths"] == ["/finto/hey_jarvis.onnx", "/finto/alexa.onnx"]


def test_richiamo_wake_word_carica_il_rilevatore_una_sola_volta(monkeypatch):
    """Il rilevatore iniettato non deve mai passare da `_carica_rilevatore`."""
    import bmo_core.richiamo as modulo

    def esplodi(_modello):
        raise AssertionError("non doveva caricare openwakeword: il rilevatore era già iniettato")

    monkeypatch.setattr(modulo, "_carica_rilevatore", esplodi)
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.9}])
    microfono = MicrofonoFinto(_frame(1))
    richiamo = RichiamoWakeWord(microfono=microfono, rilevatore=rilevatore)
    assert richiamo() is True
