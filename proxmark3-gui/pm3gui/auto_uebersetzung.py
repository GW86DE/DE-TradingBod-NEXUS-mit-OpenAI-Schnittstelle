"""Automatische Deutsch-Uebersetzung der Befehlsbeschreibungen.

Der Proxmark3-Client hat ueber 1000 Befehle. Die wichtigsten sind in
``daten/uebersetzungen.json`` von Hand uebersetzt; fuer alle uebrigen erzeugt
dieses Modul aus dem (kurzen, formelhaften) englischen Originaltext einen
verstaendlichen deutschen Titel und eine deutsche Beschreibung.

Vorgehen:
* Der **Titel** ergibt sich aus dem letzten Wort des Befehls (dem Unterbefehl,
  z. B. ``reader``, ``dump``, ``sim``) - siehe :data:`TITEL`.
* Die **Beschreibung** wird uebersetzt, indem zuerst laengere Phrasen und dann
  einzelne Woerter ersetzt werden (:data:`PHRASEN`, :data:`WOERTER`).
  Fachbegriffe und Produktnamen (MIFARE, T55x7, UID, NDEF, iCLASS, ...) bleiben
  unveraendert - :data:`BEGRIFFE`.

Bewusst schlicht gehalten: Es ist keine echte Sprachuebersetzung, sondern ein
Baukasten fuer die immer gleichen Fachsaetze. Wo etwas holprig klingt, kann in
``uebersetzungen.json`` eine saubere Uebersetzung von Hand nachgetragen werden;
die hat immer Vorrang.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Titel je Unterbefehl (letztes Wort des Befehlspfads)
# ---------------------------------------------------------------------------
TITEL: dict[str, str] = {
    "help": "Hilfe",
    "list": "Verlauf anzeigen",
    "info": "Info",
    "reader": "Lesen",
    "read": "Lesen",
    "rdbl": "Block lesen",
    "rdsc": "Sektor lesen",
    "dump": "Auslesen (Abbild)",
    "view": "Abbilddatei ansehen",
    "sim": "Simulieren",
    "clone": "Klonen",
    "write": "Schreiben",
    "wrbl": "Block schreiben",
    "restore": "Abbild zurueckschreiben",
    "wipe": "Loeschen / zuruecksetzen",
    "sniff": "Mitschneiden",
    "demod": "Signal auswerten (demodulieren)",
    "config": "Einstellungen",
    "chk": "Schluessel/Passwoerter pruefen",
    "brute": "Durchprobieren (Brute-Force)",
    "encode": "Kodieren",
    "decode": "Dekodieren",
    "auth": "Anmelden (Authentisieren)",
    "test": "Test",
    "watch": "Dauerhaft mitlesen",
    "load": "Laden",
    "save": "Speichern",
    "eload": "Abbild in Emulator laden",
    "esave": "Emulatorspeicher speichern",
    "eview": "Emulatorspeicher anzeigen",
    "eget": "Emulatorspeicher lesen",
    "eset": "Emulatorspeicher setzen",
    "esetblk": "Emulator-Block setzen",
    "ndefread": "NDEF lesen",
    "ndefwrite": "NDEF schreiben",
    "ndefformat": "Als NDEF formatieren",
    "raw": "Rohbefehl senden",
    "apdu": "APDU senden",
    "select": "Karte auswaehlen",
    "scan": "Suchen / abtasten",
    "tune": "Antenne abstimmen",
    "search": "Suchen",
    "detect": "Erkennen",
    "decrypt": "Entschluesseln",
    "encrypt": "Verschluesseln",
    "setuid": "UID setzen",
    "wipe_": "Loeschen",
    "recover": "Wiederherstellen / ermitteln",
    "keygen": "Schluessel erzeugen",
    "pwdgen": "Passwort berechnen",
    "verify": "Pruefen",
    "delete": "Loeschen",
    "create": "Anlegen",
    "format": "Formatieren",
    "clear": "Leeren",
    "hints": "Tipps ein-/ausschalten",
    "tearoff": "Tear-off-Test",
    "gen": "Erzeugen",
    "gview": "Signal anzeigen",
    "gsave": "Signal speichern",
    "plot": "Signal darstellen",
    "samples": "Signal einlesen",
    "mad": "MAD anzeigen",
}

# ---------------------------------------------------------------------------
# Phrasen (werden vor den Einzelwoertern ersetzt, laengste zuerst)
# ---------------------------------------------------------------------------
_PHRASEN_ROH: list[tuple[str, str]] = [
    ("this help", "Diese Hilfe"),
    ("dump to binary file", "in eine Binaerdatei auslesen"),
    ("dump tag to binary file", "Tag in eine Binaerdatei auslesen"),
    ("to binary file", "in eine Binaerdatei"),
    ("from binary file", "aus einer Binaerdatei"),
    ("binary file", "Binaerdatei"),
    ("dump file", "Abbilddatei"),
    ("tag information", "Tag-Informationen"),
    ("get tag information", "Tag-Informationen lesen"),
    ("get card information", "Karten-Informationen lesen"),
    ("card information", "Karten-Informationen"),
    ("read block", "Block lesen"),
    ("write block", "Block schreiben"),
    ("read blocks", "Bloecke lesen"),
    ("write blocks", "Bloecke schreiben"),
    ("read tag", "Tag lesen"),
    ("read card", "Karte lesen"),
    ("dump card", "Karte auslesen"),
    ("dump tag", "Tag auslesen"),
    ("act like", "verhaelt sich wie"),
    ("act as", "verhaelt sich wie"),
    ("clone to", "klonen auf"),
    ("write to", "schreiben auf"),
    ("read from", "lesen von"),
    ("into the emulator memory", "in den Emulatorspeicher"),
    ("emulator memory", "Emulatorspeicher"),
    ("into flash memory", "in den Flash-Speicher"),
    ("flash memory", "Flash-Speicher"),
    ("into the graphbuffer", "in den Signalpuffer"),
    ("from graphbuffer", "aus dem Signalpuffer"),
    ("graphbuffer", "Signalpuffer"),
    ("demodbuffer", "Demodulationspuffer"),
    ("plot window", "Plotfenster"),
    ("graph window", "Plotfenster"),
    ("simulate iso14443-a tag", "ISO-14443-A-Tag simulieren"),
    ("simulate iso14443a tag", "ISO-14443-A-Tag simulieren"),
    ("simulate iso15693 tag", "ISO-15693-Tag simulieren"),
    ("dictionary attack", "Woerterbuch-Angriff"),
    ("dictionary check", "Woerterbuch-Pruefung"),
    ("bruteforce attack", "Durchprobieren (Brute-Force)"),
    ("brute force", "Durchprobieren"),
    ("authentication dictionary", "Schluessel-Woerterbuch"),
    ("default keys", "Standardschluessel"),
    ("known keys", "bekannte Schluessel"),
    ("all keys", "alle Schluessel"),
    ("recover key", "Schluessel ermitteln"),
    ("recover keys", "Schluessel ermitteln"),
    ("send raw", "Rohdaten senden"),
    ("raw hex", "Roh-Hex"),
    ("hex data", "Hex-Daten"),
    ("ndef records", "NDEF-Datensaetze"),
    ("ndef record", "NDEF-Datensatz"),
    ("ndef message", "NDEF-Nachricht"),
    ("capability container", "Capability Container"),
    ("get information", "Informationen lesen"),
    ("show information", "Informationen anzeigen"),
    ("print information", "Informationen ausgeben"),
    ("factory default", "Werkszustand"),
    ("factory defaults", "Werkszustand"),
    ("wipe card to zeros", "Karte auf Null zuruecksetzen"),
    ("set the", "setzt die"),
    ("get the", "liest die"),
    ("list of", "Liste der"),
    ("continuously", "fortlaufend"),
    ("in one go", "auf einmal"),
    ("nfc forum type", "NFC-Forum-Typ"),
    ("smart card", "Kontaktkarte (Smartcard)"),
    ("access control", "Zutrittskontrolle"),
    ("transport card", "Verkehrskarte"),
    ("transport cards", "Verkehrskarten"),
    ("animal id", "Tierkennzeichnung"),
    ("animal ids", "Tierkennzeichnungen"),
    ("cryptographic", "kryptografisch"),
    ("authentication", "Authentisierung"),
    ("authenticate", "authentisieren"),
    ("password", "Passwort"),
    ("passwords", "Passwoerter"),
    ("configuration", "Konfiguration"),
    ("configure", "einstellen"),
    ("preference", "Einstellung"),
    ("preferences", "Einstellungen"),
    ("settings", "Einstellungen"),
    ("regression tests", "Regressionstests"),
    ("self tests", "Selbsttests"),
    ("self test", "Selbsttest"),
    ("perform tests", "Tests ausfuehren"),
    ("execute", "ausfuehren"),
    ("generate", "erzeugen"),
    ("diversified keys", "abgeleitete Schluessel"),
    ("magic card", "Magic-Karte"),
    ("magic gen1a", "Magic-Karte (Gen1a)"),
    ("magic gen", "Magic-Karte Gen"),
    ("eavesdrop", "Mithoeren (Mitschnitt)"),
    ("upload", "hochladen"),
    ("download", "herunterladen"),
    ("turn on / off", "ein-/ausschalten"),
    ("on / off", "ein/aus"),
    ("on device", "am Geraet"),
    ("on the device", "am Geraet"),
    ("add-on", "Zusatzmodul"),
    ("smart card", "Kontaktkarte"),
    ("client debug", "Client-Debug"),
    ("debug level", "Debug-Stufe"),
    ("data stream", "Datenstrom"),
    ("side channel", "Seitenkanal"),
    ("hint display", "Hinweis-Anzeige"),
    ("wave form", "Signalform"),
    ("waveform", "Signalform"),
]

# ---------------------------------------------------------------------------
# Einzelwoerter
# ---------------------------------------------------------------------------
WOERTER: dict[str, str] = {
    "tag": "Tag",
    "tags": "Tags",
    "card": "Karte",
    "cards": "Karten",
    "file": "Datei",
    "files": "Dateien",
    "read": "lesen",
    "reads": "liest",
    "write": "schreiben",
    "writes": "schreibt",
    "dump": "auslesen",
    "memory": "Speicher",
    "block": "Block",
    "blocks": "Bloecke",
    "page": "Seite",
    "pages": "Seiten",
    "sector": "Sektor",
    "sectors": "Sektoren",
    "simulate": "simuliert",
    "simulates": "simuliert",
    "set": "setzen",
    "get": "lesen",
    "list": "auflisten",
    "emulator": "Emulator",
    "information": "Informationen",
    "info": "Info",
    "key": "Schluessel",
    "keys": "Schluessel",
    "history": "Verlauf",
    "extract": "auslesen",
    "clone": "klonen",
    "clones": "klont",
    "attempt": "versucht",
    "display": "anzeigen",
    "displays": "zeigt",
    "show": "anzeigen",
    "shows": "zeigt",
    "print": "ausgeben",
    "prints": "gibt aus",
    "demodulate": "demoduliert (auswerten)",
    "reader": "Lesegeraet",
    "trace": "Mitschnitt",
    "traces": "Mitschnitte",
    "act": "verhaelt sich",
    "content": "Inhalt",
    "contents": "Inhalt",
    "create": "anlegen",
    "creates": "erzeugt",
    "binary": "binaer",
    "save": "speichern",
    "saves": "speichert",
    "load": "laden",
    "loads": "laedt",
    "send": "senden",
    "sends": "sendet",
    "receive": "empfangen",
    "mode": "Modus",
    "test": "Test",
    "tests": "Tests",
    "uid": "UID",
    "decode": "dekodieren",
    "decodes": "dekodiert",
    "encode": "kodieren",
    "encodes": "kodiert",
    "buffer": "Puffer",
    "type": "Typ",
    "system": "System",
    "change": "aendern",
    "changes": "aendert",
    "check": "pruefen",
    "checks": "prueft",
    "bruteforce": "Durchprobieren",
    "raw": "Rohbefehl",
    "format": "formatieren",
    "attack": "Angriff",
    "view": "ansehen",
    "password": "Passwort",
    "application": "Anwendung",
    "applications": "Anwendungen",
    "applet": "Applet",
    "applets": "Applets",
    "command": "Befehl",
    "commands": "Befehle",
    "over": "ueber",
    "restore": "zurueckschreiben",
    "wipe": "loeschen",
    "generate": "erzeugen",
    "samples": "Signalproben",
    "hex": "Hex",
    "perform": "ausfuehren",
    "records": "Datensaetze",
    "record": "Datensatz",
    "pin": "PIN",
    "select": "auswaehlen",
    "sniff": "mitschneiden",
    "authenticate": "authentisieren",
    "settings": "Einstellungen",
    "setting": "Einstellung",
    "use": "verwenden",
    "byte": "Byte",
    "bytes": "Bytes",
    "bits": "Bits",
    "bit": "Bit",
    "graph": "Signal",
    "window": "Fenster",
    "code": "Code",
    "device": "Geraet",
    "forum": "Forum",
    "value": "Wert",
    "values": "Werte",
    "modulation": "Modulation",
    "id": "Kennung",
    "ids": "Kennungen",
    "verify": "pruefen",
    "new": "neu",
    "flash": "Flash",
    "communication": "Kommunikation",
    "default": "Standard",
    "defaults": "Standardwerte",
    "convert": "umwandeln",
    "detect": "erkennen",
    "decrypt": "entschluesseln",
    "encrypt": "verschluesseln",
    "try": "versucht",
    "antenna": "Antenne",
    "configure": "einstellen",
    "acquire": "einlesen",
    "reset": "zuruecksetzen",
    "transponder": "Transponder",
    "field": "Feld",
    "given": "angegeben",
    "string": "Zeichenkette",
    "clock": "Takt",
    "start": "starten",
    "transaction": "Transaktion",
    "run": "ausfuehren",
    "known": "bekannt",
    "update": "aktualisieren",
    "encrypted": "verschluesselt",
    "service": "Dienst",
    "diversified": "abgeleitet",
    "family": "Familie",
    "between": "zwischen",
    "internal": "intern",
    "protocol": "Protokoll",
    "measure": "messen",
    "traffic": "Datenverkehr",
    "fake": "gefaelscht",
    "magic": "Magic",
    "protect": "schuetzen",
    "after": "nach",
    "delete": "loeschen",
    "message": "Nachricht",
    "wallet": "Wallet",
    "credential": "Berechtigung",
    "credentials": "Berechtigungen",
    "token": "Token",
    "decoded": "dekodiert",
    "against": "gegen",
    "find": "finden",
    "available": "verfuegbar",
    "word": "Wort",
    "turn": "schalten",
    "off": "aus",
    "on": "ein",
    "add": "hinzufuegen",
    "debug": "Debug",
    "output": "Ausgabe",
    "one": "eine",
    "array": "Feld (Array)",
    "signal": "Signal",
    "input": "Eingabe",
    "rate": "Rate",
    "identify": "erkennen",
    "trim": "beschneiden",
    "specified": "angegeben",
    "states": "Zustaende",
    "crypto": "Krypto",
    "challenge": "Challenge",
    "public": "oeffentlich",
    "scan": "abtasten",
    "eavesdrop": "mithoeren",
    "counter": "Zaehler",
    "zeros": "Null",
    "enable": "einschalten",
    "disable": "ausschalten",
    "attributes": "Eigenschaften",
    "via": "ueber",
    "erase": "loeschen",
    "wait": "warten",
    "area": "Bereich",
    "version": "Version",
    "name": "Name",
    "loop": "Schleife",
    "response": "Antwort",
    "operations": "Operationen",
    "barcode": "Barcode",
    "get/set": "lesen/setzen",
    "if": "falls",
    "passwords": "Passwoerter",
    "receive": "empfangen",
    "automated": "automatisch",
    "program": "programmieren",
    "support": "Unterstuetzung",
    "style": "Stil",
    "next": "naechste",
    "xor": "XOR",
    "data": "Daten",
    "stream": "Datenstrom",
    "side": "Seite",
    "level": "Stufe",
    "timeout": "Zeitlimit",
    "delay": "Verzoegerung",
    "hint": "Hinweis",
    "hints": "Hinweise",
    "partial": "teilweise",
    "provided": "angegeben",
    "onto": "auf",
    "deobfuscated": "entschluesselt",
    "passbook": "Passbook",
    "sample": "Signalprobe",
    "wave": "Signalform",
    "watch": "dauerhaft mitlesen",
    "client": "Client",
    "not": "nicht",
    "smart": "Kontakt-",
    "installed": "installiert",
    "fuzzing": "Fuzzing (gezieltes Stoeren)",
    "anticollision": "Antikollision",
    "collect": "sammeln",
    "control": "steuern",
    "enumerate": "auflisten",
    "caution": "Vorsicht",
    "phase": "Phase",
    "react": "reagieren",
    "strange": "seltsam",
    "may": "koennen",
    "selection": "Auswahl",
    "warning": "Warnung",
    "chaining": "Verkettung",
    "eeprom": "EEPROM",
    "dictionary": "Woerterbuch",
    "nested": "Nested",
    "static": "statisch",
    "hardnested": "Hardnested",
    "darkside": "Darkside",
    "sectors": "Sektoren",
    "sector": "Sektor",
    "keytype": "Schluesseltyp",
    "reads": "liest",
    "writes": "schreibt",
    "simulates": "simuliert",
    "deletes": "loescht",
    "creates": "erzeugt",
    "returns": "liefert",
    "shows": "zeigt",
    "prints": "gibt aus",
    "loads": "laedt",
    "saves": "speichert",
    "eavesdrops": "hoert mit",
    "obfuscated": "verschleiert",
    "identification": "Identifikation",
    "identifier": "Kennung",
    "counters": "Zaehler",
    "readers": "Lesegeraete",
    "devices": "Geraete",
    "get": "lesen",
    "put": "schreiben",
    "automatic": "automatisch",
    "automatically": "automatisch",
    "recovery": "Wiederherstellung",
    "recover": "ermitteln",
    "tool": "Werkzeug",
    "checksum": "Pruefsumme",
    "speed": "Geschwindigkeit",
    "unlock": "entsperren",
    "lock": "sperren",
    "writing": "Schreiben",
    "reading": "Lesen",
    "out": "",
    "stop": "Ende",
    "starting": "Anfang",
    "relay": "weiterleiten",
    "host": "Rechner",
    "checksums": "Pruefsummen",
    "bin": "binaer",
    "the": "",
    "a": "",
    "an": "",
    "to": "",
    "of": "",
    "for": "fuer",
    "and": "und",
    "or": "oder",
    "from": "von",
    "in": "in",
    "into": "in",
    "on": "auf",
    "with": "mit",
    "as": "als",
    "like": "wie",
    "all": "alle",
    "by": "durch",
    "this": "",
    "s": "",
}

# Begriffe/Namen, die nie uebersetzt werden (bleiben wie im Original stehen).
BEGRIFFE = {
    "mifare", "ntag", "desfire", "ultralight", "iclass", "picopass", "legic",
    "felica", "topaz", "hitag", "t55x7", "t55xx", "t5577", "q5/t5555",
    "em4305/4469", "em4x05/em4x69", "em410x", "em4x50", "em4x70", "indala",
    "gallagher", "saflok", "fudan", "jooki", "seos", "hid", "prox", "awid",
    "destron", "idteck", "ioprox", "jablotron", "keri", "motorola", "nedap",
    "nexwatch", "noralsy", "pac", "paradox", "presco", "pyramid", "securakey",
    "ti", "viking", "visa2000", "nfc", "ndef", "mad", "aid", "uid", "pin",
    "spiffs", "usart", "mqtt", "emv", "piv", "gdm", "slix", "fsk", "ask",
    "iso", "iso-14443-b", "iso-15693", "a/7816", "tid", "ef", "eas", "afi",
    "pace", "mac", "vas", "bwm", "lto-cm", "wiegand", "crc", "apdu", "json",
    "ev1", "gdm", "tearoff", "tear-off", "fuji/xerox", "lf", "hf", "khz",
    "proxmark3", "pm3", "plus", "prime", "classic", "thinfilm",
}


# ---------------------------------------------------------------------------
# Satz-Vorlagen: passen sie auf die GANZE Beschreibung, entsteht ein fluessiger
# deutscher Satz. Der in Klammern erfasste Teil (meist ein Fachbegriff wie
# "EM410x" oder "ISO18092/FeliCa") bleibt unveraendert stehen.
# ---------------------------------------------------------------------------
_A = r"(?:an?|the)\s+"  # englische Artikel (optional)
_VORLAGEN_ROH: list[tuple[str, str]] = [
    (r"^this help$", "Diese Hilfe"),
    (r"^demodulate (?:a |an )?(.+?) (?:tag )?from the graphbuffer$",
     r"{1} aus dem Signalpuffer auswerten (demodulieren)"),
    (r"^read (?:a |an )?(.+?) (?:tag )?from the graphbuffer$",
     r"{1} aus dem Signalpuffer lesen"),
    (r"^list (.+?) history$", r"Verlauf der {1}-Befehle anzeigen"),
    (r"^simulate (.+?) tag$", r"{1}-Tag simulieren"),
    (r"^fake (.+?) tag$", r"{1}-Tag vortaeuschen (simulieren)"),
    (r"^simulate (.+)$", r"{1} simulieren"),
    (r"^act like (?:an? |the )?(.+?) reader$", r"Verhaelt sich wie ein {1}-Lesegeraet"),
    (r"^act as (?:an? |the )?(.+?) reader$", r"Verhaelt sich wie ein {1}-Lesegeraet"),
    (r"^read (?:an? |the )?(.+?) from (?:the )?card$", r"{1} von der Karte lesen"),
    (r"^read (?:an? |the )?(.+?) from (?:the )?tag$", r"{1} vom Tag lesen"),
    (r"^write (?:an? |the )?(.+?) to (?:the )?card$", r"{1} auf die Karte schreiben"),
    (r"^write (?:an? |the )?(.+?) to (?:the )?tag$", r"{1} auf das Tag schreiben"),
    (r"^clone (.+?) to (.+)$", r"{1} auf {2} klonen"),
    (r"^dump (.+?) to (?:a )?(?:binary |bin )?file$", r"{1} in eine Datei auslesen"),
    (r"^dump (.+)$", r"{1} auslesen"),
    (r"^perform self ?tests?$", "Selbsttest ausfuehren"),
    (r"^run self ?tests?$", "Selbsttest ausfuehren"),
    (r"^(.+?) tag information$", r"Tag-Informationen ({1})"),
    (r"^tag information$", "Tag-Informationen anzeigen"),
    (r"^display content from tag dump file$", "Inhalt einer gespeicherten Abbilddatei anzeigen"),
    (r"^set (.+?) preference$", r"Einstellung „{1}“ setzen"),
    (r"^get (.+?) preference$", r"Einstellung „{1}“ anzeigen"),
    (r"^get (.+?) list$", r"{1} auflisten"),
    (r"^get (.+)$", r"{1} lesen"),
    (r"^turn (on|off) (.+)$", r"{2} " + "{ein}"),  # Sonderfall, s. unten
]


def _vorlagen_kompilieren() -> list[tuple[re.Pattern, str]]:
    return [(re.compile(en, re.IGNORECASE), de) for en, de in _VORLAGEN_ROH]


_VORLAGEN = _vorlagen_kompilieren()


def _vorlage_anwenden(text_en: str) -> str | None:
    """Versucht, die ganze Beschreibung ueber eine Satz-Vorlage zu uebersetzen."""
    kurz = text_en.strip().rstrip(".")
    for muster, deutsch in _VORLAGEN:
        treffer = muster.match(kurz)
        if not treffer:
            continue
        if "{ein}" in deutsch:  # turn on/off
            ein_aus = "einschalten" if treffer.group(1).lower() == "on" else "ausschalten"
            return f"{treffer.group(2)} {ein_aus}".strip()
        ergebnis = deutsch
        for i, gruppe in enumerate(treffer.groups(), start=1):
            ergebnis = ergebnis.replace(f"{{{i}}}", (gruppe or "").strip())
        return ergebnis
    return None


def _phrasen_kompilieren() -> list[tuple[re.Pattern, str]]:
    roh = sorted(_PHRASEN_ROH, key=lambda p: -len(p[0]))
    return [(re.compile(re.escape(en), re.IGNORECASE), de) for en, de in roh]


_PHRASEN = _phrasen_kompilieren()


def titel_fuer(name: str, standard: str) -> str:
    """Deutscher Titel fuer einen Unterbefehl (letztes Wort des Pfads)."""
    return TITEL.get(name, standard)


def _wort_ersetzen(treffer: re.Match) -> str:
    wort = treffer.group(0)
    # Einzelne Grossbuchstaben sind fast immer Teil eines Codes/Namens
    # (z. B. das "A" in "ISO 14443-A", "P" in "P1P2") - nie antasten.
    if len(wort) == 1 and wort.isupper():
        return wort
    klein = wort.lower()
    if klein in BEGRIFFE:
        return wort  # Fachbegriff unveraendert lassen
    if klein in WOERTER:
        return WOERTER[klein]
    return wort  # unbekannt: stehen lassen


def beschreibung_uebersetzen(text_en: str) -> str:
    """Uebersetzt eine englische Beschreibung so gut es das Woerterbuch erlaubt."""
    if not text_en:
        return text_en
    # 1. Ganze Beschreibung ueber eine Satz-Vorlage (liefert fluessiges Deutsch).
    #    Danach werden auch die eingesetzten (erfassten) Teile noch Wort fuer
    #    Wort uebersetzt - Fachbegriffe bleiben dabei geschuetzt.
    vorlage = _vorlage_anwenden(text_en)
    if vorlage is not None:
        text = vorlage
    else:
        # 2. Sonst Phrasen und dann Einzelwoerter ersetzen.
        text = text_en
        for muster, deutsch in _PHRASEN:
            text = muster.sub(deutsch, text)
    # Einzelwoerter ersetzen. Der Lookbehind sorgt dafuer, dass innerhalb von
    # Codes wie "14443-A" oder "Q5/T5555" nicht mitten hineingegriffen wird.
    text = re.sub(r"(?<![\w-])[A-Za-z][A-Za-z0-9/+-]*", _wort_ersetzen, text)
    # Aufraeumen: doppelte Leerzeichen, Leerzeichen vor Satzzeichen.
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text:
        text = text[0].upper() + text[1:]
    return text
