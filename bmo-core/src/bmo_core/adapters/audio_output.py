"""Adapter uscita audio: mpv, identico su PC di sviluppo e su Pi."""
from __future__ import annotations

import subprocess
from pathlib import Path

# Catene di filtri per dare a BMO una voce robotica (#42). mpv le applica
# **in riproduzione**, quindi non costano ne' un passaggio ffmpeg, ne' un
# file intermedio, ne' latenza: misurato il 23/9, il picco di memoria di mpv
# e' 74,2-74,9 MB con o senza filtro, cioe' rumore di misura.
#
# `loudnorm` non e' un vezzo: le catene partono da livelli molto diversi
# (fra -15 e -30 dB) e senza normalizzare BMO cambierebbe volume a seconda
# del filtro scelto.
_NORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
FILTRI_VOCE = {
    # Nessun trattamento: la voce come esce dal motore.
    "naturale": None,
    # Passa-banda: simula l'altoparlante da 40 mm che BMO avra' davvero.
    "altoparlante": f"highpass=f=350,lowpass=f=3400,acompressor=ratio=4,{_NORM}",
    # Riduzione di bit: sapore da console portatile.
    "console": f"highpass=f=350,lowpass=f=3400,acrusher=bits=6:mode=log:aa=1,{_NORM}",
    # Modulazione d'ampiezza a frequenza audio: il robot piu' marcato, e il
    # meno intelligibile. La modulazione ad anello "vera" (`amultiply` con una
    # sinusoide) richiederebbe un secondo ingresso, che una catena `--af` non
    # puo' fornire; `tremolo` a 55 Hz da' la stessa modulazione.
    "anello": f"tremolo=f=55:d=0.9,highpass=f=300,lowpass=f=3400,{_NORM}",
    # Flanger: riflesso metallico, come dentro una scatola.
    "metallico": f"flanger=delay=2:depth=3:regen=40:speed=0.5,highpass=f=300,lowpass=f=3600,{_NORM}",
    # Il compromesso fra carattere e intelligibilita'.
    "bmo": (
        "highpass=f=400,lowpass=f=3200,acrusher=bits=8:mode=log:aa=1,"
        f"flanger=delay=1:depth=2:regen=20:speed=0.3,acompressor=ratio=3,{_NORM}"
    ),
}


def catena_filtro(nome: str | None) -> str | None:
    """La catena di un preset, o `None` se non c'e' niente da applicare.

    Un nome sconosciuto non solleva: BMO deve parlare anche con una variabile
    d'ambiente scritta male, semmai senza effetto.
    """
    return FILTRI_VOCE.get((nome or "naturale").strip().lower())


class MpvAdapter:
    """Riproduzione via mpv.

    Nessuna differenza hardware da astrarre qui: mpv gira nativo e
    identico sia sul PC di sviluppo (omarchy/Linux) sia sul Pi.
    """

    def __init__(self) -> None:
        self._processo: subprocess.Popen | None = None

    def riproduci(self, sorgente: Path | str, *, filtro: str | None = None) -> None:
        """Suona `sorgente`, eventualmente attraverso una catena di filtri.

        `filtro` e' una catena per `--af` (vedi `FILTRI_VOCE`), ed e' un
        argomento della singola riproduzione e non dell'adapter di proposito:
        lo stesso `MpvAdapter` suona anche il tono della sveglia, che non deve
        diventare robotico solo perche' la voce lo e'.
        """
        self.ferma()
        comando = ["mpv", "--no-video", "--really-quiet"]
        if filtro:
            comando.append(f"--af=lavfi=[{filtro}]")
        comando.append(str(sorgente))
        self._processo = subprocess.Popen(comando)

    def attendi(self, timeout_s: float | None = None) -> None:
        """Aspetta che la riproduzione finisca da sola.

        `riproduci` non blocca: lancia mpv e torna subito, che è giusto per un
        tono o una clip che parte e si dimentica. Per la **voce** (#42) serve
        l'opposto: se chi parla non aspetta, la riga dopo della macchina a
        stati fa ripartire l'ascolto o suona qualcos'altro, e `riproduci`
        comincia uccidendo il processo precedente — cioè taglia BMO a
        metà frase.

        Senza `timeout_s` aspetta quanto serve. Con un timeout scaduto non
        solleva: torna e basta, lasciando mpv a finire per conto suo, perché
        un'attesa troppo lunga non deve diventare un BMO bloccato.
        """
        if self._processo is None:
            return
        try:
            self._processo.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass

    def ferma(self) -> None:
        if self._processo is not None and self._processo.poll() is None:
            self._processo.terminate()
            self._processo.wait(timeout=5)
        self._processo = None
