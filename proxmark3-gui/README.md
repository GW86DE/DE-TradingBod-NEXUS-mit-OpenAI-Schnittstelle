# Proxmark3 – Deutsche Oberfläche (GUI)

Eine **deutschsprachige, anklickbare Bedienoberfläche** für den offiziellen
Proxmark3-Client. Die Oberfläche macht die über 1000 Befehle des Clients
übersichtlich, nach Themen sortiert und mit deutschen Erklärungen zugänglich –
ohne dass man sich die Kommandozeilen-Befehle merken muss.

> **Kurz gesagt:** Diese GUI ist eine *Hülle* um das Programm `pm3`, das man
> sonst im Terminal bedient. Sie sendet genau die Befehle, die man sonst tippen
> würde, und zeigt die Antworten des Geräts an – nur eben zum Anklicken und auf
> Deutsch.

## Was kann die Oberfläche?

- **Alle Client-Funktionen zum Anklicken** – automatisch aus der offiziellen
  Befehlsliste (`doc/commands.md`) erzeugt, nach Kategorien wie *Hochfrequenz*,
  *Niederfrequenz*, *Hardware* usw. gegliedert.
- **Deutsche Erklärungen** zu jedem wichtigen Befehl, mit
  Schwierigkeitsstufen (*einfach / mittel / Experte*) und Warnhinweisen bei
  Befehlen, die eine Karte dauerhaft verändern können.
- **Assistent** mit fertigen Abläufen für häufige Aufgaben („Was für eine Karte
  ist das?", „MIFARE-Karte auslesen", „Ist mein Proxmark in Ordnung?").
- **Konsole** für Fortgeschrittene, mit Verlauf.
- **Bebilderte Installationsanleitung** für Windows, Linux und macOS – direkt
  in der Oberfläche.
- **Demo-Modus:** läuft komplett ohne angeschlossenes Gerät zum Ausprobieren
  und Lernen.
- **Keine Zusatzpakete nötig** – nur Python 3 (Standardbibliothek). Die
  Oberfläche läuft im Browser, der Server nur lokal auf dem eigenen Rechner.

## Schnellstart

### Zum Ausprobieren (Demo, ohne Gerät)

```bash
cd proxmark3-gui
python3 start.py --demo
```

Der Browser öffnet sich automatisch unter `http://127.0.0.1:8137/`.

### Mit echtem Proxmark3

1. Einmalig den Proxmark3-Client installieren – die Schritte stehen im Reiter
   **Installation** in der Oberfläche (oder unten unter „Installation").
2. Proxmark per USB anschließen.
3. Starten:

   ```bash
   python3 start.py
   ```

Die Oberfläche erkennt Client und Gerät selbstständig. Der Status oben rechts
zeigt: **Gerät verbunden** (grün), **Client bereit / kein Gerät** (blau) oder
**Demo-Modus** (gelb). Ein Klick darauf öffnet **Installation → Verbindung
einrichten**. Dort sieht man, was gefunden wurde, und kann den Pfad zu
`proxmark3.exe` sowie den COM-Port auch von Hand eintragen. Die Angaben werden in
`einstellungen.json` gespeichert.

Automatisch gesucht wird unter Windows u. a. in
`C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe`, `C:\Proxmark3\…` sowie in
den Ordnern „Downloads“, „Desktop“ und „Dokumente“. Der COM-Port des Proxmark
wird über seine USB-Kennung erkannt. Abbilder und Mitschnitte, die der Client
speichert, landen im Ordner `Proxmark3-Dateien` im Benutzerverzeichnis.

### Zum Doppelklicken

- **Windows:** `Proxmark3-GUI-starten.bat`
- **macOS / Linux:** `Proxmark3-GUI-starten.command`

## Aufbau des Projekts

```
proxmark3-gui/
├─ start.py                      Startpunkt (python3 start.py)
├─ Proxmark3-GUI-starten.bat     Klick-Start Windows
├─ Proxmark3-GUI-starten.command Klick-Start macOS/Linux
├─ pm3gui/
│  ├─ __main__.py                Kommandozeilen-Schalter
│  ├─ katalog.py                 lädt & übersetzt die Befehlsliste
│  ├─ client.py                  ruft die echte pm3-Programmdatei auf (+ Demo)
│  ├─ server.py                  lokaler Webserver + JSON-Schnittstelle
│  ├─ daten/
│  │  ├─ befehle.json            automatisch erzeugter Befehlskatalog
│  │  └─ uebersetzungen.json     handgepflegte deutsche Texte
│  └─ web/                       Oberfläche (HTML/CSS/JS, ohne Frameworks)
├─ werkzeuge/
│  ├─ katalog_erzeugen.py        erzeugt daten/befehle.json aus commands.md
│  └─ commands.md                Kopie der Proxmark3-Befehlsliste
└─ tests/
   └─ test_katalog_und_server.py Tests (ohne Gerät lauffähig)
```

## Katalog aktualisieren

Kommt eine neue Proxmark3-Version mit neuen Befehlen heraus, lässt sich der
Katalog neu erzeugen:

```bash
python3 werkzeuge/katalog_erzeugen.py --laden   # holt commands.md frisch aus dem Repo
```

Neue Befehle erscheinen dann sofort in der Oberfläche. Für die es noch keine
deutsche Erklärung gibt, wird automatisch der englische Originaltext angezeigt.
Deutsche Texte werden von Hand in `pm3gui/daten/uebersetzungen.json` ergänzt –
dort sind Kategorien, Abschnitte, Befehle, Warnungen und das Lexikon getrennt
gepflegt.

## Tests

```bash
python3 tests/test_katalog_und_server.py
```

Prüft Generator, Katalog, Demo-Client, den Aufruf eines nachgebauten Clients
(Port, Zeichensatz), die HTTP-Schnittstelle samt Schutzmaßnahmen sowie die
Windows-Portsuche mit nachgebauter Registrierung – ganz ohne angeschlossenes Gerät.

## Sicherheit

- Der Webserver bindet nur an `127.0.0.1` (nur der eigene Rechner).
- Andere Webseiten, die im selben Browser offen sind, können keine Befehle
  auslösen: Es werden nur JSON-Anfragen mit lokalem Host und passender Herkunft
  angenommen.
- Als Client-Pfad lässt sich nur eine Datei namens `proxmark3(.exe)` bzw. `pm3`
  eintragen.
- Es werden ausschließlich Befehle ausgeführt, die im Proxmark3-Katalog stehen –
  beliebige System- oder Shell-Befehle sind nicht möglich.
- Der Client wird über `pm3 -c "<befehl>"` aufgerufen; diese GUI enthält keine
  eigene Funkansteuerung.

## Rechtlicher Hinweis

Der Proxmark3 ist ein Werkzeug für Sicherheitsforschung, Technikverständnis und
die Arbeit mit den **eigenen** Karten und Anlagen. Bitte nur an Karten und
Systemen einsetzen, die einem gehören oder für die eine ausdrückliche Erlaubnis
vorliegt. Das Auslesen, Kopieren oder Nachbilden fremder Karten kann rechtlich
unzulässig sein.

## Herkunft / Danksagung

Die Befehlsliste stammt aus dem Projekt
[RfidResearchGroup/proxmark3](https://github.com/RfidResearchGroup/proxmark3)
(Iceman-Fork). Diese Oberfläche ist ein eigenständiges Zusatzprojekt und
ersetzt den Client nicht, sondern bedient ihn.
