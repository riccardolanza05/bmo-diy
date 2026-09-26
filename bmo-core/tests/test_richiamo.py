from pathlib import Path

import pytest

from bmo_core.richiamo import (
    BYTE_PER_FRAME,
    MODELLI_PREDEFINITI,
    RichiamoWakeWord,
    _carica_rilevatore,
    attendi_wake_word,
)


class RilevatoreFinto:
    """Sostituto di openwakeword.Model: restituisce punteggi preparati in ordine."""

    def __init__(self, punteggi):
        self._punteggi = list(punteggi)
        self.reset_chiamato = 0

    def predict(self, x):
        return self._punteggi.pop(0)

    def reset(self):
        self.reset_chiamato += 1


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


def test_ogni_ascolto_azzera_il_buffer_del_rilevatore():
    """Bug reale trovato dal vivo il 26/9: openwakeword.Model tiene un
    prediction_buffer che sopravvive fra un ascolto e l'altro finché lo
    stesso Model resta in vita (esegui() lo riusa per ogni giro). Senza
    azzerarlo, un punteggio residuo dal richiamo appena sentito poteva far
    scattare una cascata di richiami — rumore di fondo o radio bastavano a
    superare di nuovo la soglia quasi subito."""
    rilevatore = RilevatoreFinto([{"hey_jarvis": 0.9}, {"hey_jarvis": 0.9}])
    microfono = MicrofonoFinto(_frame(2))
    richiamo = RichiamoWakeWord(microfono=microfono, rilevatore=rilevatore)
    richiamo()
    assert rilevatore.reset_chiamato == 1
    richiamo()
    assert rilevatore.reset_chiamato == 2


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


def test_modelli_predefiniti_sono_i_due_file_bmo():
    """Deciso il 26/9: non più `hey_jarvis`, due file veri nel repo invece
    di un nome di modello preaddestrato. Solo due, non tre: il terzo (bmo3)
    resta deliberatamente fuori dal repo, sul BMO personale di Riccardo."""
    assert len(MODELLI_PREDEFINITI) == 2
    for percorso in MODELLI_PREDEFINITI:
        assert Path(percorso).is_file(), f"modello mancante: {percorso}"
        assert Path(percorso).suffix == ".onnx"
        assert Path(percorso).stem in ("bmo1", "bmo2")


def test_modelli_predefiniti_si_caricano_davvero():
    """Pesi veri, non un `RilevatoreFinto`: un file .onnx rotto o un nome
    sbagliato si scoprirebbe solo qui."""
    rilevatore = _carica_rilevatore(MODELLI_PREDEFINITI)
    assert set(rilevatore.models.keys()) == {"bmo1", "bmo2"}
