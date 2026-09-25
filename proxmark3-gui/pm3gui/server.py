"""Lokaler Webserver der Proxmark3-GUI.

Startet einen kleinen HTTP-Server aus der Python-Standardbibliothek (keine
zusaetzlichen Pakete noetig), der die Weboberflaeche ausliefert und eine
schlanke JSON-Schnittstelle bereitstellt. Die Oberflaeche wird dann im Browser
angezeigt.

Sicherheit: Der Server bindet standardmaessig nur an 127.0.0.1 (nur der eigene
Rechner). Befehle koennen nur ausgefuehrt werden, wenn sie im Katalog des
offiziellen Clients vorkommen - beliebige Systembefehle sind nicht moeglich.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import katalog as katalog_modul
from .sitzung import MAX_BEFEHL
from .client import (
    ERLAUBTE_NAMEN,
    Pm3Client,
    lade_einstellungen,
    pfad_ist_client,
    speichere_einstellungen,
)

WEB = Path(__file__).resolve().parent / "web"

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class _Anwendung:
    """Buendelt Katalog und Client, damit der Handler zustandslos bleibt."""

    def __init__(self, demo: bool = False, zeitlimit: int = 60) -> None:
        self.katalog = katalog_modul.lade_katalog()
        self.client = Pm3Client(demo_erzwingen=demo, zeitlimit=zeitlimit)


def _erzeuge_handler(app: _Anwendung) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Proxmark3GUI"
        protocol_version = "HTTP/1.1"

        # -- Hilfen ----------------------------------------------------------

        def _sende_json(self, daten: object, status: int = 200) -> None:
            rumpf = json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(rumpf)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(rumpf)

        def _sende_datei(self, pfad: Path) -> None:
            if not pfad.exists() or not pfad.is_file():
                self.send_error(404, "Nicht gefunden")
                return
            # Kein Ausbrechen aus dem Web-Verzeichnis erlauben.
            try:
                pfad.resolve().relative_to(WEB.resolve())
            except ValueError:
                self.send_error(403, "Verboten")
                return
            rumpf = pfad.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _MIME.get(pfad.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(rumpf)))
            self.end_headers()
            self.wfile.write(rumpf)

        def _lies_json_rumpf(self) -> dict:
            laenge = int(self.headers.get("Content-Length", 0) or 0)
            if laenge <= 0:
                return {}
            roh = self.rfile.read(laenge)
            try:
                return json.loads(roh.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

        def log_message(self, *args) -> None:  # noqa: D401 - Ausgabe unterdruecken
            pass

        # -- GET -------------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            zerlegt = urlparse(self.path)
            pfad = zerlegt.path

            if pfad in ("/", "/index.html"):
                self._sende_datei(WEB / "index.html")
                return

            if pfad == "/api/katalog":
                self._sende_json(
                    {
                        "baum": app.katalog.baum,
                        "glossar": app.katalog.glossar,
                        "statistik": app.katalog.statistik(),
                        "metadaten": app.katalog.metadaten(),
                    }
                )
                return

            if pfad == "/api/zustand":
                self._sende_json(self._zustand_mit_details())
                return

            if pfad == "/api/suche":
                argumente = parse_qs(zerlegt.query)
                text = (argumente.get("q", [""])[0])
                nur_offline = argumente.get("offline", ["0"])[0] == "1"
                self._sende_json({"treffer": app.katalog.suche(text, nur_offline)})
                return

            # Statische Dateien aus dem Web-Verzeichnis.
            ziel = (WEB / pfad.lstrip("/")).resolve()
            self._sende_datei(ziel)

        # -- POST ------------------------------------------------------------

        def _zustand_mit_details(self) -> dict:
            daten = dict(app.client.zustand().__dict__)
            daten["durchsucht"] = app.client.durchsucht
            daten["einstellungen"] = lade_einstellungen()
            return daten

        def _anfrage_vertrauenswuerdig(self) -> bool:
            """Schutz gegen fremde Webseiten (CSRF / DNS-Rebinding).

            Eine beliebige Internetseite im selben Browser koennte sonst
            Anfragen an 127.0.0.1 schicken und so Befehle am Proxmark ausloesen.
            Zugelassen werden nur JSON-Anfragen (erzwingt beim Browser eine
            Rueckfrage, die dieser Server nicht freigibt), deren Host lokal ist
            und deren Herkunft - falls angegeben - diese Oberflaeche selbst ist.
            """
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return False
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            lokal = {"127.0.0.1", "localhost", "::1", self.server.server_address[0]}
            if host not in lokal:
                return False
            herkunft = self.headers.get("Origin")
            if herkunft and urlparse(herkunft).hostname not in lokal:
                return False
            return True

        def do_POST(self) -> None:  # noqa: N802
            zerlegt = urlparse(self.path)
            if not self._anfrage_vertrauenswuerdig():
                self._sende_json({"erfolg": False, "ausgabe": "Anfrage abgelehnt."}, status=403)
                return

            if zerlegt.path == "/api/neu_suchen":
                app.client.neu_suchen()
                self._sende_json(self._zustand_mit_details())
                return

            if zerlegt.path == "/api/verbinden":
                ok, meldung = app.client.verbinden()
                antwort = self._zustand_mit_details()
                antwort.update({"erfolg": ok, "verbindungs_meldung": meldung})
                self._sende_json(antwort)
                return

            if zerlegt.path == "/api/trennen":
                app.client.trennen()
                antwort = self._zustand_mit_details()
                antwort.update({"erfolg": True, "verbindungs_meldung": "Getrennt."})
                self._sende_json(antwort)
                return

            if zerlegt.path == "/api/einstellungen":
                self._einstellungen_speichern(self._lies_json_rumpf())
                return

            if zerlegt.path != "/api/ausfuehren":
                self.send_error(404, "Nicht gefunden")
                return

            daten = self._lies_json_rumpf()
            befehl = str(daten.get("befehl", "")).strip()

            # Nur Befehle zulassen, die im Katalog stehen (Praefix-Abgleich).
            # Zusaetzliche Parameter (z. B. Blocknummern) sind erlaubt, solange
            # der Befehl mit einem bekannten Katalogpfad beginnt.
            if not self._befehl_erlaubt(befehl):
                self._sende_json(
                    {
                        "erfolg": False,
                        "ausgabe": (
                            "Dieser Befehl wird nicht ausgefuehrt: Er steht nicht im "
                            "Proxmark3-Katalog, ist zu lang oder enthaelt ';' bzw. "
                            "Zeilenumbrueche (bitte Befehle einzeln senden)."
                        ),
                        "befehl": befehl,
                    },
                    status=400,
                )
                return

            ergebnis = app.client.fuehre_aus(befehl)
            self._sende_json(ergebnis.__dict__)

        def _einstellungen_speichern(self, daten: dict) -> None:
            einstellungen = lade_einstellungen()
            client_pfad = str(daten.get("client_pfad", "")).strip().strip('"')
            anschluss = str(daten.get("anschluss", "")).strip()

            if client_pfad and not pfad_ist_client(client_pfad):
                namen = ", ".join(sorted(ERLAUBTE_NAMEN))
                self._sende_json(
                    {
                        "erfolg": False,
                        "meldung": (
                            f"Unter diesem Pfad liegt kein Proxmark3-Client ({namen}). "
                            "Bitte den vollstaendigen Pfad zur Datei proxmark3.exe angeben, "
                            "z. B. C:\\ProxSpace\\pm3\\proxmark3\\client\\proxmark3.exe"
                        ),
                    },
                    status=400,
                )
                return
            # Anschluss: nur COMx bzw. /dev/... zulassen.
            if anschluss and not (
                anschluss.upper().startswith("COM") and anschluss[3:].isdigit()
                or anschluss.startswith("/dev/")
            ):
                self._sende_json(
                    {"erfolg": False, "meldung": "Anschluss bitte als COM5 bzw. /dev/ttyACM0 angeben."},
                    status=400,
                )
                return

            if "automatisch_verbinden" in daten:
                einstellungen["automatisch_verbinden"] = bool(daten["automatisch_verbinden"])
            einstellungen["client_pfad"] = client_pfad
            einstellungen["anschluss"] = anschluss.upper() if anschluss.upper().startswith("COM") else anschluss
            speichere_einstellungen(einstellungen)
            # Neue Angaben (z. B. anderer Anschluss) erst nach Neuverbindung wirksam.
            app.client.trennen()
            app.client.neu_suchen()
            antwort = self._zustand_mit_details()
            antwort["erfolg"] = True
            self._sende_json(antwort)

        @staticmethod
        def _befehl_erlaubt(befehl: str) -> bool:
            if not befehl or len(befehl) > MAX_BEFEHL:
                return False
            # ";" und Zeilenumbrueche wuerden weitere, ungepruefte Befehle anhaengen.
            if any(z in befehl for z in (";", "\n", "\r")):
                return False
            teile = befehl.split()
            # Von lang nach kurz pruefen, ob ein Praefix ein bekannter Befehl ist.
            for laenge in range(len(teile), 0, -1):
                if app.katalog.befehl(" ".join(teile[:laenge])):
                    return True
            return False

    return Handler


def starte(
    host: str = "127.0.0.1",
    port: int = 8137,
    demo: bool = False,
    browser_oeffnen: bool = True,
    zeitlimit: int = 60,
) -> None:
    adresse = f"http://{host}:{port}/"
    app = _Anwendung(demo=demo, zeitlimit=zeitlimit)
    handler = _erzeuge_handler(app)
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError:
        # Meist laeuft die Oberflaeche schon (z. B. Startdatei doppelt geklickt).
        print(f"Die Oberflaeche laeuft bereits (Port {port} ist belegt).")
        print(f"Oeffne {adresse} im Browser ...")
        print("Fuer eine zweite Instanz einen anderen Port waehlen: start.py --port 8138")
        if browser_oeffnen:
            webbrowser.open(adresse)
        return
    stat = app.katalog.statistik()
    print("=" * 60)
    print("  Proxmark3-GUI (Deutsch)")
    print("=" * 60)
    print(f"  Adresse:     {adresse}")
    print(f"  Befehle:     {stat['befehle']}  |  Kategorien: {stat['kategorien']}")
    zustand = app.client.zustand()
    print(f"  Status:      {'DEMO-MODUS' if zustand.demo else 'Client aktiv'}")
    print(f"  {zustand.meldung}")
    print("-" * 60)
    print("  Zum Beenden: Strg+C")
    print("=" * 60)

    if browser_oeffnen:
        threading.Timer(0.7, lambda: webbrowser.open(adresse)).start()

    # Beim Start automatisch mit dem Proxmark3 verbinden (abschaltbar in der
    # Oberflaeche), damit man nichts weiter starten muss.
    if (
        not zustand.demo
        and zustand.geraet_verbunden
        and lade_einstellungen().get("automatisch_verbinden", True)
    ):
        def _auto_verbinden() -> None:
            ok, meldung = app.client.verbinden()
            print(f"  Automatisch verbinden: {meldung.splitlines()[0]}")

        threading.Thread(target=_auto_verbinden, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        app.client.trennen()
        server.server_close()
