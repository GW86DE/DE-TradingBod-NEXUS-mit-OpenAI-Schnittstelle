"""Startpunkt: ``python3 -m pm3gui``."""

from __future__ import annotations

import argparse

from . import server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deutschsprachige GUI fuer den Proxmark3-Client."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Adresse (Standard: nur eigener Rechner)")
    parser.add_argument("--port", type=int, default=8137, help="Port (Standard: 8137)")
    parser.add_argument("--demo", action="store_true", help="Demo-Modus erzwingen (kein Geraet noetig)")
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch oeffnen")
    parser.add_argument("--zeitlimit", type=int, default=60, help="Zeitlimit je Befehl in Sekunden")
    argumente = parser.parse_args(argv)

    server.starte(
        host=argumente.host,
        port=argumente.port,
        demo=argumente.demo,
        browser_oeffnen=not argumente.kein_browser,
        zeitlimit=argumente.zeitlimit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
