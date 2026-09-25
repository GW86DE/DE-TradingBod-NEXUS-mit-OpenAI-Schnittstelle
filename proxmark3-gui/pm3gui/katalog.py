"""Laedt den Befehlskatalog und die deutschen Uebersetzungen und fuehrt beide
zu einem Menuebaum zusammen, den die Oberflaeche anzeigt.

Der Katalog (``daten/befehle.json``) wird aus der Proxmark3-Doku erzeugt
(siehe ``werkzeuge/katalog_erzeugen.py``). Die Uebersetzungen
(``daten/uebersetzungen.json``) werden von Hand gepflegt. Fehlt zu einem
Befehl eine deutsche Beschreibung, wird der englische Originaltext angezeigt -
so bleibt die Oberflaeche auch bei einer neuen Proxmark3-Version vollstaendig.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from . import auto_uebersetzung

DATEN = Path(__file__).resolve().parent / "daten"
BEFEHLE_DATEI = DATEN / "befehle.json"
UEBERSETZUNGEN_DATEI = DATEN / "uebersetzungen.json"

# Reihenfolge, in der die Kategorien in der Oberflaeche erscheinen. Nicht
# aufgefuehrte Kategorien werden hinten alphabetisch angehaengt.
KATEGORIE_REIHENFOLGE = [
    "basis",
    "hw",
    "hf",
    "lf",
    "nfc",
    "data",
    "trace",
    "analyse",
    "emv",
    "smart",
    "mad",
    "wiegand",
    "reveng",
    "mem",
    "script",
    "prefs",
    "usart",
    "mqtt",
    "piv",
]

STUFEN_RANG = {"anfaenger": 0, "fortgeschritten": 1, "experte": 2, "": 1}


def _lade_json(pfad: Path) -> dict[str, Any]:
    if not pfad.exists():
        raise FileNotFoundError(
            f"Datendatei fehlt: {pfad}. Bitte 'python3 werkzeuge/katalog_erzeugen.py' ausfuehren."
        )
    return json.loads(pfad.read_text(encoding="utf-8"))


def _kurztitel(beschreibung: str, max_laenge: int = 42) -> str:
    """Kurzer Titel aus dem Anfang einer Beschreibung (bis Komma/Punkt)."""
    if not beschreibung:
        return ""
    kurz = beschreibung.split(". ")[0].split(", ")[0].strip().rstrip(".")
    if len(kurz) > max_laenge:
        kurz = kurz[:max_laenge].rsplit(" ", 1)[0] + " …"
    return kurz


def _stufe_von_pfad(pfad: str, roh: dict[str, Any]) -> str:
    """Rate die Schwierigkeitsstufe, wenn keine Uebersetzung sie vorgibt."""
    name = pfad.split(" ")[-1]
    if name in ("help", "list", "info", "reader", "search", "view", "status", "version"):
        return "anfaenger"
    if name in ("raw", "apdu", "sim", "hardnested", "brute", "loclass"):
        return "experte"
    return "fortgeschritten"


class Katalog:
    """Zusammengefuehrter, uebersetzter Befehlskatalog."""

    def __init__(self, befehle: dict[str, Any], uebersetzungen: dict[str, Any]) -> None:
        self._roh = befehle
        self._ue = uebersetzungen
        self._baum = self._baue_baum()

    # -- Aufbau ---------------------------------------------------------------

    def _kat_text(self, kat_id: str, feld: str, standard: str = "") -> str:
        eintrag = self._ue.get("kategorien", {}).get(kat_id, {})
        return eintrag.get(feld, standard)

    def _abschnitt_titel(self, pfad: str, standard: str) -> str:
        eintrag = self._ue.get("abschnitte", {}).get(pfad, {})
        return eintrag.get("titel", standard)

    def _abschnitt_beschreibung(self, pfad: str, standard: str) -> str:
        eintrag = self._ue.get("abschnitte", {}).get(pfad, {})
        return eintrag.get("beschreibung", standard)

    def _befehl_deutsch(self, pfad: str) -> dict[str, Any]:
        return self._ue.get("befehle", {}).get(pfad, {})

    def _warnung(self, pfad: str) -> str:
        return self._ue.get("warnungen", {}).get(pfad, "")

    def _baue_baum(self) -> list[dict[str, Any]]:
        abschnitte_meta = {a["pfad"]: a for a in self._roh.get("abschnitte", [])}

        # Befehle nach Abschnitt gruppieren.
        nach_abschnitt: dict[str, list[dict[str, Any]]] = {}
        for befehl in self._roh.get("befehle", []):
            nach_abschnitt.setdefault(befehl["abschnitt"], []).append(befehl)

        # Abschnitte nach Kategorie gruppieren.
        kategorien: dict[str, dict[str, Any]] = {}
        for abschnitt_pfad, befehle in nach_abschnitt.items():
            meta = abschnitte_meta.get(abschnitt_pfad, {})
            kat_id = meta.get("kategorie") or (
                befehle[0]["kategorie"] if befehle else "basis"
            )

            kat = kategorien.setdefault(
                kat_id,
                {
                    "id": kat_id,
                    "titel": self._kat_text(kat_id, "titel", kat_id),
                    "symbol": self._kat_text(kat_id, "symbol", "•"),
                    "beschreibung": self._kat_text(kat_id, "beschreibung", ""),
                    "abschnitte": [],
                },
            )

            aufbereitet = [self._bereite_befehl_auf(b) for b in befehle]
            aufbereitet.sort(key=lambda b: (STUFEN_RANG.get(b["stufe"], 1), b["pfad"]))

            kat["abschnitte"].append(
                {
                    "pfad": abschnitt_pfad,
                    "titel": self._abschnitt_titel(
                        abschnitt_pfad, meta.get("titel", abschnitt_pfad or "Allgemein")
                    ),
                    "beschreibung": self._abschnitt_beschreibung(
                        abschnitt_pfad, meta.get("beschreibung_en", "")
                    ),
                    "befehle": aufbereitet,
                }
            )

        for kat in kategorien.values():
            kat["abschnitte"].sort(key=lambda a: a["pfad"])
            kat["anzahl"] = sum(len(a["befehle"]) for a in kat["abschnitte"])

        def sortier_schluessel(kat_id: str) -> tuple[int, str]:
            if kat_id in KATEGORIE_REIHENFOLGE:
                return (KATEGORIE_REIHENFOLGE.index(kat_id), kat_id)
            return (len(KATEGORIE_REIHENFOLGE), kat_id)

        return [kategorien[k] for k in sorted(kategorien, key=sortier_schluessel)]

    def _bereite_befehl_auf(self, befehl: dict[str, Any]) -> dict[str, Any]:
        pfad = befehl["pfad"]
        deutsch = self._befehl_deutsch(pfad)
        stufe = deutsch.get("stufe") or _stufe_von_pfad(pfad, befehl)

        # Beschreibung: handgepflegt -> automatisch uebersetzt -> Titel/Name.
        auto = auto_uebersetzung.beschreibung_uebersetzen(befehl["beschreibung_en"])
        beschreibung = deutsch.get("beschreibung") or auto or befehl["name"]

        # Titel: handgepflegt -> Standardtitel des Unterbefehls -> kurzer Anfang
        # der deutschen Beschreibung -> zur Not der Name. So ist die fett
        # gedruckte Zeile moeglichst deutsch statt eines englischen Fachnamens.
        titel = (
            deutsch.get("titel")
            or auto_uebersetzung.TITEL.get(befehl["name"])
            or _kurztitel(beschreibung)
            or befehl["name"]
        )

        # "handgeprueft" = von Hand uebersetzt; "auto" = maschinell aus dem
        # Original erzeugt (in der Oberflaeche entsprechend gekennzeichnet).
        if deutsch:
            herkunft = "handgeprueft"
        elif auto and auto.lower() != (befehl["beschreibung_en"] or "").lower():
            herkunft = "auto"
        else:
            herkunft = "original"

        return {
            "pfad": pfad,
            "name": befehl["name"],
            "kategorie": befehl["kategorie"],
            "abschnitt": befehl["abschnitt"],
            "offline": befehl["offline"],
            "ist_hilfe": befehl.get("ist_hilfe", False),
            "titel": titel,
            "beschreibung": beschreibung,
            "beschreibung_en": befehl["beschreibung_en"],
            "stufe": stufe,
            "uebersetzt": bool(deutsch),
            "herkunft": herkunft,
            "warnung": self._warnung(pfad),
        }

    # -- Oeffentliche Schnittstelle ------------------------------------------

    @property
    def baum(self) -> list[dict[str, Any]]:
        return self._baum

    @property
    def glossar(self) -> list[dict[str, str]]:
        return self._ue.get("glossar", [])

    @functools.cached_property
    def _flach(self) -> dict[str, dict[str, Any]]:
        eintraege: dict[str, dict[str, Any]] = {}
        for kat in self._baum:
            for abschnitt in kat["abschnitte"]:
                for befehl in abschnitt["befehle"]:
                    eintraege[befehl["pfad"]] = befehl
        return eintraege

    def alle_befehle(self) -> list[dict[str, Any]]:
        return list(self._flach.values())

    def befehl(self, pfad: str) -> dict[str, Any] | None:
        return self._flach.get(pfad)

    def suche(self, text: str, nur_offline: bool = False) -> list[dict[str, Any]]:
        text = text.strip().lower()
        treffer = []
        for befehl in self._flach.values():
            if nur_offline and not befehl["offline"]:
                continue
            if not text:
                treffer.append(befehl)
                continue
            heuhaufen = " ".join(
                [
                    befehl["pfad"],
                    befehl["titel"],
                    befehl["beschreibung"],
                    befehl["beschreibung_en"],
                ]
            ).lower()
            if text in heuhaufen:
                treffer.append(befehl)
        return treffer

    def statistik(self) -> dict[str, int]:
        alle = self.alle_befehle()
        return {
            "befehle": len(alle),
            "uebersetzt": sum(1 for b in alle if b["uebersetzt"]),
            "handgeprueft": sum(1 for b in alle if b["herkunft"] == "handgeprueft"),
            "auto": sum(1 for b in alle if b["herkunft"] == "auto"),
            "deutsch": sum(1 for b in alle if b["herkunft"] in ("handgeprueft", "auto")),
            "kategorien": len(self._baum),
            "abschnitte": sum(len(k["abschnitte"]) for k in self._baum),
            "offline_faehig": sum(1 for b in alle if b["offline"]),
        }

    def metadaten(self) -> dict[str, Any]:
        return {
            "herkunft": self._roh.get("herkunft", ""),
            "erzeugt_am": self._roh.get("erzeugt_am", ""),
        }


@functools.lru_cache(maxsize=1)
def lade_katalog() -> Katalog:
    """Laedt den Katalog einmalig (mit Zwischenspeicher)."""
    return Katalog(_lade_json(BEFEHLE_DATEI), _lade_json(UEBERSETZUNGEN_DATEI))
