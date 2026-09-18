"""Bindeglied zwischen der Oberflaeche und dem echten Proxmark3-Client.

Die Klasse :class:`Pm3Client` sucht die installierte ``pm3``-Programmdatei,
erkennt angeschlossene Geraete und fuehrt einzelne Befehle ueber
``pm3 -c "<befehl>"`` aus. Ist kein Client installiert, laeuft alles im
Demo-Modus weiter: Die Oberflaeche bleibt vollstaendig bedienbar, nur werden
statt echter Geraeteantworten erklaerende Hinweise angezeigt.

Wichtig: Dieses Modul ruft ausschliesslich die offizielle
Proxmark3-Client-Programmdatei auf. Es enthaelt keine eigene Funkansteuerung -
es ist eine deutschsprachige Huelle um das Programm, das ohnehin von der
Kommandozeile aus bedient wird.
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


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
    demo: bool = True
    meldung: str = ""


# Uebliche Namen und Orte der Proxmark3-Programmdatei.
_BINAERNAMEN = ["pm3", "proxmark3"]
_SUCHPFADE = [
    "/usr/local/bin",
    "/usr/bin",
    "/opt/proxmark3",
    "/opt/homebrew/bin",
    str(Path.home() / "proxmark3"),
    str(Path.home() / ".local" / "bin"),
    r"C:\\ProxSpace\\pm3",
    r"C:\\Proxmark3",
]

# Muster fuer die serielle Schnittstelle je nach Betriebssystem.
_ANSCHLUSS_MUSTER = {
    "Linux": ["/dev/ttyACM*", "/dev/ttyUSB*"],
    "Darwin": ["/dev/tty.usbmodem*", "/dev/cu.usbmodem*"],
    "Windows": [],  # Unter Windows werden COM-Ports separat ermittelt.
}


class Pm3Client:
    def __init__(self, demo_erzwingen: bool = False, zeitlimit: int = 60) -> None:
        self._demo_erzwingen = demo_erzwingen
        self._zeitlimit = zeitlimit
        self._client_pfad = "" if demo_erzwingen else self._finde_client()
        self._version = ""

    # -- Suche ---------------------------------------------------------------

    def _finde_client(self) -> str:
        # Ausdrueckliche Vorgabe per Umgebungsvariable hat Vorrang.
        umgebung = os.environ.get("PM3_CLIENT")
        if umgebung and Path(umgebung).exists():
            return umgebung

        for name in _BINAERNAMEN:
            gefunden = shutil.which(name)
            if gefunden:
                return gefunden

        for verzeichnis in _SUCHPFADE:
            for name in _BINAERNAMEN:
                for endung in ("", ".exe", ".bat"):
                    kandidat = Path(verzeichnis) / f"{name}{endung}"
                    if kandidat.exists():
                        return str(kandidat)
        return ""

    def _anschluesse(self) -> list[str]:
        system = platform.system()
        if system == "Windows":
            return self._windows_com_ports()
        treffer: list[str] = []
        for muster in _ANSCHLUSS_MUSTER.get(system, []):
            treffer.extend(sorted(glob.glob(muster)))
        return treffer

    @staticmethod
    def _windows_com_ports() -> list[str]:
        try:
            import serial.tools.list_ports  # type: ignore

            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    # -- Zustand -------------------------------------------------------------

    def zustand(self) -> Zustand:
        if self._demo_erzwingen or not self._client_pfad:
            return Zustand(
                client_gefunden=False,
                demo=True,
                meldung=(
                    "Kein Proxmark3-Client gefunden - Demo-Modus. Die Oberflaeche "
                    "ist voll bedienbar; es werden aber keine echten Befehle an ein "
                    "Geraet gesendet. Installation siehe Reiter 'Installation'."
                    if not self._demo_erzwingen
                    else "Demo-Modus ist ausdruecklich eingeschaltet."
                ),
            )

        anschluesse = self._anschluesse()
        verbunden = bool(anschluesse)
        return Zustand(
            client_gefunden=True,
            client_pfad=self._client_pfad,
            client_version=self.version(),
            geraet_verbunden=verbunden,
            geraet_anschluss=anschluesse[0] if anschluesse else "",
            demo=False,
            meldung=(
                f"Client gefunden. Geraet an {anschluesse[0]}."
                if verbunden
                else "Client gefunden, aber kein Geraet angeschlossen. "
                "Offline-Befehle funktionieren trotzdem."
            ),
        )

    def version(self) -> str:
        if not self._client_pfad:
            return ""
        if self._version:
            return self._version
        try:
            roh = subprocess.run(
                [self._client_pfad, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self._version = (roh.stdout or roh.stderr).strip().splitlines()[0] if (
                roh.stdout or roh.stderr
            ) else ""
        except Exception:
            self._version = ""
        return self._version

    # -- Ausfuehrung ---------------------------------------------------------

    def fuehre_aus(self, befehl: str, offline_ok: bool = True) -> Ergebnis:
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

        anschluss = zustand.geraet_anschluss
        argumente = [self._client_pfad]
        if anschluss:
            argumente += [anschluss]
        argumente += ["-c", befehl]

        try:
            roh = subprocess.run(
                argumente,
                capture_output=True,
                text=True,
                timeout=self._zeitlimit,
            )
            ausgabe = roh.stdout or ""
            if roh.stderr:
                ausgabe += ("\n" if ausgabe else "") + roh.stderr
            return Ergebnis(
                befehl=befehl,
                ausgabe=ausgabe.strip() or "(keine Ausgabe)",
                erfolg=roh.returncode == 0,
                dauer=time.monotonic() - beginn,
            )
        except subprocess.TimeoutExpired:
            return Ergebnis(
                befehl=befehl,
                ausgabe=(
                    f"Zeitlimit ({self._zeitlimit}s) ueberschritten. Der Befehl "
                    "laeuft eventuell noch auf dem Geraet."
                ),
                erfolg=False,
                dauer=time.monotonic() - beginn,
            )
        except FileNotFoundError:
            return Ergebnis(
                befehl=befehl,
                ausgabe="Client-Programmdatei nicht mehr auffindbar.",
                erfolg=False,
                dauer=time.monotonic() - beginn,
            )

    @staticmethod
    def _demo_text(befehl: str, zustand: Zustand) -> str:
        return (
            "== DEMO-MODUS ==\n"
            f"Befehl, der an den Proxmark3-Client gesendet wuerde:\n\n"
            f"    {befehl}\n\n"
            "Es ist aktuell kein Client/Geraet aktiv, daher wird nichts "
            "ausgefuehrt. Sobald ein Proxmark3 angeschlossen und der Client "
            "installiert ist, erscheint hier die echte Geraeteantwort.\n\n"
            f"Hinweis: {zustand.meldung}"
        )
