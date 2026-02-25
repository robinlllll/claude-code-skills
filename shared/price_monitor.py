#!/usr/bin/env python3
"""
Price Movement Monitor Daemon.

Checks portfolio tickers every 10 minutes during US market hours.
Sends Telegram alerts when significant price moves are detected.
Calendar-aware: extends monitoring to pre/post market for earnings tickers.

CLI:
    python price_monitor.py --daemon    # run continuously
    python price_monitor.py --once      # single check and exit
    python price_monitor.py --status    # show current state
    python price_monitor.py --test      # test alert (dry run)
"""

import sys
import io
import os
import json
import time
import sqlite3
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import (
    PRICE_CHECK_INTERVAL_SECONDS,
    PRICE_INTRADAY_THRESHOLD_PCT,
    PRICE_RAPID_THRESHOLD_PCT,
    PRICE_VOLUME_THRESHOLD_RATIO,
    PRICE_DEDUP_WINDOW_HOURS,
    GEMINI_API_KEY,
    DATA_DIR,
    LOGS_DIR,
    MODEL_GEMINI_FLASH,
)
from shared.telegram_notify import notify as telegram_notify

# ── Paths ─────────────────────────────────────────────────────────────────────

PRICE_MONITOR_DB = DATA_DIR / "price_monitor.db"
PRICE_ALERTS_LOG = DATA_DIR / "price_alerts.jsonl"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

log_file = LOGS_DIR / "price_monitor.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("price_monitor")

# ── Tenacity retries ──────────────────────────────────────────────────────────

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
    _HAS_TENACITY = True
except ImportError:
    _HAS_TENACITY = False
    # Provide no-op decorator when tenacity not installed
    def retry(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator
    def stop_after_attempt(n): return None
    def wait_exponential(**kwargs): return None

# ── Database setup ────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a connection to the price monitor SQLite DB."""
    conn = sqlite3.connect(str(PRICE_MONITOR_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_dedup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            alerted_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monitor_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def purge_old_dedup(conn: sqlite3.Connection) -> None:
    """Remove dedup entries older than PRICE_DEDUP_WINDOW_HOURS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=PRICE_DEDUP_WINDOW_HOURS)).isoformat()
    conn.execute("DELETE FROM alert_dedup WHERE alerted_at < ?", (cutoff,))
    conn.commit()


def already_alerted(conn: sqlite3.Connection, ticker: str, direction: str) -> bool:
    """Return True if we have already alerted for this ticker+direction within the dedup window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=PRICE_DEDUP_WINDOW_HOURS)).isoformat()
    row = conn.execute(
        "SELECT 1 FROM alert_dedup WHERE ticker = ? AND direction = ? AND alerted_at >= ? LIMIT 1",
        (ticker, direction, cutoff),
    ).fetchone()
    return row is not None


def record_dedup(conn: sqlite3.Connection, ticker: str, direction: str) -> None:
    """Record that we sent an alert for this ticker+direction."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_dedup (ticker, direction, alerted_at) VALUES (?, ?, ?)",
        (ticker, direction, now),
    )
    conn.commit()


# ── State (last_prices, avg_volumes) in SQLite ────────────────────────────────

def save_state(conn: sqlite3.Connection, key: str, value: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO monitor_state (key, value) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    conn.commit()


def load_state(conn: sqlite3.Connection, key: str) -> dict:
    row = conn.execute("SELECT value FROM monitor_state WHERE key = ?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return {}
    return {}


# ── Market hours ──────────────────────────────────────────────────────────────

def _get_et_now():
    """Return current time in ET and the timezone object."""
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
    except ImportError:
        try:
            import pytz
            et = pytz.timezone("America/New_York")
        except ImportError:
            return None, None
    return datetime.now(et), et


def is_market_hours() -> bool:
    """Return True if current time is within NYSE trading hours (9:30-16:00 ET, weekdays)."""
    now, et = _get_et_now()
    if now is None:
        # Fallback: assume UTC-5
        now_utc = datetime.now(timezone.utc)
        now = now_utc - timedelta(hours=5)

    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def is_extended_hours(earnings_map: dict[str, str]) -> bool:
    """
    Return True if we should be checking prices in extended hours
    because portfolio tickers have earnings today.

    Extended windows:
    - BMO tickers: 4:00 AM - 9:30 AM ET (pre-market)
    - AMC tickers: 4:00 PM - 8:00 PM ET (post-market)
    - Investor events: same as AMC window (often release news after close)
    """
    if not earnings_map:
        return False

    now, et = _get_et_now()
    if now is None:
        return False
    if now.weekday() >= 5:
        return False

    hour_min = now.hour * 60 + now.minute

    has_bmo = any(s == "BMO" for s in earnings_map.values())
    has_amc = any(s in ("AMC", "INVESTOR") for s in earnings_map.values())

    # Pre-market window: 4:00 AM - 9:30 AM for BMO tickers
    if has_bmo and 4 * 60 <= hour_min < 9 * 60 + 30:
        return True

    # Post-market window: 4:00 PM - 8:00 PM for AMC tickers
    if has_amc and 16 * 60 <= hour_min < 20 * 60:
        return True

    return False


def get_extended_hours_tickers(earnings_map: dict[str, str]) -> list[str]:
    """Return which tickers should be checked right now in extended hours."""
    now, et = _get_et_now()
    if now is None:
        return []

    hour_min = now.hour * 60 + now.minute
    tickers = []

    for ticker, session in earnings_map.items():
        # Pre-market: check BMO tickers between 4 AM and 9:30 AM
        if session == "BMO" and 4 * 60 <= hour_min < 9 * 60 + 30:
            tickers.append(ticker)
        # Post-market: check AMC / INVESTOR tickers between 4 PM and 8 PM
        elif session in ("AMC", "INVESTOR") and 16 * 60 <= hour_min < 20 * 60:
            tickers.append(ticker)

    return tickers


def seconds_until_next_market_open() -> int:
    """Return seconds until next market open (9:30 ET next weekday)."""
    now, et = _get_et_now()
    if now is None:
        return 3600  # fallback: 1 hour

    candidate = now.replace(hour=9, minute=30, second=0, microsecond=0)

    # If it's before market open today and today is a weekday
    if candidate > now and now.weekday() < 5:
        delta = candidate - now
        return int(delta.total_seconds())

    # Advance to next weekday
    candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    candidate = candidate.replace(hour=9, minute=30, second=0, microsecond=0)
    delta = candidate - now
    return int(delta.total_seconds())


# ── Portfolio tickers ─────────────────────────────────────────────────────────

def get_portfolio_tickers() -> list[str]:
    """Get current portfolio tickers, normalized for yfinance."""
    from shared.config import normalize_ticker_for_yfinance

    raw_tickers = []
    try:
        from shared.morning_brief import _get_portfolio_tickers
        raw_tickers = _get_portfolio_tickers()
    except Exception as e:
        logger.warning(f"Could not import morning_brief._get_portfolio_tickers: {e}")

    # Fallback: scan thesis directories
    if not raw_tickers:
        from shared.config import VAULT_THESIS_DIR
        if VAULT_THESIS_DIR.exists():
            for d in VAULT_THESIS_DIR.iterdir():
                if d.is_dir() and (d / "thesis.md").exists():
                    raw_tickers.append(d.name.upper())

    # Normalize IBKR → yfinance format
    normalized = []
    for t in raw_tickers[:20]:
        yf_ticker = normalize_ticker_for_yfinance(t)
        if yf_ticker:
            normalized.append(yf_ticker)
    return normalized


# ── Price fetching ─────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def fetch_prices(tickers: list[str]) -> dict[str, dict]:
    """
    Fetch current prices for a list of tickers using yfinance.
    Returns {ticker: {price, prev_close, change_pct, volume}}.
    """
    if not tickers:
        return {}

    import yfinance as yf

    tickers_str = " ".join(tickers)
    data = yf.download(
        tickers_str,
        period="2d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
    )

    result = {}

    if len(tickers) == 1:
        ticker = tickers[0]
        try:
            closes = data["Close"].dropna()
            volumes = data["Volume"].dropna()
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
                current_price = float(closes.iloc[-1])
                change_pct = (current_price - prev_close) / prev_close * 100
                volume = float(volumes.iloc[-1]) if len(volumes) >= 1 else 0
                result[ticker] = {
                    "price": current_price,
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                    "volume": volume,
                }
            elif len(closes) == 1:
                # Only one day of data: no prev_close available
                result[ticker] = {
                    "price": float(closes.iloc[-1]),
                    "prev_close": None,
                    "change_pct": 0.0,
                    "volume": float(volumes.iloc[-1]) if len(volumes) >= 1 else 0,
                }
        except Exception as e:
            logger.debug(f"Could not parse price for {ticker}: {e}")
    else:
        for ticker in tickers:
            try:
                if ticker not in data.columns.get_level_values(0):
                    continue
                closes = data[ticker]["Close"].dropna()
                volumes = data[ticker]["Volume"].dropna()
                if len(closes) >= 2:
                    prev_close = float(closes.iloc[-2])
                    current_price = float(closes.iloc[-1])
                    change_pct = (current_price - prev_close) / prev_close * 100
                    volume = float(volumes.iloc[-1]) if len(volumes) >= 1 else 0
                    result[ticker] = {
                        "price": current_price,
                        "prev_close": prev_close,
                        "change_pct": change_pct,
                        "volume": volume,
                    }
                elif len(closes) == 1:
                    result[ticker] = {
                        "price": float(closes.iloc[-1]),
                        "prev_close": None,
                        "change_pct": 0.0,
                        "volume": float(volumes.iloc[-1]) if len(volumes) >= 1 else 0,
                    }
            except Exception as e:
                logger.debug(f"Could not parse price for {ticker}: {e}")

    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def fetch_avg_volume(tickers: list[str]) -> dict[str, float]:
    """
    Fetch 20-day average volume for a list of tickers.
    Returns {ticker: avg_volume_float}.
    """
    if not tickers:
        return {}

    import yfinance as yf

    tickers_str = " ".join(tickers)
    data = yf.download(
        tickers_str,
        period="1mo",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
    )

    result = {}

    if len(tickers) == 1:
        ticker = tickers[0]
        try:
            volumes = data["Volume"].dropna()
            if len(volumes) > 0:
                result[ticker] = float(volumes.tail(20).mean())
        except Exception as e:
            logger.debug(f"Could not fetch avg volume for {ticker}: {e}")
    else:
        for ticker in tickers:
            try:
                if ticker not in data.columns.get_level_values(0):
                    continue
                volumes = data[ticker]["Volume"].dropna()
                if len(volumes) > 0:
                    result[ticker] = float(volumes.tail(20).mean())
            except Exception as e:
                logger.debug(f"Could not fetch avg volume for {ticker}: {e}")

    return result


# ── Trigger checks ─────────────────────────────────────────────────────────────

def check_triggers(
    prices: dict[str, dict],
    avg_volumes: dict[str, float],
    last_prices: dict[str, float],
) -> list[dict]:
    """
    Check three trigger conditions for each ticker:
    1. Daily change > PRICE_INTRADAY_THRESHOLD_PCT (%)
    2. Rapid change since last check > PRICE_RAPID_THRESHOLD_PCT (%)
    3. Volume > PRICE_VOLUME_THRESHOLD_RATIO × 20-day avg

    Returns a list of alert dicts: {ticker, price, change_pct, rapid_pct, volume_ratio, triggers}
    """
    alerts = []

    for ticker, pdata in prices.items():
        price = pdata.get("price")
        change_pct = pdata.get("change_pct", 0.0)
        volume = pdata.get("volume", 0)
        avg_vol = avg_volumes.get(ticker, 0)

        if price is None:
            continue

        triggers = []
        rapid_pct = None

        # Trigger 1: Intraday daily change
        if abs(change_pct) >= PRICE_INTRADAY_THRESHOLD_PCT:
            triggers.append("intraday")

        # Trigger 2: Rapid change since last check
        if ticker in last_prices and last_prices[ticker] and last_prices[ticker] > 0:
            rapid_pct = (price - last_prices[ticker]) / last_prices[ticker] * 100
            if abs(rapid_pct) >= PRICE_RAPID_THRESHOLD_PCT:
                triggers.append("rapid")

        # Trigger 3: Volume spike
        volume_ratio = None
        if avg_vol and avg_vol > 0 and volume > 0:
            volume_ratio = volume / avg_vol
            if volume_ratio >= PRICE_VOLUME_THRESHOLD_RATIO:
                triggers.append("volume")

        if triggers:
            alerts.append({
                "ticker": ticker,
                "price": price,
                "change_pct": change_pct,
                "rapid_pct": rapid_pct,
                "volume": volume,
                "avg_volume": avg_vol,
                "volume_ratio": volume_ratio,
                "triggers": triggers,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })

    return alerts


# ── News + Gemini attribution ─────────────────────────────────────────────────

def _fetch_yahoo_news(ticker: str) -> list[str]:
    """Fetch recent Yahoo Finance news headlines for a ticker."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        news = tk.news or []
        headlines = []
        for item in news[:5]:
            title = item.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        logger.debug(f"Yahoo news fetch failed for {ticker}: {e}")
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def search_reason(ticker: str, change_pct: float) -> str:
    """
    Use Yahoo Finance news + Gemini Flash to generate a one-sentence
    explanation of why the stock is moving.
    """
    headlines = _fetch_yahoo_news(ticker)
    direction = "上涨" if change_pct >= 0 else "下跌"

    if not headlines:
        return f"{ticker} 暂无近期新闻"

    news_block = "\n".join(f"- {h}" for h in headlines)
    prompt = (
        f"股票 {ticker} 今日{direction} {abs(change_pct):.1f}%。"
        f"以下是近期新闻标题：\n{news_block}\n\n"
        f"请用一句话（不超过30字）概括最可能的原因。直接给出原因，不要解释。"
    )

    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, skipping attribution")
        return "; ".join(headlines[:2])

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(MODEL_GEMINI_FLASH)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        pass

    # Try new google.genai SDK
    try:
        from google import genai as new_genai
        client = new_genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MODEL_GEMINI_FLASH,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini attribution failed for {ticker}: {e}")
        return "; ".join(headlines[:2])


# ── Alert sending ─────────────────────────────────────────────────────────────

def _build_telegram_message(alert: dict, reason: str, event_context: dict | None = None) -> str:
    """Build the Telegram alert message. event_context from calendar if available."""
    ticker = alert["ticker"]
    price = alert["price"]
    change_pct = alert["change_pct"]
    volume_ratio = alert.get("volume_ratio")
    rapid_pct = alert.get("rapid_pct")
    triggers = alert.get("triggers", [])
    session_tag = alert.get("session_tag", "")  # e.g., "PRE-MARKET", "POST-MARKET"

    direction_emoji = "📈" if change_pct >= 0 else "📉"
    change_sign = "+" if change_pct >= 0 else ""

    header = f"{direction_emoji} *{ticker}* {change_sign}{change_pct:.1f}% (${price:.2f})"
    if session_tag:
        header += f" — {session_tag}"
    msg_lines = [header]

    # Event context line (earnings / investor day)
    if event_context:
        event_type = event_context.get("event_type", "")
        session = event_context.get("session", "")
        if "Earnings" in event_type:
            session_zh = {"BMO": "盘前", "AMC": "盘后"}.get(session, "")
            msg_lines.append(f"⚡ {session_zh}财报日")
        elif event_type in ("Analyst Meeting", "Special Situation", "Guidance Call"):
            msg_lines.append(f"🎤 {event_type}")

    # Triggers line
    trigger_parts = []
    if "intraday" in triggers:
        trigger_parts.append(f"日内 {change_sign}{change_pct:.1f}%")
    if "rapid" in triggers and rapid_pct is not None:
        rapid_sign = "+" if rapid_pct >= 0 else ""
        trigger_parts.append(f"急速 {rapid_sign}{rapid_pct:.1f}%")
    if "volume" in triggers and volume_ratio is not None:
        trigger_parts.append(f"量比 {volume_ratio:.1f}x")

    if trigger_parts:
        msg_lines.append(f"触发: {', '.join(trigger_parts)}")

    if volume_ratio is not None and "volume" not in triggers:
        msg_lines.append(f"量比: {volume_ratio:.1f}x")

    if reason:
        msg_lines.append(f"原因: {reason}")

    # Suggest next action for earnings
    if event_context and "Earnings" in event_context.get("event_type", ""):
        msg_lines.append(f"→ /organizer-transcript {ticker}")

    return "\n".join(msg_lines)


def log_alert(alert: dict, reason: str) -> None:
    """Append alert to JSONL log file."""
    from jsonl_utils import safe_jsonl_append

    record = {**alert, "reason": reason, "logged_at": datetime.now(timezone.utc).isoformat()}
    try:
        safe_jsonl_append(PRICE_ALERTS_LOG, record)
    except Exception as e:
        logger.warning(f"Failed to write to JSONL log: {e}")


def send_alert(alert: dict, reason: str) -> bool:
    """Send Telegram alert and log to JSONL. Returns True if sent."""
    msg = _build_telegram_message(alert, reason)
    logger.info(f"Sending alert: {msg[:120].replace(chr(10), ' ')}")
    sent = telegram_notify(msg)
    log_alert(alert, reason)
    return sent


# ── Main run_once ─────────────────────────────────────────────────────────────

def _load_calendar_context() -> tuple[dict[str, str], dict[str, dict]]:
    """
    Load today's calendar events. Returns:
    - earnings_map: {ticker: "BMO"|"AMC"|...} for tickers with earnings
    - event_lookup: {ticker: {event_type, session, ...}} for all event tickers
    """
    try:
        from shared.calendar_events import (
            get_earnings_tickers_today,
            get_investor_event_tickers_today,
            get_todays_events,
            format_events_summary,
        )
        earnings_map = get_earnings_tickers_today()
        investor_map = get_investor_event_tickers_today()

        # Merge investor events into earnings_map with "INVESTOR" session tag
        for ticker, etype in investor_map.items():
            if ticker not in earnings_map:
                earnings_map[ticker] = "INVESTOR"

        # Build lookup for enriched alerts
        event_lookup = {}
        for e in get_todays_events():
            t = e.get("ticker")
            if t and t not in event_lookup:
                event_lookup[t] = e

        if earnings_map:
            summary = format_events_summary(get_todays_events())
            if summary:
                logger.info(f"Calendar events today:\n{summary}")

        return earnings_map, event_lookup
    except Exception as e:
        logger.debug(f"Calendar events not available: {e}")
        return {}, {}


def run_once(dry_run: bool = False) -> list[dict]:
    """
    Single check cycle:
    1. Load calendar context (earnings, investor events)
    2. Fetch portfolio tickers
    3. Fetch current prices
    4. Load/save state (last_prices, avg_volumes)
    5. Check triggers
    6. Dedup + send alerts with event context
    Returns list of alerts fired.
    """
    conn = get_db()
    purge_old_dedup(conn)

    # Load calendar context
    earnings_map, event_lookup = _load_calendar_context()

    tickers = get_portfolio_tickers()
    if not tickers:
        logger.warning("No portfolio tickers found — skipping cycle")
        conn.close()
        return []

    logger.info(f"Checking {len(tickers)} tickers: {', '.join(tickers)}")

    # Load state
    last_prices: dict[str, float] = load_state(conn, "last_prices")
    avg_volumes: dict[str, float] = load_state(conn, "avg_volumes")

    # Fetch current prices
    try:
        prices = fetch_prices(tickers)
    except Exception as e:
        logger.error(f"fetch_prices failed: {e}")
        conn.close()
        return []

    if not prices:
        logger.warning("No price data returned")
        conn.close()
        return []

    # Refresh avg_volumes if empty or stale (once per session is fine)
    if not avg_volumes:
        try:
            avg_volumes = fetch_avg_volume(tickers)
            save_state(conn, "avg_volumes", avg_volumes)
        except Exception as e:
            logger.warning(f"fetch_avg_volume failed: {e}")
            avg_volumes = {}

    # Update last_prices for next cycle
    new_last_prices = {t: d["price"] for t, d in prices.items() if d.get("price") is not None}

    # Check triggers
    triggered = check_triggers(prices, avg_volumes, last_prices)
    alerts_sent = []

    for alert in triggered:
        ticker = alert["ticker"]
        change_pct = alert["change_pct"]
        direction = "up" if change_pct >= 0 else "down"

        if already_alerted(conn, ticker, direction):
            logger.info(f"  Dedup: {ticker} {direction} already alerted recently, skipping")
            continue

        # Look up calendar event context for this ticker
        # Match by raw ticker (yfinance format) — strip suffix for calendar lookup
        cal_ticker = ticker.split(".")[0] if "." in ticker else ticker
        event_ctx = event_lookup.get(cal_ticker)

        # Tag session if in extended hours
        if not is_market_hours() and cal_ticker in earnings_map:
            session = earnings_map[cal_ticker]
            alert["session_tag"] = {"BMO": "PRE-MARKET", "AMC": "POST-MARKET"}.get(session, "")

        # Get attribution
        try:
            reason = search_reason(ticker, change_pct)
        except Exception as e:
            logger.warning(f"search_reason failed for {ticker}: {e}")
            reason = ""

        if dry_run:
            msg = _build_telegram_message(alert, reason, event_ctx)
            logger.info(f"[DRY RUN] Would send:\n{msg}")
            alerts_sent.append(alert)
        else:
            msg = _build_telegram_message(alert, reason, event_ctx)
            logger.info(f"Sending alert: {msg[:120].replace(chr(10), ' ')}")
            sent = telegram_notify(msg)
            log_alert(alert, reason)
            if sent:
                record_dedup(conn, ticker, direction)
                alerts_sent.append(alert)
                logger.info(f"  Alert sent for {ticker} ({direction})")
            else:
                logger.warning(f"  Failed to send alert for {ticker}")

    # Save updated last_prices
    save_state(conn, "last_prices", new_last_prices)
    conn.close()

    logger.info(f"Cycle complete: {len(triggered)} triggered, {len(alerts_sent)} sent")
    return alerts_sent


# ── Daemon loop ───────────────────────────────────────────────────────────────

def run_daemon() -> None:
    """Run the price monitor daemon. Calendar-aware: extends to pre/post market for earnings."""
    logger.info("Price monitor daemon started (calendar-aware)")
    logger.info(f"  Interval: {PRICE_CHECK_INTERVAL_SECONDS}s ({PRICE_CHECK_INTERVAL_SECONDS // 60} min)")
    logger.info(f"  Intraday threshold: {PRICE_INTRADAY_THRESHOLD_PCT}%")
    logger.info(f"  Rapid threshold: {PRICE_RAPID_THRESHOLD_PCT}%")
    logger.info(f"  Volume ratio threshold: {PRICE_VOLUME_THRESHOLD_RATIO}x")
    logger.info(f"  Dedup window: {PRICE_DEDUP_WINDOW_HOURS}h")
    logger.info(f"  Extended hours: enabled (earnings/investor events from /calendar)")

    # Send daily events summary once per day
    _last_summary_date = None

    stop_file = DATA_DIR / "price_monitor.STOP"

    while True:
        # Kill switch: exit if STOP file exists
        if stop_file.exists():
            logger.info(f"STOP file detected ({stop_file}). Exiting daemon.")
            telegram_notify("🛑 Price monitor stopped (STOP file detected)")
            break

        # Load calendar context for extended hours check
        earnings_map = {}
        try:
            from shared.calendar_events import get_earnings_tickers_today, get_investor_event_tickers_today, format_events_summary, get_todays_events
            earnings_map = get_earnings_tickers_today()
            investor_map = get_investor_event_tickers_today()
            for ticker, etype in investor_map.items():
                if ticker not in earnings_map:
                    earnings_map[ticker] = "INVESTOR"

            # Send daily events summary via Telegram (once per day, at first check)
            today_str = datetime.now().strftime("%Y-%m-%d")
            if earnings_map and _last_summary_date != today_str:
                summary = format_events_summary(get_todays_events())
                if summary:
                    telegram_notify(f"📅 *今日财经日历*\n{summary}")
                    logger.info(f"Sent daily calendar summary ({len(earnings_map)} event tickers)")
                _last_summary_date = today_str
        except Exception as e:
            logger.debug(f"Calendar check failed: {e}")

        if is_market_hours():
            try:
                run_once()
            except Exception as e:
                logger.error(f"Unexpected error in run_once: {e}", exc_info=True)
            time.sleep(PRICE_CHECK_INTERVAL_SECONDS)
        elif is_extended_hours(earnings_map):
            # Extended hours: check only earnings/event tickers
            ext_tickers = get_extended_hours_tickers(earnings_map)
            logger.info(f"Extended hours check: {', '.join(ext_tickers)}")
            try:
                run_once()  # run_once will load calendar context itself
            except Exception as e:
                logger.error(f"Extended hours error: {e}", exc_info=True)
            time.sleep(PRICE_CHECK_INTERVAL_SECONDS)
        else:
            secs = seconds_until_next_market_open()
            # Check if we need to wake up earlier for BMO earnings
            early_wake = None
            if earnings_map and any(s == "BMO" for s in earnings_map.values()):
                # Wake up at 4 AM ET for BMO tickers
                now_et, _ = _get_et_now()
                if now_et and now_et.hour < 4:
                    wake_at = now_et.replace(hour=4, minute=0, second=0)
                    early_wake = int((wake_at - now_et).total_seconds())

            if early_wake and early_wake < secs:
                sleep_secs = min(early_wake, 3600)
                logger.info(
                    f"Market closed. BMO earnings today — waking at 4 AM ET "
                    f"(~{early_wake // 60} min). Sleeping {sleep_secs // 60} min."
                )
            else:
                sleep_secs = min(secs, 3600)
                logger.info(
                    f"Market closed. Next open in ~{secs // 60} min. "
                    f"Sleeping {sleep_secs // 60} min."
                )
            time.sleep(sleep_secs)


# ── Status display ─────────────────────────────────────────────────────────────

def show_status() -> None:
    """Print current monitor state to stdout."""
    conn = get_db()

    last_prices = load_state(conn, "last_prices")
    avg_volumes = load_state(conn, "avg_volumes")

    # Recent dedup entries
    rows = conn.execute(
        "SELECT ticker, direction, alerted_at FROM alert_dedup ORDER BY alerted_at DESC LIMIT 10"
    ).fetchall()

    conn.close()

    print("\n=== Price Monitor Status ===")
    print(f"Market hours: {is_market_hours()}")
    print(f"DB: {PRICE_MONITOR_DB}")
    print(f"Alert log: {PRICE_ALERTS_LOG}")
    print(f"\nTracked tickers ({len(last_prices)}): {', '.join(sorted(last_prices.keys()))}")
    print(f"Avg volume cache ({len(avg_volumes)} tickers)")

    print(f"\nRecent alerts (last {len(rows)}):")
    if rows:
        for r in rows:
            print(f"  {r['ticker']:10s} {r['direction']:5s}  {r['alerted_at'][:19]}")
    else:
        print("  (none)")

    # Count alerts from JSONL log today
    today = datetime.now(timezone.utc).date().isoformat()
    today_count = 0
    if PRICE_ALERTS_LOG.exists():
        with open(str(PRICE_ALERTS_LOG), encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("logged_at", "").startswith(today):
                        today_count += 1
                except json.JSONDecodeError:
                    pass
    print(f"\nAlerts sent today: {today_count}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Price movement monitor for portfolio tickers"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true", help="Run continuously as a daemon")
    group.add_argument("--once", action="store_true", help="Single check and exit")
    group.add_argument("--status", action="store_true", help="Show current state and exit")
    group.add_argument("--test", action="store_true", help="Dry-run single check (no Telegram)")

    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    elif args.once:
        alerts = run_once(dry_run=False)
        print(f"\n{len(alerts)} alert(s) sent.")
    elif args.status:
        show_status()
    elif args.test:
        print("=== DRY RUN (no Telegram messages will be sent) ===")
        alerts = run_once(dry_run=True)
        print(f"\n{len(alerts)} alert(s) would have been sent.")


if __name__ == "__main__":
    main()
