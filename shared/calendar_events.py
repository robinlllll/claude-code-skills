#!/usr/bin/env python3
"""
Calendar Events Parser.

Parses EVENTS lists from ~/CALENDAR-CONVERTER/generate_calendar_*.py
to provide today's financial events (earnings, conferences, analyst days)
for use by the price monitor and morning brief.
"""

import re
import ast
from pathlib import Path
from datetime import datetime, timedelta

CALENDAR_DIR = Path.home() / "CALENDAR-CONVERTER"

# Event types that warrant extended-hours monitoring
EARNINGS_TYPES = {"Earnings Call", "Earnings Release", "Financial Release"}
INVESTOR_EVENT_TYPES = {"Analyst Meeting", "Special Situation", "Guidance Call"}

# Regex to extract ticker from title: "HD-US Earnings Call" → "HD"
# Also handles "HD-US", "MELI-US Earnings Call 833-821-3654 pwd: N/A"
_TICKER_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,9})-US\b")


def _extract_ticker(title: str) -> str | None:
    """Extract ticker from event title. Returns None if no ticker found."""
    m = _TICKER_RE.match(title.strip())
    return m.group(1) if m else None


def _parse_events_from_file(path: Path) -> list[tuple]:
    """
    Parse EVENTS list from a generate_calendar_*.py file.
    Returns list of (date_str, time_str, title, event_type) tuples.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    # Find the EVENTS = [...] block
    match = re.search(r"EVENTS\s*=\s*\[", text)
    if not match:
        return []

    # Find the matching closing bracket
    start = match.start()
    bracket_depth = 0
    end = start
    for i in range(match.end() - 1, len(text)):
        if text[i] == "[":
            bracket_depth += 1
        elif text[i] == "]":
            bracket_depth -= 1
            if bracket_depth == 0:
                end = i + 1
                break

    if end <= start:
        return []

    events_str = text[start:end]
    # Remove comments (lines starting with #)
    lines = []
    for line in events_str.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Remove inline comments
        if "#" in line:
            line = line[:line.index("#")]
        lines.append(line)
    events_str = "\n".join(lines)

    try:
        # Safe eval: extract just the list assignment
        # Parse "EVENTS = [...]"
        events_str = events_str.split("=", 1)[1].strip()
        events = ast.literal_eval(events_str)
        return events
    except Exception:
        return []


def get_todays_events(date: datetime | None = None) -> list[dict]:
    """
    Get all financial events for today (or specified date).

    Returns list of dicts:
        {
            "ticker": "HD",         # or None for conferences
            "title": "HD-US Earnings Call",
            "time_code": "06:00",   # or BEFORE_MARKET, AFTER_MARKET, etc.
            "event_type": "Earnings Call",
            "is_earnings": True,
            "is_investor_event": False,
            "session": "BMO",       # BMO / AMC / MARKET / ALL_DAY / None
        }
    """
    if date is None:
        date = datetime.now()
    target_date = date.strftime("%Y-%m-%d")

    # Scan all calendar scripts
    all_events = []
    for script in sorted(CALENDAR_DIR.glob("generate_calendar*.py")):
        all_events.extend(_parse_events_from_file(script))

    # Filter to today
    results = []
    for event in all_events:
        if len(event) != 4:
            continue
        date_str, time_code, title, event_type = event
        if date_str != target_date:
            continue

        ticker = _extract_ticker(title)
        is_earnings = event_type in EARNINGS_TYPES
        is_investor = event_type in INVESTOR_EVENT_TYPES

        # Determine session (BMO / AMC / MARKET)
        session = _classify_session(time_code)

        results.append({
            "ticker": ticker,
            "title": title,
            "time_code": time_code,
            "event_type": event_type,
            "is_earnings": is_earnings,
            "is_investor_event": is_investor,
            "session": session,
        })

    return results


def get_events_in_range(start: datetime | None = None, end: datetime | None = None) -> list[dict]:
    """
    Get all financial events within a date range (inclusive).

    Args:
        start: Start date (defaults to today)
        end: End date (defaults to start + 7 days)

    Returns list of dicts (same shape as get_todays_events() + "date" field).
    """
    if start is None:
        start = datetime.now()
    if end is None:
        end = start + timedelta(days=7)

    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Scan all calendar scripts
    all_events = []
    for script in sorted(CALENDAR_DIR.glob("generate_calendar*.py")):
        all_events.extend(_parse_events_from_file(script))

    # Filter to date range
    results = []
    for event in all_events:
        if len(event) != 4:
            continue
        date_str, time_code, title, event_type = event
        if not (start_str <= date_str <= end_str):
            continue

        ticker = _extract_ticker(title)
        is_earnings = event_type in EARNINGS_TYPES
        is_investor = event_type in INVESTOR_EVENT_TYPES
        session = _classify_session(time_code)

        results.append({
            "ticker": ticker,
            "title": title,
            "date": date_str,
            "time_code": time_code,
            "event_type": event_type,
            "is_earnings": is_earnings,
            "is_investor_event": is_investor,
            "session": session,
        })

    return results


def _classify_session(time_code: str) -> str | None:
    """Classify time code into trading session."""
    if time_code == "BEFORE_MARKET":
        return "BMO"
    if time_code == "AFTER_MARKET":
        return "AMC"
    if time_code == "ALL_DAY":
        return "ALL_DAY"
    if time_code == "UNSPECIFIED":
        return None

    # Parse HH:MM
    try:
        parts = time_code.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        t = hour * 60 + minute

        if t < 9 * 60 + 30:    # before 9:30
            return "BMO"
        elif t >= 16 * 60:      # 16:00 or later
            return "AMC"
        else:
            return "MARKET"
    except (ValueError, IndexError):
        return None


def get_earnings_tickers_today(date: datetime | None = None) -> dict[str, str]:
    """
    Get tickers with earnings today and their session.

    Returns {ticker: "BMO"|"AMC"|"MARKET"|None}
    Only includes unique tickers (deduped across Earnings Release + Earnings Call).
    """
    events = get_todays_events(date)
    result = {}
    for e in events:
        if e["is_earnings"] and e["ticker"]:
            ticker = e["ticker"]
            # Prefer the most specific session info
            if ticker not in result or (result[ticker] is None and e["session"]):
                result[ticker] = e["session"]
    return result


def get_investor_event_tickers_today(date: datetime | None = None) -> dict[str, str]:
    """
    Get tickers with investor events today (analyst days, special situations).

    Returns {ticker: event_type}
    """
    events = get_todays_events(date)
    result = {}
    for e in events:
        if e["is_investor_event"] and e["ticker"]:
            result[e["ticker"]] = e["event_type"]
    return result


def format_events_summary(events: list[dict]) -> str:
    """Format today's events as a compact summary string."""
    if not events:
        return ""

    earnings = [e for e in events if e["is_earnings"] and e["ticker"]]
    investor = [e for e in events if e["is_investor_event"] and e["ticker"]]
    conferences = [e for e in events if e["event_type"] in ("Conference", "Conference by Participant") and e["ticker"]]

    lines = []
    if earnings:
        # Group by session
        bmo = [e["ticker"] for e in earnings if e["session"] == "BMO"]
        amc = [e["ticker"] for e in earnings if e["session"] == "AMC"]
        other = [e["ticker"] for e in earnings if e["session"] not in ("BMO", "AMC")]

        # Deduplicate
        bmo = sorted(set(bmo))
        amc = sorted(set(amc))
        other = sorted(set(other))

        parts = []
        if bmo:
            parts.append(f"盘前: {', '.join(bmo)}")
        if amc:
            parts.append(f"盘后: {', '.join(amc)}")
        if other:
            parts.append(f"其他: {', '.join(other)}")
        lines.append(f"📊 财报 ({len(set(e['ticker'] for e in earnings))}): {' | '.join(parts)}")

    if investor:
        tickers = sorted(set(e["ticker"] for e in investor))
        lines.append(f"🎤 投资者活动: {', '.join(tickers)}")

    if conferences:
        tickers = sorted(set(e["ticker"] for e in conferences))
        lines.append(f"📌 会议出席: {', '.join(tickers)}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    events = get_todays_events()
    print(f"Today's events: {len(events)}")
    for e in events[:20]:
        print(f"  {e['time_code']:15s} {e['event_type']:25s} {e['ticker'] or '---':10s} {e['title'][:50]}")

    print()
    earnings = get_earnings_tickers_today()
    print(f"Earnings tickers: {earnings}")

    investor = get_investor_event_tickers_today()
    print(f"Investor events: {investor}")

    print()
    print(format_events_summary(events))
