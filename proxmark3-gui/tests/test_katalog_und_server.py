"""Tests fuer Katalog, Client (Demo) und Server-Schnittstelle.

Laeuft ohne zusaetzliche Pakete und ohne angeschlossenen Proxmark:

    python3 tests/test_katalog_und_server.py

Rueckgabewert 0 = alle Tests bestanden.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# Projektwurzel importierbar machen.
WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from pm3gui import client as client_modul  # noqa: E402
from pm3gui import katalog as katalog_modul  # noqa: E402
from pm3gui.client import Pm3Client  # noqa: E402

# Tests duerfen weder die echte Einstellungsdatei noch den echten
# Arbeitsordner anfassen.
_TEMP = Path(tempfile.mkdtemp(prefix="pm3gui-test-"))
client_modul.EINSTELLUNGEN_DATEI = _TEMP / "einstellungen.json"
client_modul.ARBEITSORDNER = _TEMP / "arbeit"
os.environ.pop("PM3_CLIENT", None)
os.environ.pop("PM3_PORT", None)

# Nachgebauter Client: gibt seine Argumente (mit Farbcodes und Umlaut) aus.
FAKE_CLIENT = _TEMP / "bin" / "proxmark3"
FAKE_CLIENT.parent.mkdir(parents=True)
FAKE_CLIENT.write_text(
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "if '--version' in sys.argv:\n"
    "    print('Client: Iceman/master/v9.9.9 (Test)'); sys.exit(0)\n"
    "print('\\x1b[32m[+]\\x1b[0m ARGS=' + '|'.join(sys.argv[1:]) + ' Gr\\u00f6\\u00dfe')\n",
    encoding="utf-8",
)
FAKE_CLIENT.chmod(FAKE_CLIENT.stat().st_mode | stat.S_IXUSR)
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


# ---------------------------------------------------------------------------
# Echter Client-Aufruf (mit nachgebautem Client)
# ---------------------------------------------------------------------------
def test_client_echt() -> None:
    print("Client-Aufruf mit nachgebautem proxmark3")
    client_modul.speichere_einstellungen({"client_pfad": str(FAKE_CLIENT), "anschluss": "/dev/ttyTEST0"})
    client = Pm3Client()
    z = client.zustand()
    pruefe(z.client_gefunden and not z.demo, "Client aus Einstellungsdatei gefunden")
    pruefe(z.geraet_anschluss == "/dev/ttyTEST0", "gespeicherter Anschluss hat Vorrang")
    pruefe("v9.9.9" in z.client_version, "Version wird gelesen")

    erg = client.fuehre_aus("hw status")
    pruefe(erg.erfolg and not erg.demo, "Befehl wird wirklich ausgefuehrt")
    pruefe("ARGS=-p|/dev/ttyTEST0|-c|hw status" in erg.ausgabe, "Aufruf lautet: proxmark3 -p <port> -c <befehl>")
    pruefe("\x1b[" not in erg.ausgabe, "Farbcodes werden entfernt")
    pruefe("Gr\u00f6\u00dfe" in erg.ausgabe, "Umlaute kommen korrekt an (UTF-8)")
    pruefe(client_modul.ARBEITSORDNER.is_dir(), "Arbeitsordner fuer Dateien wird angelegt")

    pruefe(client_modul.pfad_ist_client(str(FAKE_CLIENT)), "Pfadpruefung akzeptiert proxmark3")
    pruefe(not client_modul.pfad_ist_client("/bin/sh"), "Pfadpruefung lehnt fremde Programme ab")
    client_modul.speichere_einstellungen({})


def _post(basis: str, pfad: str, daten: dict, kopf: dict | None = None) -> tuple[int, dict]:
    kopfzeilen = {"Content-Type": "application/json"}
    kopfzeilen.update(kopf or {})
    anfrage = urllib.request.Request(
        f"{basis}{pfad}", data=json.dumps(daten).encode("utf-8"), headers=kopfzeilen, method="POST"
    )
    try:
        with urllib.request.urlopen(anfrage) as antwort:
            return antwort.status, json.loads(antwort.read())
    except urllib.error.HTTPError as fehler:
        return fehler.code, json.loads(fehler.read() or b"{}")


def test_server_einstellungen_und_schutz() -> None:
    print("Einstellungen per Oberflaeche und Schutz vor fremden Seiten")
    app = _Anwendung(demo=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _erzeuge_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    basis = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        code, _ = _post(basis, "/api/einstellungen", {"client_pfad": "C:/Windows/System32/cmd.exe"})
        pruefe(code == 400, "fremdes Programm als Client-Pfad wird abgelehnt")
        code, _ = _post(basis, "/api/einstellungen", {"anschluss": "COM5 & del *"})
        pruefe(code == 400, "ungueltiger Anschluss wird abgelehnt")

        code, z = _post(basis, "/api/einstellungen", {"client_pfad": str(FAKE_CLIENT), "anschluss": "com7"})
        pruefe(code == 200 and z.get("client_gefunden"), "gueltiger Client-Pfad wird gespeichert und genutzt")
        pruefe(z.get("einstellungen", {}).get("anschluss") == "COM7", "COM-Port wird vereinheitlicht")

        code, erg = _post(basis, "/api/ausfuehren", {"befehl": "hw version"})
        pruefe(code == 200 and "-c|hw version" in erg.get("ausgabe", ""), "Befehl laeuft ueber gespeicherten Client")

        # Fremde Webseite (andere Herkunft) darf nichts ausloesen.
        code, _ = _post(basis, "/api/ausfuehren", {"befehl": "hw status"}, {"Origin": "https://boese.example"})
        pruefe(code == 403, "Anfrage von fremder Webseite wird abgelehnt")
        # Einfache Formular-Anfrage (ohne JSON-Kennung) wird abgelehnt.
        code, _ = _post(basis, "/api/ausfuehren", {"befehl": "hw status"}, {"Content-Type": "text/plain"})
        pruefe(code == 403, "Anfrage ohne JSON-Kennung wird abgelehnt")
        # DNS-Rebinding: fremder Hostname
        code, _ = _post(basis, "/api/ausfuehren", {"befehl": "hw status"}, {"Host": "boese.example"})
        pruefe(code == 403, "Anfrage mit fremdem Hostnamen wird abgelehnt")
        # Eigene Oberflaeche (gleiche Herkunft) ist erlaubt.
        code, _ = _post(basis, "/api/ausfuehren", {"befehl": "hw status"}, {"Origin": basis})
        pruefe(code == 200, "Anfrage der eigenen Oberflaeche ist erlaubt")
    finally:
        server.shutdown()
        server.server_close()
        client_modul.speichere_einstellungen({})


# ---------------------------------------------------------------------------
# Windows-Teile (mit nachgebauter Registrierung, laeuft auch unter Linux)
# ---------------------------------------------------------------------------
class _FakeWinreg:
    """Minimaler Nachbau des Windows-Moduls ``winreg``."""

    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self, baum: dict) -> None:
        self._baum = baum

    class _Schluessel:
        def __init__(self, knoten: dict) -> None:
            self.knoten = knoten

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def OpenKey(self, eltern, pfad):  # noqa: N802
        knoten = self._baum if eltern == "HKLM" else eltern.knoten
        for teil in pfad.split("\\"):
            if teil not in knoten.get("keys", {}):
                raise OSError(pfad)
            knoten = knoten["keys"][teil]
        return self._Schluessel(knoten)

    def EnumValue(self, schluessel, i):  # noqa: N802
        werte = list(schluessel.knoten.get("values", {}).items())
        if i >= len(werte):
            raise OSError
        return werte[i][0], werte[i][1], 1

    def EnumKey(self, schluessel, i):  # noqa: N802
        namen = list(schluessel.knoten.get("keys", {}))
        if i >= len(namen):
            raise OSError
        return namen[i]

    def QueryValueEx(self, schluessel, name):  # noqa: N802
        return schluessel.knoten["values"][name], 1


def _pfad(baum: dict, pfad: str, werte: dict | None = None) -> None:
    knoten = baum
    for teil in pfad.split("\\"):
        knoten = knoten.setdefault("keys", {}).setdefault(teil, {})
    if werte:
        knoten.setdefault("values", {}).update(werte)


def test_windows() -> None:
    print("Windows: COM-Port-Erkennung und DLL-Pfad (nachgebaut)")
    baum: dict = {}
    _pfad(baum, r"HARDWARE\DEVICEMAP\SERIALCOMM", {
        r"\Device\Serial0": "COM1",
        r"\Device\USBSER001": "COM4",
        r"\Device\USBSER000": "COM7",
    })
    usb = r"SYSTEM\CurrentControlSet\Enum\USB\VID_9AC4&PID_4B8F"
    _pfad(baum, usb + r"\abc\Device Parameters", {"PortName": "COM7"})
    _pfad(baum, usb + r"\alt\Device Parameters", {"PortName": "COM9"})  # nicht mehr eingesteckt

    sys.modules["winreg"] = _FakeWinreg(baum)
    try:
        ports = client_modul._windows_anschluesse()
    finally:
        del sys.modules["winreg"]
    pruefe(ports[:1] == ["COM7"], f"Proxmark per USB-Kennung zuerst erkannt ({ports})")
    pruefe("COM9" not in ports, "frueher benutzter, abgezogener Port wird ignoriert")
    pruefe(ports == ["COM7", "COM4", "COM1"], "weitere USB-Ports vor sonstigen Ports")

    alt = client_modul.IST_WINDOWS
    client_modul.IST_WINDOWS = True
    try:
        c = Pm3Client(demo_erzwingen=True)
        c._client_pfad = "C:/ProxSpace/pm3/proxmark3/client/proxmark3.exe"
        umg = c._umgebung()
        pfad = umg["PATH"]
        pruefe("ProxSpace/msys2/mingw64/bin" in pfad.replace("\\", "/"), "ProxSpace-DLL-Ordner kommt in den PATH")
        pruefe(umg.get("PYTHONHOME", "").replace("\\", "/").endswith("ProxSpace/msys2/mingw64"),
               "ProxSpace: PYTHONHOME wie in der ProxSpace-Konsole")
        pruefe("qt6/plugins/platforms" in umg.get("QT_QPA_PLATFORM_PLUGIN_PATH", "").replace("\\", "/"),
               "ProxSpace: Qt-Plugin-Pfad gesetzt")

        # Fertiges Paket: client\proxmark3.exe mit client\libs (wie dessen setup.bat)
        paket = _TEMP / "paket" / "client"
        (paket / "libs" / "shell").mkdir(parents=True)
        c._client_pfad = str(paket / "proxmark3.exe")
        umg = c._umgebung()
        pruefe(str(paket / "libs") in umg["PATH"].split(os.pathsep), "Paket: libs-Ordner kommt in den PATH")
        pruefe(umg.get("QT_QPA_PLATFORM_PLUGIN_PATH", "").rstrip("/\\") == str(paket / "libs"),
               "Paket: Qt-Plugin-Pfad zeigt auf libs")
        kandidaten = client_modul._windows_kandidaten()
        erwartet = Path.home() / "ProxSpace" / "pm3" / "proxmark3" / "client" / "proxmark3.exe"
        pruefe(erwartet in kandidaten, "ProxSpace-Standardpfad (pm3/proxmark3/client) wird durchsucht")
    finally:
        client_modul.IST_WINDOWS = alt


def main() -> int:
    for test in (
        test_windows,
        test_generator,
        test_katalog,
        test_client_demo,
        test_server,
        test_client_echt,
        test_server_einstellungen_und_schutz,
    ):
        test()
    print()
    if _fehler:
        print(f"FEHLGESCHLAGEN: {len(_fehler)} Pruefung(en) nicht bestanden.")
        return 1
    print("Alle Tests bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
