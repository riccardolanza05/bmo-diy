import pytest

from bmo_core.suoni import BIP_ASCOLTO, BIP_ERRORE, CARTELLA_PACCHETTO, Suoni, SuoniMuti, trova_suono


class AltoparlanteFinto:
    def __init__(self, errore=None):
        self.eventi = []
        self._errore = errore

    def riproduci(self, sorgente, *, filtro=None):
        if self._errore:
            raise self._errore
        self.eventi.append(("riproduci", sorgente, filtro))

    def attendi(self, timeout_s=None):
        self.eventi.append(("attendi", timeout_s))

    def ferma(self):
        self.eventi.append(("ferma",))


@pytest.fixture(autouse=True)
def senza_variabili(monkeypatch):
    monkeypatch.delenv("BMO_SUONO_ERRORE", raising=False)
    monkeypatch.delenv("BMO_SUONO_TIMER", raising=False)
    monkeypatch.delenv("BMO_SUONO_ASCOLTO", raising=False)


def test_l_errore_incluso_nel_pacchetto_e_breve_e_ha_la_licenza():
    """CC0, e molto più corto della frase che segue (richiesto il 25/9)."""
    import subprocess

    percorso = CARTELLA_PACCHETTO / "errore.ogg"
    assert percorso.exists()
    assert "CC0" in (CARTELLA_PACCHETTO / "LICENZE.md").read_text()
    assert trova_suono("errore", BIP_ERRORE) == str(percorso)
    try:
        durata = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(percorso)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("ffprobe non disponibile")
    assert float(durata) < 0.5


def test_un_file_nella_cartella_dati_vince_sul_pacchetto(tmp_path, monkeypatch):
    monkeypatch.setenv("BMO_DATI", str(tmp_path))
    (tmp_path / "suoni").mkdir()
    (tmp_path / "suoni" / "errore.mp3").write_bytes(b"finto")
    assert trova_suono("errore", BIP_ERRORE) == str(tmp_path / "suoni" / "errore.mp3")


def test_la_variabile_vince_su_tutto(monkeypatch):
    monkeypatch.setenv("BMO_SUONO_ERRORE", "/tmp/altro.wav")
    assert trova_suono("errore", BIP_ERRORE) == "/tmp/altro.wav"


def test_senza_niente_si_usa_il_ripiego():
    assert trova_suono("inesistente", "av://lavfi:sine") == "av://lavfi:sine"


def test_errore_suona_senza_filtro_e_aspetta_la_fine():
    altoparlante = AltoparlanteFinto()
    Suoni(altoparlante).errore()
    (azione, sorgente, filtro), attesa = altoparlante.eventi
    assert azione == "riproduci" and sorgente.endswith("errore.ogg") and filtro is None
    assert attesa[0] == "attendi" and attesa[1] is not None  # con un tetto


def test_mpv_assente_non_blocca():
    Suoni(AltoparlanteFinto(errore=FileNotFoundError("mpv"))).errore()


def test_ascolto_usa_il_tono_di_ripiego_di_default():
    """Nessun file scelto ancora (a differenza di errore/timer, #21): è il tono."""
    assert trova_suono("ascolto", BIP_ASCOLTO) == BIP_ASCOLTO


def test_ascolto_suona_e_aspetta_la_fine():
    altoparlante = AltoparlanteFinto()
    Suoni(altoparlante).ascolto()
    (azione, sorgente, filtro), attesa = altoparlante.eventi
    assert azione == "riproduci" and sorgente == BIP_ASCOLTO and filtro is None
    assert attesa[0] == "attendi" and attesa[1] is not None  # con un tetto


def test_mpv_assente_non_blocca_ascolto():
    Suoni(AltoparlanteFinto(errore=FileNotFoundError("mpv"))).ascolto()


def test_i_suoni_muti_non_fanno_niente():
    SuoniMuti().errore()
    SuoniMuti().ascolto()
