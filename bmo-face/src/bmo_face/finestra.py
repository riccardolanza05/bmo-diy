"""La finestra su schermo di bmo-face: renderer + socket, dal vivo (issue #23).

Due modalità:
- `--pixel`: 1 pixel del pannello = 1 pixel reale dello schermo. Per
  controllare l'arte e le animazioni senza la densità dello schermo del PC
  di mezzo.
- dimensione fisica (predefinita, criterio b della #23): la finestra occupa
  sullo schermo lo stesso ingombro in millimetri del pannello vero. Se lo
  schermo di sviluppo ha un pitch più grosso del pannello target (il caso di
  questo laptop, vedi `dimensione_fisica.py`), l'immagine viene rimpicciolita
  e perde nitidezza che il pannello vero non perderebbe: un avviso lo dice
  chiaro all'avvio — la prova risulta più severa del display reale, mai più
  ottimista.

I pixel reali (non quelli "logici" di GTK) contano per entrambe le modalità:
su questo laptop (scala 1.5, §2.11-adiacente) lasciare che sia GTK a
ridimensionare produrrebbe un'immagine sfocata, non l'equivalente del
pannello SPI vero. La finestra chiede sempre esplicitamente i pixel fisici
che le servono, dividendo per `get_scale_factor()` solo per la dimensione
*logica* richiesta a GTK (stessa tecnica già usata altrove sul PC di
Riccardo per rendering ad alta risoluzione).

Uso:
    python -m bmo_face.build_face --destinazione assets/
    python -m bmo_face.finestra --assets assets/                   # dimensione fisica, 2.4"
    python -m bmo_face.finestra --assets assets/ --pixel            # 1:1, per giudicare l'arte
    python -m bmo_face.finestra --assets assets/ --pannello 3.5     # l'altro preset del BOM
    python -m bmo_face.finestra --assets assets/ --mm-larghezza 40 --mm-altezza 30  # caso peggiore
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .animazione import ComandoFaccia, Renderer
from .dimensione_fisica import PRESET_PANNELLI, e_sottocampionato, pitch_schermo_mm, px_per_dimensione_fisica
from .formato import NOME_BIN, NOME_JSON, carica_manifesto, mappa_bin
from .servitore import ServitoreFaccia

FPS_FINESTRA = 25


def _host_px(argomenti: argparse.Namespace, pannello_px: tuple[int, int]) -> tuple[int, int]:
    """Quanti pixel reali dello schermo di sviluppo deve occupare la finestra."""
    if argomenti.pixel:
        return pannello_px
    mm_larghezza = argomenti.mm_larghezza
    mm_altezza = argomenti.mm_altezza
    if mm_larghezza is None or mm_altezza is None:
        mm_larghezza, mm_altezza = PRESET_PANNELLI[argomenti.pannello]
    pitch = tuple(argomenti.pitch_mm) if argomenti.pitch_mm else pitch_schermo_mm(argomenti.monitor)
    if pitch is None:
        raise SystemExit(
            "impossibile leggere le dimensioni fisiche dello schermo (hyprctl non disponibile o non "
            "sotto Hyprland): usa --pixel per la modalità 1:1, oppure --pitch-mm LARGHEZZA ALTEZZA "
            "per darlo a mano (mm per pixel, da hyprctl monitors -j su questa macchina o dal "
            "datasheet del pannello dello schermo di sviluppo)"
        )
    host = px_per_dimensione_fisica(mm_larghezza, mm_altezza, pitch)
    if e_sottocampionato(host, pannello_px):
        print(
            f"[finestra: attenzione — questo schermo (pitch {pitch[0]:.3f}×{pitch[1]:.3f} mm/px) è "
            f"più grossolano del pannello {pannello_px[0]}×{pannello_px[1]} target: la faccia sarà "
            f"mostrata a {host[0]}×{host[1]} px, sottocampionata. La prova di leggibilità è quindi "
            "più severa del display vero, mai più ottimista — vedi il README, «Le persone di casa» "
            "no, «Finestra a dimensione fisica».]",
            file=sys.stderr,
        )
    return host


def _comando_snapshot(servitore: ServitoreFaccia) -> ComandoFaccia:
    """Una copia di `servitore.comando`, presa sotto lock: il renderer non
    deve mai leggere un `ComandoFaccia` che il thread del socket sta mutando."""
    with servitore.lock:
        return ComandoFaccia(**vars(servitore.comando))


def _texture_da_frame(frame, larghezza: int, altezza: int):
    import gi

    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib

    if frame.size != (larghezza, altezza):
        frame = frame.resize((larghezza, altezza))
    grezzo = frame.convert("RGB").tobytes()
    return Gdk.MemoryTexture.new(larghezza, altezza, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(grezzo), larghezza * 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assets", type=Path, default=Path("."), help="cartella con faces.bin e faces.json")
    parser.add_argument("--pixel", action="store_true", help="1 pixel del pannello = 1 pixel reale (modalità 1:1)")
    parser.add_argument("--pannello", choices=sorted(PRESET_PANNELLI), default="2.4", help="preset del BOM (§1.3)")
    parser.add_argument("--mm-larghezza", type=float, default=None, help="ingombro fisico, sostituisce --pannello")
    parser.add_argument("--mm-altezza", type=float, default=None)
    parser.add_argument(
        "--pitch-mm", type=float, nargs=2, default=None, metavar=("X", "Y"), help="pitch dello schermo a mano"
    )
    parser.add_argument("--monitor", default=None, help="nome del monitor Hyprland, se ce n'è più di uno")
    parser.add_argument("--socket", type=Path, default=None, help="percorso del socket Unix (predefinito: automatico)")
    argomenti = parser.parse_args()

    manifesto = carica_manifesto(argomenti.assets / NOME_JSON)
    host_larghezza, host_altezza = _host_px(argomenti, (manifesto.larghezza, manifesto.altezza))

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import GLib, Gtk

    with mappa_bin(argomenti.assets / NOME_BIN) as dati:
        renderer = Renderer(manifesto, dati)
        servitore = ServitoreFaccia(percorso=argomenti.socket)
        servitore.avvia()
        print(f"[finestra: {host_larghezza}×{host_altezza} px, socket su {servitore.percorso}]", file=sys.stderr)

        app = Gtk.Application(application_id="dev.bmodiy.face")

        def attiva(app: Gtk.Application) -> None:
            finestra = Gtk.ApplicationWindow(application=app, title="BMO")
            finestra.set_resizable(False)
            scala = finestra.get_scale_factor() or 1
            immagine = Gtk.Picture()
            immagine.set_content_fit(Gtk.ContentFit.FILL)
            immagine.set_size_request(
                max(1, round(host_larghezza / scala)), max(1, round(host_altezza / scala))
            )
            finestra.set_child(immagine)

            def fotogramma() -> bool:
                comando = _comando_snapshot(servitore)
                frame = renderer.disegna(comando, time.monotonic())
                immagine.set_paintable(_texture_da_frame(frame, host_larghezza, host_altezza))
                return True  # continua a girare: GLib.timeout_add richiama finché non torna False

            fotogramma()
            GLib.timeout_add(round(1000 / FPS_FINESTRA), fotogramma)
            finestra.present()

        app.connect("activate", attiva)
        try:
            app.run(None)
        finally:
            servitore.ferma()


if __name__ == "__main__":
    main()
