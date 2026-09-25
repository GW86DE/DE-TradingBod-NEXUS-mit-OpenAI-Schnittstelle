"""Bindeglied zwischen der Oberflaeche und dem echten Proxmark3-Client.

Die Klasse :class:`Pm3Client` sucht die installierte Client-Programmdatei
(``proxmark3``/``proxmark3.exe``), erkennt den Anschluss des Geraets und fuehrt
einzelne Befehle ueber ``proxmark3 -p <anschluss> -c "<befehl>"`` aus. Ist kein
Client installiert, laeuft alles im Demo-Modus weiter: Die Oberflaeche bleibt
vollstaendig bedienbar, nur werden statt echter Geraeteantworten erklaerende
Hinweise angezeigt.

Dieses Modul ruft ausschliesslich die offizielle Proxmark3-Client-Programmdatei
auf. Es enthaelt keine eigene Funkansteuerung - es ist eine deutschsprachige
Huelle um das Programm, das sonst von der Kommandozeile aus bedient wird.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

IST_WINDOWS = platform.system() == "Windows"

# Einstellungsdatei neben start.py (vom Nutzer in der Oberflaeche gepflegt).
EINSTELLUNGEN_DATEI = Path(__file__).resolve().parent.parent / "einstellungen.json"

# Ordner, in dem der Client Abbilder, Mitschnitte usw. ablegt.
ARBEITSORDNER = Path.home() / "Proxmark3-Dateien"

# Zulaessige Dateinamen fuer den Client (Schutz vor dem Eintragen beliebiger
# Programme ueber die Oberflaeche).
ERLAUBTE_NAMEN = {"proxmark3", "proxmark3.exe", "pm3"}

# USB-Kennungen des Proxmark3 (Iceman-Firmware bzw. aeltere Firmware).
PROXMARK_USB_IDS = [("9AC4", "4B8F"), ("2D2D", "504D")]

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass
class Ergebnis:
    """Ergebnis eines Befehlsaufrufs."""

    befehl: str
    ausgabe: str
    erfolg: bool
    dauer: float
    demo: bool = False


@dataclass
class Zustand:
    """Aktueller Zustand von Client und Geraet."""

    client_gefunden: bool
    client_pfad: str = ""
    client_version: str = ""
    geraet_verbunden: bool = False
    geraet_anschluss: str = ""
    anschluesse: list[str] = field(default_factory=list)
    demo: bool = True
    demo_erzwungen: bool = False
    betriebssystem: str = platform.system()
    arbeitsordner: str = str(ARBEITSORDNER)
    meldung: str = ""


# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------
def lade_einstellungen() -> dict:
    try:
        return json.loads(EINSTELLUNGEN_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def speichere_einstellungen(daten: dict) -> None:
    EINSTELLUNGEN_DATEI.write_text(
        json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def pfad_ist_client(pfad: str) -> bool:
    """Prueft, ob ``pfad`` auf eine existierende Client-Programmdatei zeigt."""
    if not pfad:
        return False
    kandidat = Path(pfad)
    return kandidat.is_file() and kandidat.name.lower() in ERLAUBTE_NAMEN


# ---------------------------------------------------------------------------
# Suche nach der Client-Programmdatei
# ---------------------------------------------------------------------------
def _windows_kandidaten() -> list[Path]:
    """Typische Ablageorte unter Windows (ProxSpace und fertige Pakete)."""
    heim = Path.home()
    laufwerke = [Path(f"{b}:/") for b in "CDE" if Path(f"{b}:/").exists()]
    wurzeln: list[Path] = []
    for lw in laufwerke:
        wurzeln += [lw / "ProxSpace", lw / "Proxmark3", lw / "pm3"]
    wurzeln += [heim / "ProxSpace", heim / "Proxmark3"]

    kandidaten: list[Path] = []
    for w in wurzeln:
        kandidaten += [
            # ProxSpace: Repo wird im Unterordner "pm3" geklont.
            w / "pm3" / "proxmark3" / "client" / "proxmark3.exe",
            w / "pm3" / "client" / "proxmark3.exe",
            w / "proxmark3" / "client" / "proxmark3.exe",
            w / "client" / "proxmark3.exe",
            w / "proxmark3.exe",
        ]
    return kandidaten


def _unix_kandidaten() -> list[Path]:
    heim = Path.home()
    return [
        Path("/usr/local/bin/proxmark3"),
        Path("/usr/bin/proxmark3"),
        Path("/opt/homebrew/bin/proxmark3"),
        Path("/opt/proxmark3/client/proxmark3"),
        heim / "proxmark3" / "client" / "proxmark3",
        heim / ".local" / "bin" / "proxmark3",
    ]


def _begrenzte_suche(start: Path, name: str, max_tiefe: int = 4, max_eintraege: int = 30000) -> str:
    """Sucht ``name`` unterhalb von ``start`` - mit Tiefen- und Mengengrenze,
    damit grosse Ordner (z. B. Downloads) die Oberflaeche nicht ausbremsen."""
    if not start.is_dir():
        return ""
    gezaehlt = 0
    start_tiefe = len(start.parts)
    for wurzel, ordner, dateien in os.walk(start):
        gezaehlt += len(dateien) + len(ordner)
        if gezaehlt > max_eintraege:
            return ""
        if len(Path(wurzel).parts) - start_tiefe >= max_tiefe:
            ordner[:] = []
        # Uninteressante, oft riesige Ordner ueberspringen.
        ordner[:] = [o for o in ordner if not o.startswith(".") and o.lower() not in (
            "node_modules", "appdata", "$recycle.bin", "windows", "msys2")]
        for d in dateien:
            if d.lower() == name:
                return str(Path(wurzel) / d)
    return ""


def finde_client() -> tuple[str, list[str]]:
    """Liefert (Pfad, durchsuchte Orte). Leerer Pfad = nicht gefunden."""
    durchsucht: list[str] = []

    # 1. Ausdrueckliche Vorgaben: Umgebungsvariable, dann Einstellungsdatei.
    for quelle in (os.environ.get("PM3_CLIENT", ""), lade_einstellungen().get("client_pfad", "")):
        if quelle:
            durchsucht.append(quelle)
            if Path(quelle).is_file():
                return quelle, durchsucht

    # 2. Suchpfad des Systems. Unter Linux/macOS ist "pm3" das offizielle
    #    Startskript, das den Anschluss selbst findet; "proxmark3" geht auch.
    namen = ["proxmark3.exe", "proxmark3"] if IST_WINDOWS else ["proxmark3", "pm3"]
    for name in namen:
        durchsucht.append(f"PATH:{name}")
        gefunden = shutil.which(name)
        if gefunden:
            return gefunden, durchsucht

    # 3. Typische Installationsorte.
    for kandidat in (_windows_kandidaten() if IST_WINDOWS else _unix_kandidaten()):
        durchsucht.append(str(kandidat))
        if kandidat.is_file():
            return str(kandidat), durchsucht

    # 4. Begrenzte Suche in Ordnern, in die man Downloads typischerweise entpackt.
    if IST_WINDOWS:
        heim = Path.home()
        for ordner in (heim / "Downloads", heim / "Desktop", heim / "Documents"):
            durchsucht.append(f"{ordner} (Unterordner)")
            gefunden = _begrenzte_suche(ordner, "proxmark3.exe")
            if gefunden:
                return gefunden, durchsucht

    return "", durchsucht


# ---------------------------------------------------------------------------
# Suche nach dem Anschluss
# ---------------------------------------------------------------------------
def _windows_anschluesse() -> list[str]:
    """COM-Ports ueber die Registrierung ermitteln (ohne Zusatzpakete).

    Proxmark-Geraete (per USB-Kennung erkannt) stehen vorne in der Liste,
    danach weitere USB-Seriell-Anschluesse, zuletzt alle uebrigen.
    """
    try:
        import winreg  # nur unter Windows vorhanden
    except ImportError:
        return []

    aktiv: dict[str, str] = {}  # COMx -> Geraetename
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as schluessel:
            i = 0
            while True:
                try:
                    name, wert, _ = winreg.EnumValue(schluessel, i)
                except OSError:
                    break
                aktiv[str(wert).upper()] = str(name)
                i += 1
    except OSError:
        return []

    proxmark: list[str] = []
    for vid, pid in PROXMARK_USB_IDS:
        basis = rf"SYSTEM\CurrentControlSet\Enum\USB\VID_{vid}&PID_{pid}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, basis) as geraete:
                j = 0
                while True:
                    try:
                        instanz = winreg.EnumKey(geraete, j)
                    except OSError:
                        break
                    j += 1
                    try:
                        with winreg.OpenKey(geraete, instanz + r"\Device Parameters") as param:
                            port = str(winreg.QueryValueEx(param, "PortName")[0]).upper()
                    except OSError:
                        continue
                    # Die Registrierung merkt sich auch fruehere Geraete -
                    # nur aktuell vorhandene Anschluesse zaehlen.
                    if port in aktiv and port not in proxmark:
                        proxmark.append(port)
        except OSError:
            continue

    usb = sorted(p for p, n in aktiv.items() if "USBSER" in n.upper() and p not in proxmark)
    rest = sorted(p for p in aktiv if p not in proxmark and p not in usb)
    return proxmark + usb + rest


def finde_anschluesse() -> list[str]:
    vorgabe = os.environ.get("PM3_PORT") or lade_einstellungen().get("anschluss", "")
    if IST_WINDOWS:
        gefunden = _windows_anschluesse()
    elif platform.system() == "Darwin":
        gefunden = sorted(glob.glob("/dev/tty.usbmodem*"))
    else:
        gefunden = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*"))
    if vorgabe:
        gefunden = [vorgabe] + [a for a in gefunden if a != vorgabe]
    return gefunden


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class Pm3Client:
    def __init__(self, demo_erzwingen: bool = False, zeitlimit: int = 60) -> None:
        self._demo_erzwingen = demo_erzwingen
        self._zeitlimit = zeitlimit
        self._client_pfad = ""
        self._durchsucht: list[str] = []
        self._version = ""
        if not demo_erzwingen:
            self.neu_suchen()

    def neu_suchen(self) -> None:
        self._client_pfad, self._durchsucht = finde_client()
        self._version = ""

    @property
    def durchsucht(self) -> list[str]:
        return list(self._durchsucht)

    # -- Umgebung fuer den Kindprozess ---------------------------------------

    def _umgebung(self) -> dict[str, str]:
        umgebung = dict(os.environ)
        if IST_WINDOWS and self._client_pfad:
            zusatz = [str(Path(self._client_pfad).parent)]
            # Mit ProxSpace gebaute Clients brauchen die DLLs aus dessen MSYS2.
            teile = Path(self._client_pfad).parts
            for i, teil in enumerate(teile):
                if teil.lower() == "proxspace":
                    zusatz.append(str(Path(*teile[: i + 1]) / "msys2" / "mingw64" / "bin"))
                    break
            umgebung["PATH"] = os.pathsep.join(zusatz + [umgebung.get("PATH", "")])
        return umgebung

    def _starte(self, argumente: list[str], zeitlimit: int) -> subprocess.CompletedProcess:
        ARBEITSORDNER.mkdir(parents=True, exist_ok=True)
        zusatz = {}
        if IST_WINDOWS:
            # Kein zusaetzliches schwarzes Fenster je Befehl aufblitzen lassen.
            zusatz["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(
            argumente,
            capture_output=True,
            text=True,
            encoding="utf-8",  # Der Client gibt UTF-8 aus, auch unter Windows.
            errors="replace",
            timeout=zeitlimit,
            cwd=str(ARBEITSORDNER),
            env=self._umgebung(),
            stdin=subprocess.DEVNULL,
            **zusatz,
        )

    # -- Zustand -------------------------------------------------------------

    def zustand(self) -> Zustand:
        if self._demo_erzwingen:
            return Zustand(
                client_gefunden=False,
                demo=True,
                demo_erzwungen=True,
                meldung="Demo-Modus ist ausdruecklich eingeschaltet (Start mit --demo).",
            )
        if not self._client_pfad:
            return Zustand(
                client_gefunden=False,
                demo=True,
                meldung=(
                    "Kein Proxmark3-Client gefunden - Demo-Modus. Die Oberflaeche ist voll "
                    "bedienbar, es werden aber keine Befehle an ein Geraet gesendet. "
                    "Im Reiter 'Installation' koennen Sie den Client einrichten oder "
                    "den Pfad zu proxmark3.exe eintragen."
                ),
            )

        anschluesse = finde_anschluesse()
        verbunden = bool(anschluesse)
        return Zustand(
            client_gefunden=True,
            client_pfad=self._client_pfad,
            client_version=self.version(),
            geraet_verbunden=verbunden,
            geraet_anschluss=anschluesse[0] if anschluesse else "",
            anschluesse=anschluesse,
            demo=False,
            meldung=(
                f"Client gefunden. Geraet an {anschluesse[0]}."
                if verbunden
                else "Client gefunden, aber kein Geraet angeschlossen. "
                "Befehle mit dem Vermerk 'ohne Geraet' funktionieren trotzdem."
            ),
        )

    def version(self) -> str:
        if not self._client_pfad:
            return ""
        if self._version:
            return self._version
        try:
            roh = self._starte([self._client_pfad, "--version"], zeitlimit=15)
            zeilen = [_ANSI.sub("", z).strip() for z in (roh.stdout + roh.stderr).splitlines()]
            zeilen = [z for z in zeilen if z]
            treffer = [z for z in zeilen if "client" in z.lower()] or zeilen
            self._version = treffer[0][:160] if treffer else ""
        except (OSError, subprocess.SubprocessError):
            self._version = ""
        return self._version

    # -- Ausfuehrung ---------------------------------------------------------

    def fuehre_aus(self, befehl: str) -> Ergebnis:
        """Fuehrt einen einzelnen Client-Befehl aus.

        Im Demo-Modus wird nichts an ein Geraet gesendet; stattdessen wird ein
        erklaerender Hinweis zurueckgegeben.
        """
        befehl = befehl.strip()
        beginn = time.monotonic()

        if not befehl:
            return Ergebnis(befehl, "Kein Befehl angegeben.", False, 0.0)

        zustand = self.zustand()
        if zustand.demo:
            return Ergebnis(
                befehl=befehl,
                ausgabe=self._demo_text(befehl, zustand),
                erfolg=True,
                dauer=time.monotonic() - beginn,
                demo=True,
            )

        argumente = [self._client_pfad]
        # Das Startskript "pm3" sucht den Anschluss selbst; der eigentliche
        # Client "proxmark3" bekommt ihn ausdruecklich mit.
        if zustand.geraet_anschluss and Path(self._client_pfad).name != "pm3":
            argumente += ["-p", zustand.geraet_anschluss]
        argumente += ["-c", befehl]

        try:
            roh = self._starte(argumente, self._zeitlimit)
            ausgabe = roh.stdout or ""
            if roh.stderr:
                ausgabe += ("\n" if ausgabe else "") + roh.stderr
            ausgabe = _ANSI.sub("", ausgabe).strip()
            return Ergebnis(
                befehl=befehl,
                ausgabe=ausgabe or "(keine Ausgabe)",
                erfolg=roh.returncode == 0,
                dauer=time.monotonic() - beginn,
            )
        except subprocess.TimeoutExpired:
            return Ergebnis(
                befehl=befehl,
                ausgabe=(
                    f"Zeitlimit ({self._zeitlimit} s) ueberschritten und abgebrochen. "
                    "Lange Vorgaenge lassen sich mit einem hoeheren Zeitlimit starten "
                    "(start.py --zeitlimit 600)."
                ),
                erfolg=False,
                dauer=time.monotonic() - beginn,
            )
        except OSError as fehler:
            return Ergebnis(
                befehl=befehl,
                ausgabe=(
                    f"Der Client konnte nicht gestartet werden ({fehler}).\n"
                    f"Pfad: {self._client_pfad}\n"
                    "Unter Windows fehlen dann meist Programmbibliotheken (DLLs): "
                    "proxmark3.exe muss im Ordner seines Pakets bleiben."
                ),
                erfolg=False,
                dauer=time.monotonic() - beginn,
            )

    @staticmethod
    def _demo_text(befehl: str, zustand: Zustand) -> str:
        return (
            "== DEMO-MODUS ==\n"
            "Befehl, der an den Proxmark3-Client gesendet wuerde:\n\n"
            f"    {befehl}\n\n"
            "Es ist aktuell kein Client aktiv, daher wird nichts ausgefuehrt. "
            "Sobald der Client eingerichtet ist, erscheint hier die echte Geraeteantwort.\n\n"
            f"Hinweis: {zustand.meldung}"
        )
