"""Dauerhafte Verbindung zum Proxmark3-Client.

Statt fuer jeden Befehl ``proxmark3 -c "<befehl>"`` neu zu starten (jedes Mal
neu verbinden, Zwischenergebnisse wie der Signalpuffer gehen verloren), haelt
:class:`Sitzung` einen einzigen Client-Prozess offen und schickt ihm die
Befehle nacheinander.

Das nutzt eine eingebaute Faehigkeit des offiziellen Clients: Ist seine
Standardeingabe keine Konsole, liest er Befehle zeilenweise von dort
(``main_loop`` in ``client/src/proxmark3.c``). Das Ende eines Befehls erkennt
die Sitzung an einer Markierung: Nach jedem Befehl wird ``rem <marke>``
gesendet; der Client antwortet darauf mit ``... remark: <marke>``.
"""

from __future__ import annotations

import itertools
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass

_MARKE = "PM3GUIENDE"
# Der Client liest Eingabezeilen mit fgets() in einen 256-Byte-Puffer.
MAX_ZEILE = 255
MAX_BEFEHL = MAX_ZEILE - len(f";rem {_MARKE}999999Z") - 1
# Vom Client im Pipe-Modus ausgegebene Eingabezeile, z. B. "[usb|script] pm3 --> hw status"
_PROMPT_ECHO = re.compile(r"^\[([^\]]*)\]\s+\S+\s+-->\s")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass
class Antwort:
    ausgabe: str
    fertig: bool  # False = Zeitlimit erreicht, Befehl laeuft evtl. noch


class Sitzung:
    """Ein offen gehaltener Client-Prozess."""

    def __init__(self, argumente: list[str], umgebung: dict[str, str], arbeitsordner: str,
                 zusatz: dict | None = None) -> None:
        self._argumente = argumente
        self._umgebung = umgebung
        self._arbeitsordner = arbeitsordner
        self._zusatz = zusatz or {}
        self._prozess: subprocess.Popen | None = None
        self._zeilen: queue.Queue[str | None] = queue.Queue()
        self._sperre = threading.Lock()
        self._zaehler = itertools.count(1)
        self.startausgabe = ""
        # Inhalt der letzten Eingabezeile, z. B. "usb|script" oder "offline|script".
        self.letzter_prompt = ""

    @property
    def geraet_offline(self) -> bool:
        """True, wenn der Client meldet, dass kein Geraet (mehr) verbunden ist."""
        return self.letzter_prompt.split("|")[0].strip().lower() == "offline"

    # -- Lebenszyklus --------------------------------------------------------

    def starte(self, zeitlimit: float = 25.0) -> tuple[bool, str]:
        """Startet den Client und wartet, bis er Befehle annimmt."""
        try:
            self._prozess = subprocess.Popen(
                self._argumente,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self._arbeitsordner,
                env=self._umgebung,
                **self._zusatz,
            )
        except OSError as fehler:
            return False, f"Client konnte nicht gestartet werden: {fehler}"

        threading.Thread(target=self._lesen, daemon=True).start()
        # Erst wenn die Startmarke zurueckkommt, ist der Client bereit.
        antwort = self._sende("", zeitlimit)
        self.startausgabe = antwort.ausgabe
        if not antwort.fertig or not self.laeuft:
            self.beende()
            return False, antwort.ausgabe or "Der Client hat nicht geantwortet."
        return True, antwort.ausgabe

    def _lesen(self) -> None:
        assert self._prozess and self._prozess.stdout
        for zeile in self._prozess.stdout:
            self._zeilen.put(_ANSI.sub("", zeile.rstrip("\r\n")))
        self._zeilen.put(None)  # Prozess beendet

    @property
    def laeuft(self) -> bool:
        return self._prozess is not None and self._prozess.poll() is None

    def beende(self) -> None:
        prozess, self._prozess = self._prozess, None
        if prozess is None:
            return
        try:
            if prozess.poll() is None and prozess.stdin:
                prozess.stdin.write("quit\n")
                prozess.stdin.flush()
                prozess.stdin.close()
            prozess.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            prozess.kill()
            try:
                prozess.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    # -- Befehle -------------------------------------------------------------

    def befehl(self, befehl: str, zeitlimit: float) -> Antwort:
        # Zeilenumbrueche oder ";" wuerden weitere Befehle einschleusen.
        if any(z in befehl for z in ("\n", "\r", ";")):
            return Antwort("Ein Befehl darf keine Zeilenumbrueche oder ';' enthalten.", True)
        with self._sperre:
            return self._sende(befehl.strip(), zeitlimit)

    def _sende(self, befehl: str, zeitlimit: float) -> Antwort:
        if not self.laeuft or not self._prozess or not self._prozess.stdin:
            return Antwort("Keine Verbindung zum Client.", False)

        # Reste eines frueheren, abgebrochenen Befehls verwerfen.
        while True:
            try:
                if self._zeilen.get_nowait() is None:
                    self._zeilen.put(None)
                    break
            except queue.Empty:
                break

        # Abschlusszeichen "Z", damit z. B. Marke 1 nicht in Marke 10 steckt.
        marke = f"{_MARKE}{next(self._zaehler)}Z"
        # Befehl und Marke in EINER Zeile, per ";" getrennt (der Client fuehrt
        # beide nacheinander aus). Eine zweite, wartende Zeile wuerde unter
        # Linux/macOS von kbd_enter_pressed() als "Enter = Abbrechen" gelesen
        # und laengere Befehle (sniff, sim, ...) sofort beenden.
        zeile = f"{befehl};rem {marke}" if befehl else f"rem {marke}"
        if len(zeile) >= MAX_ZEILE:
            return Antwort(f"Befehl zu lang (hoechstens {MAX_BEFEHL} Zeichen).", True)
        try:
            self._prozess.stdin.write(zeile + "\n")
            self._prozess.stdin.flush()
        except (OSError, ValueError):
            return Antwort("Die Verbindung zum Client ist abgebrochen.", False)

        ende = time.monotonic() + zeitlimit
        gesammelt: list[str] = []
        while True:
            rest = ende - time.monotonic()
            if rest <= 0:
                return Antwort("\n".join(gesammelt), False)
            try:
                zeile = self._zeilen.get(timeout=min(rest, 0.5))
            except queue.Empty:
                continue
            if zeile is None:
                self._zeilen.put(None)
                gesammelt.append("(Der Client wurde beendet.)")
                return Antwort("\n".join(gesammelt), False)
            if f"remark: {marke}" in zeile:
                return Antwort("\n".join(gesammelt).strip("\n"), True)
            echo = _PROMPT_ECHO.match(zeile)
            if echo:
                self.letzter_prompt = echo.group(1)
            if _MARKE in zeile or echo:
                # Echo der eigenen Eingaben und verspaetete Marken frueherer,
                # abgebrochener Befehle ausblenden.
                continue
            gesammelt.append(zeile)
