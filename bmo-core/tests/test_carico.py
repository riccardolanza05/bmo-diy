from bmo_core.carico import tieni_viva_la_wake_word


class _RilevatoreFinto:
    """Sostituto di `RichiamoWakeWord`: solo `ascolta_punteggio()`, come lo usa
    `tieni_viva_la_wake_word` — non serve un microfono o un modello vero."""

    def __init__(self, punteggi):
        self._punteggi = list(punteggi)
        self.chiamate = 0

    def ascolta_punteggio(self):
        self.chiamate += 1
        return self._punteggi.pop(0) if self._punteggi else None


def test_tieni_viva_la_wake_word_continua_finche_non_passano_i_secondi():
    """Ogni chiamata ad `ascolta_punteggio()` consuma tempo reale sul Pi vero
    (il buffer di silenzio di `MicrofonoCopione`): qui si controlla solo che
    il ciclo si fermi quando l'orologio iniettato supera `secondi`, non prima."""
    tempi = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    rilevatore = _RilevatoreFinto([None, None, None])
    falsi = tieni_viva_la_wake_word(rilevatore, secondi=4.0, orologio=lambda: next(tempi))
    assert rilevatore.chiamate == 3
    assert falsi == 0


def test_tieni_viva_la_wake_word_conta_i_falsi_positivi_senza_fermarsi():
    """Un punteggio sopra soglia durante la pausa (rumore di fondo sul
    silenzio) non deve interrompere la pausa: solo essere contato."""
    tempi = iter([0.0, 1.0, 2.0])
    rilevatore = _RilevatoreFinto([0.9])
    falsi = tieni_viva_la_wake_word(rilevatore, secondi=2.0, orologio=lambda: next(tempi))
    assert falsi == 1
    assert rilevatore.chiamate == 1


def test_tieni_viva_la_wake_word_zero_secondi_non_ascolta_niente():
    rilevatore = _RilevatoreFinto([])
    falsi = tieni_viva_la_wake_word(rilevatore, secondi=0.0, orologio=lambda: 5.0)
    assert falsi == 0
    assert rilevatore.chiamate == 0
