#!/usr/bin/env python3
"""Erzeugt den Befehlskatalog (``befehle.json``) aus der Proxmark3-Doku.

Die Datei ``doc/commands.md`` aus dem Proxmark3-Repository (Iceman-Fork,
RfidResearchGroup/proxmark3) enthaelt einen vollstaendigen Dump aller
Client-Befehle. Dieses Werkzeug wandelt den Dump in das JSON-Format um, das die
GUI zum Aufbau ihres Menuebaums verwendet.

Aufruf:

    python3 werkzeuge/katalog_erzeugen.py                 # nutzt werkzeuge/commands.md
    python3 werkzeuge/katalog_erzeugen.py --quelle /pfad/commands.md
    python3 werkzeuge/katalog_erzeugen.py --laden         # laedt die Datei aus dem Netz

Der Katalog wird nach ``pm3gui/daten/befehle.json`` geschrieben.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import re
import sys
from pathlib import Path
from typing import Iterable

PROJEKT = Path(__file__).resolve().parent.parent
STANDARD_QUELLE = PROJEKT / "werkzeuge" / "commands.md"
STANDARD_ZIEL = PROJEKT / "pm3gui" / "daten" / "befehle.json"
HERKUNFT_URL = (
    "https://raw.githubusercontent.com/RfidResearchGroup/proxmark3/master/doc/commands.md"
)

_ABSCHNITT = re.compile(r"^###\s+(.+?)\s*$")
_BESCHREIBUNG = re.compile(r"^\s*\{\s*(.*?)\s*\}\s*$")
_TABELLENZEILE = re.compile(r"^\|`(?P<pfad>[^`]+)`\|(?P<offline>[^|]*)\|`(?P<text>.*)`\s*$")


def _saeubern(text: str) -> str:
    """Entfernt Fuellzeichen und doppelte Leerzeichen aus einem Textfeld."""
    return " ".join(text.replace(" ", " ").split()).strip()


def zerlege(zeilen: Iterable[str]) -> dict:
    """Zerlegt den Markdown-Dump in Abschnitte und Befehle."""
    abschnitte: dict[str, dict] = {}
    befehle: list[dict] = []
    gesehen: set[str] = set()

    aktueller_abschnitt = ""  # Wurzelebene (help, auto, clear, ...)
    abschnitte[""] = {
        "pfad": "",
        "kategorie": "basis",
        "titel": "Grundbefehle",
        "beschreibung_en": "Basic client commands",
    }
    warte_auf_beschreibung = False

    for rohzeile in zeilen:
        zeile = rohzeile.rstrip("\n")

        treffer = _ABSCHNITT.match(zeile)
        if treffer:
            aktueller_abschnitt = _saeubern(treffer.group(1))
            abschnitte.setdefault(
                aktueller_abschnitt,
                {
                    "pfad": aktueller_abschnitt,
                    "kategorie": aktueller_abschnitt.split(" ")[0],
                    "titel": aktueller_abschnitt,
                    "beschreibung_en": "",
                },
            )
            warte_auf_beschreibung = True
            continue

        if warte_auf_beschreibung:
            treffer = _BESCHREIBUNG.match(zeile)
            if treffer:
                text = _saeubern(treffer.group(1)).rstrip(".")
                abschnitte[aktueller_abschnitt]["beschreibung_en"] = text
                warte_auf_beschreibung = False
                continue
            if zeile.strip():
                warte_auf_beschreibung = False

        treffer = _TABELLENZEILE.match(zeile)
        if not treffer:
            continue

        pfad = _saeubern(treffer.group("pfad"))
        if not pfad or pfad.startswith("-"):
            continue
        if pfad in gesehen:
            continue
        gesehen.add(pfad)

        teile = pfad.split(" ")
        # Einwortbefehle (help, auto, clear, ...) liegen auf der Wurzelebene und
        # werden in der GUI unter "basis" zusammengefasst.
        kategorie = teile[0] if len(teile) > 1 else "basis"
        befehle.append(
            {
                "pfad": pfad,
                "name": teile[-1],
                "kategorie": kategorie,
                "abschnitt": aktueller_abschnitt,
                "offline": treffer.group("offline").strip().upper().startswith("Y"),
                "beschreibung_en": _saeubern(treffer.group("text")),
                "ist_hilfe": teile[-1] in ("help", "?"),
            }
        )

    return {"abschnitte": abschnitte, "befehle": befehle}


def baue_katalog(quelltext: str, herkunft: str = HERKUNFT_URL) -> dict:
    """Baut die vollstaendige Katalogstruktur inklusive Kategorieliste."""
    zerlegt = zerlege(quelltext.splitlines())
    abschnitte = zerlegt["abschnitte"]
    befehle = zerlegt["befehle"]

    kategorien: dict[str, dict] = {}
    for befehl in befehle:
        kat = befehl["kategorie"]
        eintrag = kategorien.setdefault(
            kat,
            {
                "id": kat or "basis",
                "name": kat or "Grundbefehle",
                "beschreibung_en": abschnitte.get(kat, {}).get("beschreibung_en", ""),
                "anzahl": 0,
            },
        )
        eintrag["anzahl"] += 1

    return {
        "herkunft": herkunft,
        "erzeugt_am": _datetime.date.today().isoformat(),
        "hinweis": (
            "Automatisch erzeugt aus doc/commands.md des Proxmark3-Clients. "
            "Nicht von Hand bearbeiten - siehe werkzeuge/katalog_erzeugen.py."
        ),
        "kategorien": sorted(kategorien.values(), key=lambda k: k["id"]),
        "abschnitte": sorted(abschnitte.values(), key=lambda a: a["pfad"]),
        "befehle": befehle,
    }


def _lade_aus_netz(url: str) -> str:
    import urllib.request

    with urllib.request.urlopen(url, timeout=30) as antwort:  # noqa: S310
        return antwort.read().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quelle", type=Path, default=STANDARD_QUELLE)
    parser.add_argument("--ziel", type=Path, default=STANDARD_ZIEL)
    parser.add_argument(
        "--laden",
        action="store_true",
        help="commands.md frisch aus dem Proxmark3-Repository laden",
    )
    argumente = parser.parse_args(argv)

    if argumente.laden:
        print(f"Lade {HERKUNFT_URL} ...")
        text = _lade_aus_netz(HERKUNFT_URL)
        argumente.quelle.write_text(text, encoding="utf-8")
    else:
        if not argumente.quelle.exists():
            print(f"Quelle nicht gefunden: {argumente.quelle}", file=sys.stderr)
            return 1
        text = argumente.quelle.read_text(encoding="utf-8")

    katalog = baue_katalog(text)
    argumente.ziel.parent.mkdir(parents=True, exist_ok=True)
    argumente.ziel.write_text(
        json.dumps(katalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{len(katalog['befehle'])} Befehle, {len(katalog['abschnitte'])} Abschnitte, "
        f"{len(katalog['kategorien'])} Kategorien -> {argumente.ziel}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
