import pytest

from bmo_core.vad import (
    DURATA_FRAME_MS,
    ascolta_fino_al_silenzio,
    dimensione_frame,
    ritaglia_in_frame,
    valida_frequenza,
)


class RilevatoreFinto:
    """Sostituto di webrtcvad.Vad: restituisce risultati preparati in ordine."""

    def __init__(self, risultati):
        self._risultati = list(risultati)

    def is_speech(self, frame, frequenza):
        return self._risultati.pop(0)


def _frame(n):
    return [f"f{i}".encode() for i in range(n)]


def test_valida_frequenza_accetta_solo_quelle_note():
    valida_frequenza(16000)  # non solleva
    with pytest.raises(ValueError):
        valida_frequenza(44100)


def test_dimensione_frame_30ms_a_16khz():
    # 16000 campioni/s × 0,030 s × 2 byte/campione = 960 byte.
    assert dimensione_frame(16000, durata_ms=30) == 960


def test_ritaglia_in_frame_riaccorpa_pezzi_arbitrari():
    pezzi = [b"12345", b"6789", b"0ab"]  # 12 byte totali, in pezzi da 5/4/3
    frame = list(ritaglia_in_frame(pezzi, dimensione=4))
    assert frame == [b"1234", b"5678", b"90ab"]


def test_ritaglia_in_frame_scarta_l_avanzo_finale():
    frame = list(ritaglia_in_frame([b"12345"], dimensione=4))
    assert frame == [b"1234"]  # il "5" finale non basta per un frame intero


def test_aspetta_la_voce_prima_di_contare_il_silenzio():
    """Senza questo, il silenzio iniziale farebbe scattare subito l'endpoint."""
    frame = _frame(7)
    rilevatore = RilevatoreFinto([False, False, True, True, False, False, False])
    audio, diagnostica = ascolta_fino_al_silenzio(
        frame, 16000, rilevatore, cap_s=10.0, silenzio_ms=90, durata_frame_ms=30
    )
    # I due frame di silenzio iniziale sono scartati, non fanno parte della clip.
    assert audio == b"".join(frame[2:])
    assert diagnostica.frame_di_rumore_scartati == 2
    assert diagnostica.voce_rilevata is True
    assert diagnostica.motivo_fine == "silenzio"


def test_il_silenzio_finale_resta_nella_clip():
    """L'hangover non si taglia: rischierebbe di troncare l'ultima consonante."""
    frame = _frame(5)
    rilevatore = RilevatoreFinto([True, False, False, False, True])  # il quinto non si legge nemmeno
    audio, _ = ascolta_fino_al_silenzio(frame, 16000, rilevatore, cap_s=10.0, silenzio_ms=90, durata_frame_ms=30)
    assert audio == b"".join(frame[:4])  # voce + i tre silenzi che fanno scattare l'endpoint


def test_mai_iniziato_torna_audio_vuoto():
    frame = _frame(5)
    rilevatore = RilevatoreFinto([False] * 5)
    audio, diagnostica = ascolta_fino_al_silenzio(
        frame, 16000, rilevatore, cap_s=0.09, silenzio_ms=800, durata_frame_ms=30
    )
    assert audio == b""
    assert diagnostica.voce_rilevata is False
    assert diagnostica.motivo_fine == "mai_iniziato"
    assert diagnostica.frame_di_rumore_scartati == 3  # 0,09 s / 0,03 s per frame


def test_il_tetto_ferma_anche_a_meta_frase():
    frame = _frame(10)
    rilevatore = RilevatoreFinto([True] * 10)  # non tace mai
    audio, diagnostica = ascolta_fino_al_silenzio(
        frame, 16000, rilevatore, cap_s=0.15, silenzio_ms=800, durata_frame_ms=30
    )
    assert audio == b"".join(frame[:5])  # 0,15 s / 0,03 s per frame
    assert diagnostica.motivo_fine == "tetto"
    assert diagnostica.voce_rilevata is True


def test_durata_totale_e_coerente_col_numero_di_frame():
    # 3 frame di silenzio di fila servono per fermarsi esattamente al 4°.
    frame = _frame(4)
    rilevatore = RilevatoreFinto([True, False, False, False])
    _, diagnostica = ascolta_fino_al_silenzio(frame, 16000, rilevatore, cap_s=10.0, silenzio_ms=90, durata_frame_ms=30)
    assert diagnostica.durata_totale_s == pytest.approx(4 * DURATA_FRAME_MS / 1000)
