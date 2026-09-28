import os
import subprocess
import sys
import time

from bmo_core.misura_ram import (
    Memoria,
    Riepilogo,
    componente_di,
    discendenti,
    genitori,
    leggi_smaps_rollup,
    processi_con,
)

SMAPS = """\
00400000-7ffd4a1f5000 ---p 00000000 00:00 0                              [rollup]
Rss:              225580 kB
Pss:              214311 kB
Pss_Anon:         150000 kB
Shared_Clean:      11000 kB
Shared_Dirty:          0 kB
Private_Clean:     20000 kB
Private_Dirty:    190000 kB
Swap:                 12 kB
SwapPss:              10 kB
"""


def test_leggi_smaps_rollup():
    mem = leggi_smaps_rollup(SMAPS)
    assert mem == Memoria(rss=225580, pss=214311, uss=210000, swap=10, pss_anon=150000, pss_file=0)


def test_leggi_smaps_rollup_senza_swappss_usa_swap():
    mem = leggi_smaps_rollup("Rss: 10 kB\nPss: 8 kB\nSwap: 4 kB\n")
    assert mem.swap == 4


def test_componente_di():
    assert componente_di("/x/.venv/bin/python -m bmo_core.macchina --voce-tts") == "bmo-core"
    assert componente_di("python -m bmo_face.finestra --assets assets/") == "bmo-face"
    assert componente_di("mpv --no-video /tmp/voce.ogg") == "mpv"
    assert componente_di("arecord -f S16_LE -r 16000") == "arecord"
    assert componente_di("bash ./avvia_demo.sh") == "altro"


def test_discendenti_segue_tutto_l_albero():
    mappa = {10: 1, 11: 10, 12: 11, 13: 10, 20: 1}
    assert sorted(discendenti(10, mappa)) == [11, 12, 13]
    assert discendenti(20, mappa) == []


def test_discendenti_di_un_processo_vero():
    figlio = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        time.sleep(0.1)
        assert figlio.pid in discendenti(os.getpid(), genitori())
    finally:
        figlio.kill()
        figlio.wait()


def test_cerca_scarta_gli_involucri_e_prende_i_figli():
    # 5 = timeout, 6 = python bmo_core.macchina, 7 = mpv lanciato da bmo-core
    mappa = {5: 1, 6: 5, 7: 6, 8: 1}
    righe = {
        5: "timeout 60 python -m bmo_core.macchina",
        6: "python -m bmo_core.macchina --wake-word",
        7: "mpv --no-video voce.ogg",
        8: "vim note.txt",
    }
    assert processi_con("bmo_core.macchina", mappa, righe) == [6, 7]


def test_riepilogo_picchi_per_componente_e_totale():
    r = Riepilogo()
    r.aggiungi(1.0, {"bmo-core": Memoria(pss=100), "mpv": Memoria(pss=30)}, disponibile=300)
    r.aggiungi(2.0, {"bmo-core": Memoria(pss=120)}, disponibile=250)
    assert r.picco_totale.pss == 130
    assert r.istante_picco == 1.0
    assert r.picchi["bmo-core"].pss == 120
    assert r.picchi["mpv"].pss == 30
    assert r.minimo_disponibile == 250
    assert "picco PSS totale" in r.testo()
