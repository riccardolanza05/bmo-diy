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
# In ordine, dal piu' leggero al piu' marcato. I primi sono nati dopo la prova
# d'ascolto del 23/9: i trattamenti forti rendono BMO "troppo robotico", e la
# strada giusta e' suggerire un piccolo altoparlante, non simulare un robot.
FILTRI_VOCE = {
    # Nessun trattamento: la voce come esce dal motore.
    "naturale": None,
    # Un accenno: toglie solo gli estremi, che un altoparlante da 40 mm non
    # riprodurrebbe comunque. Si sente a malapena, ed e' voluto.
    "appena": f"highpass=f=200,lowpass=f=5500,acompressor=ratio=2,{_NORM}",
    # Una radiolina: si capisce che il suono esce da qualcosa di piccolo,
    # ma la voce resta naturale.
    "radiolina": f"highpass=f=300,lowpass=f=4200,acompressor=ratio=3,{_NORM}",
    # Come "radiolina" piu' un velo digitale: 10 bit si notano appena, molto
    # meno dei 6 di "console".
    "digitale": f"highpass=f=250,lowpass=f=4800,acrusher=bits=10:mode=log:aa=1,{_NORM}",
    # Passa-banda stretto: simula l'altoparlante da 40 mm che BMO avra' davvero.
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


# Il timbro scelto all'ascolto il 24/9: si capisce che il suono esce da
# qualcosa di piccolo, ma la voce resta naturale. I trattamenti piu' marcati
# risultavano "troppo robotici".
FILTRO_PREDEFINITO = "radiolina"

# Quanto silenzio lasciare dove il TTS mette una pausa. I modelli neurali
# prendono fiato a ogni punto con una lunghezza da lettura ad alta voce, che
# in una conversazione sembra esitazione. Un'incollatura secca (0) farebbe
# correre le frasi una sull'altra; 0,15 s tiene lo stacco e toglie l'attesa.
PAUSA_MAX_PREDEFINITA_S = 0.15

# Sotto questa soglia il silenzio non viene toccato: e' una pausa naturale
# dentro la frase, non un fine periodo.
_PAUSA_MINIMA_DA_TAGLIARE_S = 0.25
_SOGLIA_SILENZIO = "-45dB"


def catena_filtro(nome: str | None) -> str | None:
    """La catena di timbro di un preset, o `None` se non c'e' niente da applicare.

    Un nome sconosciuto non solleva: BMO deve parlare anche con una variabile
    d'ambiente scritta male, semmai senza effetto.
    """
    return FILTRI_VOCE.get((nome or FILTRO_PREDEFINITO).strip().lower())


def taglia_pause(massimo_s: float | None = None) -> str | None:
    """Accorcia i silenzi lunghi, compreso quello iniziale.

    `silenceremove` lavora in riproduzione come il resto, quindi non costa
    nulla. Taglia anche il silenzio in testa (`start_periods=1`), che non e'
    un vezzo: e' tempo fra il momento in cui BMO dovrebbe cominciare a
    parlare e la prima sillaba, cioe' latenza percepita in meno gratis.

    `massimo_s` a zero o negativo disattiva il taglio.
    """
    massimo_s = PAUSA_MAX_PREDEFINITA_S if massimo_s is None else massimo_s
    if massimo_s <= 0:
        return None
    return (
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={_SOGLIA_SILENZIO}"
        f":stop_periods=-1:stop_duration={_PAUSA_MINIMA_DA_TAGLIARE_S}"
        f":stop_threshold={_SOGLIA_SILENZIO}:stop_silence={massimo_s}"
    )


def catena_voce(filtro: str | None = None, pausa_max_s: float | None = None) -> str | None:
    """La catena completa della voce: prima le pause, poi il timbro.

    L'ordine conta: i preset finiscono con `loudnorm`, che deve vedere
    l'audio gia' accorciato.
    """
    pezzi = [pezzo for pezzo in (taglia_pause(pausa_max_s), catena_filtro(filtro)) if pezzo]
    return ",".join(pezzi) or None


class MpvAdapter:
    """Riproduzione via mpv.

    Nessuna differenza hardware da astrarre qui: mpv gira nativo e
    identico sia sul PC di sviluppo (omarchy/Linux) sia sul Pi.
    """

    def __init__(self) -> None:
        self._processo: subprocess.Popen | None = None

    def riproduci(self, sorgente: Path | str, *, filtro: str | None = None, volume: int | None = None) -> None:
        """Suona `sorgente`, eventualmente attraverso una catena di filtri.

        `filtro` e' una catena per `--af` (vedi `FILTRI_VOCE`), ed e' un
        argomento della singola riproduzione e non dell'adapter di proposito:
        lo stesso `MpvAdapter` suona anche il tono della sveglia, che non deve
        diventare robotico solo perche' la voce lo e'.

        `volume` (issue successiva alla #23, volumi indipendenti per
        sorgente) e' lo stesso genere di argomento: il volume **di mpv**
        (`--volume`, 0-100, interno a questo processo), non quello di
        sistema. Chi chiama (`VoceTts`, `Suoni`) tiene il proprio livello e
        lo passa qui a ogni riproduzione, cosi' regolare "la voce" non tocca
        "il timer" ne' il volume dell'altoparlante nel suo complesso.
        """
        self.ferma()
        comando = ["mpv", "--no-video", "--really-quiet"]
        if filtro:
            comando.append(f"--af=lavfi=[{filtro}]")
        if volume is not None:
            comando.append(f"--volume={int(volume)}")
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
