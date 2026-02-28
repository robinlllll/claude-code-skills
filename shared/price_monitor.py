#!/usr/bin/env python3
"""
Price Movement Monitor Daemon.

Checks portfolio tickers twice per day (open 9:35 AM + close 4:05 PM ET).
Sends one Telegram alert per ticker when daily change >= 5%.
News attribution via Finnhub + Gemini Flash.

CLI:
    python price_monitor.py --daemon    # run continuously (twice daily)
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
    for t in raw_tickers:
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

ALERT_THRESHOLD_PCT = 5.0  # Daily change threshold

def check_triggers(prices: dict[str, dict]) -> list[dict]:
    """Return tickers where daily change >= 5%."""
    alerts = []
    for ticker, pdata in prices.items():
        price = pdata.get("price")
        change_pct = pdata.get("change_pct", 0.0)
        prev_close = pdata.get("prev_close")
        if price is None:
            continue
        if abs(change_pct) >= ALERT_THRESHOLD_PCT:
            alerts.append({
                "ticker": ticker,
                "price": price,
                "prev_close": prev_close,
                "change_pct": change_pct,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })
    return alerts


# ── News (Yahoo Finance) + Gemini attribution ───────────────────────────────

def _fetch_news(ticker: str) -> list[str]:
    """Fetch recent Yahoo Finance news headlines for a ticker."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        news = tk.news or []
        headlines = []
        for item in news[:5]:
            # yfinance >= 0.2.36: nested under item["content"]["title"]
            content = item.get("content", {})
            title = content.get("title", "") if isinstance(content, dict) else ""
            if not title:
                title = item.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        logger.debug(f"Yahoo news fetch failed for {ticker}: {e}")
        return []


def search_reason(ticker: str, change_pct: float) -> str:
    """
    Use Yahoo Finance news + Gemini Flash to generate a one-sentence
    explanation of why the stock is moving. Returns empty string if no news.
    """
    headlines = _fetch_news(ticker)
    direction = "上涨" if change_pct >= 0 else "下跌"

    if not headlines:
        return ""

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
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MODEL_GEMINI_FLASH,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini attribution failed for {ticker}: {e}")
        return "; ".join(headlines[:2])


# ── Alert sending ─────────────────────────────────────────────────────────────

def _build_telegram_message(alert: dict, reason: str, session: str = "") -> str:
    """Build a concise Telegram alert message."""
    ticker = alert["ticker"]
    price = alert["price"]
    prev_close = alert.get("prev_close")
    change_pct = alert["change_pct"]

    direction_emoji = "📈" if change_pct >= 0 else "📉"
    change_sign = "+" if change_pct >= 0 else ""

    msg_lines = [f"{direction_emoji} *{ticker}* {session} {change_sign}{change_pct:.1f}%"]

    if prev_close:
        msg_lines.append(f"${price:.2f} ← ${prev_close:.2f}")
    else:
        msg_lines.append(f"${price:.2f}")

    if reason:
        msg_lines.append(f"原因: {reason}")

    return "\n".join(msg_lines)


def log_alert(alert: dict, reason: str, session: str = "") -> None:
    """Append alert to JSONL log file."""
    from jsonl_utils import safe_jsonl_append

    record = {**alert, "reason": reason, "session": session, "logged_at": datetime.now(timezone.utc).isoformat()}
    try:
        safe_jsonl_append(PRICE_ALERTS_LOG, record)
    except Exception as e:
        logger.warning(f"Failed to write to JSONL log: {e}")


# ── Main run_once ─────────────────────────────────────────────────────────────

def run_once(session: str = "", dry_run: bool = False) -> list[dict]:
    """
    Single check cycle (open or close):
    1. Fetch portfolio tickers
    2. Fetch current prices
    3. Check 5% threshold
    4. Send one Telegram message per triggered ticker
    Returns list of alerts fired.
    """
    tickers = get_portfolio_tickers()
    if not tickers:
        logger.warning("No portfolio tickers found — skipping cycle")
        return []

    logger.info(f"[{session}] Checking {len(tickers)} tickers: {', '.join(tickers)}")

    # Fetch current prices
    try:
        prices = fetch_prices(tickers)
    except Exception as e:
        logger.error(f"fetch_prices failed: {e}")
        return []

    if not prices:
        logger.warning("No price data returned")
        return []

    # Check 5% threshold
    triggered = check_triggers(prices)
    alerts_sent = []

    if not triggered:
        logger.info(f"[{session}] No tickers above {ALERT_THRESHOLD_PCT}% threshold")
        return []

    logger.info(f"[{session}] {len(triggered)} ticker(s) above threshold")

    for alert in triggered:
        ticker = alert["ticker"]
        change_pct = alert["change_pct"]

        # Get Finnhub news + Gemini attribution
        try:
            reason = search_reason(ticker, change_pct)
        except Exception as e:
            logger.warning(f"search_reason failed for {ticker}: {e}")
            reason = ""

        msg = _build_telegram_message(alert, reason, session)

        if dry_run:
            logger.info(f"[DRY RUN] Would send:\n{msg}")
            alerts_sent.append(alert)
        else:
            logger.info(f"Sending: {msg[:100].replace(chr(10), ' ')}")
            sent = telegram_notify(msg)
            log_alert(alert, reason, session)
            if sent:
                alerts_sent.append(alert)
                logger.info(f"  Sent: {ticker} ({'+' if change_pct >= 0 else ''}{change_pct:.1f}%)")
            else:
                logger.warning(f"  Failed to send alert for {ticker}")

    logger.info(f"[{session}] Done: {len(alerts_sent)}/{len(triggered)} sent")
    return alerts_sent


# ── Daemon loop ───────────────────────────────────────────────────────────────

def _send_events_reminder() -> None:
    """
    Send Telegram reminders for today's portfolio events (earnings, meetings, conferences).
    Only sends for tickers in the portfolio. Also previews tomorrow's BMO earnings.
    """
    try:
        from shared.calendar_events import get_todays_events
    except ImportError:
        logger.debug("calendar_events not available")
        return

    portfolio = set(t.split(".")[0] for t in get_portfolio_tickers())
    if not portfolio:
        return

    events = get_todays_events()
    if not events:
        logger.info("No calendar events today")
        return

    # Filter to portfolio tickers only
    portfolio_events = [e for e in events if e.get("ticker") and e["ticker"] in portfolio]
    if not portfolio_events:
        logger.info(f"No portfolio events today ({len(events)} total events)")
        return

    earnings = [e for e in portfolio_events if e["is_earnings"]]
    meetings = [e for e in portfolio_events if e["is_investor_event"]]
    conferences = [e for e in portfolio_events if e["event_type"] in ("Conference", "Conference by Participant")]

    lines = ["📅 *今日持仓事件*"]

    if earnings:
        bmo = sorted(set(e["ticker"] for e in earnings if e["session"] == "BMO"))
        amc = sorted(set(e["ticker"] for e in earnings if e["session"] == "AMC"))
        other = sorted(set(e["ticker"] for e in earnings if e["session"] not in ("BMO", "AMC")))
        parts = []
        if bmo:
            parts.append(f"盘前: {', '.join(bmo)}")
        if amc:
            parts.append(f"盘后: {', '.join(amc)}")
        if other:
            parts.append(f"其他: {', '.join(other)}")
        lines.append(f"📊 *财报* — {' | '.join(parts)}")

    if meetings:
        for e in meetings:
            lines.append(f"🎤 *{e['ticker']}* — {e['event_type']}")

    if conferences:
        tickers = sorted(set(e["ticker"] for e in conferences))
        lines.append(f"📌 会议出席: {', '.join(tickers)}")

    if len(lines) == 1:
        return  # header only, no events

    # Also check tomorrow for BMO earnings (heads-up)
    tomorrow = datetime.now() + timedelta(days=1)
    try:
        tomorrow_events = get_todays_events(tomorrow)
        tomorrow_bmo = [
            e for e in tomorrow_events
            if e.get("ticker") and e["ticker"] in portfolio
            and e["is_earnings"] and e["session"] == "BMO"
        ]
        if tomorrow_bmo:
            tickers = sorted(set(e["ticker"] for e in tomorrow_bmo))
            lines.append(f"⏰ 明日盘前财报: {', '.join(tickers)}")
    except Exception:
        pass

    msg = "\n".join(lines)
    logger.info(f"Sending events reminder: {len(portfolio_events)} events")
    telegram_notify(msg)


def run_daemon() -> None:
    """
    Run the price monitor daemon.
    - 8:00 AM ET: portfolio events reminder (earnings, meetings)
    - 9:35 AM ET: open price check (>=5%)
    - 4:05 PM ET: close price check (>=5%)
    """
    logger.info("Price monitor daemon started (open/close mode)")
    logger.info(f"  Schedule: 8:00 AM (events) + 9:35 AM (open) + 4:05 PM (close) ET")
    logger.info(f"  Threshold: {ALERT_THRESHOLD_PCT}%")
    logger.info(f"  Alerts: one message per ticker")

    stop_file = DATA_DIR / "price_monitor.STOP"
    checks_done_today: set[str] = set()  # {"events", "open", "close"}
    last_date: str | None = None

    while True:
        # Kill switch
        if stop_file.exists():
            logger.info(f"STOP file detected ({stop_file}). Exiting daemon.")
            telegram_notify("🛑 Price monitor stopped")
            break

        now_et, _ = _get_et_now()
        if now_et is None:
            time.sleep(60)
            continue

        # Reset checks on new day
        today = now_et.strftime("%Y-%m-%d")
        if today != last_date:
            checks_done_today = set()
            last_date = today

        # Skip weekends
        if now_et.weekday() >= 5:
            time.sleep(3600)
            continue

        hour_min = now_et.hour * 60 + now_et.minute

        # Events reminder: after 8:00 AM ET — portfolio earnings/meetings today
        if hour_min >= 8 * 60 and "events" not in checks_done_today:
            logger.info("=== 事件提醒 ===")
            try:
                _send_events_reminder()
            except Exception as e:
                logger.error(f"Events reminder failed: {e}", exc_info=True)
            checks_done_today.add("events")

        # Open check: after 9:35 AM ET
        if hour_min >= 9 * 60 + 35 and "open" not in checks_done_today:
            logger.info("=== 开盘 check ===")
            try:
                run_once(session="开盘")
            except Exception as e:
                logger.error(f"Open check failed: {e}", exc_info=True)
            checks_done_today.add("open")

        # Close check: after 4:05 PM ET
        if hour_min >= 16 * 60 + 5 and "close" not in checks_done_today:
            logger.info("=== 收盘 check ===")
            try:
                run_once(session="收盘")
            except Exception as e:
                logger.error(f"Close check failed: {e}", exc_info=True)
            checks_done_today.add("close")

        # Calculate sleep until next check
        if "events" not in checks_done_today:
            target_min = 8 * 60
        elif "open" not in checks_done_today:
            target_min = 9 * 60 + 35
        elif "close" not in checks_done_today:
            target_min = 16 * 60 + 5
        else:
            # All done today — sleep until tomorrow
            logger.info("All checks done. Sleeping until next trading day.")
            time.sleep(3600)
            continue

        sleep_secs = max((target_min - hour_min) * 60, 60)
        sleep_secs = min(sleep_secs, 3600)
        logger.info(f"Next check in ~{sleep_secs // 60} min")
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
