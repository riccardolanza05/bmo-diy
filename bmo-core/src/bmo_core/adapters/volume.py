"""Il volume dell'altoparlante.

Non e' il volume del lettore musicale: riguarda tutto quello che BMO emette,
voce e clip comprese, perche' "abbassa il volume" detto a un BMO che parla
troppo forte non riguarda la musica. Due implementazioni, come per gli altri
adapter: PipeWire sul PC di sviluppo, ALSA sul Pi, dove non c'e' un server
audio ma la scheda del HAT.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_USCITA_PREDEFINITA = "@DEFAULT_AUDIO_SINK@"

# issue #64: "Master" (il valore usato finora) non esiste su nessuna scheda
# vista finora — confermato dal vivo il 28/9 sul jack del Pi 3 A+, dove
# `amixer scontrols` restituisce solo 'PCM'; il WM8960 (non ancora montato)
# espone secondo la documentazione Waveshare 'Speaker'/'Playback'. Ordine di
# preferenza fra i nomi noti quando più di uno risulta regolabile.
_CANDIDATI_PREFERITI = ("Speaker", "PCM", "Master", "Playback")
VARIABILE_AMBIENTE_CONTROLLO = "BMO_VOLUME_ALSA_CONTROLLO"


def _esegui(comando: list[str]) -> str | None:
    try:
        finito = subprocess.run(comando, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return finito.stdout if finito.returncode == 0 else None


class VolumePipeWire:
    """`wpctl`, il controllo di PipeWire: e' quello che gira su omarchy."""

    def imposta(self, percentuale: int) -> bool:
        return _esegui(["wpctl", "set-volume", _USCITA_PREDEFINITA, f"{int(percentuale)}%"]) is not None

    def leggi(self) -> int | None:
        uscita = _esegui(["wpctl", "get-volume", _USCITA_PREDEFINITA])
        # "Volume: 0.60" oppure "Volume: 0.60 [MUTED]"
        trovato = re.search(r"([\d.]+)", uscita or "")
        return round(float(trovato.group(1)) * 100) if trovato else None


def _comando_scontrols(scheda: str | None) -> list[str]:
    return ["amixer"] + (["-c", scheda] if scheda else []) + ["scontrols"]


def _comando_sget(nome: str, scheda: str | None) -> list[str]:
    return ["amixer"] + (["-c", scheda] if scheda else []) + ["sget", nome]


def controlli_con_volume(scheda: str | None = None) -> list[str]:
    """I nomi dei controlli di `amixer scontrols` che hanno davvero un volume
    regolabile in percentuale (non solo uno switch on/off come "Auto-Mute
    Mode" o "IEC958"), nell'ordine in cui `amixer` li elenca.
    """
    uscita = _esegui(_comando_scontrols(scheda)) or ""
    nomi = re.findall(r"'([^']+)'", uscita)
    capaci = []
    for nome in nomi:
        dettaglio = _esegui(_comando_sget(nome, scheda)) or ""
        if re.search(r"\[\d+%\]", dettaglio):
            capaci.append(nome)
    return capaci


def rileva_controllo(scheda: str | None = None) -> str | None:
    """Il nome del controllo giusto per "alza/abbassa il volume" su questa
    macchina (issue #64), invece del "Master" fisso che falliva in silenzio.

    Priorità: la variabile d'ambiente `BMO_VOLUME_ALSA_CONTROLLO`, se
    impostata (per quando il rilevamento sbaglia o per fissare un nome prima
    di sapere cosa espone il HAT vero); poi il primo nome fra quelli noti
    (`_CANDIDATI_PREFERITI`) che risulta realmente presente e regolabile;
    altrimenti il primo controllo regolabile trovato, qualunque sia il nome;
    `None` se `amixer scontrols` non elenca nessun controllo con volume (il
    chiamante deve avvisare, vedi `VolumeAlsa`).
    """
    forzato = os.environ.get(VARIABILE_AMBIENTE_CONTROLLO)
    if forzato:
        return forzato
    capaci = controlli_con_volume(scheda)
    for preferito in _CANDIDATI_PREFERITI:
        if preferito in capaci:
            return preferito
    return capaci[0] if capaci else None


class VolumeAlsa:
    """`amixer`, per il Pi con la scheda del HAT e senza server audio.

    Il controllo si rileva da solo al primo uso (`rileva_controllo`), non
    alla costruzione: così creare l'oggetto resta economico (nessun
    `subprocess`) anche nei test che non lo usano mai. Passare `controllo`
    esplicito salta del tutto il rilevamento.
    """

    def __init__(self, controllo: str | None = None, scheda: str | None = None) -> None:
        self.scheda = scheda
        self._controllo_esplicito = controllo
        self._controllo_rilevato: str | None = None
        self._rilevato = False

    @property
    def controllo(self) -> str | None:
        if self._controllo_esplicito is not None:
            return self._controllo_esplicito
        if not self._rilevato:
            self._controllo_rilevato = rileva_controllo(self.scheda)
            self._rilevato = True
            if self._controllo_rilevato is None:
                print(
                    "ATTENZIONE: nessun controllo volume ALSA trovato (amixer scontrols "
                    f"non ne elenca nessuno con volume regolabile); imposta "
                    f"{VARIABILE_AMBIENTE_CONTROLLO} a mano, altrimenti \"alza/abbassa il "
                    "volume\" non avrà nessun effetto.",
                    file=sys.stderr,
                )
        return self._controllo_rilevato

    def imposta(self, percentuale: int) -> bool:
        controllo = self.controllo
        if controllo is None:
            return False
        comando = ["amixer", "-q"] + (["-c", self.scheda] if self.scheda else [])
        return _esegui(comando + ["sset", controllo, f"{int(percentuale)}%"]) is not None

    def leggi(self) -> int | None:
        controllo = self.controllo
        if controllo is None:
            return None
        uscita = _esegui(_comando_sget(controllo, self.scheda))
        trovato = re.search(r"\[(\d+)%\]", uscita or "")
        return int(trovato.group(1)) if trovato else None
