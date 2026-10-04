"""Scatta una foto con la camera CSI del Pi (adapter `CameraGrezzaV4L2`) e la scrive su file (issue #77).

    PYTHONPATH=.../bmo-core/src python scatta.py /tmp/foto.jpg [--ruota 0|180]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from bmo_core.adapters.camera import CameraGrezzaV4L2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("destinazione", type=Path)
    parser.add_argument("--ruota", type=int, choices=(0, 180), default=None, help="predefinito: BMO_CAMERA_RUOTA o 0")
    argomenti = parser.parse_args()
    camera = CameraGrezzaV4L2(ruota=argomenti.ruota)
    inizio = time.monotonic()
    foto = camera.scatta_foto(argomenti.destinazione)
    print(f"{foto} ({foto.stat().st_size // 1024} kB) in {time.monotonic() - inizio:.1f} s; "
          f"esposizione {camera.esposizione}, guadagno {camera.guadagno}")


if __name__ == "__main__":
    main()
