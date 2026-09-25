"use strict";

// Laengere deutsche Texte fuer die Reiter "Installation" und "Hilfe".
// Getrennt gehalten, damit app.js uebersichtlich bleibt.

const TEXTE = {
  installation: `
    <h2>Proxmark3 einrichten</h2>
    <p>Diese Oberflaeche ist eine <strong>Huelle um den offiziellen Proxmark3-Client</strong>.
    Damit echte Befehle an das Geraet gehen, muss dieser Client einmal installiert werden.
    Ohne Installation laeuft alles im <em>Demo-Modus</em> &ndash; zum Ausprobieren und Lernen.</p>
    <p>Empfohlen wird die weit verbreitete Iceman-Firmware:
    <code>RfidResearchGroup/proxmark3</code>. Waehlen Sie unten Ihr Betriebssystem.</p>

    <div class="betriebssystem-waehler">
      <button class="os-knopf aktiv" data-os="windows">Windows</button>
      <button class="os-knopf" data-os="linux">Linux</button>
      <button class="os-knopf" data-os="macos">macOS</button>
    </div>

    <div class="os-abschnitt aktiv" data-os="windows">
      <h3>Windows &ndash; vorab wichtig</h3>
      <ul>
        <li><strong>Treiber:</strong> Windows 10 und 11 richten den Proxmark beim Einstecken selbst ein.
          Er erscheint im Geraete-Manager unter &bdquo;Anschluesse (COM &amp; LPT)&ldquo; als
          <code>COM3</code>, <code>COM5</code> o. Ae.</li>
        <li><strong>Client und Firmware muessen zusammenpassen.</strong> Viele Geraete (vor allem
          &bdquo;Proxmark3 Easy&ldquo;) kommen mit alter Firmware. Nach der Installation des Clients
          muss dann einmal die passende Firmware aufgespielt werden (Schritt unten).</li>
        <li><strong>Nur ein Programm gleichzeitig:</strong> Solange der Client in einem anderen Fenster
          laeuft (z. B. <code>./pm3</code> in ProxSpace), ist der COM-Port belegt und diese Oberflaeche
          kann nicht verbinden. Das andere Fenster also vorher mit <code>quit</code> beenden.</li>
      </ul>

      <h3>Weg 1 &ndash; fertiges Paket (am einfachsten)</h3>
      <ol class="schritt-liste">
        <li>Auf <code>www.proxmarkbuilds.org</code> (in der offiziellen Proxmark3-Anleitung empfohlen)
          das Windows-Paket der <strong>Iceman</strong>-Version herunterladen &ndash; passend zum Geraet:
          <em>RDV4</em> oder <em>generic</em> (fuer Proxmark3 Easy und Nachbauten).</li>
        <li>Die Datei entpacken, am besten nach <code>C:\\Proxmark3</code>.
          Darin liegen u. a. <code>pm3.bat</code>, <code>pm3-flash-all.bat</code> und der Ordner
          <code>client</code> mit <code>proxmark3.exe</code> &ndash; diese Oberflaeche sucht dort und in
          &bdquo;Downloads&ldquo;/&bdquo;Desktop&ldquo; automatisch danach.</li>
        <li>Oben auf <strong>&bdquo;Automatisch suchen&ldquo;</strong> klicken. Wird nichts gefunden,
          den Pfad zu <code>proxmark3.exe</code> ins Feld eintragen und speichern.</li>
        <li>Firmware aufspielen (siehe &bdquo;Firmware aufspielen&ldquo; unten), dann
          <strong>&bdquo;Verbindung testen&ldquo;</strong>.</li>
      </ol>

      <h3>Weg 2 &ndash; selbst bauen mit ProxSpace</h3>
      <div class="dialog-warnung">
        <strong>Bekanntes Problem (Stand 2026):</strong> MSYS2 liefert die Firmware-Werkzeuge
        <code>arm-none-eabi-gcc/binutils/newlib</code> nur noch fuer die Umgebung &bdquo;ucrt64&ldquo;,
        ProxSpace verlangt aber noch die &bdquo;mingw64&ldquo;-Pakete. Bei der Einrichtung erscheint dann
        <code>error: target not found: mingw-w64-x86_64-arm-none-eabi-gcc</code>, und die Firmware laesst sich
        nicht bauen. Solange ProxSpace das nicht behoben hat, ist <strong>Weg 1</strong> der einfachere Weg.
        Wer trotzdem selbst bauen moechte, legt zuerst im Windows-Explorer den Ordner
        <code>C:\\ProxSpace\\msys2\\ucrt64</code> an (ProxSpace bringt ihn nicht mit; ohne ihn meldet die
        Installation <code>/ucrt64 exists in filesystem</code>, weil MSYS2 dann <code>ucrt64.exe</code> fuer
        diesen Ordner haelt). Danach die Werkzeuge in der fertig eingerichteten
        ProxSpace-Konsole (<code>pm3 ~$</code>) von Hand installieren:
        <pre><code>pacman -S --noconfirm mingw-w64-ucrt-x86_64-arm-none-eabi-gcc \\
  mingw-w64-ucrt-x86_64-arm-none-eabi-binutils mingw-w64-ucrt-x86_64-arm-none-eabi-newlib</code></pre>
        und macht sie vor jedem <code>make</code> auffindbar:
        <pre><code>export PATH="$PATH:/ucrt64/bin"
arm-none-eabi-gcc --version</code></pre>
      </div>
      <ol class="schritt-liste">
        <li><strong>ProxSpace</strong> herunterladen: <code>github.com/Gator96100/ProxSpace/releases</code>
          (die ZIP-Datei unter &bdquo;Assets&ldquo; der neuesten Version) und nach <code>C:\\ProxSpace</code>
          entpacken (Pfad <strong>ohne</strong> Leerzeichen und Umlaute). Im Ordner muss danach direkt
          <code>runme64.bat</code> liegen.
          <br><span class="hinweis-klein">Achtung: <strong>nicht</strong> in OneDrive, auf den Desktop oder
          unter &bdquo;Dokumente&ldquo; entpacken (werden oft von OneDrive synchronisiert, und Pfade wie
          &bdquo;Proxmark 3&ldquo; oder &bdquo;Pers&ouml;nlich&ldquo; enthalten Leerzeichen bzw. Umlaute &ndash;
          dann bricht die Einrichtung ab, erkennbar an einem seltsamen Ordner wie &bdquo;3&ldquo;).
          Die Adresszeile im Explorer muss am Ende &bdquo;Lokaler Datentr&auml;ger (C:) &rsaquo; ProxSpace&ldquo; zeigen.</span>
          <br><span class="hinweis-klein">Ebenso <strong>nicht</strong> MSYS2 von msys2.org
          installieren &ndash; ProxSpace bringt sein eigenes, fertig vorbereitetes MSYS2 mit.</span></li>
        <li><strong>Immer</strong> ueber <code>C:\\ProxSpace\\runme64.bat</code> starten (Doppelklick),
          nie ueber MSYS2-Verknuepfungen im Startmenue oder <code>mingw64.exe</code>.
          Beim allerersten Start werden Pakete aktualisiert; das Fenster kann sich dabei von selbst
          schliessen. Dann <code>runme64.bat</code> einfach noch einmal starten &ndash; jetzt werden alle
          Werkzeuge installiert (kann 10&ndash;30 Minuten dauern).</li>
        <li>Fertig eingerichtet ist ProxSpace, wenn die Eingabezeile <code>pm3 ~$</code> lautet.
          Steht dort stattdessen <code>name@rechner MINGW64 ~</code>, ist ProxSpace nicht aktiv
          (dann fehlt z. B. <code>git</code>: &bdquo;command not found&ldquo;). Kurztest:
          <pre><code>git --version</code></pre>
          <span class="hinweis-klein">Bleibt die Einrichtung minutenlang bei &bdquo;Installing: &hellip;&ldquo; stehen:
          nicht ins Fenster klicken (Windows haelt die Ausgabe dann an &ndash; mit Esc fortsetzen). Haeufig
          bremst auch der Virenscanner die tausenden kleinen Dateien aus; eine Ausnahme fuer
          <code>C:\\ProxSpace</code> in &bdquo;Windows-Sicherheit &rsaquo; Viren- &amp; Bedrohungsschutz &rsaquo;
          Ausschl&uuml;sse&ldquo; hilft dann. Ein Neustart von <code>runme64.bat</code> setzt an der Stelle fort.</span></li>
        <li>Quellcode holen:
          <pre><code>git clone https://github.com/RfidResearchGroup/proxmark3.git
cd proxmark3</code></pre></li>
        <li>Firmware-Werkzeuge auffindbar machen (nach jedem Neustart von ProxSpace, siehe Kasten oben):
          <pre><code>export PATH="$PATH:/ucrt64/bin"</code></pre></li>
        <li>Bauen (dauert 5&ndash;20 Minuten) &ndash; je nach Geraet <strong>eine</strong> der beiden Zeilen:
          <pre><code>make clean &amp;&amp; make -j4                          # Proxmark3 RDV4
make clean &amp;&amp; make -j4 PLATFORM=PM3GENERIC      # Proxmark3 Easy / Nachbauten</code></pre>
          Erfolgreich ist es, wenn am Ende keine Zeile mit <code>Error</code> steht.</li>
        <li>Firmware aufspielen (Proxmark eingesteckt):
          <pre><code>./pm3-flash-all</code></pre></li>
        <li>Kurz testen mit <code>./pm3</code> und darin <code>hw version</code>. Danach mit
          <code>quit</code> beenden, damit der Anschluss fuer diese Oberflaeche frei wird.</li>
        <li>Diese Oberflaeche findet den Client dann automatisch unter
          <code>C:\\ProxSpace\\pm3\\proxmark3\\client\\proxmark3.exe</code>.</li>
      </ol>

      <h3>Firmware aufspielen</h3>
      <p>Zeigt <code>hw version</code> eine Warnung, dass Client und Firmware nicht zusammenpassen,
      muss die Firmware aus demselben Paket aufs Geraet:</p>
      <ul>
        <li><strong>ProxSpace:</strong> im ProxSpace-Fenster im Ordner <code>proxmark3</code>:
          <code>./pm3-flash-all</code></li>
        <li><strong>Fertiges Paket:</strong> im entpackten Ordner <code>pm3-flash-all.bat</code>
          doppelklicken. (Die Firmware-Dateien <code>fullimage.elf</code> und <code>bootrom.elf</code>
          liegen im Unterordner <code>client</code>.)</li>
        <li>Klappt das Aufspielen nicht: Proxmark abziehen, den <strong>Knopf gedrueckt halten</strong>,
          wieder einstecken und den Knopf waehrend des gesamten Vorgangs gedrueckt lassen.</li>
      </ul>
      <p class="hinweis-klein">&#9888; Waehrend des Aufspielens den Proxmark <strong>nicht</strong>
      abziehen. Den Bootloader (<code>bootrom</code>) nur erneuern, wenn die Anleitung des Pakets das
      verlangt &ndash; ein Abbruch dabei kann das Geraet unbrauchbar machen.</p>
    </div>

    <div class="os-abschnitt" data-os="linux">
      <h3>Linux (Debian / Ubuntu / Raspberry Pi)</h3>
      <ol class="schritt-liste">
        <li>Benoetigte Pakete installieren:
          <pre><code>sudo apt update
sudo apt install --no-install-recommends git ca-certificates build-essential pkg-config \\
  libreadline-dev gcc-arm-none-eabi libnewlib-dev qtbase5-dev libbz2-dev libbluetooth-dev \\
  libpython3-dev libssl-dev</code></pre></li>
        <li>Ihren Benutzer der Gruppe <code>dialout</code> hinzufuegen (fuer USB-Zugriff),
          danach neu anmelden:
          <pre><code>sudo usermod -aG dialout $USER</code></pre></li>
        <li>Quellcode holen:
          <pre><code>git clone https://github.com/RfidResearchGroup/proxmark3.git
cd proxmark3</code></pre></li>
        <li>Uebersetzen und installieren:
          <pre><code>make clean &amp;&amp; make -j$(nproc)
sudo make install</code></pre></li>
        <li>Proxmark anschliessen und testen:
          <pre><code>pm3</code></pre>
          Im Client dann <code>hw status</code> eingeben.</li>
      </ol>
      <p class="hinweis-klein">Der Anschluss heisst unter Linux meist <code>/dev/ttyACM0</code>.
      Diese GUI erkennt ihn automatisch.</p>
    </div>

    <div class="os-abschnitt" data-os="macos">
      <h3>macOS &ndash; ueber Homebrew</h3>
      <ol class="schritt-liste">
        <li>Falls noch nicht vorhanden, <strong>Homebrew</strong> installieren
          (siehe <code>brew.sh</code>).</li>
        <li>Fertige Formel installieren:
          <pre><code>brew install rfidresearchgroup/proxmark3/proxmark3</code></pre>
          Alternativ selbst uebersetzen (siehe Projektwiki).</li>
        <li>Proxmark anschliessen und testen:
          <pre><code>pm3</code></pre>
          Im Client dann <code>hw status</code> eingeben.</li>
      </ol>
      <p class="hinweis-klein">Der Anschluss heisst unter macOS meist
      <code>/dev/tty.usbmodemiceman1</code>. Diese GUI erkennt ihn automatisch.</p>
    </div>

    <h3>Woran erkenne ich, dass alles laeuft?</h3>
    <p>Oben rechts zeigt diese Oberflaeche den Status an:</p>
    <ul>
      <li><strong>Geraet verbunden</strong> (gruen) &ndash; Client gefunden, Proxmark angeschlossen. Alle Befehle funktionieren.</li>
      <li><strong>Client bereit (kein Geraet)</strong> (blau) &ndash; Client installiert, aber kein Proxmark angesteckt. Offline-Befehle funktionieren.</li>
      <li><strong>Demo-Modus</strong> (gelb) &ndash; kein Client gefunden. Zum Ausprobieren; es wird nichts gesendet.</li>
    </ul>
    <p class="hinweis-klein">Liegt Ihr Client an einem ungewoehnlichen Ort, koennen Sie den Pfad
    ueber die Umgebungsvariable <code>PM3_CLIENT</code> vorgeben.</p>
  `,

  hilfe: `
    <h2>Kurzanleitung</h2>
    <p>Diese Oberflaeche macht die Funktionen des Proxmark3-Clients zum Anklicken.
    Sie sendet dabei genau die Befehle, die man sonst von Hand tippen wuerde.</p>

    <h3>Die Reiter im Ueberblick</h3>
    <ul>
      <li><strong>Befehle</strong> &ndash; alle Funktionen nach Kategorie (Hochfrequenz, Niederfrequenz, Hardware &hellip;).
        Links die Kategorie waehlen, dann auf eine Karte klicken.</li>
      <li><strong>Assistent</strong> &ndash; fertige Ablaeufe fuer haeufige Aufgaben. Ein Klick fuehrt mehrere Schritte nacheinander aus.</li>
      <li><strong>Konsole</strong> &ndash; direkte Eingabe fuer Fortgeschrittene, mit Verlauf ueber die Pfeiltasten.</li>
      <li><strong>Installation</strong> &ndash; Schritt-fuer-Schritt-Einrichtung des Clients.</li>
      <li><strong>Lexikon</strong> &ndash; kurze Erklaerungen zu Fachbegriffen.</li>
    </ul>

    <h3>So gehen Sie am besten vor</h3>
    <ol class="schritt-liste">
      <li>Pruefen Sie oben rechts den Status. Steht dort <em>Demo-Modus</em>, richten Sie zuerst den Client ein (Reiter Installation).</li>
      <li>Legen Sie eine Karte auf die Antenne des Proxmark.</li>
      <li>Wissen Sie nicht, was fuer eine Karte das ist? Reiter <strong>Assistent</strong> &rarr; &bdquo;Ich weiss nicht, was fuer eine Karte das ist&ldquo;.</li>
      <li>Zum gezielten Arbeiten den Reiter <strong>Befehle</strong> nutzen und die passende Kategorie waehlen.</li>
    </ol>

    <h3>Farben der Markierungen</h3>
    <ul>
      <li><span class="marke marke--anfaenger">einfach</span> &ndash; gut zum Einsteigen, meist ungefaehrlich.</li>
      <li><span class="marke marke--fortgeschritten">mittel</span> &ndash; setzt etwas Vorwissen voraus.</li>
      <li><span class="marke marke--experte">Experte</span> &ndash; nur mit Verstaendnis der Technik verwenden.</li>
      <li><span class="marke marke--offline">ohne Geraet</span> &ndash; funktioniert auch ohne angeschlossenen Proxmark.</li>
      <li><span class="marke marke--warnung">&#9888; Achtung</span> &ndash; kann eine Karte oder einen Chip dauerhaft veraendern. Vorher den Warnhinweis lesen.</li>
    </ul>

    <h3>Wichtiger Hinweis zum verantwortungsvollen Umgang</h3>
    <p>Der Proxmark3 ist ein Werkzeug fuer Sicherheitsforschung, Technikverstaendnis und die Arbeit
    mit den <strong>eigenen</strong> Karten und Anlagen. Setzen Sie ihn nur an Karten und Systemen ein,
    die Ihnen gehoeren oder fuer die Sie eine ausdrueckliche Erlaubnis haben. Das Auslesen, Kopieren
    oder Nachbilden fremder Karten kann rechtlich unzulaessig sein.</p>

    <h3>Nichts geht?</h3>
    <ul>
      <li><strong>Kein Geraet erkannt:</strong> USB-Kabel pruefen (Datenkabel, nicht nur Ladekabel), unter Linux Gruppe <code>dialout</code> pruefen.</li>
      <li><strong>Befehl bleibt haengen:</strong> Es gibt ein Zeitlimit je Befehl (Standard 60 s). Beim Start ueber <code>--zeitlimit</code> anpassbar.</li>
      <li><strong>Client zu alt/neu:</strong> <code>hw version</code> zeigt an, ob Client und Firmware zusammenpassen.</li>
    </ul>
  `,
};
