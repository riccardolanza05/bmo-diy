#!/usr/bin/env python3
"""Calibrazione guidata e interattiva della wake word col microfono VERO del HAT (issue #79).

Strumento di misura: il servizio NON lo importa. Va lanciato SUL PI da un terminale (`ssh -t`), con
`bmo-core` fermo (il microfono è esclusivo). Comando completo, dal portatile:

    ssh -t clanker_home@clanker.local \\
      'sudo systemctl stop bmo-core; ~/bmo-pi/venv/bin/python ~/calibra_wake_word.py; sudo systemctl start bmo-core'

Il programma scrive a terminale il PUNTO in cui metterti e la PAROLA da dire. Per ogni ripetizione fa un bip
(1 bip = «Hey BMO»/bmo1, 2 bip = «BMO»/bmo2, 3 bip = la terza parola/bmo3), tu dici la parola subito dopo, e
vedi subito il punteggio di ciascun modello e il livello della tua voce.

Tasti: INVIO per andare avanti. Se un modello non ha sentito niente ma la parola l'hai detta, premi INVIO:
conta come NON rilevata (è proprio il dato che cerchiamo). `r` + INVIO ripete la ripetizione (es. se non
hai fatto in tempo). `q` + INVIO esce stampando quanto raccolto.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

SOGLIE = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7)
SCHEDA = "wm8960soundcard"
SOGLIA_NULLA = 0.05  # sotto questo punteggio dice «non ho sentito niente» e chiede cosa fare

# (modello atteso, parola da dire, numero di bip). Il 14/10 la mappa è stata invertita su indicazione di
# Riccardo e CONFERMATA dalla calibrazione: bmo2 = «Hey BMO» (media 0,62), bmo1 = «BMO» (0,81), bmo3 = terza
# parola (0,62), nessun incrocio. Il riepilogo finale mostra quale modello ha reagito davvero.
PAROLE = [
    ("bmo2", "«Hey BMO»", 1),
    ("bmo1", "«BMO»", 2),
    ("bmo3", None, 3),  # il testo si prende da --terza
]

POSIZIONI = [
    ("1 m", "A 1 METRO dal HAT, di fronte, alla stessa altezza."),
    ("3 m", "A 3 METRI dal HAT, in mezzo alla stanza, in linea col HAT."),
    ("lontano", "Nel PUNTO PIÙ LONTANO della stanza dove vorrai usare BMO (anche di lato o di spalle al HAT)."),
]


def mixer(*args: str) -> None:
    subprocess.run(["amixer", "-c", SCHEDA, "-q", *args], check=False)


def imposta_guadagno(capture: str | None, boost: str | None) -> None:
    if capture is not None:
        mixer("sset", "Capture", str(capture))
    if boost is not None:
        mixer("cset", "name=Left Input Boost Mixer LINPUT1 Volume", str(boost))
        mixer("cset", "name=Right Input Boost Mixer RINPUT1 Volume", str(boost))


SILENZIOSO = False  # se il bip non si sente, il cue è solo la riga «ADESSO» a terminale


def prepara_audio() -> None:
    """Uscita al massimo e instradata: con Speaker 85% il bip a 0,35 era sotto la soglia di ascolto (14/10)."""
    mixer("cset", "name=Left Output Mixer PCM Playback Switch", "on")
    mixer("cset", "name=Right Output Mixer PCM Playback Switch", "on")
    mixer("sset", "Playback", "255")
    mixer("sset", "Speaker", "100%")
    mixer("sset", "Speaker AC", "5")
    mixer("sset", "Speaker DC", "5")


def bip(n: int = 1) -> None:
    """`n` bip brevi dall'altoparlante: il numero dice quale parola dire."""
    if SILENZIOSO:
        return
    t = np.arange(int(0.18 * 48000)) / 48000
    onda = (0.9 * np.sin(2 * np.pi * 1000 * t) * 32767).astype("<i2")
    pausa = np.zeros(int(0.12 * 48000), dtype="<i2")
    sequenza = np.concatenate([np.concatenate([onda, pausa]) for _ in range(n)])
    stereo = np.repeat(sequenza[:, None], 2, axis=1).tobytes()
    subprocess.run(["aplay", "-q", "-D", f"plughw:CARD={SCHEDA},DEV=0", "-t", "raw", "-f", "S16_LE",
                    "-r", "48000", "-c", "2"], input=stereo, check=False)


def dbfs(x: float) -> float:
    return float(20 * np.log10(max(x, 1.0) / 32768))


class Acquisizione(threading.Thread):
    """Legge il microfono in continuo e tiene (istante, pezzo int16, punteggi per modello)."""

    def __init__(self, dispositivo: str, cartella_modelli: str) -> None:
        super().__init__(daemon=True)
        from bmo_core.adapters.audio_input import ArecordConvertitoreAdapter
        from bmo_core.wake_word import RilevatoreLeggero

        modelli = [str(m) for m in sorted(Path(cartella_modelli).glob("bmo*.onnx"))]
        self.nomi = [Path(m).stem for m in modelli]
        self._rilevatore = RilevatoreLeggero(modelli)
        self._microfono = ArecordConvertitoreAdapter(dispositivo=dispositivo)
        self.registro: list[tuple[float, np.ndarray, dict[str, float]]] = []
        self._ferma = threading.Event()
        self.t0 = time.time()
        self.errore: str | None = None

    def run(self) -> None:
        from bmo_core.wake_word import CAMPIONI_PER_PEZZO

        resto = np.empty(0, dtype=np.int16)
        flusso = self._microfono.flusso_pcm()
        try:
            for grezzo in flusso:
                if self._ferma.is_set():
                    break
                resto = np.concatenate([resto, np.frombuffer(grezzo, dtype=np.int16)])
                while len(resto) >= CAMPIONI_PER_PEZZO:
                    pezzo, resto = resto[:CAMPIONI_PER_PEZZO], resto[CAMPIONI_PER_PEZZO:]
                    p = {k: float(v) for k, v in self._rilevatore.predict(pezzo).items()}
                    self.registro.append((time.time() - self.t0, pezzo, p))
        except Exception as e:  # noqa: BLE001 - lo strumento deve dire cosa è andato storto
            self.errore = f"{type(e).__name__}: {e}"
        finally:
            flusso.close()

    def ferma(self) -> None:
        self._ferma.set()

    def adesso(self) -> float:
        return time.time() - self.t0

    def finestra(self, da: float, a: float) -> dict:
        w = [r for r in list(self.registro) if da <= r[0] < a]
        if not w:
            return {"vuota": True, "punteggi": {}, "rms_dbfs": -99.0, "picco_dbfs": -99.0}
        audio = np.concatenate([r[1] for r in w]).astype(np.float64)
        punteggi = {m: max(r[2].get(m, 0.0) for r in w) for m in self.nomi}
        return {
            "vuota": False,
            "punteggi": punteggi,
            "rms_dbfs": dbfs(float(np.sqrt(np.mean(audio ** 2)))),
            "picco_dbfs": dbfs(float(np.abs(audio).max())),
        }


def chiedi(testo: str) -> str:
    try:
        return input(testo).strip().lower()
    except EOFError:
        return "q"


def esegui_posizione(acq: Acquisizione, nome: str, descrizione: str, parole: list[tuple[str, str, int]],
                     ripetizioni: int, finestra_s: float, soglia_vista: float) -> dict:
    print("\n" + "=" * 72)
    print(f"POSIZIONE «{nome}»: {descrizione}")
    print("=" * 72)
    r = chiedi("Quando sei al posto, premi INVIO (q+INVIO per finire): ")
    if r == "q":
        return {"nome": nome, "interrotta": True}
    print("  … 5 secondi di silenzio (non parlare) per misurare l'ambiente …", flush=True)
    t = acq.adesso()
    time.sleep(5.2)
    base = acq.finestra(t, acq.adesso())
    print(f"  ambiente: {base['rms_dbfs']:.1f} dBFS, punteggio massimo {max(base['punteggi'].values(), default=0):.2f}"
          " (sopra la soglia sarebbe un falso scatto)")
    risultato = {"nome": nome, "base": base, "parole": {}}
    for modello, testo_parola, n_bip in parole:
        print(f"\n--- Parola: {testo_parola}  ({modello}, {n_bip} bip) — {ripetizioni} volte, tono normale ---")
        misure = []
        i = 0
        while i < ripetizioni:
            i += 1
            print(f"  [{i}/{ripetizioni}] preparati… poi dì {testo_parola}", flush=True)
            time.sleep(0.8)
            print(f"      >>> ADESSO: {testo_parola} <<<", flush=True)
            bip(n_bip)
            t_in = acq.adesso()
            time.sleep(finestra_s)
            w = acq.finestra(t_in, acq.adesso())
            atteso = w["punteggi"].get(modello, 0.0)
            altri = "  ".join(f"{m}={v:.2f}" for m, v in w["punteggi"].items() if m != modello)
            esito = "SENTITA" if atteso >= soglia_vista else "non sentita"
            sat = "  (SATURA!)" if w["picco_dbfs"] > -1.0 else ""
            print(f"      {modello}={atteso:.2f}  {esito}   | {altri} | voce {w['rms_dbfs']:.1f} dBFS, "
                  f"picco {w['picco_dbfs']:.1f}{sat}")
            if max(w["punteggi"].values(), default=0.0) < SOGLIA_NULLA:
                r = chiedi("      Nessun modello ha reagito. INVIO = l'ho detta (la conto mancata), "
                           "r+INVIO = ripeti, q+INVIO = esci: ")
                if r == "r":
                    i -= 1
                    continue
                if r == "q":
                    risultato["parole"][modello] = misure
                    risultato["interrotta"] = True
                    return risultato
            misure.append({"atteso": atteso, "punteggi": w["punteggi"], "rms_dbfs": w["rms_dbfs"],
                           "picco_dbfs": w["picco_dbfs"]})
            time.sleep(1.2)
        risultato["parole"][modello] = misure
    return risultato


def esegui_rumore(acq: Acquisizione, secondi: float) -> dict:
    """Falsi scatti: TV, musica o conversazione accese, e TU NON DICI LA PAROLA."""
    print("\n" + "=" * 72)
    print("PROVA DI RUMORE: accendi la TV o la musica (o parlate fra di voi) come in una serata normale.")
    print("NON dire «Hey BMO», «BMO» né la terza parola.")
    print("=" * 72)
    r = chiedi(f"Quando è acceso, premi INVIO (ascolto {secondi:.0f} s; q+INVIO per saltare): ")
    if r == "q":
        return {"nome": "rumore", "interrotta": True}
    print(f"  … ascolto {secondi:.0f} secondi …", flush=True)
    t = acq.adesso()
    time.sleep(secondi + 0.2)
    base = acq.finestra(t, acq.adesso())
    # i massimi per ogni 80 ms, per vedere quanti scatti ci sarebbero a ogni soglia
    pezzi = [r_[2] for r_ in list(acq.registro) if t <= r_[0] < t + secondi]
    scatti = {s: sum(1 for p in pezzi if max(p.values(), default=0.0) >= s) for s in SOGLIE}
    print(f"  rumore: {base['rms_dbfs']:.1f} dBFS, punteggio massimo {max(base['punteggi'].values(), default=0):.2f}; "
          "pezzi da 80 ms sopra la soglia: " + "  ".join(f">={s}: {n}" for s, n in scatti.items()))
    return {"nome": "rumore", "base": base, "scatti": {str(k): v for k, v in scatti.items()}, "parole": {}}


def riepilogo(risultati: list[dict]) -> None:
    print("\n" + "#" * 72)
    print("RIEPILOGO (punteggio del modello della parola detta; ✓ = sopra la soglia)")
    print("#" * 72)
    intest = "  ".join(f">={s:<4}" for s in SOGLIE)
    print(f"{'posizione':10s} {'parola':8s} {'media':>6s} {'min':>5s} {'voce dBFS':>10s}   {intest}")
    for r in risultati:
        for modello, misure in r.get("parole", {}).items():
            if not misure:
                continue
            v = [m["atteso"] for m in misure]
            conteggi = "  ".join(f"{sum(1 for x in v if x >= s)}/{len(v):<3}" for s in SOGLIE)
            voce = np.mean([m["rms_dbfs"] for m in misure])
            print(f"{r['nome']:10s} {modello:8s} {np.mean(v):6.2f} {min(v):5.2f} {voce:10.1f}   {conteggi}")
        if r.get("base"):
            print(f"{'':10s} {'ambiente':8s} max punteggio {max(r['base']['punteggi'].values(), default=0):.2f}, "
                  f"{r['base']['rms_dbfs']:.1f} dBFS")


def confusione(risultati: list[dict], parole: list[tuple[str, str, int]]) -> None:
    """Per ogni parola detta, il punteggio medio di ciascun modello: dice quale modello è quale."""
    modelli = sorted({m for r in risultati for ms in r.get("parole", {}).values() for x in ms for m in x["punteggi"]})
    if not modelli:
        return
    print("\nCHI HA REAGITO A COSA (punteggio medio per modello, tutte le posizioni):")
    print(f"{'parola detta':28s} " + "  ".join(f"{m:>6s}" for m in modelli) + "   modello più alto")
    for modello_atteso, testo, _ in parole:
        righe = [x for r in risultati for x in r.get("parole", {}).get(modello_atteso, [])]
        if not righe:
            continue
        medie = {m: float(np.mean([x["punteggi"].get(m, 0.0) for x in righe])) for m in modelli}
        migliore = max(medie, key=medie.get)
        nota = "" if migliore == modello_atteso else f"   <-- atteso {modello_atteso}: la mappa è probabilmente invertita"
        print(f"{testo:28s} " + "  ".join(f"{medie[m]:6.2f}" for m in modelli) + f"   {migliore}{nota}")


def raccomanda(risultati: list[dict]) -> None:
    """La soglia più alta che riconosce almeno l'80% delle ripetizioni da lontano (3 m e oltre) restando sopra l'ambiente."""
    # In produzione scatta se UNO QUALUNQUE dei tre modelli supera la soglia: conta il massimo fra i modelli.
    lontane = [max(m["punteggi"].values(), default=0.0) for r in risultati if r.get("nome") in ("3 m", "lontano")
               for ms in r.get("parole", {}).values() for m in ms]
    ambiente = [max(r["base"]["punteggi"].values(), default=0.0) for r in risultati if r.get("base")]
    if not lontane:
        print("\nNiente da raccomandare: nessuna ripetizione da 3 m o più.")
        return
    amb = max(ambiente, default=0.0)
    print(f"\nAmbiente: punteggio massimo visto {amb:.2f}.")
    scelta = None
    for s in np.arange(0.9, 0.04, -0.05):
        richiamo = sum(1 for x in lontane if x >= s) / len(lontane)
        if richiamo >= 0.8 and s > amb:
            scelta = (round(float(s), 2), richiamo)
            break
    if scelta:
        print(f"RACCOMANDATA: soglia {scelta[0]:.2f} → riconosce {scelta[1]:.0%} delle {len(lontane)} ripetizioni da 3 m e oltre, "
              f"sopra il rumore dell'ambiente.")
    else:
        m = sum(1 for x in lontane if x >= 0.05) / len(lontane)
        print(f"NESSUNA soglia riconosce l'80% da lontano sopra l'ambiente (a 0.05 si arriva al {m:.0%}). "
              "Il problema non è la soglia: serve più guadagno o un modello addestrato meglio.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--capture", default="40", help="guadagno di cattura 0-63 all'inizio (predefinito 40)")
    p.add_argument("--boost", default="2", help="boost LINPUT1/RINPUT1 0-3 all'inizio (predefinito 2)")
    p.add_argument("--ripetizioni", type=int, default=5)
    p.add_argument("--finestra", type=float, default=3.0, help="secondi di ascolto dopo ogni bip")
    p.add_argument("--soglia-vista", type=float, default=0.3, help="soglia con cui si scrive «SENTITA» a terminale")
    p.add_argument("--terza", default="la terza parola (bmo3)", help="il testo della terza parola da mostrare")
    p.add_argument("--solo", default=None, help="solo queste posizioni, separate da virgola (1 m,3 m,lontano)")
    p.add_argument("--senza-rumore", action="store_true", help="salta la prova dei falsi scatti con TV/musica")
    p.add_argument("--rumore-secondi", type=float, default=30.0)
    p.add_argument("--dispositivo", default=f"hw:CARD={SCHEDA},DEV=0")
    p.add_argument("--cartella-modelli", default=str(Path.home() / "bmo-pi/bmo-diy/bmo-core/modelli-wake-word"))
    p.add_argument("--uscita", type=Path, default=None, help="JSON con tutte le misure grezze")
    a = p.parse_args()

    imposta_guadagno(a.capture, a.boost)
    acq = Acquisizione(a.dispositivo, a.cartella_modelli)
    acq.start()
    time.sleep(3.0)  # il tempo di riempire lo stato del rilevatore
    if acq.errore or not acq.registro:
        print(f"Non riesco ad aprire il microfono ({acq.errore or 'nessun dato'}). Hai fermato bmo-core? "
              "`sudo systemctl stop bmo-core`", file=sys.stderr)
        return 1

    global SILENZIOSO
    prepara_audio()
    for tentativo in range(2):
        print("Prova del bip…", flush=True)
        bip(1)
        r = chiedi("Hai sentito il bip? INVIO = sì, n+INVIO = no: ")
        if r != "n":
            break
        if tentativo == 0:
            print("Riprovo con il volume dell'altoparlante al massimo e il bip più lungo…", flush=True)
            mixer("sset", "Speaker", "100%")
    else:
        SILENZIOSO = True
        print("Va bene: senza bip. Il segnale sarà la riga «>>> ADESSO: parola <<<» a terminale: "
              "dì la parola appena la vedi. Il numero di bip non serve: la parola è scritta.")

    parole = [(m, t or a.terza, n) for m, t, n in PAROLE]
    posizioni = [x for x in POSIZIONI if not a.solo or x[0] in [s.strip() for s in a.solo.split(",")]]
    print(f"Microfono aperto. Guadagno: Capture {a.capture}, boost {a.boost}. Modelli: {', '.join(acq.nomi)}.")
    print("Tono di voce NORMALE. 1 bip = «Hey BMO», 2 bip = «BMO», 3 bip = " + a.terza + ".")
    risultati: list[dict] = []
    try:
        for nome, descrizione in posizioni:
            r = esegui_posizione(acq, nome, descrizione, parole, a.ripetizioni, a.finestra, a.soglia_vista)
            risultati.append(r)
            if r.get("interrotta"):
                break
        if not a.senza_rumore and not (risultati and risultati[-1].get("interrotta")):
            risultati.append(esegui_rumore(acq, a.rumore_secondi))
    except KeyboardInterrupt:
        print("\nInterrotto.")
    finally:
        acq.ferma()
        mixer("sset", "Speaker", "85%")  # il volume di tutti i giorni
    riepilogo(risultati)
    confusione(risultati, parole)
    raccomanda(risultati)
    uscita = a.uscita or Path.home() / "bmo-test" / "misure" / time.strftime("calibrazione-%Y-%m-%d_%H%M%S.json")
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(json.dumps({"capture": a.capture, "boost": a.boost, "risultati": risultati}, indent=1,
                                 default=float), encoding="utf-8")
    print(f"\nMisure grezze: {uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
