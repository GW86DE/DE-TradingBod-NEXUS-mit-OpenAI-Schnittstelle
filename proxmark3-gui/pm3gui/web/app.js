"use strict";

// ---------------------------------------------------------------------------
// Zustand
// ---------------------------------------------------------------------------
const Zustand = {
  katalog: null,
  aktiveKategorie: null,
  suchtext: "",
  nurOffline: false,
  nurEinfach: false,
  demo: true,
  verlauf: [],
  verlaufZeiger: -1,
};

const $ = (auswahl) => document.querySelector(auswahl);
const $$ = (auswahl) => Array.from(document.querySelectorAll(auswahl));

function escape(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  reiterEinrichten();
  dialogEinrichten();
  sucheEinrichten();
  konsoleEinrichten();
  await katalogLaden();
  await zustandAktualisieren();
  installationRendern();
  hilfeRendern();
  glossarRendern();
  assistentRendern();
  // Status alle 5 Sekunden auffrischen (Geraet an-/abstecken erkennen).
  setInterval(zustandAktualisieren, 5000);
});

async function katalogLaden() {
  try {
    const antwort = await fetch("/api/katalog");
    Zustand.katalog = await antwort.json();
    kategorienRendern();
    const ersteKat = Zustand.katalog.baum[0];
    if (ersteKat) kategorieWaehlen(ersteKat.id);
    const s = Zustand.katalog.statistik;
    $("#fuss-info").textContent =
      `${s.befehle} Befehle · ${s.kategorien} Kategorien · ${s.uebersetzt} auf Deutsch erklaert`;
  } catch (fehler) {
    $("#befehlsbereich").innerHTML =
      `<p class="leer-hinweis">Katalog konnte nicht geladen werden.<br>${escape(fehler)}</p>`;
  }
}

async function zustandAktualisieren() {
  try {
    const antwort = await fetch("/api/zustand");
    const z = await antwort.json();
    Zustand.demo = z.demo;
    const anzeige = $("#status-anzeige");
    const text = $("#status-text");
    anzeige.className = "status";
    if (z.demo) {
      anzeige.classList.add("status--demo");
      text.textContent = "Demo-Modus";
    } else if (z.geraet_verbunden) {
      anzeige.classList.add("status--verbunden");
      text.textContent = "Geraet verbunden";
    } else {
      anzeige.classList.add("status--offline");
      text.textContent = "Client bereit (kein Geraet)";
    }
    anzeige.title = z.meldung || "";
  } catch (fehler) {
    /* Server noch nicht bereit - ignorieren. */
  }
}

// ---------------------------------------------------------------------------
// Reiter
// ---------------------------------------------------------------------------
function reiterEinrichten() {
  $$(".reiter-knopf").forEach((knopf) => {
    knopf.addEventListener("click", () => {
      const ziel = knopf.dataset.reiter;
      $$(".reiter-knopf").forEach((k) => k.classList.toggle("aktiv", k === knopf));
      $$(".reiter-inhalt").forEach((abschnitt) => {
        abschnitt.classList.toggle("aktiv", abschnitt.id === `reiter-${ziel}`);
      });
      if (ziel === "konsole") $("#konsole-feld").focus();
    });
  });
}

// ---------------------------------------------------------------------------
// Kategorien / Befehle
// ---------------------------------------------------------------------------
function kategorienRendern() {
  const behaelter = $("#kategorien");
  behaelter.innerHTML = "";
  Zustand.katalog.baum.forEach((kat) => {
    const knopf = document.createElement("button");
    knopf.className = "kat-knopf";
    knopf.dataset.kat = kat.id;
    knopf.innerHTML =
      `<span class="kat-symbol">${escape(kat.symbol)}</span>` +
      `<span class="kat-name">${escape(kat.titel)}</span>` +
      `<span class="kat-zahl">${kat.anzahl}</span>`;
    knopf.addEventListener("click", () => kategorieWaehlen(kat.id));
    behaelter.appendChild(knopf);
  });
}

function kategorieWaehlen(katId) {
  Zustand.aktiveKategorie = katId;
  Zustand.suchtext = "";
  $("#suche").value = "";
  $$(".kat-knopf").forEach((k) => k.classList.toggle("aktiv", k.dataset.kat === katId));
  befehleRendern();
}

function aktiveBefehleErmitteln() {
  const kat = (Zustand.katalog.baum || []).find((k) => k.id === Zustand.aktiveKategorie);
  if (!kat) return [];
  let abschnitte = kat.abschnitte.map((a) => ({
    ...a,
    befehle: a.befehle.filter(befehlPasst),
  }));
  return abschnitte.filter((a) => a.befehle.length > 0);
}

function befehlPasst(befehl) {
  if (Zustand.nurOffline && !befehl.offline) return false;
  if (Zustand.nurEinfach && befehl.stufe !== "anfaenger") return false;
  return true;
}

function befehleRendern() {
  const bereich = $("#befehlsbereich");
  const abschnitte = aktiveBefehleErmitteln();
  if (!abschnitte.length) {
    bereich.innerHTML = `<p class="leer-hinweis">Keine Befehle mit den aktuellen Filtern.</p>`;
    return;
  }
  bereich.innerHTML = "";
  abschnitte.forEach((abschnitt) => {
    const block = document.createElement("div");
    block.className = "abschnitt-block";
    const kopf = abschnitt.titel && abschnitt.pfad
      ? `<h3 class="abschnitt-kopf">${escape(abschnitt.titel)} <code>${escape(abschnitt.pfad)}</code></h3>`
      : `<h3 class="abschnitt-kopf">${escape(abschnitt.titel || "Allgemein")}</h3>`;
    const beschr = abschnitt.beschreibung
      ? `<p class="abschnitt-beschreibung">${escape(abschnitt.beschreibung)}</p>`
      : "";
    block.innerHTML = kopf + beschr + `<div class="befehl-raster"></div>`;
    const raster = block.querySelector(".befehl-raster");
    abschnitt.befehle.forEach((befehl) => raster.appendChild(befehlKarte(befehl)));
    bereich.appendChild(block);
  });
}

function befehlKarte(befehl) {
  const karte = document.createElement("div");
  karte.className = "befehl-karte";
  const marken = [];
  marken.push(`<span class="marke marke--${befehl.stufe}">${stufeName(befehl.stufe)}</span>`);
  if (befehl.offline) marken.push(`<span class="marke marke--offline">ohne Geraet</span>`);
  if (befehl.warnung) marken.push(`<span class="marke marke--warnung">&#9888; Achtung</span>`);
  karte.innerHTML =
    `<div class="befehl-titel">${escape(befehl.titel)}</div>` +
    `<div class="befehl-pfad">${escape(befehl.pfad)}</div>` +
    `<div class="befehl-beschr">${escape(befehl.beschreibung)}</div>` +
    `<div class="marken">${marken.join("")}</div>`;
  karte.addEventListener("click", () => befehlDialogOeffnen(befehl));
  return karte;
}

function stufeName(stufe) {
  return { anfaenger: "einfach", fortgeschritten: "mittel", experte: "Experte" }[stufe] || stufe;
}

// ---------------------------------------------------------------------------
// Suche
// ---------------------------------------------------------------------------
function sucheEinrichten() {
  let zeitgeber = null;
  $("#suche").addEventListener("input", (e) => {
    clearTimeout(zeitgeber);
    Zustand.suchtext = e.target.value;
    zeitgeber = setTimeout(sucheRendern, 160);
  });
  $("#nur-offline").addEventListener("change", (e) => {
    Zustand.nurOffline = e.target.checked;
    Zustand.suchtext ? sucheRendern() : befehleRendern();
  });
  $("#nur-einfach").addEventListener("change", (e) => {
    Zustand.nurEinfach = e.target.checked;
    Zustand.suchtext ? sucheRendern() : befehleRendern();
  });
}

function sucheRendern() {
  const text = Zustand.suchtext.trim().toLowerCase();
  if (!text) {
    $$(".kat-knopf").forEach((k) =>
      k.classList.toggle("aktiv", k.dataset.kat === Zustand.aktiveKategorie));
    befehleRendern();
    return;
  }
  $$(".kat-knopf").forEach((k) => k.classList.remove("aktiv"));
  const treffer = [];
  (Zustand.katalog.baum || []).forEach((kat) => {
    kat.abschnitte.forEach((abschnitt) => {
      abschnitt.befehle.forEach((befehl) => {
        if (!befehlPasst(befehl)) return;
        const heu = `${befehl.pfad} ${befehl.titel} ${befehl.beschreibung} ${befehl.beschreibung_en}`.toLowerCase();
        if (heu.includes(text)) treffer.push(befehl);
      });
    });
  });
  const bereich = $("#befehlsbereich");
  if (!treffer.length) {
    bereich.innerHTML = `<p class="leer-hinweis">Nichts gefunden fuer &bdquo;${escape(text)}&ldquo;.</p>`;
    return;
  }
  bereich.innerHTML = `<h3 class="abschnitt-kopf">${treffer.length} Treffer</h3><div class="befehl-raster"></div>`;
  const raster = bereich.querySelector(".befehl-raster");
  treffer.slice(0, 200).forEach((befehl) => raster.appendChild(befehlKarte(befehl)));
}

// ---------------------------------------------------------------------------
// Befehls-Dialog
// ---------------------------------------------------------------------------
let dialogAktuellerBefehl = null;

function dialogEinrichten() {
  $("#dialog-schliessen").addEventListener("click", dialogSchliessen);
  $("#dialog-huelle").addEventListener("click", (e) => {
    if (e.target.id === "dialog-huelle") dialogSchliessen();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") dialogSchliessen();
  });
}

function befehlDialogOeffnen(befehl) {
  dialogAktuellerBefehl = befehl;
  const inhalt = $("#dialog-inhalt");
  const warnung = befehl.warnung
    ? `<div class="dialog-warnung">&#9888; ${escape(befehl.warnung)}</div>`
    : "";
  const nichtUebersetzt = !befehl.uebersetzt
    ? `<p class="hinweis-klein">Fuer diesen Befehl liegt noch keine deutsche Beschreibung vor &ndash; angezeigt wird der Originaltext des Clients.</p>`
    : "";
  inhalt.innerHTML =
    `<h2>${escape(befehl.titel)}</h2>` +
    `<p class="dialog-pfad">${escape(befehl.pfad)}</p>` +
    `<div class="marken" style="margin:10px 0">` +
      `<span class="marke marke--${befehl.stufe}">${stufeName(befehl.stufe)}</span>` +
      (befehl.offline ? `<span class="marke marke--offline">ohne Geraet nutzbar</span>` : "") +
    `</div>` +
    `<p>${escape(befehl.beschreibung)}</p>` +
    (befehl.beschreibung_en && befehl.uebersetzt
      ? `<p class="hinweis-klein"><em>Original:</em> ${escape(befehl.beschreibung_en)}</p>`
      : "") +
    warnung +
    nichtUebersetzt +
    `<div class="dialog-feld-zeile">` +
      `<label for="dialog-parameter">Zusatzangaben (optional) &ndash; werden an den Befehl angehaengt:</label>` +
      `<input id="dialog-parameter" type="text" placeholder="z. B. --blk 4 -k FFFFFFFFFFFF" />` +
    `</div>` +
    `<div class="dialog-vorschau" id="dialog-vorschau">${escape(befehl.pfad)}</div>` +
    `<div class="dialog-knoepfe">` +
      `<button class="knopf knopf--haupt" id="dialog-ausfuehren">In Konsole ausfuehren</button>` +
      `<button class="knopf" id="dialog-hilfe">Hilfe zum Befehl</button>` +
      `<button class="knopf" id="dialog-kopieren">Befehl kopieren</button>` +
    `</div>`;

  const param = $("#dialog-parameter");
  const vorschau = $("#dialog-vorschau");
  const aktualisiere = () => {
    const zusatz = param.value.trim();
    vorschau.textContent = zusatz ? `${befehl.pfad} ${zusatz}` : befehl.pfad;
  };
  param.addEventListener("input", aktualisiere);
  $("#dialog-ausfuehren").addEventListener("click", () => {
    befehlInKonsole(vorschau.textContent);
    dialogSchliessen();
  });
  $("#dialog-hilfe").addEventListener("click", () => {
    befehlInKonsole(`${befehl.pfad} help`);
    dialogSchliessen();
  });
  $("#dialog-kopieren").addEventListener("click", () => {
    navigator.clipboard?.writeText(vorschau.textContent);
    $("#dialog-kopieren").textContent = "Kopiert!";
  });

  $("#dialog-huelle").hidden = false;
  param.focus();
}

function dialogSchliessen() {
  $("#dialog-huelle").hidden = true;
  dialogAktuellerBefehl = null;
}

// ---------------------------------------------------------------------------
// Konsole
// ---------------------------------------------------------------------------
function konsoleEinrichten() {
  const feld = $("#konsole-feld");
  $("#konsole-senden").addEventListener("click", () => konsoleSenden(feld.value));
  feld.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      konsoleSenden(feld.value);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      verlaufBlaettern(-1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      verlaufBlaettern(1);
    }
  });
}

function verlaufBlaettern(richtung) {
  if (!Zustand.verlauf.length) return;
  Zustand.verlaufZeiger = Math.max(
    0,
    Math.min(Zustand.verlauf.length, Zustand.verlaufZeiger + richtung)
  );
  $("#konsole-feld").value = Zustand.verlauf[Zustand.verlaufZeiger] || "";
}

function befehlInKonsole(befehl) {
  // Zum Konsolenreiter wechseln und ausfuehren.
  $$(".reiter-knopf").forEach((k) => k.classList.toggle("aktiv", k.dataset.reiter === "konsole"));
  $$(".reiter-inhalt").forEach((a) => a.classList.toggle("aktiv", a.id === "reiter-konsole"));
  konsoleSenden(befehl);
}

async function konsoleSenden(befehl) {
  befehl = (befehl || "").trim();
  if (!befehl) return;
  $("#konsole-feld").value = "";
  Zustand.verlauf.push(befehl);
  Zustand.verlaufZeiger = Zustand.verlauf.length;

  konsoleAnhaengen(`pm3> ${befehl}`, "konsole-zeile-befehl");
  const laden = konsoleAnhaengen("… wird ausgefuehrt", "konsole-zeile-demo");

  try {
    const antwort = await fetch("/api/ausfuehren", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ befehl }),
    });
    const ergebnis = await antwort.json();
    laden.remove();
    const klasse = ergebnis.demo
      ? "konsole-zeile-demo"
      : ergebnis.erfolg
      ? ""
      : "konsole-zeile-fehler";
    konsoleAnhaengen(ergebnis.ausgabe || "(keine Ausgabe)", klasse);
    if (!ergebnis.demo && typeof ergebnis.dauer === "number") {
      konsoleAnhaengen(`  [${ergebnis.dauer.toFixed(2)} s]`, "konsole-trenner");
    }
  } catch (fehler) {
    laden.remove();
    konsoleAnhaengen(`Fehler: ${fehler}`, "konsole-zeile-fehler");
  }
  konsoleAnhaengen("─".repeat(50), "konsole-trenner");
}

function konsoleAnhaengen(text, klasse) {
  const ausgabe = $("#konsole-ausgabe");
  const zeile = document.createElement("div");
  if (klasse) zeile.className = klasse;
  zeile.textContent = text;
  ausgabe.appendChild(zeile);
  ausgabe.scrollTop = ausgabe.scrollHeight;
  return zeile;
}

// ---------------------------------------------------------------------------
// Assistent (haeufige Aufgaben)
// ---------------------------------------------------------------------------
const ASSISTENT_AUFGABEN = [
  {
    symbol: "❓",
    titel: "Ich weiss nicht, was fuer eine Karte das ist",
    text: "Der Proxmark probiert selbstaendig LF und HF durch und erkennt den Typ.",
    schritte: ["auto"],
  },
  {
    symbol: "🔍",
    titel: "13,56-MHz-Karte pruefen (NFC/MIFARE)",
    text: "Karte auflegen und den Typ samt UID bestimmen lassen.",
    schritte: ["hf search"],
  },
  {
    symbol: "📡",
    titel: "125-kHz-Karte pruefen (alte Zutrittskarte)",
    text: "Aeltere Zutritts- oder Tierchipkarte erkennen.",
    schritte: ["lf search"],
  },
  {
    symbol: "💾",
    titel: "MIFARE-Classic-Karte auslesen",
    text: "Erst Info, dann ein Abbild der Karte in eine Datei speichern.",
    schritte: ["hf mf info", "hf mf dump"],
  },
  {
    symbol: "🏷️",
    titel: "NFC-Tag (NTAG) auslesen",
    text: "Typ bestimmen und gespeicherte NDEF-Inhalte (Links, Text) anzeigen.",
    schritte: ["hf mfu info", "hf mfu ndefread"],
  },
  {
    symbol: "🔧",
    titel: "Ist mein Proxmark in Ordnung?",
    text: "Version, Status und Antennenmessung auf einen Blick.",
    schritte: ["hw version", "hw status", "hw tune"],
  },
  {
    symbol: "📡",
    titel: "Antenne abstimmen",
    text: "LF- und HF-Antennenspannung messen (guter Test nach dem Zusammenbau).",
    schritte: ["hw tune"],
  },
  {
    symbol: "🧾",
    titel: "Fremden Leser mitschneiden",
    text: "Kommunikation zwischen einem fremden Leser und einer Karte aufzeichnen und anzeigen.",
    schritte: ["hf 14a sniff", "trace list"],
  },
];

function assistentRendern() {
  const raster = $("#assistent-raster");
  raster.innerHTML = "";
  ASSISTENT_AUFGABEN.forEach((aufgabe) => {
    const karte = document.createElement("div");
    karte.className = "aufgabe-karte";
    karte.innerHTML =
      `<div class="aufgabe-symbol">${escape(aufgabe.symbol)}</div>` +
      `<div class="aufgabe-titel">${escape(aufgabe.titel)}</div>` +
      `<div class="aufgabe-text">${escape(aufgabe.text)}</div>` +
      `<div class="aufgabe-schritte">Befehle: ${aufgabe.schritte.map(escape).join(" → ")}</div>`;
    karte.addEventListener("click", () => assistentStarten(aufgabe));
    raster.appendChild(karte);
  });
}

async function assistentStarten(aufgabe) {
  $$(".reiter-knopf").forEach((k) => k.classList.toggle("aktiv", k.dataset.reiter === "konsole"));
  $$(".reiter-inhalt").forEach((a) => a.classList.toggle("aktiv", a.id === "reiter-konsole"));
  konsoleAnhaengen(`### ${aufgabe.titel}`, "konsole-zeile-demo");
  for (const schritt of aufgabe.schritte) {
    await konsoleSenden(schritt);
  }
}

// ---------------------------------------------------------------------------
// Installation, Hilfe, Glossar (aus texte.js)
// ---------------------------------------------------------------------------
function installationRendern() {
  $("#installation-inhalt").innerHTML = TEXTE.installation;
  const waehler = $("#installation-inhalt").querySelector(".betriebssystem-waehler");
  if (waehler) {
    waehler.querySelectorAll(".os-knopf").forEach((knopf) => {
      knopf.addEventListener("click", () => {
        const ziel = knopf.dataset.os;
        $("#installation-inhalt").querySelectorAll(".os-knopf").forEach((k) =>
          k.classList.toggle("aktiv", k === knopf));
        $("#installation-inhalt").querySelectorAll(".os-abschnitt").forEach((a) =>
          a.classList.toggle("aktiv", a.dataset.os === ziel));
      });
    });
  }
}

function hilfeRendern() {
  $("#hilfe-inhalt").innerHTML = TEXTE.hilfe;
}

function glossarRendern() {
  const behaelter = $("#glossar-inhalt");
  let html = `<h2>Lexikon &ndash; Begriffe kurz erklaert</h2>`;
  (Zustand.katalog?.glossar || []).forEach((eintrag) => {
    html +=
      `<div class="glossar-eintrag">` +
      `<span class="glossar-begriff">${escape(eintrag.begriff)}</span> &ndash; ` +
      `${escape(eintrag.erklaerung)}</div>`;
  });
  behaelter.innerHTML = html;
}
