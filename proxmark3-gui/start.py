#!/usr/bin/env python3
"""Bequemer Startpunkt fuer die Proxmark3-GUI.

    python3 start.py            # startet Server und oeffnet den Browser
    python3 start.py --demo     # erzwingt den Demo-Modus
    python3 start.py --help     # zeigt alle Schalter

Dieses Skript stellt lediglich sicher, dass das Paket ``pm3gui`` gefunden wird,
und ruft dann dessen Startpunkt auf.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Projektverzeichnis in den Suchpfad legen, damit "pm3gui" importierbar ist.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pm3gui.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
