import json

import pytest

from bmo_core.musica import Musica, cartella_musica, scegli_brani, stazioni_radio


class LettoreFinto:
    def __init__(self, suona=False):
        self.code = []
        self.azioni = []
        self.suona = suona

    def riproduci(self, tracce):
        self.code.append(list(tracce))
        self.suona = True

    def pausa(self):
        self.azioni.append("pausa")

    def riprendi(self):
        self.azioni.append("riprendi")

    def stop(self):
        self.azioni.append("stop")
        self.suona = False

    def successivo(self):
        self.azioni.append("successivo")

    def in_riproduzione(self):
        return self.suona


class VolumeFinto:
    def __init__(self):
        self.impostati = []

    def imposta(self, percentuale):
        self.impostati.append(percentuale)

    def leggi(self):
        return self.impostati[-1] if self.impostati else None


def _libreria(tmp_path):
    for nome in (
        "Daft Punk/Discovery/01 One More Time.mp3",
        "Daft Punk/Discovery/02 Aerodynamic.mp3",
        "Lucio Battisti/Il mio canto libero.flac",
        "copertina.jpg",
    ):
        percorso = tmp_path / nome
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(b"x")
    return tmp_path


def _musica(tmp_path, stazioni=None, suona=False):
    lettore, volume = LettoreFinto(suona), VolumeFinto()
    return Musica(lettore=lettore, volume=volume, cartella=_libreria(tmp_path), stazioni=stazioni or {}), lettore, volume


def test_cerca_i_brani_per_nome_di_file_e_cartella(tmp_path):
    cartella = _libreria(tmp_path)
    assert [p.stem for p in scegli_brani(cartella, "daft punk")] == ["01 One More Time", "02 Aerodynamic"]
    assert [p.stem for p in scegli_brani(cartella, "canto libero")] == ["Il mio canto libero"]
    # Nessuna corrispondenza completa: si ripiega su chi contiene una parola sola.
    assert [p.stem for p in scegli_brani(cartella, "battisti aerodynamic")] != []
    # Le immagini non sono musica.
    assert all(p.suffix != ".jpg" for p in scegli_brani(cartella, ""))


def test_riproduci_dalla_libreria(tmp_path):
    musica, lettore, _ = _musica(tmp_path)
    esito = musica.riproduci("daft punk", "libreria")
    assert esito == {
        "stato": "ok",
        "sorgente": "libreria",
        "titolo": "01 One More Time",
        "brani_in_coda": 2,
    }
    assert len(lettore.code[0]) == 2


def test_brano_non_trovato_lo_dice(tmp_path):
    musica, lettore, _ = _musica(tmp_path)
    assert musica.riproduci("una canzone che non ho", "libreria")["stato"] == "non_trovato"
    assert lettore.code == []  # niente suona: BMO non deve fingere


def test_radio_solo_se_c_e_l_elenco(tmp_path):
    musica, lettore, _ = _musica(tmp_path)
    assert musica.riproduci("radio deejay", "radio")["stato"] == "non_disponibile"

    musica, lettore, _ = _musica(tmp_path, stazioni={"Radio Deejay": "http://stream/deejay"})
    assert musica.riproduci("metti radio deejay", "radio") == {
        "stato": "ok",
        "sorgente": "radio",
        "stazione": "Radio Deejay",
    }
    assert lettore.code == [["http://stream/deejay"]]


def test_sorgente_sconosciuta(tmp_path):
    musica, _, _ = _musica(tmp_path)
    with pytest.raises(ValueError):
        musica.riproduci("qualcosa", "youtube")


def test_controllo_solo_se_qualcosa_sta_suonando(tmp_path):
    musica, lettore, _ = _musica(tmp_path)
    assert musica.controllo("pausa") == {"stato": "niente_in_riproduzione"}
    assert lettore.azioni == []

    musica.riproduci("daft punk", "libreria")
    assert musica.controllo("pausa") == {"stato": "ok", "azione": "pausa"}
    assert musica.controllo("successivo")["stato"] == "ok"
    assert lettore.azioni == ["pausa", "successivo"]

    musica.controllo("stop")
    assert musica.in_ascolto is None

    with pytest.raises(ValueError):
        musica.controllo("rewind")


def test_volume(tmp_path):
    musica, _, volume = _musica(tmp_path)
    assert musica.regola_volume(60) == {"stato": "ok", "percentuale": 60}
    assert volume.impostati == [60]
    for sbagliato in (-1, 101):
        with pytest.raises(ValueError):
            musica.regola_volume(sbagliato)


def test_stazioni_da_file(tmp_path):
    percorso = tmp_path / "radio.json"
    assert stazioni_radio(percorso) == {}  # il file può non esserci
    percorso.write_text(json.dumps({"Radio Deejay": "http://stream/deejay"}))
    assert stazioni_radio(percorso) == {"Radio Deejay": "http://stream/deejay"}
    percorso.write_text("non è json")
    assert stazioni_radio(percorso) == {}  # e può essere rotto: BMO parte lo stesso


def test_cartella_musica_configurabile(tmp_path, monkeypatch):
    monkeypatch.setenv("BMO_MUSICA", str(tmp_path / "brani"))
    assert cartella_musica() == tmp_path / "brani"
