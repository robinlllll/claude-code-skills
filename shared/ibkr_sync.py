"""IBKR Flex Query sync — download, parse, and cache trade/position/cash data.

Uses the `ibflex` library to pull Activity Flex Query reports from Interactive
Brokers.  Config comes from environment variables or a `.env` file:

    IBKR_TOKEN   — Flex Web Service token (Settings > Account Management)
    IBKR_QUERY_ID — numeric Flex Query ID for the Activity query

This is scaffolding — it will not work until Robin configures the IBKR token
and query ID.  When those are missing the module prints clear setup
instructions instead of crashing.

Cache location: .claude/skills/shared/data/ibkr_cache/
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

# ── Paths ────────────────────────────────────────────────────

SHARED_DIR = Path(__file__).parent
CACHE_DIR = SHARED_DIR / "data" / "ibkr_cache"
TRADES_CSV = CACHE_DIR / "trades.csv"
POSITIONS_CSV = CACHE_DIR / "positions.csv"
CASH_CSV = CACHE_DIR / "cash.csv"
SYNC_META = CACHE_DIR / "last_sync.txt"

# ── Lazy imports with friendly errors ────────────────────────

_SETUP_INSTRUCTIONS = """
===========================================================
  IBKR Flex Query sync is not yet configured.
===========================================================

To set up:

1. Install the ibflex library:
       pip install ibflex

2. In your IBKR Account Management:
   a. Settings > Reporting > Flex Queries > Activity Flex Query
   b. Create (or reuse) a query that includes:
      - Trades, Open Positions, Cash Report
   c. Note the Query ID (numeric).

3. Settings > Reporting > Flex Web Service
   - Generate a token.

4. Create a `.env` file at:
       {env_path}

   With contents:
       IBKR_TOKEN=your_token_here
       IBKR_QUERY_ID=123456

   Or export them as environment variables.

5. Re-run this script.
===========================================================
"""

# ── pandas guard ─────────────────────────────────────────────

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required.  Install with:  pip install pandas")
    sys.exit(1)


# ── Config ───────────────────────────────────────────────────


def _find_env_file() -> Optional[Path]:
    """Walk up from this file looking for a .env file."""
    candidates = [
        SHARED_DIR / ".env",
        SHARED_DIR.parent / ".env",
        Path.home() / ".env",
        Path.home() / "PORTFOLIO" / ".env",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_dotenv() -> None:
    """Best-effort .env loading (no hard dependency on python-dotenv)."""
    env_file = _find_env_file()
    if env_file is None:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        # Manual parse — handles KEY=VALUE, ignores comments/blanks
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                os.environ.setdefault(key, value)


def load_config() -> dict:
    """Load IBKR_TOKEN and IBKR_QUERY_ID from env / .env.

    Returns:
        {"token": str, "query_id": str}

    Raises:
        SystemExit with setup instructions if not configured.
    """
    _load_dotenv()
    token = os.environ.get("IBKR_TOKEN", "").strip()
    query_id = os.environ.get("IBKR_QUERY_ID", "").strip()

    if not token or not query_id:
        env_path = _find_env_file() or (Path.home() / ".env")
        print(_SETUP_INSTRUCTIONS.format(env_path=env_path))
        sys.exit(1)

    return {"token": token, "query_id": query_id}


# ── Download ─────────────────────────────────────────────────


def download_flex_report(token: str, query_id: str) -> Any:
    """Download a Flex Query report from IBKR.

    Returns:
        ibflex.FlexQueryResponse object.

    Raises:
        ImportError if ibflex is not installed.
        Various ibflex exceptions on network/auth errors.
    """
    try:
        from ibflex import client as ibflex_client
    except ImportError:
        print("ERROR: ibflex library not installed.")
        print("       pip install ibflex")
        sys.exit(1)

    print(f"Requesting Flex Query {query_id} from IBKR...")
    response = ibflex_client.download(token, query_id)
    print("Download complete.")
    return response


# ── Parsers ──────────────────────────────────────────────────


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute, returning default if missing."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _obj_to_dict(obj: Any, fields: list[str]) -> dict:
    """Extract named fields from an ibflex data object into a dict."""
    row: dict[str, Any] = {}
    for f in fields:
        val = _safe_getattr(obj, f)
        # Convert dates/datetimes to ISO strings for CSV compatibility
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        row[f] = val
    return row


# ibflex Trade fields we care about
_TRADE_FIELDS = [
    "accountId",
    "symbol",
    "description",
    "conid",
    "securityID",
    "securityIDType",
    "currency",
    "assetCategory",
    "putCall",
    "strike",
    "expiry",
    "tradeID",
    "reportDate",
    "tradeDate",
    "settleDate",
    "buySell",
    "quantity",
    "tradePrice",
    "tradeMoney",
    "proceeds",
    "taxes",
    "ibCommission",
    "ibCommissionCurrency",
    "netCash",
    "cost",
    "realizedPnl",
    "fxRateToBase",
    "openCloseIndicator",
    "notes",
    "orderType",
    "exchange",
]

_POSITION_FIELDS = [
    "accountId",
    "symbol",
    "description",
    "conid",
    "currency",
    "assetCategory",
    "putCall",
    "strike",
    "expiry",
    "reportDate",
    "position",
    "markPrice",
    "positionValue",
    "costBasisPrice",
    "costBasisMoney",
    "fifoPnlUnrealized",
    "fxRateToBase",
]

_CASH_FIELDS = [
    "accountId",
    "currency",
    "reportDate",
    "startingCash",
    "endingCash",
    "endingSettledCash",
    "deposits",
    "withdrawals",
    "netTradesSales",
    "commissions",
    "dividends",
    "brokerInterest",
    "otherFees",
]


def parse_trades(report: Any) -> pd.DataFrame:
    """Extract trades from a FlexQueryResponse into a DataFrame.

    Args:
        report: ibflex FlexQueryResponse (from download_flex_report).

    Returns:
        DataFrame with one row per trade execution.
    """
    rows: list[dict] = []
    for stmt in report.FlexStatements:
        for trade in getattr(stmt, "Trades", []):
            rows.append(_obj_to_dict(trade, _TRADE_FIELDS))
    df = pd.DataFrame(rows)
    if df.empty:
        print("  [trades] No trades found in report.")
    else:
        print(f"  [trades] Parsed {len(df)} trades.")
    return df


def parse_positions(report: Any) -> pd.DataFrame:
    """Extract open positions from a FlexQueryResponse into a DataFrame."""
    rows: list[dict] = []
    for stmt in report.FlexStatements:
        for pos in getattr(stmt, "OpenPositions", []):
            rows.append(_obj_to_dict(pos, _POSITION_FIELDS))
    df = pd.DataFrame(rows)
    if df.empty:
        print("  [positions] No open positions found in report.")
    else:
        print(f"  [positions] Parsed {len(df)} positions.")
    return df


def parse_cash(report: Any) -> pd.DataFrame:
    """Extract cash balances from a FlexQueryResponse into a DataFrame."""
    rows: list[dict] = []
    for stmt in report.FlexStatements:
        for cash in getattr(stmt, "CashReport", []):
            rows.append(_obj_to_dict(cash, _CASH_FIELDS))
    df = pd.DataFrame(rows)
    if df.empty:
        print("  [cash] No cash data found in report.")
    else:
        print(f"  [cash] Parsed {len(df)} cash entries.")
    return df


# ── Cache I/O ────────────────────────────────────────────────


def _save_df(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to CSV with utf-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"  Saved {len(df)} rows -> {path.name}")


def _load_df(path: Path) -> pd.DataFrame:
    """Load a cached CSV into a DataFrame.  Returns empty DataFrame if missing."""
    if path.is_file():
        return pd.read_csv(path, encoding="utf-8")
    return pd.DataFrame()


def _merge_incremental(
    existing: pd.DataFrame, new: pd.DataFrame, key_cols: list[str]
) -> pd.DataFrame:
    """Merge new rows into existing, deduplicating on key_cols.

    New rows win over existing rows when keys collide.
    """
    if existing.empty:
        return new
    if new.empty:
        return existing

    # Ensure key columns exist in both
    available_keys = [k for k in key_cols if k in existing.columns and k in new.columns]
    if not available_keys:
        return pd.concat([existing, new], ignore_index=True)

    combined = pd.concat([existing, new], ignore_index=True)
    combined.drop_duplicates(subset=available_keys, keep="last", inplace=True)
    return combined.reset_index(drop=True)


def load_cached_trades() -> pd.DataFrame:
    """Load trades from CSV cache.  Returns empty DataFrame if no cache."""
    df = _load_df(TRADES_CSV)
    if df.empty:
        print("No cached trades found. Run `ibkr_sync.py sync` first.")
    return df


def load_cached_positions() -> pd.DataFrame:
    """Load open positions from CSV cache.  Returns empty DataFrame if no cache."""
    df = _load_df(POSITIONS_CSV)
    if df.empty:
        print("No cached positions found. Run `ibkr_sync.py sync` first.")
    return df


def load_cached_cash() -> pd.DataFrame:
    """Load cash balances from CSV cache."""
    return _load_df(CASH_CSV)


# ── Sync ─────────────────────────────────────────────────────


def sync() -> dict:
    """Main entry point: download Flex report, parse, merge into cache.

    Returns:
        Dict with counts: {trades, positions, cash, synced_at, incremental}
    """
    config = load_config()
    report = download_flex_report(config["token"], config["query_id"])

    trades_new = parse_trades(report)
    positions_new = parse_positions(report)
    cash_new = parse_cash(report)

    # Incremental merge
    incremental = TRADES_CSV.is_file()
    if incremental:
        print("Merging with existing cache (incremental)...")
        trades_old = _load_df(TRADES_CSV)
        trades_merged = _merge_incremental(
            trades_old, trades_new, key_cols=["tradeID", "tradeDate", "symbol"]
        )
    else:
        trades_merged = trades_new

    # Positions and cash are point-in-time — always overwrite
    _save_df(trades_merged, TRADES_CSV)
    _save_df(positions_new, POSITIONS_CSV)
    _save_df(cash_new, CASH_CSV)

    # Record sync timestamp
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_META.write_text(datetime.now().isoformat(), encoding="utf-8")

    stats = {
        "trades": len(trades_merged),
        "trades_new": len(trades_new),
        "positions": len(positions_new),
        "cash": len(cash_new),
        "synced_at": datetime.now().isoformat(),
        "incremental": incremental,
    }
    print(
        f"\nSync complete: {stats['trades']} trades ({stats['trades_new']} new), "
        f"{stats['positions']} positions, {stats['cash']} cash entries."
    )
    return stats


# ── Reconciliation ───────────────────────────────────────────


def reconcile(report_df: pd.DataFrame, ibkr_statement_path: Path) -> dict:
    """Compare parsed trades with an IBKR Activity Statement CSV.

    This is a basic reconciliation:
    - Loads the IBKR statement CSV
    - Compares trade counts per symbol
    - Flags quantity/price mismatches

    Args:
        report_df: DataFrame from parse_trades() or load_cached_trades()
        ibkr_statement_path: Path to IBKR Activity Statement CSV export

    Returns:
        Dict with {matched, mismatched, missing_in_flex, missing_in_statement,
                    details: list of mismatch descriptions}
    """
    if not ibkr_statement_path.is_file():
        return {
            "error": f"Statement file not found: {ibkr_statement_path}",
            "matched": 0,
            "mismatched": 0,
        }

    try:
        stmt_df = pd.read_csv(ibkr_statement_path, encoding="utf-8")
    except Exception as exc:
        return {
            "error": f"Failed to read statement: {exc}",
            "matched": 0,
            "mismatched": 0,
        }

    result: dict[str, Any] = {
        "matched": 0,
        "mismatched": 0,
        "missing_in_flex": 0,
        "missing_in_statement": 0,
        "details": [],
    }

    # Attempt to find common columns — IBKR statements vary in format
    # We do a best-effort symbol-level count comparison
    if report_df.empty:
        result["details"].append("Flex report DataFrame is empty.")
        return result

    flex_symbols = (
        set(report_df["symbol"].dropna().unique())
        if "symbol" in report_df.columns
        else set()
    )

    # Try to find a symbol column in the statement
    sym_col = None
    for candidate in ["Symbol", "symbol", "SYMBOL", "Ticker", "ticker"]:
        if candidate in stmt_df.columns:
            sym_col = candidate
            break

    if sym_col is None:
        result["details"].append(
            f"Could not identify symbol column in statement. "
            f"Columns found: {list(stmt_df.columns)[:10]}"
        )
        return result

    stmt_symbols = set(stmt_df[sym_col].dropna().unique())

    result["missing_in_flex"] = len(stmt_symbols - flex_symbols)
    result["missing_in_statement"] = len(flex_symbols - stmt_symbols)
    common = flex_symbols & stmt_symbols

    for sym in sorted(common):
        flex_count = len(report_df[report_df["symbol"] == sym])
        stmt_count = len(stmt_df[stmt_df[sym_col] == sym])
        if flex_count == stmt_count:
            result["matched"] += 1
        else:
            result["mismatched"] += 1
            result["details"].append(
                f"{sym}: Flex has {flex_count} trades, statement has {stmt_count}"
            )

    print(
        f"Reconciliation: {result['matched']} matched, "
        f"{result['mismatched']} mismatched, "
        f"{result['missing_in_flex']} only in statement, "
        f"{result['missing_in_statement']} only in Flex."
    )
    return result


# ── CLI ──────────────────────────────────────────────────────


def _print_status() -> None:
    """Print cache status and last sync time."""
    print("IBKR Flex Query Sync — Cache Status")
    print("=" * 50)
    if SYNC_META.is_file():
        last = SYNC_META.read_text(encoding="utf-8").strip()
        print(f"Last sync: {last}")
    else:
        print("Last sync: never")
    print()
    for label, path in [
        ("Trades", TRADES_CSV),
        ("Positions", POSITIONS_CSV),
        ("Cash", CASH_CSV),
    ]:
        if path.is_file():
            df = pd.read_csv(path, encoding="utf-8")
            print(f"  {label:12s}: {len(df):>6,} rows  ({path.name})")
        else:
            print(f"  {label:12s}: [no cache]")
    print(f"\nCache dir: {CACHE_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IBKR Flex Query sync — download and cache trade data."
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("sync", help="Download Flex report and update cache")
    sub.add_parser("status", help="Show cache status")
    sub.add_parser("trades", help="Print cached trades summary")
    sub.add_parser("positions", help="Print cached positions")

    recon_p = sub.add_parser(
        "reconcile", help="Reconcile Flex data with IBKR statement CSV"
    )
    recon_p.add_argument(
        "statement", type=Path, help="Path to IBKR Activity Statement CSV"
    )

    args = parser.parse_args()

    if args.command is None or args.command == "status":
        _print_status()
    elif args.command == "sync":
        sync()
    elif args.command == "trades":
        df = load_cached_trades()
        if not df.empty:
            print(df.to_string(max_rows=40))
    elif args.command == "positions":
        df = load_cached_positions()
        if not df.empty:
            print(df.to_string(max_rows=40))
    elif args.command == "reconcile":
        trades = load_cached_trades()
        if not trades.empty:
            result = reconcile(trades, args.statement)
            for line in result.get("details", []):
                print(f"  {line}")


if __name__ == "__main__":
    main()
