"""Krypto-Handelsmaschine fuer OKX -- laeuft rund um die Uhr (v8.1.1 NEXUS).

ABGRENZUNG
==========
Diese Maschine ist bewusst ein EIGENER Prozessteil neben dem bestehenden
Aktienkern (live_trader.py). Gruende:

    1. Der Aktienkern ist erprobt. Ein Umbau seiner Hauptschleife waere das
       groesste Regressionsrisiko des ganzen Projekts.
    2. Krypto hat einen voellig anderen Takt (Minuten statt Stunden) und
       darf nicht auf einen langsamen Aktienzyklus warten.
    3. Faellt eine Seite aus, laeuft die andere weiter.

WAS GETEILT WIRD
================
    Candidate Gate      identische deterministische Kaufkaskade
    Strategie           dieselben Indikatoren und Signalregeln
    Kostenrechnung      dieselbe Netto-Edge-Pruefung, mit OKX-Gebuehren
    Entscheidungslog    dasselbe Journal, ergaenzt um Quellenangaben

WAS GETRENNT IST
================
    Kontostand, Risikogrenzen, Tagesbremse, Universum, Takt.

SICHERHEITSREIHENFOLGE JE KAUF
==============================
    Universum -> Signal -> Stop/Ziel -> Groesse -> Kosten -> Candidate Gate
    -> Order -> Broker-Schutz (OCO) -> Buchung -> Protokoll

Die KI kommt in dieser Kette NICHT vor. Sie beeinflusst ausschliesslich,
WELCHE Werte ueberhaupt beobachtet werden.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import config
from broker.base import (
    AuthentifizierungsFehler, BrokerFehler, OrderStatusUnklar, VerbindungVerloren,
)
from broker.okx import base_currency, normalize_inst_id
from contracts import Instrument, SimpleContract
from decision_source import (
    BROKER, CANDIDATE_GATE, DAFUER, DAGEGEN, Entscheidungsprotokoll, LUNA,
    MARKT, NEUTRAL, NUTZER, RISK_GATE, TECHNIK, UNIVERSE, speichere as speichere_quellen,
)
from safe_persistence import atomic_write_json
from decision_analytics import (mark_execution, record_order_result,
                                record_system_error)
from scheduler_v7 import POSITIONEN, SCAN, UNIVERSUM, Taktgeber

logger = logging.getLogger(__name__)


def _tickeralter_grenze(cfg) -> float:
    """Ab welchem Alter ein Krypto-Ticker nicht mehr als frisch gilt.

    Seit v8.1.5 in der WebUI einstellbar und ohne Neustart wirksam. Die
    Schwelle entscheidet nur, ob ein Kurs BENUTZT wird -- sie kann keine
    Order groesser oder ungeschuetzter machen.
    """
    try:
        import live_settings
        wert = live_settings.handelsschwellen().get("CRYPTO_TICKER_MAX_AGE_SECONDS")
        if wert is not None:
            return max(5.0, float(wert))
    except Exception:
        logger.debug("Tickeraltergrenze nicht lesbar; Standard aus config", exc_info=True)
    return max(5.0, float(getattr(cfg, "CRYPTO_TICKER_MAX_AGE_SECONDS", 120)))


def _kerzengroesse_sekunden(text: str) -> float:
    """"15 mins" -> 900. Unbekanntes ergibt 900 als sichere Vorgabe."""
    roh = str(text or "").strip().lower()
    zahl = "".join(ch for ch in roh if ch.isdigit())
    try:
        wert = float(zahl) if zahl else 15.0
    except ValueError:
        wert = 15.0
    if "hour" in roh or "std" in roh or roh.endswith("h"):
        return wert * 3600.0
    if "day" in roh or "tag" in roh or roh.endswith("d"):
        return wert * 86400.0
    if "sec" in roh:
        return wert
    return wert * 60.0


def _ist_positiv(wert) -> bool:
    """Echte positive Zahl? NaN und Unendlich fallen durch.

    ``float("nan") <= 0`` ist False -- ein NaN-Kontostand liefe damit durch
    jede Fallunterscheidung hindurch und gaelte als "stimmt mit dem Buch
    ueberein".
    """
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return False
    return math.isfinite(zahl) and zahl > 0


def meldungen_sicherheit(titel: str, text: str, *, handlung: str = "") -> str:
    """Sicherheitsmeldung -- lokal gekapselt, damit ein Importfehler nie
    einen Verkaufspfad abbricht."""
    try:
        import meldungen
        return meldungen.sicherheit(titel, text, handlung=handlung)
    except Exception:
        return f"SICHERHEIT · {titel}\n{text}" + (f"\nWas jetzt: {handlung}" if handlung else "")


def _state_root() -> Path:
    return Path(os.getenv("TRADINGBOT_TEST_STATE_DIR", "").strip() or
                Path(__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Positionsbuch
# ---------------------------------------------------------------------------
# Herkunft und Verwaltungsmodus einer Position. Bewusst dieselbe Idee wie auf
# der Aktienseite (position_manager: source / management_mode): Was der Bot
# nicht selbst gekauft hat, verkauft er auch nicht.
HERKUNFT_BOT = "BOT"
HERKUNFT_BROKER = "BROKER_BESTAND"
VERWALTUNG_AUTO = "AUTO"
VERWALTUNG_BEOBACHTEN = "BEOBACHTEN"

# Unterhalb dieser Abweichung gilt Kontostand == Buchmenge (Rundung, Staub).
MENGEN_TOLERANZ = 0.02



@dataclass
class KryptoPosition:
    """Eine offene Kryptoposition mit ihren Schutzwerten."""
    symbol: str
    inst_id: str
    menge: float
    einstieg: float
    stop: float
    take_profit: float
    eroeffnet_am: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    order_id: str = ""
    referenz: str = ""
    broker_schutz: bool = False
    hoechstkurs: float = 0.0
    paper: bool = True
    # Ab v8.1.4: Woher stammt die Position, und darf der Bot sie automatisch
    # verwalten? Die Aktienseite fuehrt dieselbe Unterscheidung seit v6
    # (source / management_mode). Ohne sie hat der Bot am 25.08.2026 einen
    # Fremdbestand von 0,94 BTC mitverkauft.
    herkunft: str = HERKUNFT_BOT
    verwaltung: str = VERWALTUNG_AUTO
    verwaltungsnotiz: str = ""
    decision_id: int | None = None
    # Immutable strategy identity from the entry fill. The global runtime
    # switch never rewrites these fields.
    entry_strategy_mode: str = "NEXUS_STANDARD"
    strategy_name: str = "NEXUS Standard Krypto"
    strategy_version: str = "NEXUS-STANDARD-LEGACY"
    strategy_parameter_hash: str = ""
    strategy_parameters: dict = field(default_factory=dict)
    trade_quote_ccy: str = ""

    @property
    def darf_automatisch_verkaufen(self) -> bool:
        """Nur eigene Positionen unter Automatik werden vom Bot geschlossen."""
        from crypto_strategy_mode import strategy_is_resolved
        return (str(self.herkunft).upper() == HERKUNFT_BOT
                and str(self.verwaltung).upper() == VERWALTUNG_AUTO
                and strategy_is_resolved(self.strategy_snapshot()))

    def strategy_snapshot(self) -> dict:
        return {
            "entry_strategy_mode": str(self.entry_strategy_mode or ""),
            "strategy_name": str(self.strategy_name or ""),
            "strategy_version": str(self.strategy_version or ""),
            "parameter_hash": str(self.strategy_parameter_hash or ""),
            "parameters": dict(self.strategy_parameters or {}),
        }

    def pausiere(self, grund: str) -> None:
        """Automatik aus -- die Position bleibt sichtbar, aber unangetastet."""
        self.verwaltung = VERWALTUNG_BEOBACHTEN
        self.verwaltungsnotiz = str(grund)[:300]

    def als_dict(self) -> dict:
        return asdict(self)


class KryptoPositionsbuch:
    """Persistentes Positionsbuch der Kryptoseite.

    OKX kennt bei Spot keine 'Position' mit Einstandspreis -- nur Guthaben.
    Einstieg, Stop und Ziel muss der Bot deshalb selbst fuehren. Ohne
    Persistenz waeren diese Werte nach einem Neustart verloren und der Bot
    wuesste nicht mehr, wo sein Stop liegt.
    """

    def __init__(self, datei: Optional[Path] = None):
        self.datei = Path(datei or _state_root() / "crypto_positions.json")
        self.positionen: dict[str, KryptoPosition] = {}
        self._lock = threading.RLock()
        self.laden()

    def laden(self) -> None:
        if not self.datei.exists():
            return
        try:
            roh = json.loads(self.datei.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Krypto-Positionsbuch unlesbar -- starte leer.", exc_info=True)
            return
        with self._lock:
            self.positionen = {}
            for eintrag in roh.get("positionen", []):
                try:
                    p = KryptoPosition(**{k: v for k, v in eintrag.items()
                                          if k in KryptoPosition.__dataclass_fields__})
                    if (str(eintrag.get("herkunft") or HERKUNFT_BOT).upper() == HERKUNFT_BOT
                            and not str(eintrag.get("entry_strategy_mode") or "")):
                        # A pre-9.0 position has no persistent strategy proof.
                        # Never guess its exit engine during an automatic migration.
                        p.entry_strategy_mode = ""
                        p.strategy_name = ""
                        p.strategy_version = ""
                        p.strategy_parameter_hash = ""
                        p.strategy_parameters = {}
                        p.pausiere("Legacy-Position ohne belegte Einstiegsstrategie; explizite Migration erforderlich")
                    self.positionen[p.symbol.upper()] = p
                except Exception:
                    logger.debug("Ungueltiger Positionseintrag uebersprungen", exc_info=True)

    def speichern(self) -> None:
        with self._lock:
            payload = {"version": 2, "gespeichert": datetime.now(timezone.utc).isoformat(),
                       "positionen": [p.als_dict() for p in self.positionen.values()]}
        try:
            atomic_write_json(self.datei, payload)
        except Exception:
            logger.warning("Krypto-Positionsbuch nicht speicherbar", exc_info=True)

    def setze(self, position: KryptoPosition) -> None:
        with self._lock:
            self.positionen[position.symbol.upper()] = position
        self.speichern()

    def hole(self, symbol: str) -> Optional[KryptoPosition]:
        with self._lock:
            return self.positionen.get(str(symbol).upper())

    def entferne(self, symbol: str) -> None:
        with self._lock:
            self.positionen.pop(str(symbol).upper(), None)
        self.speichern()

    def symbole(self) -> list[str]:
        with self._lock:
            return sorted(self.positionen)

    def alle(self) -> list[KryptoPosition]:
        with self._lock:
            return list(self.positionen.values())


# ---------------------------------------------------------------------------
# Handelsmaschine
# ---------------------------------------------------------------------------
class CryptoEngine:
    """Fuehrt Universumspflege, Signalsuche und Positionsueberwachung aus."""

    def __init__(self, *, hub, risiko, universum, taktgeber: Optional[Taktgeber] = None,
                 ai_router=None, melder=None, cfg=None):
        self.cfg = cfg or config
        self.hub = hub
        self.risiko = risiko
        self.universum = universum
        self.takt = taktgeber or Taktgeber(cfg=self.cfg)
        self.ai = ai_router
        # Symbole, deren Fremdbestand bereits gemeldet wurde -- damit die
        # Meldung nicht in jedem Minutentakt erneut kommt.
        self._gemeldeter_ueberhang: set = set()
        # Wie oft in Folge wurde fuer ein Symbol kein Guthaben gemeldet?
        # Ein einzelner Ausfall darf keine Position abrechnen.
        self._fehlender_bestand: dict = {}
        # Zweifache Bestaetigung fuer offene Ledger-Zeilen, zu denen weder
        # Positionsbuch noch Brokerbestand existieren. Ein einzelner leerer
        # Snapshot darf die Historie nicht schliessen.
        self._fehlender_ledger_bestand: dict[int, int] = {}
        # Handelsbereitschaft: neue Kaeufe erst nach Anlaufsperre und wenn
        # alle fachlichen Voraussetzungen erfuellt sind (v8.1.4).
        from trading_ready import Handelsbereitschaft
        self.bereitschaft = Handelsbereitschaft("okx", cfg=self.cfg, melder=self._melde)
        self.melder = melder
        self.buch = KryptoPositionsbuch()
        self.letzter_universumslauf: Optional[dict] = None
        self.letzter_fehler = ""
        self._exposure_sperre: list[str] = []
        # Die Klassifizierung ist nicht nur ein Logeintrag: Die WebUI muss
        # klar zeigen, dass OKX-Demo-Startguthaben keine offenen Bot-Orders
        # sind. Bis zur ersten Reconciliation bleibt die Anzeige leer statt
        # etwas zu erfinden.
        self._letzte_exposure: dict = {}
        self.zyklen = 0
        self._selector = None

    # -- Zugriffe -----------------------------------------------------------
    @property
    def broker(self):
        return self.hub.broker("okx")

    @property
    def topf(self):
        return self.risiko.topf("okx")

    def _selektor(self):
        if self._selector is None:
            from universe.crypto_selector import CryptoUniverseSelector
            broker = self.broker
            if broker is None:
                return None
            self._selector = CryptoUniverseSelector(broker.client, cfg=self.cfg)
        return self._selector

    def _instrument(self, symbol: str, inst_id: str = "") -> Instrument:
        symbol = str(symbol).upper()
        broker = self.broker
        inst_id = str(inst_id or "").upper()
        if not inst_id:
            member = self.universum.zustand.hole("okx", symbol)
            inst_id = str(getattr(member, "inst_id", "") or "").upper()
        quote = (inst_id.rsplit("-", 1)[-1] if "-" in inst_id else
                 str(getattr(broker, "quote_ccy", "EUR")))
        inst_id = inst_id or normalize_inst_id(symbol, quote)
        contract = SimpleContract(symbol, quote, localSymbol=inst_id)
        return Instrument(name=symbol, contract=contract,
                          asset_type="crypto", currency=quote, sector="crypto",
                          exchange="OKX")

    def _melde(self, text: str, *, wichtig: bool = False, klasse: str = "") -> None:
        """Eine Meldung zustellen.

        ``klasse`` erlaubt es, ein Ereignis ausdruecklich als KRITISCH zu
        kennzeichnen -- solche Meldungen werden nie gedrosselt.
        """
        logger.info(text)
        if self.melder is None:
            return
        try:
            self.melder(text, wichtig=wichtig, klasse=klasse)
        except TypeError:
            # Aeltere Melder kennen "klasse" nicht.
            try:
                self.melder(text, wichtig=wichtig)
            except Exception:
                logger.debug("Meldung konnte nicht zugestellt werden", exc_info=True)
        except Exception:
            logger.debug("Meldung konnte nicht zugestellt werden", exc_info=True)

    # -- Hauptzyklus --------------------------------------------------------
    def zyklus(self) -> dict:
        """Ein Durchlauf. Macht nur, was laut Taktgeber faellig ist."""
        self.zyklen += 1
        ergebnis = {"zeit": datetime.now(timezone.utc).isoformat(), "arbeiten": []}

        if self.broker is None:
            self.hub.verbinde("okx")
            if self.broker is None:
                ergebnis["hinweis"] = "OKX nicht verbunden"
                self._write_runtime(ergebnis)
                return ergebnis

        self.topf.neuer_tag_pruefen()
        # Nur die eigenen Positionen zaehlen zum handelbaren Kapital.
        werte = self.risiko.aktualisiere_kontowerte(self.hub, self._eigene_positionen)
        self.bereitschaft.melde("broker_verbunden", self.broker is not None
                                and self.broker.is_connected())
        self.bereitschaft.melde("guthaben", bool(werte.get("okx")),
                                f"handelbar {werte.get('okx', 0):.2f}")
        self._melde_bereitschaft()

        # Positionen zuerst: Schutz geht immer vor neuen Chancen.
        if self.takt.faellig("crypto", POSITIONEN)[0]:
            try:
                ergebnis["positionen"] = self.pruefe_positionen()
                ergebnis["arbeiten"].append(POSITIONEN)
            finally:
                self.takt.markiere("crypto", POSITIONEN)

        if self.takt.faellig("crypto", UNIVERSUM)[0]:
            try:
                ergebnis["universum"] = self.universumslauf()
                ergebnis["arbeiten"].append(UNIVERSUM)
            finally:
                self.takt.markiere("crypto", UNIVERSUM)

        if self.takt.faellig("crypto", SCAN)[0]:
            try:
                ergebnis["scan"] = self.scan()
                ergebnis["arbeiten"].append(SCAN)
            finally:
                self.takt.markiere("crypto", SCAN)

        self._write_runtime(ergebnis)
        return ergebnis

    def _write_runtime(self, cycle: dict) -> None:
        """Getrennter OKX-Heartbeat; die eToro-Datei wird nie ueberschrieben."""
        try:
            from safe_persistence import best_effort_json
            payload = self.status()
            payload.update({
                "running": True,
                "online": bool(self.broker is not None and self.broker.is_connected()),
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "last_cycle": cycle,
            })
            broker_state = self.hub.zustaende().get("okx", {}) if hasattr(self.hub, "zustaende") else {}
            payload.update({
                "connection_state": broker_state.get("status", "UNBEKANNT"),
                "last_broker_contact": broker_state.get("letzter_kontakt", ""),
                "last_connection_error": broker_state.get("letzter_fehler", ""),
                "health_interval_seconds": float(getattr(self.cfg, "BROKER_HEALTHCHECK_SECONDS", 30)),
            })
            if self.broker is not None and hasattr(self.broker, "stream_status"):
                payload["position_stream"] = self.broker.stream_status()
            best_effort_json(_state_root() / "runtime_status_okx.json", payload,
                             label="OKX Runtime-Status", durable=False)
        except Exception:
            logger.debug("OKX Runtime-Status nicht schreibbar", exc_info=True)

    # -- Universum ----------------------------------------------------------
    def universumslauf(self) -> dict:
        """Waehlt das Krypto-Universum neu und meldet die Aenderungen."""
        selektor = self._selektor()
        if selektor is None:
            return {"ok": False, "grund": "OKX nicht verbunden"}
        favoriten = self._favoriten()
        try:
            # Favoriten erhalten nur eine garantiert vollstaendige Pruefung
            # im OKX-Katalog. Sie bestehen trotzdem alle harten Filter und
            # werden erst bei ausreichend gutem Rang/Bewaehrung handelbar.
            auswahl = selektor.auswahl(bar=self._okx_bar(), favoriten=favoriten)
        except (VerbindungVerloren, BrokerFehler) as exc:
            self.letzter_fehler = str(exc)
            logger.warning("Krypto-Universumslauf fehlgeschlagen: %s", exc)
            return {"ok": False, "grund": str(exc)}

        diff = self.universum.lauf(auswahl,
                                   offene_positionen=self.buch.symbole(),
                                   favoriten=favoriten)
        # v8.1.4: Zaehlen, welcher Filter wie viele Werte verwirft. Am
        # 25.08.2026 bestanden 2 von 581 Instrumenten die harten Filter --
        # welcher Filter dafuer verantwortlich war, stand nirgends.
        import universe_diagnose
        diagnose = universe_diagnose.protokolliere(auswahl)
        self.letzter_universumslauf = {
            "zeit": datetime.now(timezone.utc).isoformat(),
            "diff": diff.als_dict(),
            "pool": auswahl.get("pool"),
            "katalog": auswahl.get("katalog_gesamt"),
            "dauer": auswahl.get("dauer_sekunden"),
            "diagnose": diagnose,
        }
        if diff.hat_aenderungen:
            self._melde(f"Krypto-Universum: {diff.kurzfassung()}"
                        + (f" | neu: {', '.join(diff.aufgenommen)}" if diff.aufgenommen else "")
                        + (f" | Beobachtung: {', '.join(diff.beobachtung_gestartet)}"
                           if diff.beobachtung_gestartet else "")
                        + (f" | raus: {', '.join(diff.entfernt)}" if diff.entfernt else ""))
        self.bereitschaft.melde("universum", True,
                                f"{auswahl.get('pool', 0)} im Pool")
        return {"ok": True, "aenderungen": diff.kurzfassung(),
                "handelbar": len(self.universum.handelbare_symbole("okx"))}

    def _okx_bar(self) -> str:
        from broker.okx import BAR_MAP
        return BAR_MAP.get(str(getattr(self.cfg, "CRYPTO_BAR_SIZE", "15 mins")).lower(), "15m")

    def _favoriten(self) -> list[str]:
        try:
            from favorites import load_favorites
            eintraege = load_favorites()
        except Exception:
            logger.debug("Favoriten nicht lesbar", exc_info=True)
            return []
        return [str(f.symbol).upper() for f in eintraege
                if str(getattr(f, "asset_type", "")).lower() == "crypto"]

    # -- Positionsueberwachung ---------------------------------------------
    def pruefe_positionen(self) -> dict:
        """Schutz nachziehen, Ausstiege pruefen, Buch mit dem Broker abgleichen."""
        # Auch Wartungs-/Migrationstests koennen den Abgleich ohne einen
        # initialisierten Broker-Hub aufrufen. Dann bleibt die sichere
        # Zwei-Snapshot-Regel aktiv, nur die Historiennachladung entfaellt.
        try:
            broker = self.broker
        except (AttributeError, KeyError):
            broker = None
        if broker is None:
            return {"ok": False, "grund": "OKX nicht verbunden"}

        bericht = {"geprueft": 0, "geschlossen": [], "schutz_ergaenzt": [], "abgeglichen": []}
        try:
            bestaende = {p.symbol.upper(): p for p in broker.positionen()}
        except BrokerFehler as exc:
            return {"ok": False, "grund": f"Bestaende nicht abrufbar: {exc}"}

        for position in self.buch.alle():
            bericht["geprueft"] += 1
            symbol = position.symbol.upper()
            bestand = bestaende.get(symbol)

            # 1. Abgleich zwischen Kontostand und Positionsbuch.
            #
            #    ACHTUNG, das ist die Stelle, an der am 25.08.2026 ein
            #    Fremdbestand von 0,94 BTC verkauft wurde. Bis 8.1.3 stand
            #    hier "position.menge = bestand.quantity" -- der Bot hat also
            #    den GESAMTEN Kontostand der Waehrung als seine Position
            #    uebernommen. broker.positionen() liefert bei OKX Spot aber
            #    Guthaben, keine Positionen; das steht so im Adapter.
            #
            #    Ab 8.1.4 wird nach RICHTUNG unterschieden:
            #      weniger im Konto  -> Buch nach unten korrigieren (sicher)
            #      mehr   im Konto   -> Ueberhang gehoert dem Bot NICHT
            if bestand is None or not _ist_positiv(getattr(bestand, "quantity", 0.0)):
                # NICHT sofort loeschen. Ein einzelner Nullstand kann auch ein
                # unvollstaendiger Guthaben-Schnappschuss sein (Stream-Snapshot,
                # Transfer ins Funding-Konto). Erst nach zwei Zyklen in Folge
                # gilt die Position als geschlossen -- vorher wuerde ein
                # erfundenes Ergebnis in die Tagesverlustgrenze wandern.
                self._fehlender_bestand[symbol] = self._fehlender_bestand.get(symbol, 0) + 1
                if self._fehlender_bestand[symbol] < 2:
                    self._melde(f"Krypto {symbol}: kein Guthaben gemeldet. Wird im "
                                f"naechsten Takt erneut geprueft, bevor die Position "
                                f"geschlossen wird.", wichtig=False)
                    continue
                self._fehlender_bestand.pop(symbol, None)
                self._position_verschwunden(position, bericht)
                continue
            self._fehlender_bestand.pop(symbol, None)

            konto = float(bestand.quantity)
            if not _ist_positiv(konto):
                # NaN oder Unendlich: laeuft durch jeden Vergleich hindurch und
                # wuerde stillschweigend als "stimmt mit dem Buch ueberein"
                # gelten. Lieber diesen Takt ueberspringen.
                logger.warning("Krypto %s: unbrauchbarer Kontostand %r -- Takt "
                               "uebersprungen.", symbol, bestand.quantity)
                continue
            abweichung = abs(konto - position.menge) / max(position.menge, 1e-12)
            if abweichung > MENGEN_TOLERANZ:
                if konto < position.menge:
                    # Extern verkauft, Schutzorder gezogen oder Teilausfuehrung.
                    # Nach unten korrigieren ist immer sicher.
                    alt_menge = position.menge
                    position.menge = konto
                    self.buch.setze(position)
                    bericht["abgeglichen"].append(symbol)
                    self._melde(
                        f"Krypto {symbol}: Bestand kleiner als im Buch "
                        f"({konto:g} statt {alt_menge:g}) -- Buchmenge nach unten "
                        f"korrigiert. Moegliche Ursache: Schutzorder ausgeloest "
                        f"oder extern verkauft.", wichtig=True)
                else:
                    # MEHR im Konto als im Buch. Der Ueberhang ist NICHT die
                    # Position des Bots. Das Buch bleibt, wie es ist.
                    ueberhang = konto - position.menge
                    bericht.setdefault("fremdbestand", []).append(
                        {"symbol": symbol, "menge": round(ueberhang, 12)})
                    if symbol not in self._gemeldeter_ueberhang:
                        self._gemeldeter_ueberhang.add(symbol)
                        self._melde(
                            f"Krypto {symbol}: {ueberhang:g} mehr im Konto als im "
                            f"Positionsbuch. Dieser Bestand gehoert nicht zum Bot "
                            f"und wird nicht verkauft. Neue Einstiege in {symbol} "
                            f"sind gesperrt, bis das geklaert ist.", wichtig=True)
            else:
                self._gemeldeter_ueberhang.discard(symbol)

            preis = float(bestand.market_price or 0.0)
            if preis <= 0:
                continue
            position.hoechstkurs = max(position.hoechstkurs, preis)

            # 2. Broker-Schutz nachziehen, falls er fehlt.
            if not position.broker_schutz:
                try:
                    zustand = broker.reconcile_position_protection(
                        self._instrument(symbol, position.inst_id), position.menge, position.stop,
                        position.take_profit)
                    if zustand.get("protection_confirmed"):
                        position.broker_schutz = True
                        self.buch.setze(position)
                        bericht["schutz_ergaenzt"].append(symbol)
                except BrokerFehler as exc:
                    logger.warning("Schutzabgleich %s: %s", symbol, exc)

            # 3. Client-Stop als zweite Sicherung. Der Broker-Schutz ist die
            #    erste; diese Pruefung greift, wenn er fehlt oder nicht zog.
            #    Eine pausierte oder fremde Position wird NIE automatisch
            #    verkauft -- genauso wie auf der Aktienseite (OBSERVE).
            if not position.darf_automatisch_verkaufen:
                bericht.setdefault("nur_beobachtet", []).append(symbol)
                continue
            if preis <= position.stop:
                self._schliesse(position, preis, "Stop-Loss erreicht")
                bericht["geschlossen"].append(symbol)
                continue
            if position.take_profit > 0 and preis >= position.take_profit:
                self._schliesse(position, preis, "Gewinnziel erreicht")
                bericht["geschlossen"].append(symbol)
                continue

            strategy_exit, strategy_reason = self._strategy_exit(position, preis)
            if strategy_exit:
                self._schliesse(position, preis, strategy_reason)
                bericht["geschlossen"].append(symbol)
                continue

            # MFE/MAE bewusst ERST HIER: die Aufzeichnung schreibt in SQLite
            # und darf die Stop- und Zielpruefung der naechsten Position
            # unter keinen Umstaenden verzoegern.
            try:
                import trade_ledger
                trade_ledger.hoechstkurs_melden("okx", symbol, preis)
            except Exception:
                logger.debug("MFE/MAE OKX nicht fortgeschrieben", exc_info=True)

        # 4. Verwaiste offene Ledger-Zeilen abgleichen. Sie werden niemals
        #    automatisch verkauft oder einer Position zugeraten. Fehlt auch
        #    beim zweiten vollstaendigen Broker-Snapshot jeder Bestand, wird
        #    nur der offene Status beendet; Preis und P&L bleiben unbekannt.
        try:
            bericht["ledger_reconciliation"] = self._offene_ledger_abgleichen(bestaende)
        except Exception as exc:
            logger.warning("OKX-Ledgerabgleich fehlgeschlagen: %s", exc, exc_info=True)
            bericht["ledger_reconciliation"] = {"ok": False, "grund": str(exc)}

        # 5. Guthaben klassifizieren statt nur aufzuzaehlen.
        #    Vorher stand hier alle paar Minuten "OKX-Guthaben ohne
        #    Positionsbuch-Eintrag: BTC, XRP, USD, ETH" -- und warf damit
        #    Cash (USD), manuelle Altbestaende und echte ungeklaerte
        #    Exposure in einen Topf. Nur der letzte Fall ist gefaehrlich.
        try:
            import exposure_klassifizierung as ek
            import trade_ledger
            guthaben = broker.client.balances() if hasattr(broker, "client") else {}
            preise = {p.symbol.upper(): float(p.market_price or 0.0)
                      for p in broker.positionen()}
            einstufung = ek.klassifiziere(
                guthaben,
                positionsbuch=self.buch.alle(),
                offene_orders=[{"symbol": s} for s in self._offene_order_symbole()],
                ledger_trades=trade_ledger.offene_trades("okx"),
                preise=preise, cfg=self.cfg)
            bericht["exposure"] = einstufung
            self._letzte_exposure = dict(einstufung)
            logger.info("OKX-Guthaben: %s", ek.kurzfassung(einstufung))
            if einstufung.get("einstiege_gesperrt"):
                self._exposure_sperre = einstufung.get("sperrgruende", [])
                self._melde("Krypto: neue Einstiege gesperrt -- ungeklaerter Bestand: "
                            + "; ".join(self._exposure_sperre), wichtig=True)
            else:
                self._exposure_sperre = []
        except Exception as exc:
            logger.warning("Guthabenklassifizierung fehlgeschlagen: %s", exc, exc_info=True)

        bericht["ok"] = True
        self.topf.setze_offene_positionen(len(self.buch.alle()))
        # Der Abgleich ist einmal vollstaendig durchgelaufen -- das ist die
        # wichtigste Bedingung der Anlaufsperre. Ohne sie haette der Bot am
        # 25.08.2026 einen Fremdbestand als eigene Position uebernommen.
        self.bereitschaft.melde("reconciliation", True,
                                f"{bericht['geprueft']} Positionen geprueft")
        return bericht

    def _offene_ledger_abgleichen(self, bestaende: dict) -> dict:
        """Offene OKX-Ledgerzeilen gegen Buch und echten Bestand pruefen."""
        import trade_ledger

        buch_symbole = {str(p.symbol).upper() for p in self.buch.alle()}
        offen = trade_ledger.offene_trades("okx")
        geschlossen: list[int] = []
        residual: list[dict] = []
        history_recovered: list[dict] = []
        account_mismatch: list[dict] = []
        gesehen: set[int] = set()
        # Der Datenbankabgleich wird auch von Migration/Diagnose ohne einen
        # vollstaendig gestarteten Broker-Hub verwendet.
        try:
            broker = self.broker
        except (AttributeError, KeyError):
            broker = None
        current_fingerprint = (broker.account_fingerprint()
                               if broker is not None and hasattr(broker, "account_fingerprint")
                               else "")

        def historical_exit(trade: dict) -> dict | None:
            """Noch nicht verbuchte SELL-Fills nach einem Einstieg nachladen."""
            if broker is None or not hasattr(broker, "historical_fills"):
                return None
            rows = broker.historical_fills(
                str(trade.get("symbol") or ""),
                since=str(trade.get("eingestiegen_am") or ""))
            sells = [r for r in rows if str(r.get("side") or "").lower() == "sell"
                     and float(r.get("fillSz") or 0) > 0
                     and float(r.get("fillPx") or 0) > 0]
            if not sells:
                return None
            group = trade_ledger.trade_group(
                broker="okx", symbol=str(trade.get("symbol") or ""),
                eingestiegen_am=str(trade.get("eingestiegen_am") or ""))
            already = sum(float(x.get("menge") or 0) for x in group
                          if x.get("ausgestiegen_am"))
            remaining_skip = max(0.0, already)
            unbooked: list[tuple[float, float, float]] = []
            for row in sells:
                qty = float(row.get("fillSz") or 0)
                if remaining_skip >= qty - 1e-12:
                    remaining_skip -= qty
                    continue
                if remaining_skip > 0:
                    qty -= remaining_skip; remaining_skip = 0.0
                if qty > 1e-12:
                    unbooked.append((qty, float(row.get("fillPx") or 0),
                                     abs(float(row.get("fee") or 0))))
            open_qty = float(trade.get("menge") or 0)
            available = sum(x[0] for x in unbooked)
            sold = min(open_qty, available)
            if sold <= 1e-12:
                return None
            left = sold; value = 0.0; fees = 0.0
            for qty, price, fee in unbooked:
                used = min(left, qty)
                if used <= 0:
                    break
                value += used * price
                fees += fee * (used / qty)
                left -= used
            avg = value / sold if sold > 0 else 0.0
            try:
                closed_id = trade_ledger.trade_close(
                    broker="okx", symbol=str(trade.get("symbol") or ""),
                    ausstieg_preis=avg, menge=sold,
                    exit_grund="OKX-Fill-Historie nachgeladen",
                    gebuehr=fees, einstieg_preis=trade.get("einstieg_preis"),
                    eingestiegen_am=trade.get("eingestiegen_am"),
                    asset_type="crypto", waehrung=str(trade.get("waehrung") or ""),
                    paper=bool(trade.get("paper", 1)),
                    notiz="Paginiert aus /trade/fills-history rekonstruiert")
            except Exception as exc:
                logger.warning("OKX-Historienfill %s konnte nicht ins Ledger geschrieben werden: %s",
                               trade.get("symbol"), exc, exc_info=True)
                return None
            return ({"trade_id": int(closed_id or trade.get("trade_id") or 0),
                     "symbol": str(trade.get("symbol") or ""),
                     "nachgebucht": sold, "preis": avg}
                    if closed_id else None)

        for trade in offen:
            trade_id = int(trade.get("trade_id") or 0)
            symbol = str(trade.get("symbol") or "").upper()
            if not trade_id or not symbol:
                continue
            gesehen.add(trade_id)
            if symbol in buch_symbole:
                self._fehlender_ledger_bestand.pop(trade_id, None)
                position = next((p for p in self.buch.alle()
                                 if str(p.symbol).upper() == symbol), None)
                trade_ledger.set_reconciliation_status(
                    trade_id, "CONFIRMED_OPEN",
                    broker_position_id=str(getattr(position, "inst_id", "") or ""),
                    notiz="OKX-Positionsbuch und Kontoabgleich bestaetigt")
                continue

            stored_fingerprint = str(trade.get("broker_account_fingerprint") or "")
            if stored_fingerprint and current_fingerprint and stored_fingerprint != current_fingerprint:
                trade_ledger.set_reconciliation_status(
                    trade_id, "ACCOUNT_MISMATCH",
                    notiz="Trade stammt aus einem anderen OKX Demo/Live-/Unterkonto")
                account_mismatch.append({"trade_id": trade_id, "symbol": symbol})
                continue

            # Fehlende/alte REST-Seiten duerfen einen Verkauf nicht unsichtbar
            # lassen. Vor der Guthabenbewertung wird die archivierte Fill-
            # Historie paginiert nachgeladen und bereits verbuchte Teilfills
            # werden mengenbasiert abgezogen.
            try:
                recovered = historical_exit(trade)
            except Exception as exc:
                logger.warning("OKX-Fill-Historie %s nicht lesbar: %s", symbol, exc)
                recovered = None
            if recovered:
                history_recovered.append(recovered)
                refreshed = trade_ledger.offener_trade("okx", symbol)
                if refreshed is None:
                    self._fehlender_ledger_bestand.pop(trade_id, None)
                    continue
                trade = refreshed
                trade_id = int(trade.get("trade_id") or trade_id)
                gesehen.add(trade_id)
            bestand = bestaende.get(symbol)
            konto = float(getattr(bestand, "quantity", 0.0) or 0.0) if bestand else 0.0

            # Ein migrierter Alteintrag ohne irgendeinen Eigentumsbeweis darf
            # nicht allein deshalb fuer immer als Bot-Position gelten, weil
            # dasselbe Asset als frei verfuegbares Kontoguthaben existiert.
            # Genau das ist beim gemeldeten SOL-Fall passiert: Der Ledger kannte
            # weder decision/order/fill noch Positionsbuch, OKX meldete aber ein
            # reales SOL-Guthaben. Zwei vollstaendige, gleiche Snapshots schliessen
            # hier nur den unbeweisbaren Ledger-Eintrag. Das SOL-Guthaben bleibt
            # unangetastet und wird anschliessend als EXTERNAL_HOLDING angezeigt.
            legacy_unbeweisbar = (
                str(trade.get("link_status") or "") == "LEGACY_UNLINKED"
                and not trade.get("decision_id")
                and not str(trade.get("entry_order_id") or "").strip()
                and not str(trade.get("entry_fill_id") or "").strip()
                and not str(trade.get("broker_position_id") or "").strip()
                and not str(trade.get("broker_account_fingerprint") or "").strip()
            )
            if legacy_unbeweisbar:
                anzahl = self._fehlender_ledger_bestand.get(trade_id, 0) + 1
                self._fehlender_ledger_bestand[trade_id] = anzahl
                if anzahl < 2:
                    trade_ledger.set_reconciliation_status(
                        trade_id, "LEGACY_ORPHAN_PENDING",
                        notiz=("Alteintrag ohne decision/order/fill/Positionsbuch; "
                               "zweiter vollstaendiger OKX-Snapshot erforderlich"))
                    residual.append({
                        "trade_id": trade_id, "symbol": symbol,
                        "ledger_menge": float(trade.get("menge") or 0.0),
                        "broker_menge": konto,
                        "status": "LEGACY_ORPHAN_PENDING",
                    })
                    continue
                if trade_ledger.mark_reconciled_closed(
                        trade_id,
                        grund="Unbeweisbarer Legacy-Ledgereintrag zweifach abgeglichen",
                        notiz=("Kein decision/order/fill/Positionsbuch-Bezug. Ein vorhandenes "
                               f"{symbol}-Guthaben bleibt externer Bestand; kein Auto-Verkauf, "
                               "Ausstiegspreis und P&L unbekannt")):
                    geschlossen.append(trade_id)
                    self._fehlender_ledger_bestand.pop(trade_id, None)
                continue

            if _ist_positiv(konto):
                self._fehlender_ledger_bestand.pop(trade_id, None)
                trade_ledger.set_reconciliation_status(
                    trade_id, "RESIDUAL_EXPOSURE",
                    notiz=("Coin-Guthaben vorhanden, aber kein Eintrag im OKX-Positionsbuch; "
                           "wird nicht automatisch verkauft"))
                residual.append({
                    "trade_id": trade_id, "symbol": symbol,
                    "ledger_menge": float(trade.get("menge") or 0.0),
                    "broker_menge": konto,
                    "status": "RESIDUAL_EXPOSURE",
                })
                continue

            anzahl = self._fehlender_ledger_bestand.get(trade_id, 0) + 1
            self._fehlender_ledger_bestand[trade_id] = anzahl
            if anzahl < 2:
                trade_ledger.set_reconciliation_status(
                    trade_id, "PENDING_CONFIRMATION",
                    notiz="Erster vollstaendiger OKX-Snapshot ohne Bestand")
                continue
            if trade_ledger.mark_reconciled_closed(
                    trade_id,
                    grund="Brokerbestand nicht mehr vorhanden (zweifach bestaetigt)",
                    notiz="Automatischer OKX-Abgleich; Ausstiegspreis und P&L unbekannt"):
                geschlossen.append(trade_id)
                self._fehlender_ledger_bestand.pop(trade_id, None)

        for trade_id in list(self._fehlender_ledger_bestand):
            if trade_id not in gesehen:
                self._fehlender_ledger_bestand.pop(trade_id, None)
        if geschlossen:
            self._melde(
                "Krypto: verwaiste offene Historieneintraege wurden nach zwei "
                "Brokerabgleichen geschlossen. Ergebnis bleibt als unbekannt markiert: "
                + ", ".join(str(x) for x in geschlossen),
                wichtig=True)
        return {"ok": True, "geschlossen": geschlossen, "residual": residual,
                "history_recovered": history_recovered,
                "account_mismatch": account_mismatch,
                "erneut_zu_pruefen": sorted(self._fehlender_ledger_bestand)}

    def _strategy_exit(self, position: KryptoPosition, current_price: float) -> tuple[bool, str]:
        """Evaluate the immutable entry strategy of one open position."""
        from crypto_strategy_mode import FREQTRADE_SAMPLE, NEXUS_STANDARD
        mode = str(position.entry_strategy_mode or "")
        if mode == NEXUS_STANDARD:
            # Preserve the existing NEXUS 8.3.1 position behaviour exactly:
            # broker/client stop and take-profit, no new exit rule added here.
            return False, ""
        if mode != FREQTRADE_SAMPLE:
            return False, ""
        from freqtrade_sample_strategy import (
            PARAMETER_HASH, STRATEGY_VERSION, exit_decision,
        )
        if (str(position.strategy_version) != STRATEGY_VERSION
                or str(position.strategy_parameter_hash) != PARAMETER_HASH):
            position.pausiere(
                "gespeicherte Freqtrade-Strategieversion/Parameter sind nicht installiert")
            self.buch.setze(position)
            self._melde(
                f"Krypto {position.symbol}: Strategie-Snapshot nicht exakt reproduzierbar. "
                "Position auf BEOBACHTEN gesetzt; Broker-Schutz bleibt bestehen.",
                wichtig=True, klasse="KRITISCH")
            return False, ""
        broker = self.broker
        if broker is None:
            return False, ""
        try:
            candles = broker.historie(
                self._instrument(position.symbol, position.inst_id),
                str(getattr(self.cfg, "FREQTRADE_HISTORY_DURATION", "3 D")),
                "5 mins", False)
            opened = datetime.fromisoformat(str(position.eroeffnet_am).replace("Z", "+00:00"))
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds() / 60.0
            close, reason, audit = exit_decision(
                candles, entry_price=position.einstieg,
                current_price=current_price, elapsed_minutes=elapsed,
                entry_fee_pct=self._taker_satz(),
                exit_fee_pct=self._taker_satz())
            if close:
                logger.info("Freqtrade-Ausgang %s: %s | %s", position.symbol, reason, audit)
            return bool(close), str(reason or "")
        except (BrokerFehler, ValueError) as exc:
            logger.warning("Freqtrade-Ausstieg fuer %s nicht pruefbar: %s", position.symbol, exc)
            return False, ""

    def _position_verschwunden(self, position: KryptoPosition, bericht: dict) -> None:
        """Kein Guthaben mehr: die Position wurde ausserhalb des Bots geschlossen.

        Bis 8.1.3 wurde sie hier nur still aus dem Buch genommen. Damit fehlte
        der Trade im Ledger und im Risikotopf, und der wahrscheinlichste Grund
        -- die brokerseitige Schutzorder hat ausgeloest -- stand nirgends.
        """
        symbol = position.symbol.upper()
        grund = ("Broker-Schutzorder ausgeloest" if position.broker_schutz
                 else "extern geschlossen (keine Bot-Schutzorder aktiv)")
        preis = self._letzter_kurs(position)
        quote = self._quote_waehrung(position)

        if preis > 0 and position.einstieg > 0 and position.darf_automatisch_verkaufen:
            gebuehr = self._gebuehr(position.menge, preis, quote)
            brutto = (preis - position.einstieg) * position.menge
            netto = brutto - gebuehr
            self.topf.buche_ergebnis(netto, brutto=brutto)
            try:
                import trade_ledger
                trade_ledger.trade_close(
                    broker="okx", symbol=symbol, ausstieg_preis=preis,
                    menge=position.menge, exit_grund=grund, gebuehr=gebuehr,
                    einstieg_preis=position.einstieg,
                    eingestiegen_am=position.eroeffnet_am,
                    asset_type="crypto", waehrung=quote, paper=bool(position.paper),
                    notiz="ausserhalb des Bots geschlossen")
            except Exception:
                logger.debug("Trade-Ledger Fremdschliessung nicht geschrieben", exc_info=True)
            self._melde(f"Krypto {symbol}: {grund}. {position.menge:g} zu rund "
                        f"{preis:g} {quote} -- Ergebnis {netto:+.2f} {quote}.",
                        wichtig=True)
        else:
            self._melde(f"Krypto {symbol}: kein Guthaben mehr vorhanden -- {grund}. "
                        f"Ergebnis nicht ermittelbar, Position aus dem Buch entfernt.",
                        wichtig=True)

        if not position.darf_automatisch_verkaufen:
            # Eine pausierte oder fremde Position wird nicht abgerechnet und
            # nicht entfernt -- sie gehoert dem Bot nicht.
            self._melde(f"Krypto {symbol}: kein Guthaben mehr, Position steht "
                        f"aber auf {position.verwaltung} und bleibt im Buch.",
                        wichtig=True)
            return
        self.buch.entferne(symbol)
        self._gemeldeter_ueberhang.discard(symbol)
        bericht.setdefault("abgeglichen", []).append(symbol)
        self.topf.setze_offene_positionen(len(self.buch.alle()))

    def _menge_an_orderbuch_anpassen(self, symbol: str, mitglied, menge: float,
                                     quote_ccy: str) -> tuple[float, str]:
        """Verkleinert eine Order, die das Orderbuch sprengen wuerde.

        Geprueft wird, wieviel sich kaufen laesst, ohne den besten Briefkurs
        um mehr als ``CRYPTO_MAX_BOOK_IMPACT_PCT`` zu verlassen. Ist das
        Orderbuch nicht abrufbar, bleibt die Menge unveraendert -- eine
        fehlende Messung darf keinen Kauf erfinden und keinen verhindern.
        """
        broker = self.broker
        if broker is None or menge <= 0:
            return menge, ""
        grenze = float(getattr(self.cfg, "CRYPTO_MAX_BOOK_IMPACT_PCT", 0.005))
        anteil = float(getattr(self.cfg, "CRYPTO_MAX_BOOK_SHARE", 0.25))
        if grenze <= 0:
            return menge, ""

        inst_id = str(getattr(mitglied, "inst_id", "") or "").upper() or f"{symbol}-{quote_ccy}"
        try:
            buch = broker.client.orderbook(inst_id, depth=20)
        except Exception:
            logger.debug("Orderbuch %s nicht abrufbar", inst_id, exc_info=True)
            return menge, ""

        asks = [(float(p), float(q)) for p, q in (buch.get("asks") or []) if p > 0 and q > 0]
        if not asks:
            return menge, ""

        bester = asks[0][0]
        tragfaehig = 0.0
        for preis, groesse in asks:
            if (preis - bester) / bester > grenze:
                break
            tragfaehig += groesse
        # Nur einen Teil der sichtbaren Tiefe beanspruchen.
        tragfaehig *= max(0.0, min(1.0, anteil))
        if tragfaehig <= 0:
            return 0.0, (f"Orderbuch bietet innerhalb von {grenze * 100:.2f} % "
                         f"keine nutzbare Tiefe")
        if menge <= tragfaehig:
            return menge, ""

        neue_menge = self._auf_lot_runden(symbol, tragfaehig)
        if neue_menge <= 0:
            return 0.0, (f"Orderbuch traegt nur {tragfaehig:g} {symbol} -- "
                         f"unter der Mindestgroesse")
        mindestwert = float(getattr(self.cfg, "OKX_MIN_POSITION_VALUE", 15.0))
        if neue_menge * bester < mindestwert:
            return 0.0, (f"Orderbuch traegt nur {neue_menge * bester:.2f} {quote_ccy} "
                         f"innerhalb von {grenze * 100:.2f} %; Mindestordergroesse "
                         f"{mindestwert:.2f} {quote_ccy}")
        return neue_menge, (
            f"Order von {menge:g} auf {neue_menge:g} {symbol} wegen Orderbuchtiefe "
            f"reduziert (innerhalb von {grenze * 100:.2f} % ab {bester:g} "
            f"liegen {tragfaehig:g})")

    def _stop_mindestabstand(self, preis: float, stop: float, spanne: float,
                             quote_ccy: str) -> tuple[float, str]:
        """Hebt einen zu engen Stop auf den Kostenabstand an.

        Rueckgabe: (Stop, Hinweis). Der Hinweis ist leer, wenn der ATR-Stop
        ohnehin weit genug sitzt.
        """
        if preis <= 0 or stop <= 0 or stop >= preis:
            return stop, ""
        faktor = float(getattr(self.cfg, "CRYPTO_STOP_KOSTEN_FAKTOR", 1.5))
        if faktor <= 0:
            return stop, ""
        gebuehr = self._taker_satz()
        # Roundtrip: Gebuehr auf beiden Seiten plus einmal die Spanne.
        kosten_pct = 2.0 * gebuehr + max(0.0, float(spanne or 0.0))
        mindest_pct = kosten_pct * faktor
        ist_pct = (preis - stop) / preis
        if ist_pct >= mindest_pct:
            return stop, ""
        neuer_stop = preis * (1.0 - mindest_pct)
        return neuer_stop, (
            f"Stop von {ist_pct * 100:.3f} % auf {mindest_pct * 100:.3f} % "
            f"erweitert -- enger als die Handelskosten "
            f"({kosten_pct * 100:.3f} % Roundtrip) waere ein Stop-Out ein "
            f"rechnerisch sicherer Verlust")

    def _taker_satz(self) -> float:
        """Der geltende Taker-Satz -- gemessen, wenn der Broker ihn kennt."""
        broker = self.broker
        if broker is not None and hasattr(broker, "gebuehrensatz"):
            try:
                satz = float(broker.gebuehrensatz())
                if satz > 0:
                    return satz
            except Exception:
                logger.debug("Gebuehrensatz nicht abrufbar", exc_info=True)
        return float(getattr(self.cfg, "OKX_TAKER_FEE_PCT", 0.0035))

    def _second_opinion(self, symbol, protokoll, *, preis, menge, stop, ziel,
                        waehrung, signal, kosten, erwartete_bewegung,
                        mitglied) -> bool:
        """Zweite Meinung; bei kritisch kann ausschliesslich Georg freigeben."""
        import second_opinion as so

        live = bool(self.broker is not None and not self.broker.ist_paper())
        if not so.aktiv(live=live):
            return True

        fakten = {
            "symbol": symbol, "broker": "okx",
            "modus": "LIVE" if live else "DEMO",
            "preis": round(float(preis), 8),
            "menge": round(float(menge), 8),
            "wert": round(float(menge) * float(preis), 2),
            "waehrung": waehrung,
            "stop": round(float(stop), 8), "ziel": round(float(ziel), 8),
            "chance_risiko": round((ziel - preis) / (preis - stop), 2)
                             if preis > stop else None,
            "technik": [b.detail for b in protokoll.beitraege
                        if getattr(b, "quelle", "") == TECHNIK][:4],
            "kosten": {
                "huerde_pct": round(float(kosten.required_edge_pct) * 100, 3),
                "erwartete_bewegung_pct": round(float(erwartete_bewegung) * 100, 3),
                "gebuehr_pct": round(self._taker_satz() * 100, 4),
            },
            "universum": {"rang": getattr(mitglied, "letzter_rang", None),
                          "score": round(float(getattr(mitglied, "letzter_score", 0.0)), 3)},
            "portfolio": {"offene_positionen": len(self.buch.alle())},
            "decision_id": protokoll.decision_id,
        }

        # Eine vorhandene Freigabe wird ohne weitere KI-Kosten geprueft. Sie
        # gilt nur fuer dieselbe, praktisch unveraenderte Ordergrundlage.
        pending = next((e for e in so.offene("okx")
                        if str(e.get("symbol", "")).upper() == str(symbol).upper()), None)
        if pending:
            if not pending.get("freigegeben"):
                protokoll.blockiert(NUTZER, "kritische KI-Warnung wartet auf persoenliche Freigabe")
                return False
            cash = self.broker.verfuegbares_cash(waehrung)
            gueltig, warum = so.grundlage_noch_gueltig(
                pending, preis=preis, cash=float(cash or 0.0),
                bestand_vorhanden=self.buch.hole(symbol) is not None,
                risiko_offen=self.risiko.darf_kaufen("crypto")[0],
                menge=menge, stop=stop)
            so.verwerfe("okx", symbol)
            if gueltig:
                protokoll.ergaenze(NUTZER, DAFUER, gewicht=0.0,
                                   detail="persoenlich per Telegram freigegeben; feste Regeln erneut bestanden")
                return True
            self._melde(f"🛡️ {symbol}: frühere Freigabe verworfen – {warum}. "
                        "Eine neue Entscheidung braucht eine neue Freigabe.", wichtig=True)

        urteil = so.hole(self.ai, fakten)
        if not urteil.gefragt:
            return True

        # Der KI-Beitrag steht IMMER mit Gewicht 0,0 und NEUTRAL im Protokoll.
        protokoll.ki("terra", NEUTRAL, urteil.kurztext or "keine Einschaetzung",
                     modell=urteil.modell, gewicht=0.0,
                     kosten_usd=urteil.kosten_usd)

        if urteil.einschaetzung == so.NICHT_ERREICHBAR:
            self._melde(f"KI nicht erreichbar vor dem Kauf von {symbol} "
                        f"({urteil.begruendung}). Der Kauf laeuft nach den festen "
                        f"Regeln weiter.", wichtig=False)
            return True

        if urteil.kritisch:
            if so.human_gate_aktiv():
                eintrag = so.stelle_zurueck(broker="okx", symbol=symbol,
                                            urteil=urteil, fakten=fakten)
                self._melde(so.rueckfragetext(eintrag), wichtig=True, klasse="KRITISCH")
                protokoll.blockiert(NUTZER, "kritische KI-Warnung: persoenliche Freigabe erforderlich")
                return False
            self._melde(so.warntext(urteil, fakten), wichtig=True, klasse="KRITISCH")
            protokoll.ergaenze(RISK_GATE, NEUTRAL, gewicht=0.0,
                               detail="KI-Warnung kritisch; Human-Gate deaktiviert",
                               datenquelle="Second Opinion")
        return True

    def _melde_bereitschaft(self) -> None:
        """Die uebrigen Bedingungen der Anlaufsperre pruefen.

        Bewusst ohne zusaetzliche Netzabfragen: geprueft wird, was der Zyklus
        ohnehin schon weiss.
        """
        broker = self.broker
        try:
            self.bereitschaft.melde("systemzeit", True)
            self.bereitschaft.melde("protokoll", True)
            if broker is None:
                return
            # Instrumentkatalog und Handelsregeln
            try:
                instrumente = broker.client.instruments()
                self.bereitschaft.melde("instrumente", bool(instrumente),
                                        f"{len(instrumente)} Instrumente")
                beispiel = next(iter(instrumente.values()), None) if instrumente else None
                self.bereitschaft.melde(
                    "handelsregeln",
                    bool(beispiel and beispiel.lot_size and beispiel.min_size))
            except Exception as exc:
                self.bereitschaft.melde("instrumente", False, str(exc)[:120])
                self.bereitschaft.melde("handelsregeln", False, str(exc)[:120])
            # Gebuehrensatz
            satz = self._taker_satz()
            self.bereitschaft.melde("gebuehren", satz > 0, f"{satz * 100:.4f} %")
            # Kursdaten: ein frischer Ticker, nicht bloss "ein Zyklus lief".
            frisch = False
            alter = None
            try:
                tickers = broker.client.tickers()
                stempel = max((t.timestamp_ms for t in tickers.values()
                               if getattr(t, "timestamp_ms", 0)), default=0)
                if stempel:
                    alter = max(0.0, time.time() - stempel / 1000.0)
                    frisch = alter <= _tickeralter_grenze(self.cfg)
            except Exception:
                logger.debug("Tickeralter nicht bestimmbar", exc_info=True)
            self.bereitschaft.melde("kursdaten", frisch,
                                    f"letzter Ticker vor {alter:.0f} s" if alter is not None
                                    else "Alter unbekannt")

            # Signalkerze: echte Messung gegen die Kerzengroesse, nicht der
            # Anlauftimer in anderen Worten.
            kerze = _kerzengroesse_sekunden(
                str(getattr(self.cfg, "CRYPTO_BAR_SIZE", "15 mins")))
            self.bereitschaft.melde(
                "signalkerze", self.bereitschaft.kerzen_vollstaendig(kerze),
                f"Kerzengroesse {kerze / 60:.0f} min")
            # Offene, unklare Orders
            self.bereitschaft.melde("keine_unklare_order",
                                    not self._offene_order_symbole())
        except Exception:
            logger.debug("Bereitschaftspruefung unvollstaendig", exc_info=True)

    def _guthaben_uebersicht(self) -> dict:
        """Guthaben je Waehrung -- ohne zusaetzliche Netzabfrage zu erzwingen."""
        broker = self.broker
        if broker is None:
            return {}
        try:
            roh = broker.client.balances()
        except Exception:
            logger.debug("Guthaben nicht abrufbar", exc_info=True)
            return {}
        out = {}
        for waehrung, eintrag in (roh or {}).items():
            gesamt = float(eintrag.get("gesamt", 0.0) or 0.0)
            if gesamt > 0:
                out[str(waehrung).upper()] = {
                    "gesamt": round(gesamt, 8),
                    "frei": round(float(eintrag.get("cash", 0.0) or 0.0), 8),
                }
        return out

    def _eigene_positionen(self, broker_name: str):
        """(Menge, Preis) der Positionen, die dem Bot in dieser Domaene gehoeren.

        Grundlage fuer das handelbare Kapital. Fremdbestaende und pausierte
        Positionen zaehlen ausdruecklich NICHT mit.
        """
        if str(broker_name).lower() != "okx":
            return ()
        paare = []
        for position in self.buch.alle():
            if not position.darf_automatisch_verkaufen:
                continue
            preis = position.hoechstkurs or position.einstieg
            if position.menge > 0 and preis > 0:
                paare.append((position.menge, preis))
        return tuple(paare)

    def _rest_lohnt_sich(self, position: KryptoPosition, rest: float, kurs: float) -> bool:
        """Ist eine Restmenge gross genug, um weiter gefuehrt zu werden?

        Zu kleine Reste kann OKX gar nicht mehr verkaufen (minSz) -- die
        weiter zu fuehren wuerde bei jedem Zyklus eine fehlschlagende Order
        erzeugen.
        """
        if rest <= 0 or kurs <= 0:
            return False
        gerundet = self._auf_lot_runden(position.symbol, rest)
        if gerundet <= 0:
            return False
        mindestwert = float(getattr(self.cfg, "OKX_MIN_POSITION_VALUE", 15.0))
        return gerundet * kurs >= mindestwert

    def _schutz_als_verloren_merken(self, position: KryptoPosition) -> None:
        """Nach einem fehlgeschlagenen Verkauf gilt der Broker-Schutz als weg.

        ``schliesse_position`` storniert bei OKX ZUERST die Schutzorder und
        sendet danach den Verkauf. Schlaegt der Verkauf fehl, ist die
        Schutzorder trotzdem storniert -- die Position liegt ungeschuetzt im
        Konto. Bis v8.1.3 blieb ``broker_schutz`` dabei auf True, und die
        einzige Wiederherstellung (``if not position.broker_schutz``) griff
        deshalb nie.
        """
        if not position.broker_schutz:
            return
        position.broker_schutz = False
        self.buch.setze(position)
        logger.warning("Broker-Schutz fuer %s gilt nach fehlgeschlagenem Verkauf "
                       "als storniert -- wird im naechsten Takt neu gesetzt.",
                       position.symbol)

    def _schutz_nachziehen(self, position: KryptoPosition) -> None:
        """Broker-Schutz fuer die verbliebene Menge neu setzen.

        Nach einem Teilverkauf gilt die alte Schutzorder fuer eine Menge, die
        es nicht mehr gibt. Ohne dieses Nachziehen laege der Rest ungeschuetzt.
        """
        broker = self.broker
        if broker is None or position.menge <= 0:
            return
        try:
            zustand = broker.reconcile_position_protection(
                self._instrument(position.symbol, position.inst_id),
                position.menge, position.stop, position.take_profit)
            position.broker_schutz = bool(zustand.get("protection_confirmed"))
            self.buch.setze(position)
            if not position.broker_schutz:
                self._melde(f"Krypto {position.symbol}: Schutzorder fuer die Restmenge "
                            f"{position.menge:g} konnte NICHT bestaetigt werden -- "
                            f"nur der Client-Stop schuetzt.", wichtig=True)
        except BrokerFehler as exc:
            self._melde(f"Krypto {position.symbol}: Schutzorder fuer die Restmenge "
                        f"nicht setzbar ({exc}) -- nur der Client-Stop schuetzt.",
                        wichtig=True)

    @staticmethod
    def _verkaufsmeldung(position, menge, geplant, rest, rest_gefuehrt,
                         kurs, gebuehr, netto, quote, grund) -> str:
        """Verkaufsmeldung, die eine Teilausfuehrung ausdruecklich benennt."""
        import meldungen
        from datetime import datetime, timezone
        haltedauer = ""
        try:
            ein = datetime.fromisoformat(str(position.eroeffnet_am))
            if ein.tzinfo is None:
                ein = ein.replace(tzinfo=timezone.utc)
            minuten = (datetime.now(timezone.utc) - ein).total_seconds() / 60.0
            haltedauer = (f"{minuten:.0f} min" if minuten < 90
                          else f"{minuten / 60:.1f} h")
        except (TypeError, ValueError):
            haltedauer = ""
        return meldungen.verkauf(
            broker="okx", symbol=position.symbol, menge=menge, geplant=geplant,
            preis=kurs, waehrung=quote, gebuehr=gebuehr, ergebnis=netto,
            grund=grund, haltedauer=haltedauer, rest_gefuehrt=rest_gefuehrt)

    def _letzter_kurs(self, position: KryptoPosition) -> float:
        """Letzter bekannter Kurs -- ohne Ausnahme, ohne Blockieren."""
        broker = self.broker
        if broker is None:
            return 0.0
        try:
            quote = broker.latest_bid_ask(
                self._instrument(position.symbol, position.inst_id)) or {}
            return float(quote.get("last") or quote.get("bid") or 0.0)
        except Exception:
            logger.debug("Letzter Kurs fuer %s nicht abrufbar", position.symbol, exc_info=True)
            return 0.0

    @staticmethod
    def _quote_waehrung(position: KryptoPosition) -> str:
        """Quotewaehrung aus der Instrumentkennung -- nie blind EUR."""
        inst_id = str(getattr(position, "inst_id", "") or "")
        if "-" in inst_id:
            return inst_id.rsplit("-", 1)[-1].upper()
        return ""

    def _schliesse(self, position: KryptoPosition, preis: float, grund: str) -> None:
        broker = self.broker
        if broker is None:
            return
        protokoll = Entscheidungsprotokoll(position.symbol, asset_type="crypto",
                                           broker="okx", aktion="VERKAUF")
        protokoll.technik(DAFUER, 1.0, grund)
        protokoll.messwerte(
            entry_decision_id=position.decision_id,
            entry_strategy_mode=position.entry_strategy_mode,
            strategy_name=position.strategy_name,
            strategy_version=position.strategy_version,
            strategy_parameter_hash=position.strategy_parameter_hash,
            exit_reason=grund,
        )

        # Harte Obergrenze: der Bot verkauft NIE mehr, als in seinem Buch
        # steht. Selbst wenn im Konto mehr liegt -- das gehoert ihm nicht.
        verkaufsmenge = float(position.menge)
        if not position.darf_automatisch_verkaufen:
            logger.info("Verkauf %s uebersprungen: Position steht auf %s",
                        position.symbol, position.verwaltung)
            return
        if verkaufsmenge <= 0:
            return
        try:
            ergebnis = broker.schliesse_position(self._instrument(position.symbol, position.inst_id),
                                                 verkaufsmenge, preis)
        except OrderStatusUnklar as exc:
            protokoll.ergaenze(BROKER, NEUTRAL, detail=f"Transportzustand unklar: {exc}")
            protokoll.abschliessen("UNKLAR", "Verkauf konnte nicht bestaetigt werden")
            speichere_quellen(protokoll)
            self._schutz_als_verloren_merken(position)
            self._melde(f"Krypto {position.symbol}: Verkaufszustand UNKLAR -- kein zweiter "
                        f"Versuch. Bitte im OKX-Konto pruefen.",
                        wichtig=True, klasse="KRITISCH")
            return
        except BrokerFehler as exc:
            protokoll.ergaenze(BROKER, DAGEGEN, detail=str(exc))
            protokoll.abschliessen("FEHLGESCHLAGEN", str(exc))
            speichere_quellen(protokoll)
            logger.warning("Verkauf %s fehlgeschlagen: %s", position.symbol, exc)
            self._schutz_als_verloren_merken(position)
            self._melde(meldungen_sicherheit(
                f"Verkauf fehlgeschlagen · {position.symbol}",
                f"{grund} sollte {verkaufsmenge:g} schliessen, der Broker hat "
                f"abgelehnt: {exc}",
                handlung="Position im OKX-Konto pruefen. Der Bot versucht es im "
                         "naechsten Takt erneut und setzt den Schutz neu."),
                wichtig=True, klasse="KRITISCH")
            return

        # Konnte die alte Schutzorder nicht storniert werden, ist das
        # Guthaben eingefroren -- der Verkauf wird dann stillschweigend zur
        # Teilausfuehrung. Das muss sichtbar sein.
        storno = dict(getattr(broker, "letzte_stornierung", {}) or {})
        if storno.get("fehler"):
            self._melde(meldungen_sicherheit(
                f"Schutzorder nicht stornierbar · {position.symbol}",
                "Die alte Schutzorder liess sich nicht entfernen: "
                + "; ".join(str(f)[:120] for f in storno["fehler"]),
                handlung="Das Guthaben kann eingefroren sein. Offene Orders im "
                         "OKX-Konto pruefen."), wichtig=True, klasse="KRITISCH")

        menge = float(ergebnis.filled_quantity or 0.0)
        kurs = float(ergebnis.avg_fill_price or preis)
        if menge <= 0:
            protokoll.abschliessen("NICHT_AUSGEFUEHRT", ergebnis.hinweis or "keine Ausfuehrung")
            speichere_quellen(protokoll)
            self._schutz_als_verloren_merken(position)
            self._melde(meldungen_sicherheit(
                f"Verkauf nicht ausgefuehrt · {position.symbol}",
                f"{grund}: 0 von {verkaufsmenge:g} ausgefuehrt"
                + (f" ({ergebnis.hinweis})" if ergebnis.hinweis else ""),
                handlung="Der Schutz wird im naechsten Takt neu gesetzt. Bleibt "
                         "es dabei, im OKX-Konto pruefen."),
                wichtig=True, klasse="KRITISCH")
            return

        # Nie mehr verbuchen, als verkauft werden durfte. Meldet der Broker
        # eine groessere Menge, ist das ein Datenfehler und keine Erlaubnis.
        if menge > verkaufsmenge * (1.0 + 1e-9):
            logger.warning("Verkauf %s meldete %g statt hoechstens %g -- gedeckelt.",
                           position.symbol, menge, verkaufsmenge)
            menge = verkaufsmenge

        ergebnis_pnl = (kurs - position.einstieg) * menge
        quote = self._quote_waehrung(position) or str(
            getattr(broker, "quote_ccy", "") or "EUR").upper()
        gebuehr = self._gebuehr(menge, kurs, quote)
        netto = ergebnis_pnl - gebuehr
        self.topf.buche_ergebnis(netto, brutto=ergebnis_pnl, trade_id=ergebnis.reference_id)

        # --- Teilausfuehrung -------------------------------------------------
        # Bis 8.1.3 wurde die Position IMMER vollstaendig aus dem Buch
        # genommen -- auch wenn nur 10 % ausgefuehrt wurden. Am 25.08.2026
        # blieben dadurch 14,19 SOL ohne Stop, ohne Ziel und ohne Buchfuehrung
        # im Konto liegen. Ab 8.1.4 bleibt der Rest gefuehrt und geschuetzt.
        rest = round(verkaufsmenge - menge, 12)
        rest_gefuehrt = False
        if rest > 0 and self._rest_lohnt_sich(position, rest, kurs):
            position.menge = rest
            position.broker_schutz = False       # Schutz galt fuer die alte Menge
            self.buch.setze(position)
            rest_gefuehrt = True
            self._schutz_nachziehen(position)
        else:
            if rest > 0:
                self._melde(f"Krypto {position.symbol}: Restmenge {rest:g} {quote} "
                            f"liegt unter der Mindestgroesse und wird nicht mehr "
                            f"gefuehrt.", wichtig=True)
            self.buch.entferne(position.symbol)
            self._gemeldeter_ueberhang.discard(position.symbol.upper())
        try:
            import trade_ledger
            trade_ledger.trade_close(
                broker="okx", symbol=position.symbol.upper(), ausstieg_preis=kurs,
                menge=menge, exit_grund=grund, gebuehr=gebuehr, referenzpreis=preis,
                einstieg_preis=position.einstieg, eingestiegen_am=position.eroeffnet_am,
                asset_type="crypto", waehrung=quote, paper=bool(position.paper),
                mfe_pct=(100.0 * (position.hoechstkurs - position.einstieg) / position.einstieg
                         if position.hoechstkurs and position.einstieg else None))
        except Exception:
            logger.debug("Trade-Ledger Ausstieg OKX nicht geschrieben", exc_info=True)

        teil = (f"; Teilausfuehrung {menge:g} von {verkaufsmenge:g}"
                + (f", Rest {rest:g} bleibt gefuehrt und geschuetzt" if rest_gefuehrt
                   else ", Rest verfaellt") if rest > 0 else "")
        protokoll.ergaenze(BROKER, NEUTRAL,
                           detail=f"{menge:g} zu {kurs:g}, Gebuehr {gebuehr:.4f}{teil}")
        protokoll.abschliessen("AUSGEFUEHRT", grund)
        speichere_quellen(protokoll)
        self._melde(self._verkaufsmeldung(position, menge, verkaufsmenge, rest,
                                          rest_gefuehrt, kurs, gebuehr, netto,
                                          quote, grund), wichtig=True)
        self.topf.setze_offene_positionen(len(self.buch.alle()))

    def _gebuehr(self, menge: float, preis: float, quote_ccy: str = "EUR") -> float:
        """Gebuehr mit dem GEMESSENEN Satz, nicht mit der Annahme."""
        from cost_engine import commission_for
        return commission_for(menge, preis, asset_type="crypto",
                              currency=str(quote_ccy or "EUR"), broker="okx",
                              fee_pct=self._taker_satz())

    def _offene_order_symbole(self) -> list[str]:
        """Symbole mit noch nicht abgeschlossener Bot-Order."""
        try:
            from order_ownership import OrderOwnershipRegistry
            registry = OrderOwnershipRegistry()
            return [str(meta.get("symbol") or key.split(":")[-1]).upper()
                    for key, meta in registry.nicht_terminale().items()]
        except Exception:
            logger.debug("Offene Bot-Orders nicht ermittelbar", exc_info=True)
            return []

    def _standard_timeframe_confirmation(self, instrument: Instrument,
                                         protokoll: Entscheidungsprotokoll) -> tuple[bool, str]:
        """Existing NEXUS 5m/1h confirmation, isolated from SampleStrategy."""
        broker = self.broker
        try:
            trend = broker.historie(
                instrument, "14 D",
                str(getattr(self.cfg, "CRYPTO_TREND_BAR_SIZE", "1 hour")), False)
            confirm = broker.historie(
                instrument, "1 D",
                str(getattr(self.cfg, "CRYPTO_CONFIRM_BAR_SIZE", "5 mins")), False)
        except BrokerFehler as exc:
            protokoll.blockiert(BROKER, f"Mehrzeitebenen-Daten fehlen: {exc}")
            return False, "5m/1h-Daten nicht verfuegbar"
        if trend is None or len(trend) < 55:
            protokoll.blockiert(TECHNIK, "zu wenige abgeschlossene 1h-Kerzen")
            return False, "1h-Trend nicht pruefbar"
        trend_close = trend["close"].astype(float)
        trend_sma20 = float(trend_close.rolling(20).mean().iloc[-1])
        trend_sma50 = float(trend_close.rolling(50).mean().iloc[-1])
        trend_ok = (float(trend_close.iloc[-1]) > trend_sma50
                    and trend_sma20 > trend_sma50)
        candle_times = dict(protokoll.daten.get("candle_timestamps") or {})
        candle_times["1h"] = str(trend.index[-1]) if len(trend) else None
        protokoll.messwerte(sma20_1h=trend_sma20, sma50_1h=trend_sma50,
                           candle_timestamps=candle_times)
        protokoll.ergaenze(
            TECHNIK, DAFUER if trend_ok else DAGEGEN, gewicht=0.45,
            detail="1h-Aufwaertstrend bestaetigt" if trend_ok else "1h-Trend nicht positiv",
            datenquelle="OKX abgeschlossene 1h-Kerzen")
        if not trend_ok:
            return False, "1h-Trendfilter"
        if confirm is None or len(confirm) < 24:
            protokoll.blockiert(TECHNIK, "zu wenige abgeschlossene 5m-Kerzen")
            return False, "5m-Bestaetigung nicht pruefbar"
        confirm_close = confirm["close"].astype(float)
        confirm_ok = (float(confirm_close.iloc[-1]) >
                      float(confirm_close.rolling(20).mean().iloc[-1])
                      and float(confirm_close.iloc[-1]) >= float(confirm_close.iloc[-4]))
        protokoll.ergaenze(
            TECHNIK, DAFUER if confirm_ok else DAGEGEN, gewicht=0.35,
            detail="5m-Impuls bestaetigt" if confirm_ok else "5m-Impuls fehlt",
            datenquelle="OKX abgeschlossene 5m-Kerzen")
        if not confirm_ok:
            return False, "5m-Bestaetigungsfilter"
        candle_times = dict(protokoll.daten.get("candle_timestamps") or {})
        candle_times["5m"] = str(confirm.index[-1]) if len(confirm) else None
        protokoll.messwerte(candle_timestamps=candle_times)
        return True, ""

    # -- Chancensuche -------------------------------------------------------
    def scan(self) -> dict:
        broker = self.broker
        if broker is None:
            return {"ok": False, "grund": "OKX nicht verbunden"}

        from crypto_strategy_mode import CRYPTO_PAUSED, current_mode
        strategy_mode = current_mode()
        if strategy_mode == CRYPTO_PAUSED:
            return {"ok": True, "gescannt": 0, "strategy_mode": strategy_mode,
                    "hinweis": ("Krypto-Neueinstiege sind pausiert. eToro sowie "
                                "OKX-Schutz, Reconciliation und positionsgebundene "
                                "Ausstiege laufen weiter.")}

        # Ungeklaerte Exposure sperrt neue Einstiege fail-closed, bis die
        # Herkunft geklaert ist. Verkaeufe und Schutzorders bleiben erlaubt.
        if getattr(self, "_exposure_sperre", None):
            return {"ok": True, "gescannt": 0,
                    "hinweis": "Neue Einstiege gesperrt: " + "; ".join(self._exposure_sperre)}

        darf, grund = self.risiko.darf_kaufen("crypto")
        if not darf:
            return {"ok": True, "gescannt": 0, "hinweis": grund}

        # Die SampleStrategy darf nicht indirekt durch eine GPT-bewertete
        # Attention-Reihenfolge beeinflusst werden. Wie eine Freqtrade-
        # Pairlist verarbeitet sie deshalb deterministisch alle aktuell durch
        # die harten OKX-/Liquiditaetsfilter freigegebenen Paare. Im normalen
        # NEXUS-Modus bleibt das bewaehrte, begrenzte Focus-Set unveraendert.
        from crypto_strategy_mode import FREQTRADE_SAMPLE
        if strategy_mode == FREQTRADE_SAMPLE:
            symbole = sorted(self.universum.handelbare_symbole("okx"))
        else:
            symbole = self.universum.focus_set("okx")
        offene = {p.symbol.upper() for p in self.buch.alle()}
        kandidaten = [s for s in symbole if s.upper() not in offene]

        bericht = {"ok": True, "gescannt": 0, "gekauft": [], "abgelehnt": {},
                   "strategy_mode": strategy_mode}
        for symbol in kandidaten:
            darf, grund = self.risiko.darf_kaufen("crypto")
            if not darf:
                bericht["hinweis"] = grund
                break
            bericht["gescannt"] += 1
            try:
                ergebnis = self.pruefe_kandidat(symbol)
            except Exception as exc:
                logger.exception("Kandidatenpruefung %s fehlgeschlagen", symbol)
                record_system_error(
                    symbol=symbol, asset_type="crypto", broker="okx",
                    gate="candidate_processing", exc=exc,
                    paper=bool(getattr(self.cfg, "OKX_DEMO", True)),
                )
                bericht["abgelehnt"][symbol] = f"Fehler: {type(exc).__name__}"
                continue
            if ergebnis.get("gekauft"):
                bericht["gekauft"].append(symbol)
            else:
                bericht["abgelehnt"][symbol] = ergebnis.get("grund", "")
        return bericht

    def pruefe_kandidat(self, symbol: str) -> dict:
        """Der vollstaendige Kaufweg fuer genau ein Instrument."""
        broker = self.broker
        protokoll = Entscheidungsprotokoll(symbol, asset_type="crypto", broker="okx")
        from crypto_strategy_mode import (
            CRYPTO_PAUSED, FREQTRADE_SAMPLE, NEXUS_STANDARD,
            current_mode, entry_snapshot,
        )
        strategy_mode = current_mode()
        if strategy_mode == CRYPTO_PAUSED:
            protokoll.blockiert(RISK_GATE, "Krypto-Neueinstiege per Laufzeitschalter pausiert")
            return self._abschluss(protokoll, "ABGELEHNT", "Krypto-Neueinstiege pausiert")
        strategy_identity = entry_snapshot(strategy_mode)
        protokoll.messwerte(
            entry_strategy_mode=strategy_mode,
            strategy_name=strategy_identity.get("strategy_name"),
            strategy_version=strategy_identity.get("strategy_version"),
            strategy_parameter_hash=strategy_identity.get("parameter_hash"),
            strategy_parameters=strategy_identity,
        )

        # --- Anlaufsperre (v8.1.4) ------------------------------------------
        # Neue Einstiege warten, bis die Domaene handelsbereit ist UND die
        # Mindestwartezeit abgelaufen ist. Verkaeufe, Stops und Schutzorders
        # betrifft das nicht -- die laufen in pruefe_positionen() sofort.
        darf_kaufen, bereit_grund = self.bereitschaft.darf_kaufen()
        if not darf_kaufen:
            protokoll.blockiert(RISK_GATE, bereit_grund)
            return self._abschluss(protokoll, "ABGELEHNT", bereit_grund)

        mitglied = self.universum.zustand.hole("okx", symbol)
        if mitglied is None or not mitglied.handelbar:
            protokoll.blockiert(UNIVERSE, "nicht im handelbaren Universum")
            return self._abschluss(protokoll, "ABGELEHNT", "nicht im handelbaren Universum")
        # Ab 9.0.1 ist die Monatsliste nur Mitgliedschaft, keine Handelsfreigabe.
        # Eine fehlgeschlagene Monatsrotation behaelt deshalb die vorige Liste.
        # Sicherheit entsteht im Geldpfad aus der Anlaufsperre oben sowie den
        # nachfolgenden Kerzen-, Instrument-, Spread-, Kosten- und Risikogates.
        instrument = self._instrument(symbol, mitglied.inst_id)
        quote_ccy = instrument.currency
        protokoll.ergaenze(UNIVERSE, DAFUER, gewicht=0.2,
                           detail=f"Rang {mitglied.letzter_rang}, Score {mitglied.letzter_score:.3f}",
                           datenquelle="UniverseManager")
        protokoll.messwerte(
            universe_rank=getattr(mitglied, "letzter_rang", None),
            universe_score=getattr(mitglied, "letzter_score", None),
            currency=quote_ccy,
        )
        if strategy_mode == NEXUS_STANDARD and mitglied.ai_bewertung:
            protokoll.ki("luna", DAFUER if mitglied.ai_bewertung == "HIGH" else NEUTRAL,
                         f"Einstufung {mitglied.ai_bewertung}", modell=mitglied.ai_modell,
                         cache=True, gewicht=0.1)

        # --- Signal --------------------------------------------------------
        is_freqtrade = strategy_mode == FREQTRADE_SAMPLE
        try:
            df = broker.historie(
                instrument,
                str(getattr(self.cfg, "FREQTRADE_HISTORY_DURATION", "3 D")
                    if is_freqtrade else getattr(self.cfg, "CRYPTO_HISTORY_DURATION", "3 D")),
                "5 mins" if is_freqtrade else
                str(getattr(self.cfg, "CRYPTO_BAR_SIZE", "15 mins")),
                False,
            )
        except BrokerFehler as exc:
            protokoll.blockiert(BROKER, f"Kursdaten nicht verfuegbar: {exc}")
            return self._abschluss(protokoll, "ABGELEHNT", "keine Kursdaten")
        minimum_candles = 200 if is_freqtrade else 60
        if df is None or len(df) < minimum_candles:
            protokoll.blockiert(TECHNIK, f"zu wenige Kerzen ({0 if df is None else len(df)})")
            return self._abschluss(protokoll, "ABGELEHNT", "zu wenige Kerzen")

        if is_freqtrade:
            from freqtrade_sample_strategy import evaluate
            from strategy import Signal
            try:
                sample = evaluate(df)
            except ValueError as exc:
                protokoll.blockiert(TECHNIK, str(exc))
                return self._abschluss(protokoll, "ABGELEHNT", str(exc))
            signal = Signal(
                "BUY" if sample.entry else "HOLD", sample.entry_reason,
                0.5, sample.close, sample.atr)
            protokoll.messwerte(
                rsi_5m=sample.rsi, tema_5m=sample.tema,
                bb_middle_5m=sample.bb_middle, volume_5m=sample.volume,
                atr=sample.atr,
                completed_candles_only=True,
                candle_timestamps={"5m": sample.candle_time},
                signal_reason=sample.entry_reason,
                enter_tag="freqtrade_sample_entry",
            )
        else:
            from strategy import generate_signal
            signal = generate_signal(df, None)
            try:
                from strategy import prepare
                ind15 = prepare(df)
                last15 = ind15.iloc[-1] if ind15 is not None and len(ind15) else {}
                protokoll.messwerte(
                    rsi_15m=last15.get("rsi") if hasattr(last15, "get") else None,
                    atr=getattr(signal, "atr", None),
                    completed_candles_only=True,
                    candle_timestamps={"15m": str(df.index[-1]) if len(df) else None},
                    signal_reason=getattr(signal, "reason", ""),
                    enter_tag=getattr(signal, "reason", ""),
                )
            except Exception:
                logger.debug("15m-Auditindikatoren nicht extrahierbar", exc_info=True)
        if signal.action != "BUY":
            protokoll.technik(DAGEGEN, 0.6, f"{signal.action}: {signal.reason}")
            return self._abschluss(protokoll, "ABGELEHNT", f"kein Kaufsignal ({signal.reason})")
        protokoll.technik(DAFUER, 0.6, signal.reason)

        if not is_freqtrade:
            confirmed, confirmation_reason = self._standard_timeframe_confirmation(
                instrument, protokoll)
            if not confirmed:
                return self._abschluss(protokoll, "ABGELEHNT", confirmation_reason)

        preis = float(signal.price or 0.0)
        if preis <= 0:
            protokoll.blockiert(TECHNIK, "kein gueltiger Signalpreis")
            return self._abschluss(protokoll, "ABGELEHNT", "kein gueltiger Preis")

        # --- Live-Quote und Spanne ----------------------------------------
        quote = broker.latest_bid_ask(instrument) or {}
        bid, ask = float(quote.get("bid") or 0.0), float(quote.get("ask") or 0.0)
        from cost_engine import fallback_spread_pct, spread_pct_from_bid_ask
        spanne = spread_pct_from_bid_ask(bid, ask, fallback_spread_pct("crypto"))
        max_spanne = float(getattr(self.cfg, "MAX_SPREAD_CRYPTO_PCT", 0.006))
        marktqualitaet_ok = spanne <= max_spanne
        if ask > 0:
            preis = ask          # gekauft wird zum Briefkurs, nicht zum Schlusskurs
        protokoll.messwerte(price=preis, bid=bid, ask=ask, spread_pct=spanne,
                           spread_limit_pct=max_spanne, quote_source="OKX Ticker")
        protokoll.ergaenze(MARKT, DAFUER if marktqualitaet_ok else DAGEGEN, gewicht=0.3,
                           detail=f"Spanne {spanne * 100:.3f} % (Grenze {max_spanne * 100:.2f} %)",
                           datenquelle="OKX Ticker")

        # --- Schutzwerte und Menge ----------------------------------------
        if is_freqtrade:
            from freqtrade_sample_strategy import MINIMAL_ROI, STOPLOSS, roi_exit_price
            stop = preis * (1.0 + float(STOPLOSS))
            # Broker-side disaster protection uses the initial ROI target.
            # The 2%/1% time steps remain client-managed and are checked on
            # every position cycle from the immutable entry snapshot.
            ziel = roi_exit_price(
                preis, float(MINIMAL_ROI["0"]),
                entry_fee_pct=self._taker_satz(),
                exit_fee_pct=self._taker_satz())
        else:
            from risk_manager import calculate_stop_take
            stop, ziel = calculate_stop_take(preis, "BUY", signal.atr, "crypto")
        # Der Stop darf nie enger sitzen als die Handelskosten. Sonst ist ein
        # Stop-Out rechnerisch ein garantierter Verlust -- genau das ist am
        # 25.08.2026 zweimal innerhalb von 63 Sekunden passiert.
        stop, stop_hinweis = self._stop_mindestabstand(preis, stop, spanne, quote_ccy)
        if stop_hinweis:
            protokoll.ergaenze(RISK_GATE, NEUTRAL, gewicht=0.0, detail=stop_hinweis,
                               datenquelle="Kostenmodell OKX")
        menge, groessen_grund = self.topf.positionsgroesse(preis, stop, asset_type="crypto")
        menge = self._auf_lot_runden(symbol, menge)
        topf_status = self.topf.uebersicht()
        protokoll.messwerte(
            stop=stop, take=ziel, planned_qty=menge,
            equity_before=topf_status.get("kontowert"),
            daily_pnl=topf_status.get("tages_pnl"),
            open_positions=topf_status.get("offene_positionen"),
            trades_today=topf_status.get("trades_heute"),
            cooldown_active=topf_status.get("abkuehlung_aktiv"),
            risk_amount=(abs(preis - stop) * menge if menge > 0 else None),
        )
        protokoll.ergaenze(RISK_GATE, DAFUER if menge > 0 else DAGEGEN, gewicht=0.4,
                           detail=groessen_grund, datenquelle="Risikotopf OKX")

        # --- Cash-Reserve: verkleinern statt blockieren --------------------
        # Bis 8.1.2 pruefte der Bot nur "passt die geplante Order ins freie
        # Cash?" und liess bei Nein die GESAMTE Order fallen. Eine kleinere,
        # regelkonforme Order war damit unmoeglich. Jetzt wird zuerst
        # verkleinert und erst danach abgelehnt, wenn selbst die kleinste
        # zulaessige Order nicht mehr passt.
        geplante_menge = float(menge)
        menge, cash_hinweis, cash_grund = self._menge_an_cash_anpassen(
            symbol, menge, preis, quote_ccy)
        try:
            protokoll.messwerte(cash_before=broker.verfuegbares_cash(quote_ccy))
        except Exception:
            logger.debug("Cash-Auditwert nicht abrufbar", exc_info=True)
        cash_ok = menge > 0
        if cash_hinweis:
            protokoll.ergaenze(RISK_GATE, NEUTRAL, gewicht=0.0, detail=cash_hinweis,
                               datenquelle="Cash-Reserve OKX")
            # Bewusst KEINE Telegram-Meldung an dieser Stelle. Der Kandidat
            # muss erst die restliche Kaufkaskade bestehen. Sonst kaeme bei
            # knappem Guthaben je Scan eine Nachricht pro geprueftem Coin --
            # fuer Kaeufe, die danach ohnehin nicht stattfinden. Gemeldet
            # wird die Verkleinerung erst beim tatsaechlichen Kauf.
        if not cash_ok:
            protokoll.ergaenze(RISK_GATE, DAGEGEN, gewicht=0.4, detail=cash_grund,
                               datenquelle="Cash-Reserve OKX")

        # --- Orderbuchtiefe -------------------------------------------------
        # Am 25.08.2026 bestellte der Bot 46,9 SOL und bekam 0,50 -- OKX
        # stornierte den Rest, weil der geschaetzte Ausfuehrungspreis den
        # besten Kurs um mehr als 5 % verfehlte. Was ausgefuehrt wurde, wurde
        # zu einem Preis ausgefuehrt, den der Markt sofort wieder verliess.
        if cash_ok:
            menge, buch_hinweis = self._menge_an_orderbuch_anpassen(
                symbol, mitglied, menge, quote_ccy)
            cash_ok = menge > 0
            if buch_hinweis:
                protokoll.ergaenze(MARKT, NEUTRAL, gewicht=0.0, detail=buch_hinweis,
                                   datenquelle="OKX Orderbuch")
            if not cash_ok:
                cash_grund = buch_hinweis or "Orderbuch zu duenn"
                protokoll.ergaenze(MARKT, DAGEGEN, gewicht=0.4, detail=cash_grund,
                                   datenquelle="OKX Orderbuch")

        # --- Kosten --------------------------------------------------------
        # Bewusst NACH der Cash-Anpassung: die Kostenrechnung haengt an der
        # Menge. Eine verkleinerte Order darf nicht mit der Kostenschaetzung
        # der urspruenglich geplanten Groesse freigegeben werden.
        from cost_engine import estimate_roundtrip
        # Mit Menge 0 liefert das Kostenmodell eine Fantasiehuerde (Division
        # durch ein Nullvolumen) und schriebe sie ins Entscheidungsjournal.
        # Ist die Menge ohnehin abgelehnt, wird die Referenzmenge gerechnet
        # und der Beitrag klar als nicht anwendbar gekennzeichnet.
        kosten = estimate_roundtrip(menge if cash_ok else geplante_menge, preis,
                                    asset_type="crypto", currency=quote_ccy,
                                    fee_pct=self._taker_satz(),
                                    bid=bid, ask=ask, broker="okx")
        erwartete_bewegung = abs(ziel - preis) / preis if preis > 0 else 0.0
        # required_edge_pct enthaelt bereits Kostenmultiplikator und
        # Sicherheitsmarge -- genau dieselbe Huerde wie auf der Aktienseite.
        netto_edge_ok = erwartete_bewegung > float(kosten.required_edge_pct)
        protokoll.messwerte(
            final_qty=menge, position_value=(menge * preis if menge > 0 else None),
            fees_estimated=(kosten.buy_commission + kosten.sell_commission),
            cost_pct=getattr(kosten, "total_cost_pct", None),
            required_edge_pct=kosten.required_edge_pct,
            expected_move_pct=erwartete_bewegung,
            net_edge_pct=(erwartete_bewegung - kosten.required_edge_pct),
        )
        protokoll.ergaenze(BROKER, DAFUER if netto_edge_ok else DAGEGEN, gewicht=0.5,
                           detail=(f"erwartete Bewegung {erwartete_bewegung * 100:.2f} % gegen "
                                   f"Kostenhuerde {kosten.required_edge_pct * 100:.2f} % "
                                   f"(davon Gebuehren "
                                   f"{(kosten.buy_commission + kosten.sell_commission):.4f} {quote_ccy})"),
                           datenquelle="Cost Engine (OKX-Gebuehren)")

        # --- Deterministische Endpruefung ----------------------------------
        from candidate_gate import bewerte_kandidat
        entscheidung = bewerte_kandidat(
            state_allows_buy=self._zustand_erlaubt_kauf(),
            broker_online=broker.is_connected(),
            instrument_identity_ok=self._identitaet_ok(symbol),
            market_open=True,                       # Krypto handelt immer
            position_already_open=self.buch.hole(symbol) is not None,
            duplicate_open_order=broker.hat_offene_order(instrument, "BUY"),
            risk_allows_buy=self.risiko.darf_kaufen("crypto")[0],
            portfolio_allows_buy=self._portfolio_erlaubt(),
            cash_allows_buy=cash_ok,
            market_quality_ok=marktqualitaet_ok,
            cost_quote_ok=True,
            net_edge_ok=netto_edge_ok,
            quantity=menge, price=preis, stop=stop, take_profit=ziel)

        if not entscheidung.approved:
            protokoll.blockiert(CANDIDATE_GATE, f"{entscheidung.blocked_by}: {entscheidung.reason}")
            return self._abschluss(protokoll, "ABGELEHNT", entscheidung.reason)

        # --- GPT Second Opinion (v8.2) --------------------------------------
        # GANZ AM ENDE, wenn alles Deterministische bestanden ist. Die KI
        # bleibt eine neutrale Warn- und Dokumentationsquelle. Ist das Human
        # Gate aktiv, wartet allein Georgs zeitlich begrenzte Freigabe; danach
        # prueft der naechste Scan die gesamte feste Kaskade erneut.
        human_gate_ok = True
        if not is_freqtrade:
            human_gate_ok = self._second_opinion(
                symbol, protokoll, preis=preis, menge=menge, stop=stop, ziel=ziel,
                waehrung=quote_ccy, signal=signal, kosten=kosten,
                erwartete_bewegung=erwartete_bewegung, mitglied=mitglied)
        if not human_gate_ok:
            return self._abschluss(
                protokoll, "PENDING_HUMAN_APPROVAL",
                "kritische KI-Warnung wartet auf persoenliche Freigabe")

        # --- Order ---------------------------------------------------------
        # Die Entscheidung MUSS vor dem Netzwerk-Submit dauerhaft existieren.
        # So kann auch UNKNOWN_AFTER_SUBMIT niemals eine verwaiste Order ohne
        # Herkunft erzeugen.
        from decision_journal import record_decision
        ready_payload = self._decision_payload(
            protokoll, status="APPROVED", reason="alle deterministischen Gates bestanden",
            paper=bool(getattr(self.cfg, "OKX_DEMO", True)))
        ready_payload["execution_status"] = "READY_TO_SUBMIT"
        decision_id = record_decision(**ready_payload)
        if decision_id is None:
            protokoll.blockiert(CANDIDATE_GATE, "Entscheidung konnte nicht persistent verknuepft werden")
            return self._abschluss(protokoll, "SYSTEM_ERROR", "Audit-Persistenz fehlgeschlagen")
        mark_execution(decision_id, "SUBMITTING", [])
        try:
            ergebnis = broker.kaufe_mit_absicherung(instrument, menge, preis, stop, ziel)
        except OrderStatusUnklar as exc:
            mark_execution(decision_id, "UNKNOWN_AFTER_SUBMIT",
                           getattr(exc, "order_ids", []) or [],
                           reference_id=getattr(exc, "reference_id", "") or "")
            protokoll.ergaenze(BROKER, NEUTRAL, detail=f"Transportzustand unklar: {exc}")
            self._melde(f"Krypto {symbol}: Kaufzustand UNKLAR (Referenz {exc.reference_id}). "
                        f"KEIN zweiter Versuch. Bitte im OKX-Konto pruefen.", wichtig=True, klasse="KRITISCH")
            return self._abschluss(protokoll, "UNKLAR", "Transportzustand nach Kauf unklar")
        except BrokerFehler as exc:
            mark_execution(decision_id, "FAILED", [])
            protokoll.blockiert(BROKER, str(exc))
            return self._abschluss(protokoll, "FEHLGESCHLAGEN", str(exc))

        gefuellt = float(ergebnis.filled_quantity or 0.0)
        execution_status = "FILLED" if gefuellt > 0 else "SUBMITTED_NOT_FILLED"
        mark_execution(
            decision_id, execution_status, getattr(ergebnis, "order_ids", []) or [],
            reference_id=str(getattr(ergebnis, "reference_id", "") or ""),
            fill_price=getattr(ergebnis, "avg_fill_price", None),
            fill_qty=getattr(ergebnis, "filled_quantity", None),
            broker_paper=bool(getattr(ergebnis, "paper", True)),
        )
        record_order_result(
            decision_id, ergebnis, broker="okx", symbol=symbol,
            requested_qty=menge, requested_price=preis, currency=quote_ccy,
        )
        if gefuellt <= 0:
            protokoll.ergaenze(BROKER, DAGEGEN, detail=ergebnis.hinweis or "keine Ausfuehrung")
            return self._abschluss(protokoll, "NICHT_AUSGEFUEHRT", ergebnis.hinweis)

        kurs = float(ergebnis.avg_fill_price or preis)
        inst_id = str(
            getattr(getattr(instrument, "contract", None), "localSymbol", "")
            or mitglied.inst_id
            or normalize_inst_id(symbol, quote_ccy)
        ).upper()
        position = KryptoPosition(
            symbol=symbol.upper(), inst_id=inst_id,
            menge=gefuellt, einstieg=kurs, stop=stop, take_profit=ziel,
            order_id=(ergebnis.order_ids or [""])[0], referenz=ergebnis.reference_id,
            broker_schutz=bool(ergebnis.stop_order_platziert), hoechstkurs=kurs,
            paper=bool(ergebnis.paper),
            entry_strategy_mode=strategy_mode,
            strategy_name=str(strategy_identity.get("strategy_name") or ""),
            strategy_version=str(strategy_identity.get("strategy_version") or ""),
            strategy_parameter_hash=str(strategy_identity.get("parameter_hash") or ""),
            strategy_parameters=dict(strategy_identity),
            trade_quote_ccy=str(getattr(ergebnis, "trade_quote_ccy", "") or quote_ccy))
        position.decision_id = decision_id
        self.buch.setze(position)
        self.topf.setze_offene_positionen(len(self.buch.alle()))
        # Trade-Ledger (v8.1.3, Etappe A): reine Aufzeichnung. Schlaegt sie
        # fehl, ist der Kauf trotzdem gueltig -- deshalb kein Fehlerpfad.
        try:
            import trade_ledger
            entry_order_id = str(next(iter(ergebnis.order_ids or []), "") or
                                 ergebnis.reference_id or "")
            trade_ledger.trade_open(
                broker="okx", symbol=symbol.upper(), menge=gefuellt,
                einstieg_preis=kurs, referenzpreis=preis, asset_type="crypto",
                waehrung=quote_ccy, paper=bool(ergebnis.paper),
                gebuehr=self._gebuehr(gefuellt, kurs, quote_ccy),
                marktphase=self._marktphase(), decision_id=decision_id,
                strategie_version=str(strategy_identity.get("strategy_version") or ""),
                entry_strategy_mode=strategy_mode,
                strategy_parameter_hash=str(strategy_identity.get("parameter_hash") or ""),
                strategy_parameters=strategy_identity,
                enter_tag=("freqtrade_sample_entry" if is_freqtrade else
                           str(getattr(signal, "reason", "") or "")[:160]),
                broker_position_id=str(position.inst_id or ""),
                entry_order_id=entry_order_id,
                entry_fill_id=(f"okx-entry:{entry_order_id}" if entry_order_id else ""),
                broker_account_fingerprint=(
                    broker.account_fingerprint()
                    if hasattr(broker, "account_fingerprint") else ""),
                reconciliation_status="CONFIRMED_OPEN")
        except Exception:
            logger.debug("Trade-Ledger Einstieg OKX nicht geschrieben", exc_info=True)

        protokoll.ergaenze(BROKER, DAFUER, gewicht=1.0,
                           detail=(f"{gefuellt:g} zu {kurs:g}; Broker-Schutz "
                                   f"{'ja' if ergebnis.stop_order_platziert else 'nein'}"))
        # Einheitliche Kaufmeldung. Die Verkleinerungen (Cash-Reserve,
        # Orderbuchtiefe) stehen als Hinweis darin -- gemeldet wird beim
        # tatsaechlichen Kauf, einmal, mit den echten Zahlen.
        import meldungen
        hinweise = [h for h in (cash_hinweis, locals().get("buch_hinweis", ""),
                                locals().get("stop_hinweis", "")) if h]
        self._melde(meldungen.kauf(
            broker="okx", symbol=symbol, menge=gefuellt, preis=kurs,
            waehrung=quote_ccy, gebuehr=self._gebuehr(gefuellt, kurs, quote_ccy),
            gebuehr_pct=self._taker_satz(), stop=stop, ziel=ziel,
            grund=getattr(signal, "reason", "") or "technisches Einstiegssignal",
            geplant=geplante_menge, schutz=bool(ergebnis.stop_order_platziert),
            hinweise=hinweise), wichtig=True)
        return self._abschluss(protokoll, "AUSGEFUEHRT", "gekauft", gekauft=True,
                               execution=ergebnis)

    def _marktphase(self) -> str:
        """Marktphase fuer die spaetere Auswertung -- oder leer.

        Bewusst nicht geraten: eine falsche Phase verfaelscht die Auswertung
        nach Marktphase still. Leer heisst "nicht bekannt".
        """
        try:
            from market_regime import letzter_bekannter
            # NUR lesen: der Kryptopfad darf keinen Marktdaten-Download
            # ausloesen und im Kaufpfad nicht auf das Netz warten.
            return letzter_bekannter()
        except Exception:
            logger.debug("Marktphase nicht ermittelbar", exc_info=True)
            return ""

    # -- Hilfsmittel --------------------------------------------------------
    def _abschluss(self, protokoll: Entscheidungsprotokoll, ergebnis: str, grund: str,
                   *, gekauft: bool = False, execution=None) -> dict:
        protokoll.abschliessen(ergebnis, grund)
        source_payload = protokoll.als_dict()
        try:
            from decision_journal import record_decision
            status = ("APPROVED" if gekauft else
                      "BLOCKED" if str(ergebnis).upper() == "ABGELEHNT" else
                      "UNKNOWN_AFTER_SUBMIT" if str(ergebnis).upper() == "UNKLAR" else
                      str(ergebnis).upper())
            payload = self._decision_payload(
                protokoll, status=status, reason=grund,
                paper=bool(getattr(execution, "paper", True)))
            payload["execution_status"] = status
            if execution is not None:
                payload.update({
                    "execution_status": str(getattr(execution, "status", "")),
                    "order_ids": list(getattr(execution, "order_ids", []) or []),
                    "reference_id": str(getattr(execution, "reference_id", "") or ""),
                    "filled_quantity": float(getattr(execution, "filled_quantity", 0.0) or 0.0),
                    "avg_fill_price": float(getattr(execution, "avg_fill_price", 0.0) or 0.0),
                })
            decision_id = record_decision(**payload)
            speichere_quellen(source_payload, decision_id=decision_id or protokoll.decision_id)
        except Exception:
            logger.debug("Entscheidungsjournal nicht schreibbar", exc_info=True)
        return {"gekauft": gekauft, "grund": grund, "protokoll": protokoll.als_dict()}

    @staticmethod
    def _decision_payload(protokoll: Entscheidungsprotokoll, *, status: str,
                          reason: str, paper: bool) -> dict:
        source_payload = protokoll.als_dict()
        payload = {
            "decision_id": protokoll.decision_id,
            "symbol": protokoll.symbol, "asset_type": "crypto", "broker": "okx",
            "approved": str(status).upper() == "APPROVED", "status": str(status).upper(),
            "paper": bool(paper),
            "blocked_by": (protokoll.blockierer[0].quelle if protokoll.blockierer else ""),
            "reason": reason, "hauptquelle": protokoll.hauptquelle(),
            "sources": source_payload.get("quellen", []),
        }
        payload.update(dict(protokoll.daten))
        return payload

    def _auf_lot_runden(self, symbol: str, menge: float) -> float:
        broker = self.broker
        if broker is None or menge <= 0:
            return 0.0
        try:
            member = self.universum.zustand.hole("okx", symbol)
            inst_id = str(getattr(member, "inst_id", "") or normalize_inst_id(symbol, broker.quote_ccy))
            meta = broker.client.instrument(inst_id)
        except BrokerFehler:
            # Fail closed. Vorher kam die Menge UNGERUNDET zurueck -- also
            # weder auf dem Lotraster noch gegen minSz geprueft. OKX lehnt
            # so eine Order ab; schlimmer, sie wandert ungeprueft durch die
            # Cash-Rechnung. Ohne Instrumentdaten wird nicht gekauft.
            logger.warning("Lotgroesse fuer %s nicht abrufbar -- kein Kauf.", symbol)
            return 0.0
        if meta is None:
            return 0.0
        from broker.okx import quantize_down
        gerundet = quantize_down(menge, meta.lot_size)
        return gerundet if gerundet >= float(meta.min_size or 0) else 0.0

    def _zustand_erlaubt_kauf(self) -> bool:
        try:
            from bot_zustand import BotZustand
            return bool(BotZustand().darf_kaufen())
        except Exception:
            # Kein lesbarer Zustand heisst: nicht kaufen. Im Zweifel gilt
            # immer die sichere Seite.
            logger.warning("Botzustand nicht lesbar -- Kauf wird blockiert.", exc_info=True)
            return False

    def _identitaet_ok(self, symbol: str) -> bool:
        """Ein OKX-Instrument ist eindeutig, wenn es im Katalog LIVE steht."""
        broker = self.broker
        if broker is None:
            return False
        try:
            member = self.universum.zustand.hole("okx", symbol)
            inst_id = str(getattr(member, "inst_id", "") or normalize_inst_id(symbol, broker.quote_ccy))
            meta = broker.client.instrument(inst_id)
        except BrokerFehler:
            return False
        return bool(meta and meta.ist_live and meta.base_ccy.upper() == str(symbol).upper())

    def _portfolio_erlaubt(self) -> bool:
        grenze = int(getattr(self.cfg, "OKX_MAX_OPEN_POSITIONS", 6))
        return len(self.buch.alle()) < grenze

    def _menge_an_cash_anpassen(self, symbol: str, menge: float, preis: float,
                                quote_ccy: str = "") -> tuple[float, str, str]:
        """Verkleinert die Order auf das verfuegbare Cash statt sie zu blockieren.

        Rueckgabe: (menge, hinweis, ablehnungsgrund)
            menge  = 0 bedeutet: auch die kleinste zulaessige Order passt nicht
            hinweis        gefuellt, wenn tatsaechlich verkleinert wurde
            ablehnungsgrund gefuellt, wenn menge == 0

        Rechenweg:
            reserve      = freies Cash * OKX_CASH_RESERVE_PCT
            max_notional = (frei - reserve) / (1 + Taker-Gebuehr)

        Die Gebuehr wird ausdruecklich herausgerechnet. Vorher steckte sie
        stillschweigend in der Reserve -- wer bis an die Reservegrenze
        verkleinert, wuerde sie sonst genau mit der Gebuehr wieder aufbrauchen.

        Verkleinern ist sicherheitstechnisch unbedenklich: der Stopabstand
        bleibt unveraendert, die Position wird kleiner, das Risiko je Trade
        sinkt also. Die Kosten- und Netto-Edge-Pruefung laeuft anschliessend
        trotzdem mit der neuen Menge erneut.
        """
        broker = self.broker
        if broker is None:
            return 0.0, "", "OKX nicht verbunden"
        if menge <= 0 or preis <= 0:
            return 0.0, "", "Keine gueltige Menge oder kein Preis"

        waehrung = str(quote_ccy or getattr(broker, "quote_ccy", "EUR")).upper()
        frei = broker.verfuegbares_cash(waehrung)
        if frei is None:
            return 0.0, "", f"Freies {waehrung}-Guthaben nicht abrufbar"

        reserve_pct = max(0.0, float(getattr(self.cfg, "OKX_CASH_RESERVE_PCT", 0.05)))
        # Der GEMESSENE Satz, nicht die Annahme -- sonst plant die
        # Cash-Rechnung mit einer Gebuehr, die es nicht gibt.
        gebuehr_pct = max(0.0, self._taker_satz())
        mindestwert = float(getattr(self.cfg, "OKX_MIN_POSITION_VALUE", 15.0))

        reserve_betrag = frei * reserve_pct
        verfuegbar = max(0.0, frei - reserve_betrag)
        max_notional = verfuegbar / (1.0 + gebuehr_pct)

        geplanter_wert = menge * preis
        if geplanter_wert <= max_notional:
            return menge, "", ""

        # Verkleinern und auf das OKX-Mengenraster abrunden.
        neue_menge = self._auf_lot_runden(symbol, max_notional / preis)
        neuer_wert = neue_menge * preis

        if neue_menge <= 0:
            return 0.0, "", (
                f"Cash reicht nicht: frei {frei:.2f} {waehrung}, davon "
                f"{reserve_betrag:.2f} Reserve; nutzbar {max_notional:.2f} "
                f"{waehrung} liegt unter der OKX-Mindestmenge")
        if neuer_wert < mindestwert:
            return 0.0, "", (
                f"Cash reicht nicht: moeglich waeren nur {neuer_wert:.2f} "
                f"{waehrung}, Mindestordergroesse ist {mindestwert:.2f} "
                f"{waehrung} (frei {frei:.2f}, Reserve {reserve_betrag:.2f})")

        hinweis = (f"Order von {geplanter_wert:.2f} {waehrung} auf "
                   f"{neuer_wert:.2f} {waehrung} wegen Cash-Reserve reduziert "
                   f"(frei {frei:.2f}, Reserve {reserve_betrag:.2f}, "
                   f"Gebuehr {gebuehr_pct * 100:.2f} %)")
        return neue_menge, hinweis, ""

    # -- Statusanzeige ------------------------------------------------------
    def status(self) -> dict:
        try:
            from crypto_strategy_mode import status as strategy_mode_status
            strategy_status = strategy_mode_status()
        except Exception as exc:
            strategy_status = {"active_mode": "CRYPTO_PAUSED", "error": str(exc)}
        return {
            "zeit": datetime.now(timezone.utc).isoformat(),
            "zyklen": self.zyklen,
            "verbunden": self.broker is not None,
            "modus": ("DEMO" if (self.broker and self.broker.ist_paper()) else "LIVE")
                     if self.broker else "-",
            # Ab v8.1.4 gehoert alles in den Status, was der Nutzer im
            # Telegram-Status und auf dem Dashboard sehen muss. Bis 8.1.3
            # stand dort ueber OKX schlicht nichts.
            "handelsbereitschaft": self.bereitschaft.status(),
            "guthaben": self._guthaben_uebersicht(),
            "exposure": dict(self._letzte_exposure),
            "handelbares_kapital": round(float(self.topf.kontowert or 0.0), 2),
            "gebuehrensatz_pct": round(self._taker_satz() * 100, 4),
            "crypto_strategy": strategy_status,
            "positionen": [p.als_dict() for p in self.buch.alle()],
            "universum": self.universum.uebersicht("okx"),
            "risiko": self.topf.uebersicht() if self.topf else {},
            "takt": self.takt.plan().get("crypto", {}),
            "letzter_universumslauf": self.letzter_universumslauf,
            "letzter_fehler": self.letzter_fehler,
        }


__all__ = ["CryptoEngine", "KryptoPosition", "KryptoPositionsbuch"]
