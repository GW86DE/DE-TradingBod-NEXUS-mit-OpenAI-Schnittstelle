"""Zentrale Konfiguration fuer TradingBot v8.1.1 NEXUS (eToro + OKX EEA).

Der Bot ist standardmaessig PAPER-ONLY. Live-Handel bleibt durch zwei
unabhaengige Schalter geschuetzt. Die KI priorisiert ausschliesslich die
Scan-Reihenfolge bereits qualifizierter Instrumente und hat keine Orderrechte.
"""
import os
from credential_store import load_credentials as _load_credentials

# Raspberry-Pi-Dauerbetrieb wird ueber die Service-Umgebung aktiviert.
# Die Handels-/Risikologik bleibt identisch; nur Laufzeit, Logging und
# Ressourcennutzung werden fuer Pi 5 / 8 GB konservativer eingestellt.
PI_MODE = os.getenv("TRADINGBOT_PI_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
PI_TARGET = os.getenv("TRADINGBOT_PI_TARGET", "pi5-8gb").strip().lower()

# ---------------------------------------------------------------------------
# HANDELSMODUS: PAPER (Spielgeld) oder LIVE (echtes Geld)
# ---------------------------------------------------------------------------
# Der Modus wird ueber das Menue (handelsmodus.py) gesetzt und in
# 'handelsmodus.txt' gespeichert -- so muss keine Python-Datei von Hand
# bearbeitet werden. Fehlt die Datei, gilt immer PAPER.
#
# LIVE ist absichtlich ZWEISTUFIG: handelsmodus.txt/ TRADING_MODE waehlt
# den Modus, eine separate kurzlebige Freigabedatei (live_trading_arm.json)
# ist der unabhaengige Arming-Faktor. Ein einzelnes TRADING_MODE=live reicht
# damit technisch NICHT mehr fuer echte Orders.
def _lies_handelsmodus() -> str:
    try:
        from pathlib import Path as _P
        datei = _P(__file__).parent / "handelsmodus.txt"
        if datei.exists():
            wert = datei.read_text(encoding="utf-8").strip().lower()
            if wert in ("paper", "live"):
                return wert
    except Exception:
        __import__("logging").getLogger(__name__).debug("Best-effort-Ausnahme unterdrueckt", exc_info=True)
    return "paper"


TRADING_MODE = os.getenv("TRADING_MODE", _lies_handelsmodus()).lower()
PAPER_TRADING = TRADING_MODE != "live"
try:
    from live_arming import arm_status as _live_arm_status
    LIVE_ARMED, LIVE_ARM_STATUS, _LIVE_ARM_DATA = _live_arm_status()
except Exception as _arm_exc:
    LIVE_ARMED, LIVE_ARM_STATUS, _LIVE_ARM_DATA = False, f"Arming-Pruefung fehlgeschlagen: {_arm_exc}", {}
I_UNDERSTAND_THE_RISK = bool(PAPER_TRADING or LIVE_ARMED)
# ---------------------------------------------------------------------------
# BROKER
# ---------------------------------------------------------------------------
# Dieser Altname bezeichnet nur den Aktien-Core. Das Asset-Routing ordnet
# Aktien eToro und Krypto OKX zu; ein beliebiger Brokerwechsel ist gesperrt.
BROKER = "etoro"

# --- eToro Public API ------------------------------------------------------
# eToro erzeugt Keys mit einer festen Umgebung (Demo ODER Real). Deshalb
# werden beide Paare getrennt gepflegt; ein Demo-Key wird nie fuer Live benutzt.
_ETORO_LOCAL = _load_credentials("etoro_credentials.json", {})

ETORO_DEMO_API_KEY = os.getenv("ETORO_DEMO_API_KEY", str(_ETORO_LOCAL.get("demo_api_key", ""))).strip()
ETORO_DEMO_USER_KEY = os.getenv("ETORO_DEMO_USER_KEY", str(_ETORO_LOCAL.get("demo_user_key", ""))).strip()
ETORO_LIVE_API_KEY = os.getenv("ETORO_LIVE_API_KEY", str(_ETORO_LOCAL.get("live_api_key", ""))).strip()
ETORO_LIVE_USER_KEY = os.getenv("ETORO_LIVE_USER_KEY", str(_ETORO_LOCAL.get("live_user_key", ""))).strip()
ETORO_ALLOW_CFD = str(os.getenv("ETORO_ALLOW_CFD", str(_ETORO_LOCAL.get("allow_cfd", False)))).strip().lower() in {"1","true","yes","on"}
ETORO_REQUIRE_COST_QUOTE = str(os.getenv("ETORO_REQUIRE_COST_QUOTE", str(_ETORO_LOCAL.get("require_cost_quote", True)))).strip().lower() not in {"0","false","no","off"}
ETORO_COST_CACHE_SECONDS = int(os.getenv("ETORO_COST_CACHE_SECONDS", "60"))
ETORO_EXTRA_SLIPPAGE_PCT = float(os.getenv("ETORO_EXTRA_SLIPPAGE_PCT", "0.0003"))
ETORO_CASH_RESERVE_PCT = float(os.getenv("ETORO_CASH_RESERVE_PCT", "0.02"))
ETORO_API_BASE_URL = os.getenv("ETORO_API_BASE_URL", "https://public-api.etoro.com").rstrip("/")
ETORO_REQUEST_TIMEOUT_SECONDS = float(os.getenv("ETORO_REQUEST_TIMEOUT_SECONDS", "25"))
ETORO_MARKET_DATA_CACHE_SECONDS = float(os.getenv("ETORO_MARKET_DATA_CACHE_SECONDS", "3"))

# Neueinstiege in Aktien: standardmaessig NUR waehrend der regulaeren
# Boersenzeit des Underlyings. eToro kann ausgewaehlte Werte 24/5 anbieten,
# aber ausserhalb RTH sind Liquiditaet/Spread typischerweise schlechter.
# Krypto ist hiervon ausgenommen und bleibt 24/7 handelbar.
STOCK_NEW_BUYS_REGULAR_HOURS_ONLY = str(os.getenv("STOCK_NEW_BUYS_REGULAR_HOURS_ONLY", "1")).strip().lower() not in {"0","false","no","off"}
MARKET_SESSION_QUOTE_MAX_AGE_SECONDS = float(os.getenv("MARKET_SESSION_QUOTE_MAX_AGE_SECONDS", "180"))

# ---------------------------------------------------------------------------
# BOERSENKALENDER UND SITZUNGSMELDUNGEN (neu in 6.0)
# ---------------------------------------------------------------------------
# Der Boersenkalender wird vollstaendig offline berechnet (market_calendar.py):
# neun US-Bundesfeiertage plus Karfreitag, dazu verkuerzte Handelstage.
# Kein API-Schluessel, kein Netzzugriff.
#
# Zweck: An Feiertagen und ausserhalb der Handelszeit ist ein vollstaendiger
# Aktienzyklus wertlos -- er kostet aber OpenAI-Aufrufe, belastet die
# Nachrichtenquellen und erzeugt Protokollrauschen.
MARKET_CALENDAR_ENABLED = True

# Vorlauf vor Handelsbeginn, in dem bereits gearbeitet wird (Minuten).
# So liegen die ersten Kerzen vor, wenn die Boerse oeffnet.
MARKET_PREOPEN_BUFFER_MINUTES = 20

# Telegram-Meldung bei Oeffnung und Schluss des US-Aktienmarktes.
MARKET_SESSION_ALERTS = True

# Zeitzone fuer alle Zeitangaben in Meldungen und Oberflaeche.
LOCAL_TIMEZONE = os.getenv("TRADINGBOT_TIMEZONE", "Europe/Berlin")

# Krypto laeuft rund um die Uhr und bleibt vom Boersenkalender unberuehrt.
CRYPTO_IGNORES_MARKET_CALENDAR = True
# Fuer Live bleiben CFDs standardmaessig gesperrt. Der Adapter bevorzugt REAL
# mit Hebel 1 und blockiert das Instrument fail-closed, wenn die Eligibility
# das fuer das Konto nicht erlaubt.

# ---------------------------------------------------------------------------
# HANDELSUNIVERSUM -- zentral in watchlist.py gepflegt
# ---------------------------------------------------------------------------
# Die Listen stehen in watchlist.py, damit sie uebersichtlich bleiben und
# jede Position eine Branchenangabe tragen kann. Zusammensetzung:
#
#   175 US-Kernwerte        grosse und mittelgrosse, liquide Werte
#    25 US-Underdogs         kleinere Werte MIT Pflicht-Screening
#    15 EU-Kernwerte         bestehendes EU-Kernuniversum
#   + 35 bewusst begrenzte US-Zusatzwerte aus broad_stocks.json
#   ----
#   250 Aktien insgesamt    konfiguriertes Beobachtungsuniversum
#   100 Kryptowaehrungen    konfiguriertes Beobachtungsuniversum
#
# Nicht jedes konfigurierte Instrument ist bei eToro fuer jedes Konto handelbar. Beim Start wird die
# aktive eToro-Teilmenge qualifiziert und im Dashboard transparent gezeigt.
#
# WICHTIG ZU DEN UNDERDOGS
# Aufnahme in die Liste ist ausdruecklich KEINE Empfehlung und keine
# Aussage darueber, dass ein Wert "gut" ist. Es sind Kandidaten, die vor
# jedem Kauf ein Kennzahlen-Screening (underdog_screening.py) UND eine
# Nachrichtenpruefung bestehen muessen. Wer durchfaellt, wird nicht
# gehandelt -- egal wie das Chartbild aussieht.
#
from watchlist import (
    US_KERN as _US_KERN,
    EU_KERN as _EU_KERN,
    UNDERDOG_KANDIDATEN as _UNDERDOG_KANDIDATEN,
    KRYPTO as _KRYPTO,
)

EU_STOCKS = [
    {"symbol": eintrag[0], "exchange": "SMART",
     "currency": eintrag[2] if len(eintrag) > 2 else "EUR",
     "sector": eintrag[1]}
    for eintrag in _EU_KERN
]

US_STOCKS = [
    {"symbol": s, "exchange": "SMART", "currency": "USD", "sector": branche}
    for s, branche in _US_KERN
]

UNDERDOG_STOCKS = [
    {"symbol": s, "exchange": "SMART", "currency": "USD",
     "sector": branche, "underdog": True}
    for s, branche in _UNDERDOG_KANDIDATEN
]

# Underdogs mithandeln? Sie durchlaufen zusaetzliche Pruefungen, weil
# kleinere Werte heftiger auf schlechte Nachrichten reagieren.
UNDERDOGS_AKTIV = True

# v5.8: das Aktienuniversum wird bewusst auf 250 Werte begrenzt.
# Die 215 kuratierten Aktien bleiben vollstaendig erhalten; nur 35 Broad-
# Kandidaten werden zusaetzlich geladen. Damit bleibt Auswahlbreite erhalten,
# ohne den 1h-Scanner mit hunderten unkuratierten Aktien zu verduennen. Die grosse JSON-Liste
# bleibt als Reserve im Paket, wird aber nicht komplett aktiv geschaltet.
BROAD_UNIVERSE_ENABLED = True
TARGET_STOCK_UNIVERSE = 250
TARGET_CRYPTO_UNIVERSE = 100
# Breite, nicht sektorklassifizierte Zusatzwerte bekommen bis zur spaeteren
# Klassifizierung eine kleinere Positionsobergrenze. Die normalen
# Marktqualitaets-, Kosten-, Korrelation-, News-, Risiko- und KI-Filter
# bleiben voll aktiv.
BROAD_POSITION_SIZE_FACTOR = 0.50
# Zusatzwerte ausserhalb des kuratierten Kernuniversums duerfen nur handeln,
# wenn die bereits geladene Historie eine ausreichende durchschnittliche
# Dollar-Liquiditaet zeigt. 2 Mio. USD pro Stundenbar entsprechen grob einem
# zweistelligen Mio.-Tagesumsatz und halten sehr duenne Smallcaps fern.
BROAD_MIN_AVG_DOLLAR_VOLUME = 2_000_000.0
BOT_ORDER_REGISTRY_FILE = "bot_order_registry.json"

from universe_catalog import expand_stocks, expand_crypto
_base_stocks = EU_STOCKS + US_STOCKS + (UNDERDOG_STOCKS if UNDERDOGS_AKTIV else [])
STOCK_CATALOG_SYMBOLS = (expand_stocks(_base_stocks, TARGET_STOCK_UNIVERSE)
                         if BROAD_UNIVERSE_ENABLED else _base_stocks)
# 75 feste Kernwerte plus bis zu 25 ausschliesslich menschlich freigegebene
# dynamische Werte. Das Ziel/Maximum sind 100 aktive Aktien; der Katalog
# umfasst 250. Ein Favorit allein fuegt keine Aktie hinzu.
STOCK_FIXED_CORE_LIMIT = 75
STOCK_DYNAMIC_SLOTS = 25
STOCK_FIXED_CORE_SYMBOLS = list(STOCK_CATALOG_SYMBOLS[:STOCK_FIXED_CORE_LIMIT])
# Woechentliche KI-Research-Ideen koennen NIEMALS direkt hier schreiben. Nur
# nach zweistufiger menschlicher Telegram-Freigabe + bestandener deterministischer
# eToro-Aufnahmepruefung entsteht approved_universe.json. Diese Erweiterungen
# werden ausschliesslich beim Prozessstart angehaengt und danach normal erneut
# vom eToro-Adapter qualifiziert.
from approved_universe import merge_approved_stocks
STOCK_SYMBOLS = merge_approved_stocks(STOCK_FIXED_CORE_SYMBOLS)[:100]

# Forex standardmaessig aus: andere Eigenschaften als Aktien, und die
# Strategie wurde auf Aktienlogik entwickelt und getestet.
FOREX_PAIRS = []

CRYPTO_EXCHANGE = "OKX"
_crypto_catalog = (expand_crypto(_KRYPTO, CRYPTO_EXCHANGE, TARGET_CRYPTO_UNIVERSE)
                   if BROAD_UNIVERSE_ENABLED else [{"symbol": s} for s in _KRYPTO])
# Nur UI-/Diagnosekatalog. Die handelbare Liste entsteht autonom aus den
# tatsaechlich live gelisteten OKX-EEA-Paaren; eToro bekommt diese Werte nie.
CRYPTO_SYMBOLS = [
    {**row, "exchange": "OKX", "currency": "EUR",
     "inst_id": f"{str(row.get('symbol', '')).upper()}-EUR"}
    for row in _crypto_catalog
]

# ---------------------------------------------------------------------------
# Strategie
# ---------------------------------------------------------------------------
BAR_SIZE = "1 hour"
HISTORY_DURATION = "60 D"
SMA_FAST = 20
SMA_SLOW = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
ENTRY_MODE = "trend"
CROSS_LOOKBACK = 5
RSI_PULLBACK_LEVEL = 45
RSI_EXIT_OVERBOUGHT = 75
USE_ML_FILTER = False  # erst aktivieren, wenn Out-of-Sample klar besser
ML_CONFIRM_THRESHOLD = 0.52

# ---------------------------------------------------------------------------
# Risiko
# ---------------------------------------------------------------------------
RISK_PER_TRADE_PCT = 0.005
MAX_POSITION_PCT = 0.04
MAX_OPEN_POSITIONS = 8
MAX_DAILY_LOSS_PCT = 0.02
MAX_UNREALIZED_DAILY_LOSS_PCT = 0.03  # blockiert nur neue Kaeufe
STOP_LOSS_PCT = 0.025
TAKE_PROFIT_PCT = 0.05
USE_ATR_STOPS = True
ATR_STOP_MULTIPLIER = 2.2
ATR_TAKE_MULTIPLIER = 3.2
BACKTEST_POSITION_PCT = MAX_POSITION_PCT

# Crypto bekommt zusaetzlich eine harte Gesamtobergrenze.
MAX_CRYPTO_PORTFOLIO_PCT = 0.15
CRYPTO_MAX_POSITION_PCT = 0.03
CRYPTO_RISK_PER_TRADE_PCT = 0.003
CRYPTO_CLIENT_STOP = True
CRYPTO_LIVE_TRADING = False  # bewusst separat freischalten
CRYPTO_QUANTITY_STEP = 0.0001

# ---------------------------------------------------------------------------
# RISIKO-PROFIL-BOOTSTRAP
# ---------------------------------------------------------------------------
# Bis v6.0 wurde 'aktives_profil.txt' von GUI, Menue und Telegram geschrieben
# und angezeigt -- beim Prozessstart aber NIE angewandt. Nach jedem Neustart
# (und der Pi startet automatisch per systemd) galten wieder die Basiswerte
# oben. Beispiel KONSERVATIV: 8 statt 2 offene Positionen und 4 % statt 3 %
# je Position. Das Profil stand korrekt in der Anzeige und war trotzdem
# nicht aktiv.
#
# Der Bootstrap spiegelt bewusst das Muster von _lies_handelsmodus():
# lesen -> validieren -> anwenden -> Fehler sichtbar machen.
# Er steht hier und nicht in live_trader.py, damit ausnahmslos JEDER
# Einstiegspunkt (Trader, GUI, Backtest, Telegram, Berichte) dieselben Zahlen
# sieht. Das funktioniert, weil im gesamten Paket kein einziges
# 'from config import X' existiert -- alle 66 Module lesen ueber 'config.X',
# also wirkt setattr() prozessweit.
PROFILE_FILE_NAME = "aktives_profil.txt"
# Als Modul-Attribut wie in risk_profile_control.py -- so laesst sich der Pfad
# im Test umbiegen, ohne die echte Datei im Paketordner anzufassen.
PROFILE_FILE = __import__("pathlib").Path(__file__).resolve().parent / PROFILE_FILE_NAME
ACTIVE_PROFILE = "unbekannt"
PROFILE_SOURCE = "keine"
PROFILE_BOOTSTRAP_OK = False
PROFILE_BOOTSTRAP_ERROR = "Bootstrap nicht ausgefuehrt"


def _lies_profilname() -> tuple:
    """(name, quelle) -- Umgebungsvariable schlaegt Datei, Datei schlaegt Default."""
    env = str(os.getenv("RISK_PROFILE", "") or "").strip().lower()
    if env:
        return env, "env:RISK_PROFILE"
    datei = PROFILE_FILE
    if not datei.exists():
        return "", "keine Datei"
    return datei.read_text(encoding="utf-8").strip().lower(), str(datei.name)


def _profil_bootstrap() -> None:
    """Gespeichertes Profil laden, validieren und auf dieses Modul anwenden.

    Drei Ausgaenge, bewusst unterschiedlich behandelt:
      * gueltiger Name   -> Profil aktiv, OK=True
      * keine Datei      -> DEFAULT_PROFILE aktiv, OK=True (Erstinstallation)
      * unlesbar/unbekannt -> KONSERVATIV als Notbremse, OK=False.
        live_trader schaltet daraufhin auf PAUSIERT: keine neuen Kaeufe,
        Schutz- und Verkaufspfad laufen weiter.
    """
    global ACTIVE_PROFILE, PROFILE_SOURCE, PROFILE_BOOTSTRAP_OK
    global PROFILE_BOOTSTRAP_ERROR, BACKTEST_POSITION_PCT

    import sys as _sys

    import profiles as _profiles

    modul = _sys.modules[__name__]
    try:
        name, quelle = _lies_profilname()
    except Exception as exc:                     # Datei da, aber nicht lesbar
        _profiles.apply_profile(modul, "konservativ")
        PROFILE_SOURCE = PROFILE_FILE_NAME
        PROFILE_BOOTSTRAP_OK = False
        PROFILE_BOOTSTRAP_ERROR = f"{PROFILE_FILE_NAME} nicht lesbar: {exc}"
        BACKTEST_POSITION_PCT = MAX_POSITION_PCT
        return

    if not name and quelle == "keine Datei":
        # Erstinstallation: kein Fehler, aber die Quelle wird benannt.
        _profiles.apply_profile(modul, _profiles.DEFAULT_PROFILE)
        PROFILE_SOURCE = quelle
        PROFILE_BOOTSTRAP_OK = True
        PROFILE_BOOTSTRAP_ERROR = ""
        BACKTEST_POSITION_PCT = MAX_POSITION_PCT
        return

    if not name:
        # Datei ist da, aber leer -- typisch fuer einen abgebrochenen
        # Schreibvorgang (Stromausfall waehrend des Speicherns). Das ist ein
        # Beschaedigungssignal und wird wie ein unbekanntes Profil behandelt.
        _profiles.apply_profile(modul, "konservativ")
        PROFILE_SOURCE = quelle
        PROFILE_BOOTSTRAP_OK = False
        PROFILE_BOOTSTRAP_ERROR = (
            f"{quelle} ist vorhanden, aber leer -- vermutlich abgebrochener "
            "Schreibvorgang. KONSERVATIV als Notbremse gesetzt, "
            "neue Kaeufe gesperrt."
        )
        BACKTEST_POSITION_PCT = MAX_POSITION_PCT
        return

    try:
        _profiles.apply_profile(modul, name)
    except KeyError:
        # Unbekannter Name = beschaedigte oder manipulierte Datei.
        # Nicht raten, sondern engstellen und melden.
        _profiles.apply_profile(modul, "konservativ")
        PROFILE_SOURCE = quelle
        PROFILE_BOOTSTRAP_OK = False
        PROFILE_BOOTSTRAP_ERROR = (
            f"Unbekanntes Profil {name!r} in {quelle}. "
            f"Gueltig: {', '.join(_profiles.PROFILES)}. "
            "KONSERVATIV als Notbremse gesetzt, neue Kaeufe gesperrt."
        )
        BACKTEST_POSITION_PCT = MAX_POSITION_PCT
        return

    PROFILE_SOURCE = quelle
    PROFILE_BOOTSTRAP_OK = True
    PROFILE_BOOTSTRAP_ERROR = ""
    # BACKTEST_POSITION_PCT wurde oben aus dem Basiswert abgeleitet und muss
    # dem Profil folgen -- sonst rechnet der Backtest mit anderen Groessen
    # als der Live-Trader.
    BACKTEST_POSITION_PCT = MAX_POSITION_PCT


try:
    _profil_bootstrap()
except Exception as _profil_exc:                 # niemals den Import sprengen
    ACTIVE_PROFILE = "unbekannt"
    PROFILE_BOOTSTRAP_OK = False
    PROFILE_BOOTSTRAP_ERROR = f"Profil-Bootstrap fehlgeschlagen: {_profil_exc}"


def profil_klartext() -> str:
    """Eine Zeile mit den tatsaechlich wirksamen Zahlen -- fuer Start und Telegram."""
    return (
        f"Profil {str(ACTIVE_PROFILE).upper()} (Quelle: {PROFILE_SOURCE}) | "
        f"Risiko/Trade {RISK_PER_TRADE_PCT * 100:.2f} % | "
        f"max. Position {MAX_POSITION_PCT * 100:.1f} % | "
        f"max. offene Positionen {MAX_OPEN_POSITIONS} | "
        f"Tagesverlust {MAX_DAILY_LOSS_PCT * 100:.1f} % | "
        f"ATR {ATR_STOP_MULTIPLIER}/{ATR_TAKE_MULTIPLIER} | "
        f"Krypto gesamt max. {MAX_CRYPTO_PORTFOLIO_PCT * 100:.0f} %"
    )

# ---------------------------------------------------------------------------
# Kosten
# ---------------------------------------------------------------------------
COMMISSION_PER_SHARE = 0.005
COMMISSION_MINIMUM = 1.00
COMMISSION_MAX_PCT = 0.01
EU_COMMISSION_PCT = 0.0005
EU_COMMISSION_MINIMUM = 1.25
CRYPTO_COMMISSION_PCT = 0.0018
CRYPTO_COMMISSION_MINIMUM = 1.75
CRYPTO_COMMISSION_MAX_PCT = 0.01
# eToro ist die einzige Ausfuehrungsquelle. Die statischen Werte oben dienen
# nur Backtest/Offline-Schaetzungen. Ein echter Neueinstieg verwendet zwingend
# die eToro-What-if-Kostenabfrage und blockiert bei fehlender Kostenquelle.
# eToro: KEINE statischen Prozentgebuehren im Trading-Core. Vor jedem
# qualifizierten Kauf wird der offizielle konto-/instrumentbezogene
# /trading/info/(demo/)costs What-if-Endpunkt abgefragt und 5 Minuten gecacht.
# Faellt diese Kostenquelle aus, wird der neue eToro-Kauf standardmaessig
# blockiert; Sicherheitsverkaeufe bleiben davon unabhaengig.
SLIPPAGE_PCT = 0.0005
CRYPTO_SLIPPAGE_PCT = 0.0015

# ---------------------------------------------------------------------------
# Scanner / eToro pacing
# ---------------------------------------------------------------------------
# Das breite Universum wird in fairen Bloecken rotiert. KI-Aufmerksamkeit darf
# nur die Reihenfolge bereits qualifizierter Instrumente veraendern.
CYCLE_MINUTES = 5
INSTRUMENTS_PER_CYCLE = 24
INSTRUMENTS_PER_CYCLE_ETORO = 24
# Pi 5 ist fuer den Scanner schnell genug. Die API-Budgets werden deshalb
# NICHT erhoeht; Stabilitaet und Broker-Pacing haben Vorrang vor CPU-Auslastung.
PAUSE_BETWEEN_INSTRUMENTS = 1.0
MAX_DATA_RETRIES = 3
DATA_RETRY_DELAY_SECONDS = 1.0
BROKER_ACCOUNT_CACHE_SECONDS = 10
INSTRUMENT_COOLDOWN_MINUTES = 30

# Nur vollstaendige Stundenkerzen verwenden. Das verhindert Signale auf einer
# noch laufenden Kerze, die spaeter wieder verschwinden kann.
USE_COMPLETED_BAR_ONLY = True

# ---------------------------------------------------------------------------
# Broker-/Internet-Verbindungsueberwachung
# ---------------------------------------------------------------------------
# Bei einem globalen eToro-/Netzausfall pausiert der Bot alle neuen Broker-Aktionen
# und versucht automatisch die Wiederverbindung.
RECONNECT_INTERVAL_SECONDS = 30
BROKER_HEALTHCHECK_SECONDS = 30
CONNECTION_ALERT_COOLDOWN_MINUTES = 15
STARTUP_WAIT_FOR_CONNECTION = True
# 0 = unbegrenzt warten. Authentifizierungs-/Konfigurationsfehler bleiben fatal.
STARTUP_RECONNECT_MAX_MINUTES = 0
RECONNECT_RESYNC_RETRIES = 3
RECONNECT_RESYNC_DELAY_SECONDS = 2
PENDING_ORDER_META_TTL_SECONDS = 21600
# Unbekannte Broker-Order-ID nach verlorenem Submit niemals automatisch als BOT
# behandeln. Dieser kurze Zeitraum dient nur zur Kennzeichnung als AMBIGUOUS.
PENDING_ORDER_OWNERSHIP_MATCH_SECONDS = 600
NOTIFY_TRADE_DETAILS = True
NOTIFY_START_PORTFOLIO = True

# Trade-Meldungen werden seit v5.10.0 immer sofort persistent in die Telegram-
# Queue geschrieben. Der Schalter bleibt nur fuer alte lokale Einstellungen.
BUNDLE_TRADE_MESSAGES = False


# ---------------------------------------------------------------------------
# Logging / State
# ---------------------------------------------------------------------------
LOG_FILE = "trading_bot.log"
DECISION_JOURNAL_FILE = "decision_journal.jsonl"
DECISION_DB_FILE = "decision_history.sqlite"
LOG_LEVEL = "INFO"
# Pi: rotierende Datei statt unbegrenzt wachsendem Log. Das begrenzt
# Speicherverbrauch und vermeidet unnoetige SD-/SSD-Schreiblast.
LOG_ROTATE_MAX_BYTES = int(os.getenv("TRADINGBOT_LOG_ROTATE_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_ROTATE_BACKUPS = int(os.getenv("TRADINGBOT_LOG_ROTATE_BACKUPS", "5"))
LOG_TO_STDOUT = os.getenv("TRADINGBOT_LOG_TO_STDOUT", "1" if PI_MODE else "0").strip().lower() in {"1","true","yes","on"}

# Runtime-Telemetrie wird auf dem Pi gebuendelt. Kritische Zustandsdateien
# bleiben weiterhin synchron/dauerhaft; nur der reine GUI-Heartbeat wird
# weniger oft auf den Datentraeger geschrieben.
RUNTIME_HEARTBEAT_THREAD_SECONDS = float(os.getenv("TRADINGBOT_RUNTIME_HEARTBEAT_SECONDS", "15" if PI_MODE else "10"))
RUNTIME_STATUS_WRITE_SECONDS = float(os.getenv("TRADINGBOT_RUNTIME_WRITE_SECONDS", "60" if PI_MODE else "10"))
RUNTIME_STATUS_MAX_AGE_SECONDS = float(os.getenv("TRADINGBOT_RUNTIME_MAX_AGE_SECONDS", "150" if PI_MODE else "45"))
SYSTEMD_WATCHDOG_MAIN_STALE_SECONDS = float(os.getenv("TRADINGBOT_WATCHDOG_MAIN_STALE_SECONDS", "150"))
# Initiale Broker-/Universumsqualifizierung kann bei 350 Instrumenten legitimerweise
# mehrere Minuten dauern. Waehrend dieser klar markierten Startphase gilt daher
# ein groesseres Watchdog-Fenster; im normalen Betrieb bleibt die Erkennung scharf.
SYSTEMD_WATCHDOG_STARTUP_GRACE_SECONDS = float(os.getenv("TRADINGBOT_WATCHDOG_STARTUP_GRACE_SECONDS", "900"))
PI_MIN_FREE_DISK_MB = int(os.getenv("TRADINGBOT_PI_MIN_FREE_DISK_MB", "1024"))
PI_MIN_AVAILABLE_RAM_MB = int(os.getenv("TRADINGBOT_PI_MIN_AVAILABLE_RAM_MB", "500"))
MODEL_PATH = "ml_model.joblib"
STATE_FILE = "bot_state.json"
POSITION_STATE_FILE = "position_state.json"
# v8.1.5: Der Aktienkern und der eToro-Risikotopf lasen bis v8.1.4 zwei
# verschiedene Dateien. Die Topfdatei blieb dadurch dauerhaft leer und
# ihre Tagesverlustbremse konnte nie ausloesen. Beide lesen jetzt diese.
RISK_STATE_FILE = "risk_state_etoro.json"
FILL_TRACKER_FILE = "fill_progress.json"
STOCK_FILL_WAIT_SECONDS = 12

# Wie lange ein Positions-Eintrag bestehen bleibt, wenn eToro ihn nicht mehr
# meldet (Minuten). Karenz verhindert, dass ein frischer Fill geloescht wird,
# bevor er in der Positionsabfrage auftaucht.
POSITION_STALE_MINUTES = 30

# Notifications -- Telegram ist seit v5.6 der einzige Benachrichtigungs- und
# Fernsteuerungskanal. E-Mail und TextMeBot wurden bewusst vollstaendig aus
# dem aktiven System entfernt, damit genau ein Kanal maximal robust ist.
NOTIFY_TELEGRAM = os.getenv("NOTIFY_TELEGRAM", "").strip().lower() in {"1", "true", "yes", "on"}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
TELEGRAM_NOTIFICATION_MODE = os.getenv("TELEGRAM_NOTIFICATION_MODE", "ON").strip().upper()
TELEGRAM_CREDENTIALS_FILE = "telegram_credentials.json"
TELEGRAM_TIMEOUT_SECONDS = 20
TELEGRAM_MAX_MESSAGE_CHARS = 3900
TELEGRAM_CONTROL_ENABLED = True
TELEGRAM_CONTROL_POLL_SECONDS = 20
TELEGRAM_CONTROL_STATUS_FILE = "telegram_control_status.json"
TELEGRAM_CONTROL_ALERT_COOLDOWN_SECONDS = 600

TELEGRAM_RISK3_CONFIRM_TTL_SECONDS = 60  # RISK3-Einmal-Button; intern auf 15..300 s begrenzt
TELEGRAM_QUEUE_FILE = "telegram_queue.json"
TELEGRAM_MAX_QUEUE_ITEMS = 250
TELEGRAM_MIN_INTERVAL_SECONDS = 1.1
TELEGRAM_RETRY_DELAY_SECONDS = 5
TELEGRAM_QUEUE_POLL_SECONDS = 1.0
# Gleiche Nachricht innerhalb dieses Fensters wird nicht erneut zugestellt.
# Kein blockierendes sleep: sicherheitskritische Einzelmeldungen gehen sofort,
# nur identische Duplikate werden zusammengefuehrt.
TELEGRAM_DEDUP_WINDOW_SECONDS = 30.0
# Kurze Sammelphase: identische, nahezu gleichzeitig erzeugte Ereignisse
# werden in der persistenten Queue zusammengefuehrt, bevor eins davon rausgeht.
TELEGRAM_COALESCE_SECONDS = 30.0
TELEGRAM_CLAIM_TIMEOUT_SECONDS = 90.0
# v5.8: Zustellstau wird lokal erkannt. Kritische Meldungen duerfen nicht
# minutenlang unbemerkt in der Queue liegen bleiben.
TELEGRAM_STALL_CRITICAL_SECONDS = 120
TELEGRAM_STALL_ANY_SECONDS = 600
TELEGRAM_STALL_FAILURE_COUNT = 5
TELEGRAM_STALL_ALERT_COOLDOWN_SECONDS = 300
TELEGRAM_STALL_FLAG_FILE = "telegram_delivery_stalled.flag"

# Optional: Telegram-Setup speichert Token/Chat-ID lokal in der Credential-
# Ablage. Umgebungsvariablen haben Vorrang.
try:
    _tg = _load_credentials(TELEGRAM_CREDENTIALS_FILE, {})
    if not os.getenv("TELEGRAM_BOT_TOKEN") and _tg.get("bot_token"):
        TELEGRAM_BOT_TOKEN = str(_tg["bot_token"]).strip()
    if not os.getenv("TELEGRAM_CHAT_ID") and _tg.get("chat_id") not in (None, ""):
        TELEGRAM_CHAT_ID = str(_tg["chat_id"]).strip()
    if not os.getenv("TELEGRAM_ALLOWED_USER_ID") and _tg.get("user_id") not in (None, ""):
        TELEGRAM_ALLOWED_USER_ID = str(_tg["user_id"]).strip()
    if not os.getenv("TELEGRAM_NOTIFICATION_MODE"):
        TELEGRAM_NOTIFICATION_MODE = str(_tg.get("notification_mode") or "ON").upper()
    if not TELEGRAM_ALLOWED_USER_ID:
        # Bei privatem Bot-Chat entspricht die Chat-ID der Nutzer-ID. Dadurch
        # kann in Gruppen nicht versehentlich jedes Mitglied Freigaben klicken.
        TELEGRAM_ALLOWED_USER_ID = str(TELEGRAM_CHAT_ID or "").strip()
    if not os.getenv("NOTIFY_TELEGRAM"):
        NOTIFY_TELEGRAM = bool(_tg.get("enabled", True) and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
except Exception:
    __import__("logging").getLogger(__name__).debug("Best-effort-Ausnahme unterdrueckt", exc_info=True)

# ---------------------------------------------------------------------------
# TAGESBERICHT / DECISION ANALYTICS
# ---------------------------------------------------------------------------
# Lokale Zeit. Der Versand wird persistent markiert und bei einem temporaren
# Netzausfall in die Telegram-Queue gelegt.
DAILY_REPORT_ENABLED = True
DAILY_REPORT_HOUR = 18
DAILY_REPORT_MINUTE = 0
DAILY_REPORT_TIMEZONE = "Europe/Berlin"
DECISION_OUTCOME_MAX_PER_CYCLE = 6
NO_BUY_ALERT_ENABLED = True
NO_BUY_ALERT_CYCLES = 6
NO_BUY_ALERT_COOLDOWN_HOURS = 12

# Zustandsdatei fuer die Telegram-Fernsteuerung.
BOT_STATE_FILE = "bot_zustand.json"

# ---------------------------------------------------------------------------
# MULTI-SOURCE NEWS / RISIKOQUELLEN (v5.2)
# ---------------------------------------------------------------------------
# Kauf-/Verkaufsentscheidungen sollen nicht von einer einzelnen News-API
# abhaengen. Der Aggregator nutzt bis zu sechs Quellen und dedupliziert
# syndizierte Meldungen, bevor sie in News-/Event-Intelligence eingehen.
#
# Kostenlose Kernquellen: SEC EDGAR, Nasdaq Trading Halts, Yahoo/Google RSS sowie GDELT nur fuer die breite Marktlage
# (Filings/XBRL, kein API-Key; Kontakt-E-Mail fuer fairen User-Agent).
# Legacy-/Key-Provider bleiben optional, sind aber standardmaessig AUS, damit
# fehlende/abgelaufene Gratis-Kontingente nicht den Scanner stoeren.
_NEWS_LOCAL = _load_credentials("news_sources_credentials.json", {})

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", str(_NEWS_LOCAL.get("finnhub_api_key", ""))).strip()
FMP_API_KEY = os.getenv("FMP_API_KEY", str(_NEWS_LOCAL.get("fmp_api_key", ""))).strip()
SEC_USER_AGENT_EMAIL = os.getenv(
    "SEC_USER_AGENT_EMAIL",
    str(_NEWS_LOCAL.get("sec_contact_email", "") or ""),
).strip()
_NEWS_ENABLED = _NEWS_LOCAL.get("enabled", {}) if isinstance(_NEWS_LOCAL.get("enabled", {}), dict) else {}
NEWS_MULTI_SOURCE_ENABLED = True
# In 8.0 sind Finnhub, FMP und Alpha Vantage regulaere, einzeln schaltbare
# Anbieter. Die alte globale Sperre fuehrte zu "abgewaehlt" trotz aktivem
# Anbieter-Schalter.
NEWS_LEGACY_OPTIONAL_SOURCES_ENABLED = True
NEWS_SOURCE_ALPHA_VANTAGE_ENABLED = bool(_NEWS_ENABLED.get("alpha_vantage", False))
NEWS_SOURCE_FINNHUB_ENABLED = bool(_NEWS_ENABLED.get("finnhub", False))
NEWS_SOURCE_FMP_ENABLED = bool(_NEWS_ENABLED.get("fmp", False))

# FMP-NACHRICHTEN: im Gratistarif NICHT enthalten (v8.1.2)
# ---------------------------------------------------------------------------
# Geprueft am 24.08.2026 mit einem echten Free-Plan-Schluessel:
#   /stable/news/stock            -> HTTP 402 Payment Required
#   /stable/news/general-latest   -> HTTP 402 Payment Required
#   /stable/search-symbol         -> OK
#   /stable/quote                 -> OK
#   /stable/profile               -> OK (inkl. Sektor und isActivelyTrading)
#   /stable/historical-price-eod/full -> OK (rund 390 Tageskerzen)
# Die 250 Anfragen pro Tag des Gratistarifs sind ein MENGENlimit, kein
# Freischalten der News-Endpunkte. Deshalb laeuft FMP standardmaessig als
# Referenz- und Kursquelle; die Nachrichtenfaehigkeit bleibt aus, bis ein
# Tarif sie tatsaechlich enthaelt. Ein 402 wird als Tarifzustand angezeigt,
# nicht als Stoerung.
FMP_NEWS_ENABLED = False
FMP_DAILY_REQUEST_LIMIT = 250
NEWS_SOURCE_SEC_ENABLED = bool(_NEWS_ENABLED.get("sec_edgar", True))
NEWS_SOURCE_GDELT_ENABLED = bool(_NEWS_ENABLED.get("gdelt", True))
NEWS_FOCUSED_GDELT_ENABLED = False  # v5.6: GDELT nur noch Markt/Krise, nie Einzel-Ticker
NEWS_SOURCE_GDELT_CACHE_SECONDS = 600
NEWS_SOURCE_YAHOO_ENABLED = bool(_NEWS_ENABLED.get("yahoo_finance", True))
NEWS_SOURCE_GOOGLE_NEWS_ENABLED = bool(_NEWS_ENABLED.get("google_news", True))
NEWS_SOURCE_NASDAQ_HALTS_ENABLED = bool(_NEWS_ENABLED.get("nasdaq_halts", True))
NEWS_SOURCE_YAHOO_FINANCE_CACHE_SECONDS = 900
NEWS_SOURCE_GOOGLE_NEWS_CACHE_SECONDS = 900
NEWS_SOURCE_NASDAQ_HALTS_CACHE_SECONDS = 60
SEC_FUNDAMENTALS_CACHE_SECONDS = 21600
NEWS_SOURCE_TIMEOUT_SECONDS = 10
NEWS_SOURCE_MAX_PER_PROVIDER = 10
NEWS_MARKET_MAX_ARTICLES = 80
NEWS_SOURCE_STATUS_FILE = "news_source_status.json"
# Fehlerhafte Quellen werden nicht bei jedem Scan erneut bombardiert.
# Besonders Rate-Limits und temporäre Providerfehler bekommen eine Pause.
NEWS_SOURCE_FAILURE_BACKOFF_SECONDS = 600
NEWS_SOURCE_RATE_LIMIT_BACKOFF_SECONDS = 3600
NEWS_SOURCE_DAILY_LIMIT_BACKOFF_SECONDS = 21600
NEWS_SOURCE_MAX_BACKOFF_SECONDS = 3600
NEWS_SOURCE_HEALTH_TTL_MULTIPLIER = 3
# Gezielte Company-Abfragen sind teurer als ein gemeinsamer Marktfeed. Der Bot
# nutzt deshalb zuerst den gepoolten Multi-Source-Marktfeed und fragt gezielt
# nur relevante Werte nach. Alpha-Vantage-Company-News bleibt standardmaessig
# deaktiviert, weil derselbe Key auch Earnings/Fundamentaldaten versorgt.
NEWS_FOCUSED_ALPHA_VANTAGE_ENABLED = False  # 25/Tag-Budget nicht fuer News verbrauchen; Key bleibt fuer Earnings/Fundamentals
# Finnhub company-news ist im kostenlosen Tarif enthalten (60 Abrufe/Minute)
# und liefert saubere, tickergenaue Meldungen. Es war bisher fuer Einzelwerte
# abgeschaltet -- genau dort, wo es am nuetzlichsten ist.
NEWS_FOCUSED_FINNHUB_ENABLED = True
# FMP wird gezielt NUR fuer bereits relevante Werte/Positionen abgefragt.
# Der 30-Minuten-Cache und Provider-Backoff verhindern Request-Spam.
# FMP antwortet im kostenlosen Tarif auf die News-Endpunkte mit HTTP 402
# (Payment Required). Standardmaessig aus, damit nicht bei jedem Symbol ein
# Abruf ins Leere laeuft. Wer einen bezahlten Tarif hat, kann es einschalten.
NEWS_FOCUSED_FMP_ENABLED = False
NEWS_FOCUSED_SEC_ENABLED = True
NEWS_FOCUSED_NASDAQ_HALTS_ENABLED = True
NEWS_FOCUSED_YAHOO_ENABLED = True
NEWS_FOCUSED_GOOGLE_NEWS_ENABLED = True
NEWS_COMPANY_NAME_MATCH_ENABLED = True  # Firmenname -> Ticker via SEC-Liste
# Positive Event-Trades brauchen Quellenvielfalt. Earnings/Fundamentaldaten
# zaehlen in event_intelligence.py als zusaetzlicher unabhaengiger Beleg.
NEWS_MIN_DIVERSE_SOURCES_FOR_EVENT = 2
UNDERDOG_MIN_DIVERSE_SOURCES_FOR_EVENT = 2
NEWS_DIVERSITY_BONUS_PER_SOURCE = 2
NEWS_DIVERSITY_BONUS_CAP = 6
# Provider-spezifische Caches: kostenlose API-Kontingente schonen.
NEWS_SOURCE_ALPHA_VANTAGE_CACHE_SECONDS = 7200
NEWS_SOURCE_FINNHUB_CACHE_SECONDS = 1800
NEWS_SOURCE_FMP_CACHE_SECONDS = 1800
NEWS_SOURCE_SEC_EDGAR_CACHE_SECONDS = 1800

# ---------------------------------------------------------------------------
# NACHRICHTEN- UND KRISENFILTER
# ---------------------------------------------------------------------------
# Vor jedem Kauf und bei offenen Positionen werden aktuelle Meldungen
# geprueft. Bei ernsten Signalen wird nicht gekauft bzw. verkauft.
#
# EHRLICHE EINORDNUNG (Details im Kopf von news_filter.py):
# Das ist eine STICHWORTSUCHE, kein Textverstaendnis. Fehlalarme sind
# normal -- der Bot laesst dann einen vielleicht guten Kauf aus. Das ist
# der guenstigere Fehler. Uebersehene Krisen sind ebenso moeglich; der
# Filter ersetzt keine eigene Aufmerksamkeit.
#
# Datenquellen werden durch news_sources.py gebuendelt. Standardkern sind
# GDELT + SEC EDGAR; Key-/Legacy-Provider
# sind optional. Nicht eingerichtete Quellen werden uebersprungen; kritische
# Datenfehler fuehren weiterhin zum sicheren Auslassen.
NEWS_FILTER_ENABLED = True

# Punkteschwelle, ab der ein Kauf verhindert wird.
# Niedriger = vorsichtiger, aber mehr Fehlalarme.
NEWS_BLOCK_SCORE = 5
NEWS_BLOCK_SCORE_UNDERDOG = 3     # strenger: kleine Werte reagieren heftiger

# Bei offenen Positionen zusaetzlich verkaufen, wenn die Nachrichtenlage
# kippt (nicht nur Kaeufe blockieren).
NEWS_SELL_ON_CRISIS = True

# Wie weit zurueck geschaut wird und wie lange Ergebnisse
# zwischengespeichert werden (spart Abrufe).
NEWS_LOOKBACK_HOURS = 48
NEWS_CACHE_MINUTES = 5
NEWS_MAX_ARTICLES = 20

# Breite Marktlage: schlagen mehrere Indexwerte gleichzeitig an, werden
# gar keine neuen Positionen eroeffnet.
NEWS_MARKET_THRESHOLD = 8

# ---------------------------------------------------------------------------
# UNDERDOG-SCREENING
# ---------------------------------------------------------------------------
# Die 25 Underdog-Kandidaten werden NICHT einfach gehandelt. Vor dem Kauf
# muessen sie ein Kennzahlen-Screening bestehen (Verschuldung, Ertragslage,
# Handelsvolumen usw. -- siehe underdog_screening.py). Wer durchfaellt,
# wird nicht gekauft.
#
# Wie oft das Screening wiederholt wird (Stunden). Kennzahlen aendern sich
# nur mit Quartalszahlen, taeglich reicht daher voellig.
UNDERDOG_SCREENING_HOURS = 24

# ---------------------------------------------------------------------------
# v5.0 INTELLIGENCE / COST / EARNINGS
# ---------------------------------------------------------------------------
# Kosten und Netto-Edge
FALLBACK_SPREAD_STOCK_PCT = 0.0008       # 0,08 % liquide Standardwerte
FALLBACK_SPREAD_UNDERDOG_PCT = 0.0030    # 0,30 % kuratierte kleinere Werte
FALLBACK_SPREAD_BROAD_PCT = 0.0060       # 0,60 % unbekannte Broad-Werte (nur Schaetzung/Diagnose)
FALLBACK_SPREAD_CRYPTO_PCT = 0.0020      # 0,20 %
UNDERDOG_SLIPPAGE_FACTOR = 1.5
BROAD_SLIPPAGE_FACTOR = 1.5
EDGE_COST_MULTIPLIER = 1.5               # erwartete Bewegung muss Kosten klar uebersteigen
EDGE_SAFETY_MARGIN_PCT = 0.0015          # zusaetzlich 0,15 %-Punkte Puffer
# Plausible Bewegung statt Take-Profit faelschlich als Erwartung zu behandeln.
EDGE_ATR_MULTIPLIER = 1.35
EDGE_TARGET_REALIZATION_FALLBACK = 0.40
EDGE_ML_MAX_ATR_BONUS = 0.35
EDGE_RISK_OFF_FACTOR = 0.75
EDGE_RISK_ON_FACTOR = 1.05
EDGE_UNDERDOG_CONFIDENCE_FACTOR = 0.90
EDGE_MAX_PLAUSIBLE_MOVE_PCT = 0.12
MAX_SPREAD_STOCK_PCT = 0.0035            # 0,35 %
MAX_SPREAD_UNDERDOG_PCT = 0.0080         # 0,80 % kuratierte kleinere Werte
MAX_SPREAD_BROAD_PCT = 0.0080            # 0,80 % Broad: echter Quote wird zwingend geprueft
MAX_SPREAD_CRYPTO_PCT = 0.0060           # 0,60 %
MAX_QUOTE_AGE_SECONDS = 90
MARKET_QUOTE_CACHE_SECONDS = 10
MARKET_QUALITY_TIMEOUT_SECONDS = 8
REQUIRE_LIVE_QUOTE_FOR_ENTRY = False     # normale Aktien: alter, bewaehrter Default
REQUIRE_LIVE_QUOTE_FOR_BROAD_ENTRY = True # Broad: kein echter Bid/Ask = kein Kauf
REQUIRE_LIVE_CRYPTO_QUOTE_FOR_ENTRY = False

# Kostenbewusstes ML-Label
ML_COST_AWARE_LABELS = True
ML_REFERENCE_NOTIONAL = 5000.0
ML_LABEL_MIN_MOVE = 0.001
# Universums-Training statt nur der allerersten Aktie. 0 = alle 100 Aktien.
# Standard 30 haelt Laufzeit/Downloadmenge fuer normale PCs vernuenftig.
ML_TRAIN_SYMBOL_LIMIT = 30
# Das ML-Label
# standardmaessig mit dem TEUREREN der beiden Kostenmodelle trainiert. So wird
# ein Modell nicht nur deshalb positiv, weil es bei einem Broker billig waere.

# Event-/Earnings-Intelligence
EVENT_INTELLIGENCE_ENABLED = True
EVENT_DRIVEN_BUY_ENABLED = True
EVENT_BUY_SCORE = 78
EVENT_EXIT_SCORE = 20
EVENT_MIN_ACCEPTABLE_SCORE = 35
EVENT_NEGATIVE_BLOCK_SCORE = 12
EVENT_MIN_VOLUME_RATIO = 1.5
EVENT_MIN_LAST_BAR_RETURN_PCT = 0.30      # Prozent, nicht Dezimalzahl
EVENT_MAX_CHASE_MOVE_PCT = 0.12           # nicht blind >12 % hinterherlaufen
# Bei starken Event-Kandidaten wird fuer die Einstiegskontrolle zusaetzlich
# eine kurze 5-Minuten-Historie geladen. So reagiert Earnings-Momentum nicht
# erst auf die naechste Stundenkerze.
EVENT_FAST_CONFIRM_SCORE = 70
EVENT_CONFIRM_DURATION = "2 D"
EVENT_CONFIRM_BAR_SIZE = "5 mins"
# Frische News/Earnings werden fuer die Bestaetigung auf kurzen, ABGESCHLOSSENEN
# 5-Minuten-Kerzen geprueft. Normale Scannerwerte bleiben auf 1h.
EVENT_SHORT_CONFIRMATION_ENABLED = True
EVENT_CONFIRM_MAX_EXTRA_PER_CYCLE = 4
UNDERDOG_REQUIRE_POSITIVE_EVENT = True
UNDERDOG_MIN_EVENT_SCORE = 62

# Earnings: normale technische Neueinstiege kurz vor Zahlen vermeiden.
# Event-getriebene Einstiege NACH starken Zahlen bleiben moeglich.
EARNINGS_AVOID_HOURS_BEFORE = 24
EARNINGS_RECENT_DAYS = 3
EARNINGS_HISTORY_CACHE_HOURS = 12
EARNINGS_CALENDAR_CACHE_HOURS = 12
EARNINGS_STRONG_SCORE = 80
# AGGRESSIVE / NORMAL / DEFENSIVE: nur die Marktreaktions-Bestaetigung wird
# angepasst; fundamentale/News- und Kostenfilter bleiben immer aktiv.
EARNINGS_ENTRY_MODE = "NORMAL"
EARNINGS_POST_DRIFT_DAYS = 5

# News-Radar: ein Request pro Zyklus priorisiert Werte mit frischen wichtigen Meldungen.
NEWS_RADAR_ENABLED = True
NEWS_RADAR_POLL_SECONDS = 240
NEWS_RADAR_LOOKBACK_MINUTES = 20
NEWS_RADAR_MIN_SCORE = 8
NEWS_RADAR_MAX_PRIORITY = 4

# Marktregime
MARKET_REGIME_ENABLED = True
MARKET_REGIME_CACHE_MINUTES = 20
MARKET_RISK_OFF_SIZE_FACTOR = 0.50
MARKET_RISK_ON_SIZE_FACTOR = 1.00

# Portfolio-Klumpenrisiko
MAX_SECTOR_POSITIONS = 3
MAX_SECTOR_EXPOSURE_PCT = 0.25
# Zusaetzlicher Korrelationsschutz auf Basis der bereits im gleichen Zyklus
# geladenen Stundenhistorien offener Positionen.
CORRELATION_GUARD_ENABLED = True
MAX_POSITION_CORRELATION = 0.85
MAX_HIGHLY_CORRELATED_POSITIONS = 2
CORRELATION_LOOKBACK_BARS = 120

# Verlustserien / Cooldown
LOSS_STREAK_LIMIT = 4
LOSS_STREAK_COOLDOWN_MINUTES = 60
MAX_TRADES_PER_DAY = 20

# Kostenquoten-Schutz: wenn Handelskosten nach mehreren abgeschlossenen Trades
# einen zu grossen Anteil des positiven Brutto-P&L auffressen, werden neue
# Einstiege fuer den Rest des Tages blockiert. Bestehende Positionen/Exits
# bleiben davon unberuehrt.
COST_RATIO_GUARD_ENABLED = True
COST_RATIO_MAX_OF_GROSS_PROFIT = 0.30
COST_RATIO_MIN_TRADES = 5

# Time Stop: Positionen ohne Fortschritt nicht ewig halten.
TIME_STOP_ENABLED = True
TIME_STOP_HOURS = 72
TIME_STOP_MIN_RETURN_PCT = 0.005          # nach 72h wenigstens +0,5 % erwartet

# ---------------------------------------------------------------------------
# AUTOMATISCHE HINTERGRUND-AKTUALISIERUNGEN / WARTUNG
# ---------------------------------------------------------------------------
# News/Krisen und Underdogs werden im laufenden Trader automatisch aktualisiert.
# Walk-Forward und ML werden NICHT ungefragt produktiv geschaltet. Der Bot
# ueberwacht ihr Alter und erinnert; Walk-Forward kann optional automatisch laufen.
AUTO_MAINTENANCE_ENABLED = True
AUTO_MAINTENANCE_REMINDERS = True
AUTO_MAINTENANCE_CHECK_MINUTES = 15
AUTO_UNDERDOG_REFRESH = True
WALKFORWARD_MAX_AGE_DAYS = 7
ML_MODEL_MAX_AGE_DAYS = 30
AUTO_WALKFORWARD_RUN = False
AUTO_ML_CANDIDATE_TRAIN = False

# Optionaler Alpha-Vantage-Key fuer Earnings Calendar / EPS Surprise.
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
try:
    _av = _load_credentials("alpha_vantage_credentials.json", {})
    if not ALPHAVANTAGE_API_KEY:
        ALPHAVANTAGE_API_KEY = str(_av.get("api_key", "")).strip()
except Exception:
    __import__("logging").getLogger(__name__).debug("Best-effort-Ausnahme unterdrueckt", exc_info=True)

GLOBAL_CRISIS_HARD_BLOCK_SCORE = 22
# Optionale GUI-Overrides fuer v5.0 Intelligence.
try:
    import json as _json_intel
    from pathlib import Path as _Path_intel
    _intel_file=_Path_intel(__file__).parent/'intelligence_settings.json'
    if _intel_file.exists():
        _allowed={
            'EDGE_COST_MULTIPLIER','EDGE_SAFETY_MARGIN_PCT','MAX_SPREAD_STOCK_PCT','MAX_SPREAD_UNDERDOG_PCT',
            'EVENT_BUY_SCORE','UNDERDOG_MIN_EVENT_SCORE','GLOBAL_CRISIS_HARD_BLOCK_SCORE','MAX_SECTOR_POSITIONS',
            'MAX_SECTOR_EXPOSURE_PCT','LOSS_STREAK_LIMIT','LOSS_STREAK_COOLDOWN_MINUTES','TIME_STOP_HOURS',
            'TIME_STOP_MIN_RETURN_PCT','EARNINGS_AVOID_HOURS_BEFORE','MAX_TRADES_PER_DAY','MARKET_RISK_OFF_SIZE_FACTOR',
            'NEWS_CACHE_MINUTES','EVENT_DRIVEN_BUY_ENABLED','EVENT_SHORT_CONFIRMATION_ENABLED','REQUIRE_LIVE_QUOTE_FOR_ENTRY','REQUIRE_LIVE_CRYPTO_QUOTE_FOR_ENTRY',
            'UNDERDOG_REQUIRE_POSITIVE_EVENT','MARKET_REGIME_ENABLED','TIME_STOP_ENABLED','NEWS_RADAR_ENABLED',
            'NEWS_RADAR_POLL_SECONDS','NEWS_RADAR_LOOKBACK_MINUTES','NEWS_RADAR_MIN_SCORE','NEWS_RADAR_MAX_PRIORITY',
            'ML_TRAIN_SYMBOL_LIMIT','EDGE_ATR_MULTIPLIER','EDGE_TARGET_REALIZATION_FALLBACK',
            'EDGE_ML_MAX_ATR_BONUS','EDGE_RISK_OFF_FACTOR','EDGE_RISK_ON_FACTOR','EDGE_UNDERDOG_CONFIDENCE_FACTOR',
            'EDGE_MAX_PLAUSIBLE_MOVE_PCT','EVENT_FAST_CONFIRM_SCORE','CORRELATION_GUARD_ENABLED',
            'MAX_POSITION_CORRELATION','MAX_HIGHLY_CORRELATED_POSITIONS','CORRELATION_LOOKBACK_BARS',
            'COST_RATIO_GUARD_ENABLED','COST_RATIO_MAX_OF_GROSS_PROFIT','COST_RATIO_MIN_TRADES',
            'EARNINGS_ENTRY_MODE','EARNINGS_POST_DRIFT_DAYS','AUTO_MAINTENANCE_ENABLED','AUTO_MAINTENANCE_REMINDERS','AUTO_MAINTENANCE_CHECK_MINUTES','AUTO_UNDERDOG_REFRESH','WALKFORWARD_MAX_AGE_DAYS','ML_MODEL_MAX_AGE_DAYS','AUTO_WALKFORWARD_RUN','AUTO_ML_CANDIDATE_TRAIN'
        }
        for _k,_v in _json_intel.loads(_intel_file.read_text(encoding='utf-8')).items():
            if _k in _allowed:globals()[_k]=_v
except Exception:
    __import__("logging").getLogger(__name__).debug("Best-effort-Ausnahme unterdrueckt", exc_info=True)


# ---------------------------------------------------------------------------
# KI-AUFMERKSAMKEIT -- KEINE HANDELSENTSCHEIDUNGEN
# ---------------------------------------------------------------------------
# Die KI erhaelt ausschliesslich das bereits von eToro qualifizierte Universum
# und darf nur dessen Scan-Reihenfolge priorisieren. Ticker aus Web/News, die
# nicht in dieser erlaubten Liste stehen, werden technisch verworfen.
AI_SETTINGS_FILE = "openai_ai_settings.json"
AI_ATTENTION_ENABLED = False
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_ATTENTION_MODEL = "gpt-5.6-terra"
AI_ATTENTION_REASONING_EFFORT = "low"
AI_ATTENTION_WEB_SEARCH = True
AI_ATTENTION_SEARCH_CONTEXT_SIZE = "low"
AI_ATTENTION_MAX_CALLS_PER_DAY = 12
AI_ATTENTION_MAX_OUTPUT_TOKENS = 1800
AI_ATTENTION_TIMEOUT_SECONDS = 60
AI_ATTENTION_USAGE_FILE = "ai_attention_usage.json"
AI_ATTENTION_REFRESH_MINUTES = 30
AI_ATTENTION_MAX_PRIORITY = 48

# ---------------------------------------------------------------------------
# WOeCHENTLICHES KI-RESEARCH + HUMAN-IN-THE-LOOP (KEINE ORDERRECHTE)
# ---------------------------------------------------------------------------
AI_RESEARCH_ENABLED = False
AI_RESEARCH_MODEL = AI_ATTENTION_MODEL
AI_RESEARCH_REASONING_EFFORT = "medium"
AI_RESEARCH_SEARCH_CONTEXT_SIZE = "medium"
AI_RESEARCH_LOOKBACK_DAYS = 90
AI_RESEARCH_MIN_PROPOSALS = 5
AI_RESEARCH_MAX_PROPOSALS = 10
AI_RESEARCH_MAX_OUTPUT_TOKENS = 5000
AI_RESEARCH_TIMEOUT_SECONDS = 120
AI_RESEARCH_WEEKDAY = 0          # Montag; Ausfuehrung erst bei offenem US-Markt
AI_RESEARCH_HOUR_LOCAL = 11
WEEKLY_INTELLIGENCE_RETRY_HOURS = 6

# Technische Aufnahmepruefung nach dem ERSTEN menschlichen Klick. Sie erzeugt
# keine Order. Die finale Aufnahme braucht danach einen ZWEITEN Klick und wird
# erst nach dem naechsten Bot-Start aktiv.
UNIVERSE_APPROVAL_HISTORY_DURATION = "260 D"
UNIVERSE_APPROVAL_MIN_HISTORY_BARS = 190
UNIVERSE_APPROVAL_MIN_AVG_DOLLAR_VOLUME = 20_000_000.0
UNIVERSE_APPROVAL_MIN_MEDIAN_DOLLAR_VOLUME = 10_000_000.0
UNIVERSE_APPROVAL_MAX_SPREAD_PCT = 0.008
UNIVERSE_APPROVAL_COST_NOTIONAL = 3000.0
UNIVERSE_APPROVAL_MAX_ROUNDTRIP_COST_PCT = 0.015
UNIVERSE_REVIEW_MAX_PER_CYCLE = 1

# Strategy Analyst: Python/SQLite berechnet, KI interpretiert nur die
# aggregierten eigenen Daten. Keine Websuche, keine Schreibrechte an Filtern.
STRATEGY_ANALYST_ENABLED = True
STRATEGY_ANALYST_USE_AI = False
STRATEGY_ANALYST_MODEL = AI_ATTENTION_MODEL
STRATEGY_ANALYST_REASONING_EFFORT = "medium"
STRATEGY_ANALYST_LOOKBACK_DAYS = 90
STRATEGY_ANALYST_MAX_OUTPUT_TOKENS = 3500
STRATEGY_ANALYST_TIMEOUT_SECONDS = 90
STRATEGY_ANALYST_WEEKDAY = 6
STRATEGY_ANALYST_HOUR_LOCAL = 18

try:
    _aid = _load_credentials(AI_SETTINGS_FILE, {})
    if _aid:
        if not os.getenv("OPENAI_API_KEY") and _aid.get("api_key"):
            OPENAI_API_KEY = str(_aid.get("api_key", "")).strip()
        AI_ATTENTION_ENABLED = bool(_aid.get("enabled", AI_ATTENTION_ENABLED))
        AI_ATTENTION_MODEL = str(_aid.get("model", AI_ATTENTION_MODEL) or AI_ATTENTION_MODEL).strip()
        AI_ATTENTION_REASONING_EFFORT = str(_aid.get("reasoning_effort", AI_ATTENTION_REASONING_EFFORT) or AI_ATTENTION_REASONING_EFFORT).strip().lower()
        AI_ATTENTION_WEB_SEARCH = bool(_aid.get("web_search", AI_ATTENTION_WEB_SEARCH))
        AI_ATTENTION_MAX_CALLS_PER_DAY = int(_aid.get("max_calls_per_day", AI_ATTENTION_MAX_CALLS_PER_DAY))
        AI_ATTENTION_REFRESH_MINUTES = int(_aid.get("refresh_minutes", AI_ATTENTION_REFRESH_MINUTES))
        AI_ATTENTION_MAX_PRIORITY = int(_aid.get("max_priority", AI_ATTENTION_MAX_PRIORITY))
        # Bestehende v5.10-Einstellung migriert sicher: War die KI dort
        # aktiviert, sind Research und reine Strategy-Auslegung standardmaessig
        # ebenfalls aktiv; beide besitzen trotzdem keinerlei Orderrechte.
        AI_RESEARCH_ENABLED = bool(_aid.get("research_enabled", AI_RESEARCH_ENABLED))
        AI_RESEARCH_MODEL = str(_aid.get("research_model", AI_ATTENTION_MODEL) or AI_ATTENTION_MODEL).strip()
        STRATEGY_ANALYST_USE_AI = bool(_aid.get("strategy_analyst_ai", STRATEGY_ANALYST_USE_AI))
        STRATEGY_ANALYST_MODEL = str(_aid.get("strategy_model", AI_ATTENTION_MODEL) or AI_ATTENTION_MODEL).strip()
except Exception:
    AI_ATTENTION_ENABLED = False

try:
    import json as _nr_json
    from pathlib import Path as _nr_Path
    _nrp=_nr_Path(__file__).parent/"news_research_settings.json"
    if _nrp.exists():
        _nrd=_nr_json.loads(_nrp.read_text(encoding="utf-8"))
        SEC_USER_AGENT_EMAIL=str(_nrd.get("sec_user_agent_email",SEC_USER_AGENT_EMAIL) or "").strip()
        NEWS_SOURCE_GDELT_ENABLED=bool(_nrd.get("gdelt_enabled", NEWS_SOURCE_GDELT_ENABLED))
        NEWS_LEGACY_OPTIONAL_SOURCES_ENABLED=bool(_nrd.get("legacy_optional_sources_enabled", NEWS_LEGACY_OPTIONAL_SOURCES_ENABLED))
except Exception:
    __import__("logging").getLogger(__name__).debug("Best-effort-Ausnahme unterdrueckt", exc_info=True)

# ---------------------------------------------------------------------------
# NACHRICHTENQUELLEN: Fehlerbehandlung (verbessert in 6.0)
# ---------------------------------------------------------------------------
# HTTP 402/401 bedeuten "Tarif deckt das nicht ab" oder "Schluessel ungueltig".
# Das behebt sich nicht durch Warten. Statt es stuendlich erneut zu versuchen
# (Protokollrauschen, unnoetige Last), wird sehr lange pausiert und der Grund
# im Status ausgewiesen.
NEWS_SOURCE_PLAN_BACKOFF_SECONDS = 86400        # 24 Stunden

# GDELT ist in der kostenlosen Nutzung streng begrenzt und antwortet schnell
# mit 429. Eine kurze Pause fuehrt direkt in die naechste Sperre.
NEWS_SOURCE_GDELT_RATE_BACKOFF_SECONDS = 7200   # 2 Stunden

# Mindestabstand zwischen zwei GDELT-Abrufen, unabhaengig vom Cache.
NEWS_SOURCE_GDELT_MIN_INTERVAL_SECONDS = 900    # 15 Minuten


# ===========================================================================
# ===========================================================================
#  TRADINGBOT v8.1.1 NEXUS -- NEUE EINSTELLUNGEN
# ===========================================================================
# Alle Werte darueber bleiben unveraendert gueltig. Dieser Block ergaenzt
# ausschliesslich. Dadurch bleibt eine uebernommene v6-Konfiguration
# vollstaendig funktionsfaehig und der Nutzer muss nichts neu eintragen.
# ===========================================================================

VERSION_NEXUS = "9.0.4-NEXUS"

ETORO_RECONCILIATION_FILE = "etoro_reconciliation.json"
ETORO_PROTECTIVE_EXIT_MATCH_TOLERANCE_PCT = 0.002
CORE_VOLUME_20_FILE = "core_volume_20.json"
CORE_VOLUME_20_HISTORY_FILE = "core_volume_20_history.json"
CRYPTO_DYNAMIC_30_FILE = "crypto_dynamic_30.json"
CRYPTO_DYNAMIC_30_HISTORY_FILE = "crypto_dynamic_30_history.json"
CRYPTO_STRATEGY_MODE_FILE = "crypto_strategy_mode.json"
FREQTRADE_HISTORY_DURATION = "3 D"
CORE_VOLUME_20_MIN_COVERAGE_DAYS = 20
# Nur noch Kompatibilitaet fuer alte 8.3.1-Zustaende. In 9.0.1 ist der feste
# 20er-Kern statisch und DYNAMIC_30 wird rein deterministisch aus OKX-Daten
# gebildet; GPT veraendert weder Rang noch Mitgliedschaft.
CORE_VOLUME_20_GPT_REVIEW = False
CRYPTO_DYNAMIC_30_MIN_COVERAGE_DAYS = 20

# ---------------------------------------------------------------------------
# BROKER: ZWEI KONTEN GLEICHZEITIG
# ---------------------------------------------------------------------------
# BROKER (oben) bleibt der Aktienbroker. OKX kommt als eigener, getrennter
# Kryptobroker dazu. Beide laufen parallel und haben getrennte Zustaende.
ETORO_ENABLED = True
OKX_ENABLED = False               # wird durch okx_credentials.json aktiviert

OKX_BASE_URL = "https://eea.okx.com"
OKX_PRIMARY_QUOTE_CCY = "EUR"
OKX_QUOTE_CCY = OKX_PRIMARY_QUOTE_CCY  # Kompatibilitaet mit v7-Modulen
# OKX EEA stellt viele liquide Spot-Maerkte nur gegen USD bereit. USD ist
# deshalb eine vollwertige Handelsquote; beliebige Krypto-gegen-Krypto-Paare
# bleiben weiterhin ausgeschlossen.
OKX_ALLOWED_QUOTE_CCY = ("EUR", "USD", "USDC")
OKX_TIMEOUT_SECONDS = 15.0
# Eine Orderanfrage darf bei Netzstau nicht erst nach vielen Sekunden beim
# Matching ankommen. OKX verwirft sie nach dieser clientseitig gesetzten
# Frist; ein unklarer Transportzustand bleibt weiterhin fail-closed.
OKX_ORDER_REQUEST_EXPIRY_SECONDS = 12.0
OKX_MAX_CLOCK_DRIFT_SECONDS = 25.0
OKX_LIVE_ARM_MINUTES = 15

# Demo und Live sind ZWEI vollstaendig getrennte Schluesselsaetze. Ein
# Demo-Key funktioniert im Livekonto nicht und umgekehrt. Genau deshalb
# werden sie hier auch getrennt gehalten und niemals gegenseitig ersetzt.
OKX_DEMO_API_KEY = os.getenv("OKX_DEMO_API_KEY", "")
OKX_DEMO_API_SECRET = os.getenv("OKX_DEMO_API_SECRET", "")
OKX_DEMO_API_PASSPHRASE = os.getenv("OKX_DEMO_API_PASSPHRASE", "")
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_API_SECRET = os.getenv("OKX_API_SECRET", "")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE", "")

# Live-Krypto bleibt bewusst ein eigener Schalter. Er wird NICHT durch den
# globalen Handelsmodus mitgeschaltet: Aktien live zu handeln heisst nicht,
# dass auch Krypto live laufen soll.
OKX_LIVE_TRADING = False

# Eigene Risikogrenzen des OKX-Topfes. Fehlt ein Wert, gilt der globale
# Standard weiter oben in dieser Datei.
OKX_RISK_PER_TRADE_PCT = 0.003
OKX_MAX_POSITION_PCT = 0.05
OKX_MAX_OPEN_POSITIONS = 6
OKX_MAX_DAILY_LOSS_PCT = 0.025
OKX_MAX_TRADES_PER_DAY = 12
# Der Stop darf nie enger sitzen als die Handelskosten (v8.1.4).
#
# Am 25.08.2026 lag der Stop im Profil OFFENSIV 0,57-0,64 % unter dem
# Einstieg -- die Roundtrip-Kosten betragen 0,70 %. Zwei Positionen wurden
# nach 63 Sekunden ausgestoppt; ein Stop-Out war damit rechnerisch ein
# garantierter Verlust, egal wie gut die Kursidee war.
#
# Der ATR-Stop bleibt, wird aber auf diesen Mindestabstand angehoben:
#     Mindestabstand = Roundtrip-Kosten x CRYPTO_STOP_KOSTEN_FAKTOR
CRYPTO_STOP_KOSTEN_FAKTOR = 1.5

# Anlaufsperre nach dem Prozessstart (v8.1.4). Waehrend dieser Zeit finden
# KEINE neuen Einstiege statt. Verkaeufe, Stops, Schutzorders, Reconciliation
# und der Universumslauf laufen sofort -- eine bestehende Position darf nach
# einem Neustart keine Sekunde ungeschuetzt sein.
#
# Am 25.08.2026 kaufte der Bot 2,5 Sekunden nach dem Start, ohne dass der
# Kontostand je gegen das Positionsbuch abgeglichen war.
STARTUP_TRADING_GRACE_MINUTES = 15.0
# Aelter als das gilt ein Ticker als nicht mehr aktuell (Bedingung
# "Kursdaten aktuell" der Handelsbereitschaft).
CRYPTO_TICKER_MAX_AGE_SECONDS = 120

# --- GPT Second Opinion vor Kauforders (v8.1.4) --------------------------
# Reine Warn- und Dokumentationsschicht. Die KI loest keine Order aus, hebt
# keine Ablehnung auf und verzoegert nie einen Verkauf oder eine Schutzorder.
#
#   aus       kein zusaetzlicher Schritt, exakt der bisherige Ablauf
#   nur_live  nur vor echten LIVE-Kauforders
#   immer     auch im Demobetrieb -- so ist die Funktion ueberhaupt sichtbar
AI_SECOND_OPINION_MODE = "aus"
AI_SECOND_OPINION_TIMEOUT_SECONDS = 8.0
AI_SECOND_OPINION_DAILY_LIMIT = 40
AI_SECOND_OPINION_COOLDOWN_MINUTES = 15.0
AI_CRITICAL_HUMAN_GATE = True
# Historisch kompatible Werte fuer Wartedateien. Ab 8.3 kann "kritisch" wieder
# eine menschliche, zeitlich begrenzte Freigabe verlangen. Die KI selbst gibt
# nichts frei; vor einem Kauf laufen alle festen Pruefungen erneut.
AI_PENDING_EXPIRY_MINUTES = 15.0
AI_PENDING_MAX_DRIFT_PCT = 0.003

# Orderbuchtiefe (v8.1.4). Eine Marktorder darf den besten Briefkurs nicht um
# mehr als diesen Anteil verlassen; genutzt wird hoechstens CRYPTO_MAX_BOOK_SHARE
# der sichtbaren Tiefe. Ohne das bestellte der Bot am 25.08.2026 46,9 SOL,
# bekam 0,50 und OKX stornierte den Rest ueber die eigene 5-%-Regel.
CRYPTO_MAX_BOOK_IMPACT_PCT = 0.005
CRYPTO_MAX_BOOK_SHARE = 0.25

OKX_MIN_POSITION_VALUE = 15.0     # unter diesem Wert lohnt keine Order

# Anteil des freien Guthabens, der NICHT verplant wird. Er faengt Kursbewegung
# zwischen Berechnung und Ausfuehrung, Rundungsdifferenzen und unerwartete
# Kosten ab. Bis 8.1.2 stand dieser Wert nur als Standard im Code und war
# damit gar nicht einstellbar; die Gebuehr steckte zudem stillschweigend mit
# in der Reserve. Beides ist ab 8.1.3 getrennt und sichtbar.
OKX_CASH_RESERVE_PCT = 0.05

ETORO_RISK_PER_TRADE_PCT = RISK_PER_TRADE_PCT
ETORO_MAX_POSITION_PCT = MAX_POSITION_PCT
ETORO_MAX_OPEN_POSITIONS = MAX_OPEN_POSITIONS
ETORO_MAX_DAILY_LOSS_PCT = MAX_DAILY_LOSS_PCT
ETORO_MAX_TRADES_PER_DAY = MAX_TRADES_PER_DAY

# Optionale Klammer ueber beide Konten. Standardmaessig AUS, weil getrennte
# Toepfe der ausdruecklich gewuenschte Normalfall sind.
GLOBAL_RISK_GUARD_ENABLED = False
GLOBAL_MAX_DAILY_LOSS_PCT = 0.03

# ---------------------------------------------------------------------------
# TAKTUNG: KRYPTO 24/7, AKTIEN NUR BEI GEOEFFNETEM MARKT
# ---------------------------------------------------------------------------
# In v6 haben sich beide Anlageklassen eine Schleife geteilt, deren Takt am
# Boersenkalender hing. Ergebnis: am Wochenende lief fuer Krypto gar nichts.
# In NEXUS hat jede Klasse ihren eigenen Takt.
CRYPTO_BAR_SIZE = "15 mins"
CRYPTO_CONFIRM_BAR_SIZE = "5 mins"
CRYPTO_TREND_BAR_SIZE = "1 hour"
CRYPTO_HISTORY_DURATION = "3 D"
CRYPTO_SCAN_INTERVAL_SECONDS = 300          # 5 Minuten
CRYPTO_UNIVERSE_REFRESH_SECONDS = 900       # 15 Minuten
CRYPTO_POSITION_CHECK_SECONDS = 60          # Schutzueberwachung
CRYPTO_NEWS_INTERVAL_SECONDS = 900

STOCK_BAR_SIZE = "1 hour"
STOCK_HISTORY_DURATION = "60 D"
STOCK_SCAN_INTERVAL_SECONDS = 300
STOCK_UNIVERSE_REFRESH_SECONDS = 2700       # 45 Minuten
STOCK_POSITION_CHECK_SECONDS = 120
STOCK_NEWS_INTERVAL_SECONDS = 900

# ---------------------------------------------------------------------------
# DYNAMISCHES UNIVERSUM -- KRYPTO (autonom)
# ---------------------------------------------------------------------------
UNIVERSE_STATE_FILE = "universe_state.json"

# NEXUS 9.0.1: exakt 20 dauerhaft gesetzte Kernwerte plus hoechstens 30
# dynamische Werte. Der Kern wird nie durch Rang oder Monatsrotation entfernt.
# "Im Universum" bedeutet nur beobachten: ein Einstieg braucht weiterhin
# vollstaendige Kerzen, frische Bid/Ask-Daten, Kosten-, Risiko- und Ordertests.
CRYPTO_CORE_LIMIT = 20
CRYPTO_UNIVERSE_DYNAMIC_LIMIT = 30
CRYPTO_UNIVERSE_ACTIVE_LIMIT = 50           # gewuenschte Groesse
CRYPTO_UNIVERSE_FOCUS_LIMIT = 12            # bekommt teure Analyse
CRYPTO_UNIVERSE_PRESELECTION = 100          # Vorauswahl fuer Quality Ranking
CRYPTO_UNIVERSE_REMOVAL_RANK = 75           # Hysterese: rein ab 50, raus ab 75
CRYPTO_UNIVERSE_MIN_RESIDENCE_HOURS = 6.0
CRYPTO_UNIVERSE_REMOVAL_CONFIRMATIONS = 3
CRYPTO_UNIVERSE_PROBATION_HOURS = 24.0      # Bewaehrung neuer Coins
CRYPTO_UNIVERSE_FAVORITE_SLOTS = 5
CRYPTO_UNIVERSE_MAX_CHANGES_PER_RUN = 0      # Erstaufbau 20+30 in einem Lauf

# Aufnahmefilter fuer die BEOBACHTUNG. Sie sind absichtlich kryptogerechter
# als die alten aktienaehnlichen Grenzen. Die strengere Ausfuehrungsgrenze
# MAX_SPREAD_CRYPTO_PCT sowie Orderbuch-, Kosten- und Risikopruefungen bleiben
# vor jedem Kauf unveraendert verbindlich.
CRYPTO_UNIVERSE_MIN_AGE_DAYS = 30.0
CRYPTO_UNIVERSE_MIN_QUOTE_VOLUME = 250_000.0
CRYPTO_UNIVERSE_MAX_SPREAD_PCT = 0.012
CRYPTO_UNIVERSE_BLOCKLIST = ()

# Ab wann gilt ein Coin als etabliert und darf OHNE Bewaehrung direkt
# gehandelt werden?
CRYPTO_ESTABLISHED_MIN_AGE_DAYS = 365.0
CRYPTO_ESTABLISHED_MIN_QUOTE_VOLUME = 50_000_000.0
CRYPTO_ESTABLISHED_MAX_SPREAD_PCT = 0.0015

# Dauerhafter Krypto-Kern, recherchiert am 27.08.2026 aus grossen/liquiden,
# etablierten Basiswerten und der offiziellen OKX-EEA-Verfuegbarkeit. Die
# Mitgliedschaft ist fest; fehlt ein live EUR-/USD-/USDC-Spotpaar oder reisst ein
# aktueller Sicherheitsfilter, bleibt der Wert sichtbar, aber kaufgesperrt.
CRYPTO_CORE_SYMBOLS = (
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "TRX", "LINK", "AVAX", "LTC",
    "DOT", "ATOM", "XLM", "UNI", "AAVE", "BCH", "HBAR", "ICP", "ETC", "SUI",
)

# ---------------------------------------------------------------------------
# DYNAMISCHES UNIVERSUM -- AKTIEN (Vorschlag + Telegram-Freigabe)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# AKTIEN: FESTER KERN + DYNAMISCHER TEIL (ab 8.1.3)
# ---------------------------------------------------------------------------
# Kein "alles dynamisch": 75 feste Kernaktien sorgen dafuer, dass bewaehrte
# Werte immer beobachtet werden. Hoechstens 25 dynamische Plaetze kommen
# hinzu -- und die werden nur nach Telegram-Freigabe belegt.
#
# Kernwerte koennen NICHT wegen eines schlechten Rangs verschwinden. Ein
# harter Sicherheitsfilter (Delisting, nicht handelbar, extremer Spread)
# blockiert sie aber weiterhin fuer neue Einstiege.
STOCK_CORE_LIMIT = STOCK_FIXED_CORE_LIMIT
STOCK_UNIVERSE_DYNAMIC_LIMIT = STOCK_DYNAMIC_SLOTS
# EINE Quelle fuer den Aktienkern, nicht zwei.
#
# In der ersten Fassung von 8.1.3 stand hier eine eigene, handgeschriebene
# Tickerliste. Sie stimmte mit STOCK_FIXED_CORE_SYMBOLS -- dem Kern, den der
# Aktienkern tatsaechlich handelt -- nur zu zwei Dritteln ueberein: 29 der 75
# Werte standen gar nicht im Katalog. Folge waeren zwei sich widersprechende
# "Kerne" gewesen: einer, der gehandelt wird, und einer, der im Universum
# steht. Genau diese Art stiller Abweichung ist spaeter nicht mehr auffindbar.
#
# Der Kern ist deshalb ab jetzt per Definition der Anfang des Katalogs.
STOCK_CORE_SYMBOLS = tuple(
    str(eintrag.get("symbol") if isinstance(eintrag, dict) else eintrag).upper()
    for eintrag in STOCK_FIXED_CORE_SYMBOLS
)

STOCK_UNIVERSE_ACTIVE_LIMIT = 100
STOCK_UNIVERSE_FOCUS_LIMIT = 15
STOCK_UNIVERSE_PRESELECTION = 250
STOCK_UNIVERSE_REMOVAL_RANK = 150
STOCK_UNIVERSE_MIN_RESIDENCE_HOURS = 24.0
STOCK_UNIVERSE_REMOVAL_CONFIRMATIONS = 3
STOCK_UNIVERSE_FAVORITE_SLOTS = 5
STOCK_UNIVERSE_MAX_CHANGES_PER_RUN = 5
# v8.1.5: Aktien werden ohne Rueckfrage aufgenommen -- aber erst nach einer
# Bewaehrung. Vier Stunden, weil der Wert bereits ueber gute Kennzahlen in die
# Rangliste gekommen ist und 24 h zu spaet zum Einsteigen waeren. Bei einem
# Universumslauf alle 45 Minuten sind das rund fuenf Messungen; die
# Stabilitaetspruefung braucht mindestens drei. Wer diesen Wert senkt, muss
# STOCK_UNIVERSE_REFRESH_SECONDS mitsenken -- sonst gibt es zu wenig Messungen
# und es wird NIE freigegeben (die Pruefung faellt dann sicherheitshalber auf
# "noch nicht").
#
# Ohne Rueckfrage heisst nicht ohne Grenzen. Diese drei Deckel bleiben:
#   STOCK_CORE_LIMIT                    75 feste Kernwerte
#   STOCK_UNIVERSE_DYNAMIC_LIMIT        hoechstens 25 dynamische Plaetze
#   STOCK_UNIVERSE_MAX_CHANGES_PER_RUN  hoechstens 5 Wechsel je Lauf
# "Im Universum" heisst weiterhin nur: wird beobachtet. Ob gekauft wird,
# entscheidet danach allein die deterministische Kaufkaskade.
STOCK_UNIVERSE_PROBATION_HOURS = 4.0
STOCK_UNIVERSE_MIN_DOLLAR_VOLUME = 20_000_000.0
STOCK_UNIVERSE_MAX_SPREAD_PCT = 0.008
STOCK_UNIVERSE_BLOCKLIST = ()

# ---------------------------------------------------------------------------
# KI-ROUTER: LUNA (guenstig, haeufig) UND TERRA (stark, selten)
# ---------------------------------------------------------------------------
AI_ROUTER_ENABLED = bool(AI_ATTENTION_ENABLED)  # alte OpenAI-Einstellung bleibt wirksam
AI_LUNA_MODEL = "gpt-5.6-luna"
AI_TERRA_MODEL = "gpt-5.6-terra"
AI_LUNA_MAX_CALLS_PER_DAY = 40
AI_TERRA_MAX_CALLS_PER_DAY = 8
AI_MAX_COST_PER_DAY_USD = 0.50
AI_TERRA_FALLBACK_TO_LUNA = True
AI_ROUTER_TIMEOUT_SECONDS = 90
AI_ROUTER_USAGE_FILE = "ai_router_usage.json"
AI_WEB_SEARCH_ENABLED = False
AI_SEARCH_CONTEXT_SIZE = "low"

# Richtpreise je 1 Mio. Token. Sie dienen nur der Budgetschaetzung -- die
# Abrechnung macht OpenAI. Bei Preisaenderungen hier anpassen.
AI_LUNA_PRICE_INPUT_PER_M = 0.20
AI_LUNA_PRICE_OUTPUT_PER_M = 1.20
AI_TERRA_PRICE_INPUT_PER_M = 2.00
AI_TERRA_PRICE_OUTPUT_PER_M = 12.00

# ---------------------------------------------------------------------------
# NEUE DATENQUELLE: MASSIVE
# ---------------------------------------------------------------------------
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")
MASSIVE_ENABLED = False
MASSIVE_DAILY_REQUEST_LIMIT = 0             # 0 = kein eigenes Tageslimit

# ---------------------------------------------------------------------------
# ENTSCHEIDUNGSPROTOKOLL MIT QUELLENANGABE
# ---------------------------------------------------------------------------
DECISION_SOURCE_FILE = "decision_sources.jsonl"

# ---------------------------------------------------------------------------
# ZUGANGSDATEN AUS DEN JSON-DATEIEN LADEN
# ---------------------------------------------------------------------------
# Umgebungsvariablen behalten Vorrang -- so kann ein Systemdienst die
# Zugangsdaten setzen, ohne dass sie auf der Platte liegen.
try:
    _okx = _load_credentials("okx_credentials.json", {})
    if _okx:
        if not os.getenv("OKX_DEMO_API_KEY"):
            OKX_DEMO_API_KEY = str(_okx.get("demo_api_key", "") or "").strip()
            OKX_DEMO_API_SECRET = str(_okx.get("demo_api_secret", "") or "").strip()
            OKX_DEMO_API_PASSPHRASE = str(_okx.get("demo_passphrase", "") or "").strip()
        if not os.getenv("OKX_API_KEY"):
            OKX_API_KEY = str(_okx.get("live_api_key", "") or "").strip()
            OKX_API_SECRET = str(_okx.get("live_api_secret", "") or "").strip()
            OKX_API_PASSPHRASE = str(_okx.get("live_passphrase", "") or "").strip()
        OKX_LIVE_TRADING = bool(_okx.get("live_trading", OKX_LIVE_TRADING))
        OKX_QUOTE_CCY = str(_okx.get("quote_ccy", OKX_QUOTE_CCY) or OKX_QUOTE_CCY).upper()
        _quotes = _okx.get("allowed_quote_ccy", OKX_ALLOWED_QUOTE_CCY)
        if isinstance(_quotes, str):
            _quotes = [x.strip() for x in _quotes.split(",")]
        _quotes = tuple(dict.fromkeys(str(x).upper() for x in (_quotes or ())
                                      if str(x).upper() in {"EUR", "USD", "USDC"}))
        OKX_ALLOWED_QUOTE_CCY = _quotes or ("EUR", "USD", "USDC")
        if OKX_QUOTE_CCY not in OKX_ALLOWED_QUOTE_CCY:
            OKX_QUOTE_CCY = OKX_ALLOWED_QUOTE_CCY[0]
        OKX_ENABLED = bool(_okx.get("enabled", True))
except Exception:
    __import__("logging").getLogger(__name__).debug("OKX-Zugangsdaten nicht lesbar", exc_info=True)

# OKX wird nur aktiviert, wenn der zum Modus passende Schluesselsatz auch
# wirklich vollstaendig ist. Ein halb ausgefuelltes Formular darf den Bot
# nicht in einen Dauerfehlerzustand schicken.
_okx_satz = ((OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE) if OKX_LIVE_TRADING
             else (OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, OKX_DEMO_API_PASSPHRASE))
OKX_CREDENTIALS_COMPLETE = all(str(x or "").strip() for x in _okx_satz)
if OKX_ENABLED and not OKX_CREDENTIALS_COMPLETE:
    OKX_ENABLED = False
    OKX_SETUP_HINWEIS = ("OKX ist eingeschaltet, aber der "
                         f"{'Live' if OKX_LIVE_TRADING else 'Demo'}-Schluesselsatz ist "
                         "unvollstaendig (Key, Secret und Passphrase noetig).")
else:
    OKX_SETUP_HINWEIS = ""

try:
    _mass = _load_credentials("massive_credentials.json", {})
    if _mass:
        if not os.getenv("MASSIVE_API_KEY"):
            MASSIVE_API_KEY = str(_mass.get("api_key", "") or "").strip()
        MASSIVE_ENABLED = bool(_mass.get("enabled", bool(MASSIVE_API_KEY)))
        MASSIVE_DAILY_REQUEST_LIMIT = int(_mass.get("daily_limit", MASSIVE_DAILY_REQUEST_LIMIT) or 0)
except Exception:
    __import__("logging").getLogger(__name__).debug("MASSIVE-Zugangsdaten nicht lesbar", exc_info=True)
if MASSIVE_ENABLED and not MASSIVE_API_KEY:
    MASSIVE_ENABLED = False

try:
    import json as _u_json
    from pathlib import Path as _u_Path
    _up = _u_Path(__file__).parent / "universe_settings.json"
    if _up.exists():
        _erlaubt_universum = {
            "CRYPTO_UNIVERSE_ACTIVE_LIMIT", "CRYPTO_UNIVERSE_FOCUS_LIMIT",
            "CRYPTO_UNIVERSE_PRESELECTION", "CRYPTO_UNIVERSE_REMOVAL_RANK",
            "CRYPTO_UNIVERSE_MIN_RESIDENCE_HOURS", "CRYPTO_UNIVERSE_REMOVAL_CONFIRMATIONS",
            "CRYPTO_UNIVERSE_PROBATION_HOURS", "CRYPTO_UNIVERSE_FAVORITE_SLOTS",
            "CRYPTO_UNIVERSE_MAX_CHANGES_PER_RUN", "CRYPTO_UNIVERSE_MIN_AGE_DAYS",
            "CRYPTO_UNIVERSE_MIN_QUOTE_VOLUME", "CRYPTO_UNIVERSE_MAX_SPREAD_PCT",
            "CRYPTO_ESTABLISHED_MIN_AGE_DAYS", "CRYPTO_ESTABLISHED_MIN_QUOTE_VOLUME",
            "CRYPTO_ESTABLISHED_MAX_SPREAD_PCT",
            "STOCK_UNIVERSE_ACTIVE_LIMIT", "STOCK_UNIVERSE_FOCUS_LIMIT",
            "STOCK_UNIVERSE_PRESELECTION", "STOCK_UNIVERSE_REMOVAL_RANK",
            "STOCK_UNIVERSE_MIN_RESIDENCE_HOURS", "STOCK_UNIVERSE_REMOVAL_CONFIRMATIONS",
            "STOCK_UNIVERSE_FAVORITE_SLOTS", "STOCK_UNIVERSE_MAX_CHANGES_PER_RUN",
            # Der Krypto-Kern ist ab 9.0.1 absichtlich nicht mehr lokal
            # ueberschreibbar: 20 feste + 30 dynamische Werte ist die
            # freigegebene, getestete Struktur. Aktien bleiben konfigurierbar.
            "STOCK_CORE_LIMIT", "STOCK_UNIVERSE_DYNAMIC_LIMIT",
            "STOCK_UNIVERSE_MIN_DOLLAR_VOLUME", "STOCK_UNIVERSE_MAX_SPREAD_PCT",
            "CRYPTO_SCAN_INTERVAL_SECONDS", "CRYPTO_UNIVERSE_REFRESH_SECONDS",
            "CRYPTO_POSITION_CHECK_SECONDS", "CRYPTO_BAR_SIZE",
            "STOCK_SCAN_INTERVAL_SECONDS", "STOCK_UNIVERSE_REFRESH_SECONDS",
            "STOCK_POSITION_CHECK_SECONDS", "STOCK_BAR_SIZE",
        }
        for _k, _v in _u_json.loads(_up.read_text(encoding="utf-8")).items():
            if _k in _erlaubt_universum:
                globals()[_k] = _v
        _blockliste = _u_json.loads(_up.read_text(encoding="utf-8")).get("CRYPTO_UNIVERSE_BLOCKLIST")
        if isinstance(_blockliste, list):
            CRYPTO_UNIVERSE_BLOCKLIST = tuple(str(x).upper() for x in _blockliste)
        # Der Aktienkern ist ab v8.1.3 ebenfalls einstellbar. Eine leere Liste
        # wird bewusst ignoriert: sie wuerde das halbe Universum abschalten.
        _kern_aktien = _u_json.loads(_up.read_text(encoding="utf-8")).get("STOCK_CORE_SYMBOLS")
        if isinstance(_kern_aktien, list) and _kern_aktien:
            STOCK_CORE_SYMBOLS = tuple(str(x).upper() for x in _kern_aktien)
except Exception:
    __import__("logging").getLogger(__name__).debug("Universumseinstellungen nicht lesbar", exc_info=True)

try:
    import json as _ai_json
    from pathlib import Path as _ai_Path
    _aip = _ai_Path(__file__).parent / "ai_router_settings.json"
    if _aip.exists():
        _aid7 = _ai_json.loads(_aip.read_text(encoding="utf-8"))
        AI_ROUTER_ENABLED = bool(_aid7.get("enabled", AI_ROUTER_ENABLED))
        AI_LUNA_MODEL = str(_aid7.get("luna_model", AI_LUNA_MODEL) or AI_LUNA_MODEL).strip()
        AI_TERRA_MODEL = str(_aid7.get("terra_model", AI_TERRA_MODEL) or AI_TERRA_MODEL).strip()
        AI_LUNA_MAX_CALLS_PER_DAY = int(_aid7.get("luna_max_calls_per_day", AI_LUNA_MAX_CALLS_PER_DAY))
        AI_TERRA_MAX_CALLS_PER_DAY = int(_aid7.get("terra_max_calls_per_day", AI_TERRA_MAX_CALLS_PER_DAY))
        AI_MAX_COST_PER_DAY_USD = float(_aid7.get("max_cost_per_day_usd", AI_MAX_COST_PER_DAY_USD))
        AI_TERRA_FALLBACK_TO_LUNA = bool(_aid7.get("terra_fallback_to_luna", AI_TERRA_FALLBACK_TO_LUNA))
        AI_WEB_SEARCH_ENABLED = bool(_aid7.get("web_search", AI_WEB_SEARCH_ENABLED))
except Exception:
    __import__("logging").getLogger(__name__).debug("AI-Router-Einstellungen nicht lesbar", exc_info=True)
if AI_ROUTER_ENABLED and not OPENAI_API_KEY:
    AI_ROUTER_ENABLED = False


def _modellname_pruefen(wert, standard):
    """Verhindert, dass ein API-Schluessel als Modellname weiterlebt.

    Passiert schneller als man denkt: ein Eingabefeld verwechselt, und der
    Schluessel steht ab da in jeder Statusanzeige, jedem Protokoll und jedem
    Screenshot. Ein Modellname ist kurz und enthaelt nie 'sk-'.
    """
    text = str(wert or "").strip()
    if not text:
        return standard
    verdaechtig = ("sk-", "sk_live", "sk_test", "xoxb-", "ghp_", "AIza")
    if any(marker.lower() in text.lower() for marker in verdaechtig) or len(text) > 40:
        __import__("logging").getLogger(__name__).error(
            "Im Modellfeld steht ein Wert, der wie ein Zugangsschluessel aussieht. "
            "Er wird verworfen; es gilt %r. Bitte diesen Schluessel widerrufen und "
            "'nexus_setup.py' erneut ausfuehren.", standard)
        return standard
    return text


AI_LUNA_MODEL = _modellname_pruefen(AI_LUNA_MODEL, "gpt-5.6-luna")
AI_TERRA_MODEL = _modellname_pruefen(AI_TERRA_MODEL, "gpt-5.6-terra")
AI_ATTENTION_MODEL = _modellname_pruefen(AI_ATTENTION_MODEL, "gpt-5.6-terra")
AI_RESEARCH_MODEL = _modellname_pruefen(AI_RESEARCH_MODEL, AI_ATTENTION_MODEL)
STRATEGY_ANALYST_MODEL = _modellname_pruefen(STRATEGY_ANALYST_MODEL, AI_ATTENTION_MODEL)

# ---------------------------------------------------------------------------
# OKX-HANDELSGEBUEHREN
# ---------------------------------------------------------------------------
# OKX weist die Gebuehr getrennt aus (anders als eToro, wo sie im Spread
# steckt). Der Bot handelt mit Marktorders und ist damit praktisch immer
# Taker -- deshalb wird konservativ mit dem Taker-Satz gerechnet.
# GEMESSEN am 25.08.2026 auf dem echten Konto: 0,3500 % je Seite, beide
# Richtungen. Das entspricht der OKX-Tabelle "Normaler Nutzer, 0-100.000 EUR"
# (Maker 0,2000 %, Taker 0,3500 %).
#
# Die frueher hier stehenden 0,10 % sind der Tarif MIT eroeffnetem
# Derivate-Konto (X-Perps). Ohne eines gelten 0,35 %. Mit der zu niedrigen
# Annahme lag die Kostenhuerde bei 0,90 % statt bei 1,65 % -- ein Kauf vom
# 25.08. haette mit dem echten Satz gar nicht stattgefunden.
#
# Ab v8.1.4 fragt der Bot den Satz zusaetzlich bei OKX ab
# (/api/v5/account/trade-fee) und nutzt den gemessenen Wert. Dieser Eintrag
# ist nur noch der Rueckfallwert, wenn die Abfrage ausfaellt.
OKX_TAKER_FEE_PCT = 0.0035
OKX_MAKER_FEE_PCT = 0.0020

# Wie viele FMP-Anfragen darf EIN Universumslauf verbrauchen? Bei 250 pro Tag
# und rund 32 Laeufen bleibt so genug Reserve fuer Diagnose und Symbolsuche.
# Jedes Symbol kostet zwei Anfragen (Profil + Tageskerzen).
FMP_REQUESTS_PER_UNIVERSE_RUN = 20
