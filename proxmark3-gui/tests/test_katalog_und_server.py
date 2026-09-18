"""Tests fuer Katalog, Client (Demo) und Server-Schnittstelle.

Laeuft ohne zusaetzliche Pakete und ohne angeschlossenen Proxmark:

    python3 tests/test_katalog_und_server.py

Rueckgabewert 0 = alle Tests bestanden.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# Projektwurzel importierbar machen.
WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from pm3gui import katalog as katalog_modul  # noqa: E402
from pm3gui.client import Pm3Client  # noqa: E402
from pm3gui.server import _Anwendung, _erzeuge_handler  # noqa: E402
from werkzeuge.katalog_erzeugen import baue_katalog, zerlege  # noqa: E402

_fehler: list[str] = []


def pruefe(bedingung: bool, nachricht: str) -> None:
    if bedingung:
        print(f"  [ok] {nachricht}")
    else:
        print(f"  [FEHLER] {nachricht}")
        _fehler.append(nachricht)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
def test_generator() -> None:
    print("Generator (commands.md -> JSON)")
    beispiel = """
### hf mfu

 { MIFARE Ultralight RFIDs...          }

|command                  |offline |description
|-------                  |------- |-----------
|`hf mfu info            `|N       |`Tag information`
|`hf mfu dump            `|N       |`Dump tag to file`
|`hf mfu view            `|Y       |`Display content from tag dump file`
""".strip()
    zerlegt = zerlege(beispiel.splitlines())
    pruefe(len(zerlegt["befehle"]) == 3, "drei Befehle erkannt")
    info = next(b for b in zerlegt["befehle"] if b["pfad"] == "hf mfu info")
    pruefe(info["offline"] is False, "Offline-Spalte 'N' korrekt gelesen")
    view = next(b for b in zerlegt["befehle"] if b["pfad"] == "hf mfu view")
    pruefe(view["offline"] is True, "Offline-Spalte 'Y' korrekt gelesen")
    pruefe(info["kategorie"] == "hf", "Kategorie aus Pfad abgeleitet")

    katalog = baue_katalog(beispiel)
    pruefe(katalog["kategorien"][0]["id"] == "hf", "Kategorie im Katalog vorhanden")
    pruefe(any(a["pfad"] == "hf mfu" for a in katalog["abschnitte"]), "Abschnitt vorhanden")


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------
def test_katalog() -> None:
    print("Katalog laden und uebersetzen")
    kat = katalog_modul.lade_katalog()
    stat = kat.statistik()
    pruefe(stat["befehle"] > 500, f"viele Befehle geladen ({stat['befehle']})")
    pruefe(stat["kategorien"] >= 10, f"mehrere Kategorien ({stat['kategorien']})")

    # Uebersetzung greift.
    hf_mf_dump = kat.befehl("hf mf dump")
    pruefe(hf_mf_dump is not None, "Befehl 'hf mf dump' vorhanden")
    if hf_mf_dump:
        pruefe(hf_mf_dump["titel"] == "Karte auslesen (Abbild)", "deutsche Uebersetzung greift")
        pruefe(hf_mf_dump["uebersetzt"] is True, "als uebersetzt markiert")

    # Warnung wird uebernommen.
    wrbl = kat.befehl("lf t55xx write")
    pruefe(bool(wrbl and wrbl["warnung"]), "Warnhinweis vorhanden bei 'lf t55xx write'")

    # Kein Absturz bei unuebersetztem Befehl, Original als Rueckfall.
    alle = kat.alle_befehle()
    ohne_ue = [b for b in alle if not b["uebersetzt"]]
    pruefe(len(ohne_ue) > 0, "es gibt (erwartbar) noch unuebersetzte Befehle")
    pruefe(all(b["beschreibung"] for b in ohne_ue), "auch unuebersetzte haben eine Beschreibung")

    # Suche
    treffer = kat.suche("dump")
    pruefe(len(treffer) > 3, f"Suche nach 'dump' liefert Treffer ({len(treffer)})")
    treffer_de = kat.suche("auslesen")
    pruefe(len(treffer_de) > 0, "Suche findet auch deutsche Begriffe")

    # Baumstruktur konsistent
    for k in kat.baum:
        pruefe(
            k["anzahl"] == sum(len(a["befehle"]) for a in k["abschnitte"]),
            f"Anzahl in Kategorie '{k['id']}' stimmt",
        )
        break  # eine Stichprobe reicht fuer die Ausgabe


# ---------------------------------------------------------------------------
# Client (Demo)
# ---------------------------------------------------------------------------
def test_client_demo() -> None:
    print("Client im Demo-Modus")
    client = Pm3Client(demo_erzwingen=True)
    zustand = client.zustand()
    pruefe(zustand.demo is True, "Demo-Modus aktiv")
    erg = client.fuehre_aus("hw status")
    pruefe(erg.demo is True, "Ausfuehrung meldet Demo")
    pruefe("hw status" in erg.ausgabe, "Befehl erscheint in der Demo-Ausgabe")
    pruefe(erg.erfolg is True, "Demo-Aufruf gilt als erfolgreich")


# ---------------------------------------------------------------------------
# Server / HTTP-Schnittstelle
# ---------------------------------------------------------------------------
def test_server() -> None:
    print("HTTP-Schnittstelle")
    app = _Anwendung(demo=True)
    handler = _erzeuge_handler(app)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    time.sleep(0.2)
    basis = f"http://127.0.0.1:{port}"

    try:
        # Startseite
        with urllib.request.urlopen(f"{basis}/") as antwort:
            html = antwort.read().decode("utf-8")
        pruefe("Proxmark3" in html, "Startseite wird ausgeliefert")

        # Katalog
        with urllib.request.urlopen(f"{basis}/api/katalog") as antwort:
            daten = json.loads(antwort.read())
        pruefe("baum" in daten and len(daten["baum"]) > 0, "Katalog-API liefert Baum")
        pruefe(daten["statistik"]["befehle"] > 500, "Katalog-API meldet Statistik")

        # Zustand
        with urllib.request.urlopen(f"{basis}/api/zustand") as antwort:
            z = json.loads(antwort.read())
        pruefe(z["demo"] is True, "Zustand-API meldet Demo")

        # Erlaubten Befehl ausfuehren
        anfrage = urllib.request.Request(
            f"{basis}/api/ausfuehren",
            data=json.dumps({"befehl": "hw status"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(anfrage) as antwort:
            erg = json.loads(antwort.read())
        pruefe(erg["demo"] is True, "erlaubter Befehl wird (im Demo) ausgefuehrt")

        # Erlaubter Befehl mit Zusatzparametern
        anfrage = urllib.request.Request(
            f"{basis}/api/ausfuehren",
            data=json.dumps({"befehl": "hf mf rdbl --blk 0"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(anfrage) as antwort:
            erg = json.loads(antwort.read())
        pruefe(erg.get("demo") is True, "Befehl mit Zusatzparametern erlaubt")

        # Unerlaubten Befehl abweisen
        anfrage = urllib.request.Request(
            f"{basis}/api/ausfuehren",
            data=json.dumps({"befehl": "rm -rf /"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(anfrage) as antwort:
                erg = json.loads(antwort.read())
                abgewiesen = not erg.get("erfolg", True)
        except urllib.error.HTTPError as fehler:
            abgewiesen = fehler.code == 400
        pruefe(abgewiesen, "unbekannter/gefaehrlicher Befehl wird abgewiesen")

        # Suche-API
        with urllib.request.urlopen(f"{basis}/api/suche?q=dump") as antwort:
            such = json.loads(antwort.read())
        pruefe(len(such["treffer"]) > 0, "Suche-API liefert Treffer")

    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    for test in (test_generator, test_katalog, test_client_demo, test_server):
        test()
    print()
    if _fehler:
        print(f"FEHLGESCHLAGEN: {len(_fehler)} Pruefung(en) nicht bestanden.")
        return 1
    print("Alle Tests bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
