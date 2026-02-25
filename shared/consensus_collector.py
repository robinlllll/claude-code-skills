"""Daily Consensus Snapshot Collector.

Runs as scheduled task (e.g. 08:45 daily) to accumulate consensus history
for all portfolio tickers. Sends Telegram alert for CRITICAL/WARNING downgrades.

Usage:
    python consensus_collector.py                  # collect all portfolio tickers
    python consensus_collector.py --tickers GOOG AAPL  # specific tickers
    python consensus_collector.py --notify         # also send Telegram alerts
    python consensus_collector.py --dry-run        # show what would be collected
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SKILLS_DIR = str(Path(__file__).resolve().parent.parent)
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)

from shared.consensus_data import (
    get_consensus,
    save_snapshot,
    load_history,
    detect_changes,
    _notify_alerts,
    HISTORY_DIR,
)

PORTFOLIO_DB = Path.home() / "PORTFOLIO" / "portfolio_monitor" / "data" / "portfolio.db"
LOG_FILE = HISTORY_DIR / "_collector_log.jsonl"


def get_portfolio_tickers() -> list[str]:
    """Get US-listed stock tickers with open positions from portfolio DB."""
    if not PORTFOLIO_DB.exists():
        return []

    conn = sqlite3.connect(str(PORTFOLIO_DB))
    try:
        rows = conn.execute(
            """
            SELECT ticker,
                   SUM(CASE WHEN direction='BUY' THEN quantity
                            WHEN direction='SELL' THEN -quantity ELSE 0 END) as net
            FROM trades
            WHERE asset_type = 'STK'
              AND ticker NOT LIKE '%/%'
              AND LENGTH(ticker) <= 6
              AND ticker NOT GLOB '[0-9][0-9][0-9][0-9]'
              AND ticker NOT LIKE '%.T'
              AND ticker NOT LIKE '%.L'
            GROUP BY ticker
            HAVING net > 0
            ORDER BY ticker
            """
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def already_collected_today(ticker: str) -> bool:
    """Check if we already have a snapshot for this ticker today."""
    history = load_history(ticker)
    if not history:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return any(s.get("timestamp", "")[:10] == today for s in history)


def collect(
    tickers: list[str],
    notify: bool = False,
    dry_run: bool = False,
) -> dict:
    """Collect consensus snapshots for all tickers.

    Returns summary dict with counts and alerts.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    collected = []
    skipped = []
    errors = []
    all_alerts = []

    print(f"Consensus Collector — {today}")
    print(f"Tickers: {len(tickers)}")
    print()

    for ticker in tickers:
        if already_collected_today(ticker):
            skipped.append(ticker)
            continue

        if dry_run:
            print(f"  [DRY] {ticker}")
            collected.append(ticker)
            continue

        try:
            # Get current data
            data = get_consensus(ticker)
            eps = data.get("estimates", {}).get("eps", [])
            trend = data.get("eps_trend", [])

            # Skip if no meaningful data
            has_data = any(
                e.get("eps_avg") is not None and str(e.get("eps_avg")) != "nan"
                for e in eps
            )
            if not has_data and not trend:
                skipped.append(ticker)
                continue

            # Get previous snapshot for diff
            history = load_history(ticker)
            prev = None
            for snap in reversed(history):
                snap_date = snap.get("timestamp", "")[:10]
                if snap_date < today:
                    prev = snap
                    break

            # Save snapshot
            save_snapshot(data)
            collected.append(ticker)

            # Check for downgrades
            alert = detect_changes(data, prev)
            if alert["signals"]:
                all_alerts.append(alert)
                severity = alert["severity"]
                n_signals = len(alert["signals"])
                print(f"  [{severity}] {ticker} — {n_signals} change signals")
            else:
                print(f"  [OK] {ticker}")

        except Exception as e:
            errors.append(f"{ticker}: {e}")
            print(f"  [ERR] {ticker}: {e}")

    # Summary
    print(
        f"\nCollected: {len(collected)}, Skipped: {len(skipped)}, Errors: {len(errors)}"
    )

    if all_alerts:
        crit = sum(1 for a in all_alerts if a["severity"] == "CRITICAL")
        warn = sum(1 for a in all_alerts if a["severity"] == "WARNING")
        watch = sum(1 for a in all_alerts if a["severity"] == "WATCH")
        all_sigs = [s for a in all_alerts for s in a["signals"]]
        ups = sum(1 for s in all_sigs if s.get("direction") == "UP")
        downs = sum(1 for s in all_sigs if s.get("direction") == "DOWN")
        print(
            f"\nChanges: {len(all_sigs)} total ({ups} UP / {downs} DOWN) across {len(all_alerts)} tickers"
        )
        parts = []
        if crit:
            parts.append(f"{crit} CRITICAL")
        if warn:
            parts.append(f"{warn} WARNING")
        if watch:
            parts.append(f"{watch} WATCH")
        print(f"  Severity: {', '.join(parts)}")
        print()
        for alert in all_alerts:
            print(f"  [{alert['severity']}] {alert['ticker']}")
            for s in alert["signals"]:
                arrow = (
                    "UP"
                    if s.get("direction") == "UP"
                    else "DN"
                    if s.get("direction") == "DOWN"
                    else "  "
                )
                print(f"    {arrow} {s['detail']}")

        if notify and not dry_run:
            _notify_alerts(all_alerts)

    # Log this run
    if not dry_run:
        log_entry = {
            "date": today,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "collected": len(collected),
            "skipped": len(skipped),
            "errors": len(errors),
            "alerts_critical": sum(
                1 for a in all_alerts if a["severity"] == "CRITICAL"
            ),
            "alerts_warning": sum(1 for a in all_alerts if a["severity"] == "WARNING"),
        }
        from jsonl_utils import safe_jsonl_append

        safe_jsonl_append(LOG_FILE, log_entry)

    return {
        "date": today,
        "collected": collected,
        "skipped": skipped,
        "errors": errors,
        "alerts": all_alerts,
    }


def main():
    parser = argparse.ArgumentParser(description="Daily consensus snapshot collector")
    parser.add_argument(
        "--tickers", nargs="+", help="Specific tickers (default: portfolio)"
    )
    parser.add_argument(
        "--notify", action="store_true", help="Send Telegram alerts for downgrades"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be collected"
    )
    args = parser.parse_args()

    tickers = args.tickers or get_portfolio_tickers()
    if not tickers:
        print("No tickers to collect.")
        return

    collect(tickers, notify=args.notify, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
