"""Le clip di BMO: suoni senza parole per i momenti in cui non parla (#21).

**Senza parole per scelta** (Riccardo, 25/9). BMO è bilingue (#42) e una
clip parlata è per forza in una lingua sola: un «un attimo…» in italiano
dopo una domanda in inglese sarebbe il problema delle due voci in un altro
costume. Un bip non ha lingua, e per una console è anche più in carattere.
In più questi suoni non dipendono né dalla rete né da edge-tts, cioè
funzionano proprio quando serve di più: quando il resto è giù.

**Sintetizzati, non registrati**: onde a impulsi in stile chiptune,
generate qui con la sola libreria standard. Niente file di terzi nel
repository (che è pubblico), niente binari da versionare: si scrivono al
primo uso nella cartella dei dati, e il nome porta una versione così che
cambiarne il disegno li rigeneri da solo.

Tre suoni, uno per ogni silenzio che conta:

- **attesa**: BMO sta pensando. Un motivetto che si ripete senza stacchi,
  così copre tanto il buco normale (~1,3 s: 0,67 di cervello + 0,6 di voce)
  quanto quelli lunghi — la ricerca sul web, le foto della #24 (< 6 s).
- **errore**: la rete non risponde. Tre note che scendono.
- **timer**: un timer è scaduto. Prende il posto del tono sinusoidale che
  mpv generava da sé (`sveglia.TONO_GENERATO`, che resta come ripiego).

Non c'è un bip all'inizio dell'ascolto, e non per dimenticanza: il
microfono è già aperto in quel momento e lo registrerebbe, e aspettare che
finisca aggiungerebbe latenza proprio dove il piano chiede 150 ms. Il segno
che BMO ascolta resta la faccia.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import wave
from array import array
from pathlib import Path
from typing import Callable

from .adapters import AudioOutputAdapter, crea_audio_output
from .config import percorso_dati

FREQUENZA_HZ = 24000
# Cambiare il disegno di un suono senza cambiare questo numero lascerebbe in
# cartella la versione vecchia, servita come buona: va incrementato.
VERSIONE = 1

# Un suono sintetico pieno scala copre la voce di chiunque stia nella stanza:
# le clip stanno ben sotto, e l'attesa ancora di più perché si ripete.
_VOLUME = 0.35

# Quanto silenzio si tollera prima di far partire l'attesa. È il criterio di
# uscita della #21 («mai muto per più di 0,3 s») letto al contrario: sotto
# questa soglia la risposta arriva prima che serva coprire qualcosa, e una
# clip che parte e viene troncata subito sarebbe peggio del silenzio.
RITARDO_ATTESA_S = 0.3

# Il ritmo dell'attesa: una nota ogni `_PASSO_ATTESA_S`, lunga
# `_NOTA_ATTESA_S`. `Clip.zitto` li usa per non troncare una nota a metà.
_NOTA_ATTESA_S = 0.12
_PASSO_ATTESA_S = 0.32

# Le note che servono, in Hz.
_DO5, _MI5, _SOL5, _DO6 = 523.25, 659.25, 783.99, 1046.50
_SOL4, _MI4, _DO4 = 392.00, 329.63, 261.63


def _nota(frequenza: float, durata_s: float, *, duty: float = 0.25, volume: float = _VOLUME) -> list[float]:
    """Una nota a impulsi, col suo inviluppo.

    L'onda a impulsi (duty 25%) è il suono delle console portatili, ed è
    meno aspra della quadra. L'attacco e il rilascio di qualche millisecondo
    non sono estetica: un'onda che parte o si ferma di colpo fa un «clic».
    """
    campioni = int(durata_s * FREQUENZA_HZ)
    attacco = int(0.005 * FREQUENZA_HZ)
    rilascio = int(min(0.04, durata_s / 3) * FREQUENZA_HZ)
    periodo = FREQUENZA_HZ / frequenza
    nota = []
    for i in range(campioni):
        valore = 1.0 if (i % periodo) / periodo < duty else -1.0
        if i < attacco:
            valore *= i / attacco
        elif i >= campioni - rilascio:
            valore *= (campioni - i) / rilascio
        nota.append(valore * volume)
    return nota


def _pausa(durata_s: float) -> list[float]:
    return [0.0] * int(durata_s * FREQUENZA_HZ)


def suono_attesa() -> list[float]:
    """Il motivetto del pensiero: quattro note brevi e morbide, in loop.

    Dura ~1,3 s, cioè quanto il buco tipico, e non ha silenzi interni oltre
    i 0,3 s neppure fra una ripetizione e l'altra: ripetuto da mpv col loop
    resta un unico «sto lavorando». Più piano delle altre, perché è quello
    che si sente più spesso.
    """
    volume = _VOLUME * 0.6
    campioni: list[float] = []
    for frequenza in (_DO5, _MI5, _SOL5, _MI5):
        campioni += _nota(frequenza, _NOTA_ATTESA_S, duty=0.125, volume=volume)
        campioni += _pausa(_PASSO_ATTESA_S - _NOTA_ATTESA_S)
    return campioni


def suono_errore() -> list[float]:
    """Tre note che scendono: «non ci arrivo» senza parole."""
    campioni: list[float] = []
    for frequenza, durata in ((_SOL4, 0.18), (_MI4, 0.18), (_DO4, 0.45)):
        campioni += _nota(frequenza, durata, duty=0.5)
        campioni += _pausa(0.04)
    return campioni


def suono_timer() -> list[float]:
    """Un richiamo vivace ripetuto tre volte, abbastanza da sentirlo da un'altra stanza."""
    frase: list[float] = []
    for frequenza in (_DO5, _MI5, _SOL5, _DO6):
        frase += _nota(frequenza, 0.09)
        frase += _pausa(0.02)
    frase += _pausa(0.25)
    return frase * 3


SUONI: dict[str, Callable[[], list[float]]] = {
    "attesa": suono_attesa,
    "errore": suono_errore,
    "timer": suono_timer,
}


def cartella_clip(percorso: Path | None = None) -> Path:
    """Accanto agli altri dati di BMO, così `BMO_DATI` sposta anche queste."""
    return percorso or (percorso_dati() / "clip")


def scrivi_wav(percorso: Path, campioni: list[float]) -> None:
    """WAV mono a 16 bit, scritto su un temporaneo e poi rinominato: un file
    mezzo scritto non deve mai essere servito come buono."""
    pcm = array("h", (max(-32767, min(32767, round(c * 32767))) for c in campioni))
    if sys.byteorder != "little":
        pcm.byteswap()
    percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(".wav.parziale")
    with wave.open(str(temporaneo), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(FREQUENZA_HZ)
        f.writeframes(pcm.tobytes())
    temporaneo.replace(percorso)


def percorso_clip(nome: str, cartella: Path | None = None) -> Path:
    """Il file di una clip, generato adesso se non c'è ancora.

    Generarle costa 7–18 ms l'una sul PC di sviluppo (misurato il 25/9; sul
    Pi sarà qualche volta tanto) e succede una volta sola per versione: non
    vale la pena di un passo d'installazione.
    """
    if nome not in SUONI:
        raise KeyError(f"clip sconosciuta: {nome!r} (disponibili: {', '.join(SUONI)})")
    percorso = cartella_clip(cartella) / f"{nome}-v{VERSIONE}.wav"
    if not percorso.exists():
        scrivi_wav(percorso, SUONI[nome]())
    return percorso


def durata_s(percorso: Path) -> float:
    with wave.open(str(percorso), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def silenzio_massimo_s(campioni: list[float]) -> float:
    """Il tratto di silenzio più lungo dentro un suono, per verificarne il disegno."""
    massimo = corrente = 0
    for c in campioni:
        corrente = corrente + 1 if c == 0.0 else 0
        massimo = max(massimo, corrente)
    return massimo / FREQUENZA_HZ


class Clip:
    """Le clip di un BMO acceso, sullo stesso altoparlante della voce.

    Il caso centrale è l'attesa: riempie il silenzio fra la fine
    dell'ascolto e la prima parola di BMO.

    **La risposta può arrivare prima della clip**, ed è il caso da gestire
    con più cura (Riccardo, 25/9). Da qui tre regole:

    1. la clip non parte subito ma dopo `ritardo_s`: se la risposta è
       pronta prima, non si sente niente, invece di un bip troncato;
    2. `zitto()` e la partenza ritardata si escludono con un lock, e dopo
       `zitto()` niente può più farla partire — senza, un timer già scattato
       potrebbe avviare mpv un istante *dopo* che la voce ha cominciato, e la
       clip taglierebbe la risposta;
    3. l'altoparlante è **lo stesso** della voce: `MpvAdapter.riproduci`
       ferma quello che sta suonando, quindi anche se qualcosa sfuggisse
       alle prime due regole la voce vincerebbe sulla clip, mai il contrario.

    `zitto()` si chiama quando la voce è pronta a suonare, non quando la
    risposta del cervello è pronta: in mezzo c'è la sintesi (~0,6 s), che
    senza clip sarebbe di nuovo silenzio. Per questo `VoceTts` la riceve
    come `prima_di_suonare`.

    **Nota troncata o voce in ritardo**: fermare la clip a metà nota fa un
    piccolo bip mozzato; aspettare la fine della nota (`fine_nota=True`)
    lo evita ma costa fino a ~0,14 s su *ogni* risposta, sul thread della
    voce — proprio il «primo suono +0,00 s» ottenuto con la #42. Non si può
    aspettare altrove: la voce, partendo, ferma comunque mpv sull'adapter
    condiviso. Predefinito spento; `BMO_CLIP_FINE_NOTA=1` lo accende, per
    decidere all'ascolto.
    """

    def __init__(
        self,
        altoparlante: AudioOutputAdapter | None = None,
        cartella: Path | None = None,
        ritardo_s: float = RITARDO_ATTESA_S,
        crea_timer: Callable[[float, Callable[[], None]], threading.Timer] = threading.Timer,
        cronometro: Callable[[], float] = time.monotonic,
        dormi: Callable[[float], None] = time.sleep,
        fine_nota: bool | None = None,
    ) -> None:
        self.altoparlante = altoparlante or crea_audio_output()
        self.cartella = cartella
        if fine_nota is None:
            fine_nota = os.environ.get("BMO_CLIP_FINE_NOTA", "").strip() in ("1", "si", "sì", "true")
        self.fine_nota = fine_nota
        # Generate adesso, non al primo turno: altrimenti la prima volta la
        # sintesi dei campioni avverrebbe sul thread del timer, col lock
        # preso, e un `zitto()` concorrente la aspetterebbe.
        for nome in SUONI:
            try:
                percorso_clip(nome, cartella)
            except OSError as errore:
                print(f"[clip: {nome} non scritta — {errore}]", file=sys.stderr)
        self.cronometro = cronometro
        self.dormi = dormi
        self._partita_a = 0.0
        self.ritardo_s = ritardo_s
        self.crea_timer = crea_timer
        self._lock = threading.Lock()
        self._attiva = False
        self._suona = False
        self._timer: threading.Timer | None = None

    def _percorso(self, nome: str) -> Path:
        # Risolto a ogni uso e non nel costruttore: BMO_DATI può cambiare
        # dopo l'importazione (i test lo fanno), e dopo la prima volta il
        # file c'è già, quindi costa un `exists()`.
        return percorso_clip(nome, self.cartella)

    def attesa(self) -> None:
        """Comincia a contare: se fra `ritardo_s` BMO tace ancora, la clip parte."""
        with self._lock:
            if self._attiva:
                return
            self._attiva = True
            self._timer = self.crea_timer(self.ritardo_s, self._parti)
            self._timer.daemon = True
            self._timer.start()

    def _parti(self) -> None:
        with self._lock:
            if not self._attiva:
                return  # la risposta è arrivata mentre il timer scattava
            try:
                self.altoparlante.riproduci(self._percorso("attesa"), ripeti=True)
            except OSError as errore:  # mpv assente: meglio muto che fermo
                print(f"[clip: attesa non riprodotta — {errore}]", file=sys.stderr)
                return
            self._suona = True
            self._partita_a = self.cronometro()

    def _fine_della_nota_s(self) -> float:
        """Quanto manca alla fine della nota in corso, o 0 se si è in una pausa.

        Con edge-tts il silenzio da coprire non scende mai sotto la soglia —
        la sola sintesi costa ~0,6 s — quindi la clip parte quasi sempre e
        viene quasi sempre interrotta presto. Troncata a metà nota si sente
        un bip mozzato; aspettarne la fine costa al più `_NOTA_ATTESA_S` di
        ritardo sulla voce. Il conto è approssimato (mpv impiega qualche
        millesimo a partire), da cui il margine.
        """
        dentro = (self.cronometro() - self._partita_a) % _PASSO_ATTESA_S
        if dentro >= _NOTA_ATTESA_S:
            return 0.0
        return _NOTA_ATTESA_S - dentro + 0.02

    def zitto(self) -> None:
        """Ferma l'attesa, partita o no. Si può chiamare quante volte si vuole.

        Con `fine_nota` aspetta prima la fine della nota in corso.
        """
        with self._lock:
            self._attiva = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._suona:
                self._suona = False
                if self.fine_nota:
                    self.dormi(self._fine_della_nota_s())
                self.altoparlante.ferma()

    def errore(self) -> None:
        """Il suono dell'errore di rete, per intero, prima di qualunque parola.

        Aspetta la fine (con un tetto): la frase che segue passa per lo
        stesso altoparlante e lo taglierebbe. Senza rete quella frase finisce
        comunque sul terminale, e allora questo suono è tutto quello che
        BMO riesce a dire.
        """
        self.zitto()
        try:
            self.altoparlante.riproduci(self._percorso("errore"))
        except OSError as errore:
            print(f"[clip: errore non riprodotto — {errore}]", file=sys.stderr)
            return
        self.altoparlante.attendi(timeout_s=3.0)


class ClipMute:
    """Le clip che non suonano: il predefinito di `Macchina`, così i test e
    `prova_frasi` non lanciano mai mpv."""

    def attesa(self) -> None:
        pass

    def zitto(self) -> None:
        pass

    def errore(self) -> None:
        pass


# I casi della prova dal vivo, dopo quello della frase già in cache: una
# risposta veloce (la clip parte comunque per coprire la sintesi, ~0,6 s),
# il buco tipico (~1,3 s) e un'attesa lunga come una ricerca o una foto.
ATTESE_DI_PROVA_S = (0.1, 1.3, 4.0)


def prova_attesa(attese_s: tuple[float, ...] = ATTESE_DI_PROVA_S) -> None:
    """La prova dal vivo: turni finti con la voce e l'altoparlante veri.

    Il cervello è sostituito da una pausa di durata nota; tutto il resto è
    il percorso di BMO — stesso adapter per voce e clip, `VoceTts` che zittisce
    la clip dopo la sintesi. Serve la rete per edge-tts: senza, la frase
    finisce sul terminale, ed è anche quello un caso da sentire.
    """
    from .macchina import VoceTts

    from .tts import sintetizza

    altoparlante = crea_audio_output()
    clip = Clip(altoparlante)
    voce = VoceTts(altoparlante=altoparlante, prima_di_suonare=clip.zitto)
    gia_detta = "Questa la sapevo già."
    try:
        sintetizza(gia_detta)  # la mette in cache: ridirla non costa rete
    except Exception as errore:  # noqa: BLE001 — è una prova, si va avanti
        print(f"[prova: cache non preparata — {errore}]", flush=True)
    print("\n— frase già in cache, cervello a 0,1 s: la clip NON deve suonare", flush=True)
    clip.attesa()
    time.sleep(0.1)
    voce(gia_detta)
    clip.zitto()
    time.sleep(1.0)
    for attesa_s in attese_s:
        print(f"\n— il cervello ci mette {attesa_s:.1f} s, più la sintesi: la clip deve partire "
              "e la voce la deve interrompere a fine nota", flush=True)
        clip.attesa()
        time.sleep(attesa_s)
        voce(f"Risposta dopo {attesa_s:.1f} secondi.".replace(".", ",", 1))
        clip.zitto()
        time.sleep(1.0)
    print("\n— rete giù: il suono d'errore, poi la frase", flush=True)
    clip.errore()
    voce("Non ci arrivo.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera le clip di BMO e, volendo, le fa sentire.")
    parser.add_argument("nomi", nargs="*", default=list(SUONI), help=f"quali clip (predefinito: {', '.join(SUONI)})")
    parser.add_argument("--ascolta", action="store_true", help="suona ogni clip dopo averla generata")
    parser.add_argument("--rigenera", action="store_true", help="riscrive le clip anche se ci sono già")
    parser.add_argument(
        "--prova-attesa", action="store_true",
        help="turni finti con voce vera: risposta veloce, normale e lenta, poi l'errore",
    )
    argomenti = parser.parse_args()
    if argomenti.prova_attesa:
        prova_attesa()
        return
    altoparlante = crea_audio_output() if argomenti.ascolta else None
    for nome in argomenti.nomi:
        if argomenti.rigenera:
            (cartella_clip() / f"{nome}-v{VERSIONE}.wav").unlink(missing_ok=True)
        percorso = percorso_clip(nome)
        print(f"{nome}: {percorso} ({durata_s(percorso):.2f} s)", flush=True)
        if altoparlante is not None:
            altoparlante.riproduci(percorso)
            altoparlante.attendi()


if __name__ == "__main__":
    main()
