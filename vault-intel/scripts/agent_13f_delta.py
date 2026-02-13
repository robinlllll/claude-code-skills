"""Agent 4: 13F Quarter-over-Quarter Delta Analysis.

Compares the two most recent quarterly holdings CSVs and flags
significant position changes, new entries, exits, and portfolio overlaps.
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"


def _find_latest_two_csvs(thirteenf_path: Path) -> tuple[Path | None, Path | None]:
    """Find the two most recent _ALL_HOLDINGS_*.csv files."""
    output_dir = thirteenf_path / "output"
    csvs = sorted(output_dir.glob("_ALL_HOLDINGS_*.csv"))
    if len(csvs) < 2:
        return (csvs[-1] if csvs else None, None)
    return csvs[-1], csvs[-2]


def _load_holdings(csv_path: Path) -> dict[tuple[str, str], dict]:
    """Load CSV into dict keyed by (Manager CIK, CUSIP)."""
    holdings = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cik = row.get("Manager CIK", "").strip()
            cusip = row.get("CUSIP", "").strip()
            if not cik or not cusip:
                continue
            key = (cik, cusip)
            holdings[key] = {
                "manager_name": row.get("Manager Name", "").strip(),
                "issuer_name": row.get("Issuer Name", "").strip(),
                "cusip": cusip,
                "value_k": float(row.get("Value ($K)", 0) or 0),
                "shares": float(row.get("Shares", 0) or 0),
                "portfolio_pct": float(row.get("Portfolio %", 0) or 0),
            }
    return holdings


def _load_cusip_map(thirteenf_path: Path) -> dict[str, str]:
    """Load CUSIP → ticker mapping."""
    map_path = thirteenf_path / "output" / "_cusip_ticker_map.json"
    if map_path.exists():
        with open(map_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_portfolio_symbols(config: dict) -> set[str]:
    """Load current portfolio position symbols."""
    pf_path = (
        config["portfolio_path"] / "portfolio_monitor" / "data" / "portfolio_data.json"
    )
    if not pf_path.exists():
        return set()
    with open(pf_path, encoding="utf-8") as f:
        data = json.load(f)
    return {p["symbol"] for p in data.get("positions", []) if p.get("symbol")}


def _quarter_label(csv_path: Path) -> str:
    """Extract quarter label from filename like _ALL_HOLDINGS_2025-Q4.csv."""
    stem = csv_path.stem  # _ALL_HOLDINGS_2025-Q4
    return stem.replace("_ALL_HOLDINGS_", "")


def run(config: dict, dry_run: bool = False, **kwargs) -> dict:
    """Run the 13F delta analysis agent."""
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "agent": "13f_delta",
        "status": "success",
        "started_at": started,
        "metrics": {},
        "issues": [],
        "actions_taken": [],
        "errors": [],
    }

    thirteenf_path = config["thirteenf_path"]
    tf_cfg = config.get("thirteenf", {})
    min_change_pct = tf_cfg.get("min_position_change_pct", 20)
    min_value_k = tf_cfg.get("min_value_k", 10000)
    tracked = set(tf_cfg.get("tracked_managers", []))

    # Find latest two CSVs
    latest_csv, prev_csv = _find_latest_two_csvs(thirteenf_path)
    if not latest_csv or not prev_csv:
        result["status"] = "partial"
        result["errors"].append("Need at least 2 quarterly CSVs for delta analysis")
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        return result

    latest_q = _quarter_label(latest_csv)
    prev_q = _quarter_label(prev_csv)
    result["metrics"]["latest_quarter"] = latest_q
    result["metrics"]["previous_quarter"] = prev_q

    # Load data
    latest = _load_holdings(latest_csv)
    prev = _load_holdings(prev_csv)
    cusip_map = _load_cusip_map(thirteenf_path)
    portfolio_symbols = _load_portfolio_symbols(config)

    # Filter by tracked managers if specified
    if tracked:
        latest = {k: v for k, v in latest.items() if k[0] in tracked}
        prev = {k: v for k, v in prev.items() if k[0] in tracked}

    new_positions = []
    exits = []
    size_changes = []

    latest_keys = set(latest.keys())
    prev_keys = set(prev.keys())

    # New positions (in latest but not previous)
    for key in latest_keys - prev_keys:
        h = latest[key]
        if h["value_k"] < min_value_k:
            continue
        ticker = cusip_map.get(h["cusip"], h["cusip"])
        overlap = ticker in portfolio_symbols
        new_positions.append(
            {
                "manager_cik": key[0],
                "manager_name": h["manager_name"],
                "ticker": ticker,
                "cusip": h["cusip"],
                "issuer_name": h["issuer_name"],
                "value_k": h["value_k"],
                "shares": h["shares"],
                "portfolio_overlap": overlap,
            }
        )

    # Exits (in previous but not latest)
    for key in prev_keys - latest_keys:
        h = prev[key]
        if h["value_k"] < min_value_k:
            continue
        ticker = cusip_map.get(h["cusip"], h["cusip"])
        overlap = ticker in portfolio_symbols
        exits.append(
            {
                "manager_cik": key[0],
                "manager_name": h["manager_name"],
                "ticker": ticker,
                "cusip": h["cusip"],
                "issuer_name": h["issuer_name"],
                "prev_value_k": h["value_k"],
                "prev_shares": h["shares"],
                "portfolio_overlap": overlap,
            }
        )

    # Size changes
    for key in latest_keys & prev_keys:
        h_new = latest[key]
        h_old = prev[key]
        if h_new["value_k"] < min_value_k and h_old["value_k"] < min_value_k:
            continue
        if h_old["shares"] == 0:
            continue
        pct_change = abs(h_new["shares"] - h_old["shares"]) / h_old["shares"] * 100
        if pct_change >= min_change_pct:
            ticker = cusip_map.get(h_new["cusip"], h_new["cusip"])
            overlap = ticker in portfolio_symbols
            size_changes.append(
                {
                    "manager_cik": key[0],
                    "manager_name": h_new["manager_name"],
                    "ticker": ticker,
                    "cusip": h_new["cusip"],
                    "issuer_name": h_new["issuer_name"],
                    "prev_shares": h_old["shares"],
                    "new_shares": h_new["shares"],
                    "change_pct": round(pct_change, 1),
                    "direction": "increase"
                    if h_new["shares"] > h_old["shares"]
                    else "decrease",
                    "new_value_k": h_new["value_k"],
                    "portfolio_overlap": overlap,
                }
            )

    # Sort by value for relevance
    new_positions.sort(key=lambda x: x["value_k"], reverse=True)
    exits.sort(key=lambda x: x["prev_value_k"], reverse=True)
    size_changes.sort(key=lambda x: x["new_value_k"], reverse=True)

    # Portfolio overlaps summary
    overlap_tickers = set()
    for item in new_positions + exits + size_changes:
        if item.get("portfolio_overlap"):
            overlap_tickers.add(item["ticker"])

    result["metrics"].update(
        {
            "new_positions": len(new_positions),
            "exits": len(exits),
            "size_changes": len(size_changes),
            "portfolio_overlaps": len(overlap_tickers),
        }
    )

    result["issues"] = []
    # Flag portfolio overlaps as issues for the briefing
    for ticker in overlap_tickers:
        result["issues"].append(
            {
                "type": "portfolio_overlap",
                "ticker": ticker,
                "severity": "P2",
                "detail": f"13F activity detected for portfolio holding {ticker}",
            }
        )

    result["actions_taken"] = []  # Read-only agent
    result["new_positions"] = new_positions[:50]  # Cap for briefing
    result["exits"] = exits[:50]
    result["size_changes"] = size_changes[:50]
    result["overlap_tickers"] = sorted(overlap_tickers)

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="13F Delta Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    result = run(cfg, dry_run=args.dry_run)

    out_path = OUTPUT_DIR / "thirteenf_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Status: {result['status']}")
    m = result["metrics"]
    print(f"  {m.get('latest_quarter', '?')} vs {m.get('previous_quarter', '?')}")
    print(
        f"  New: {m.get('new_positions', 0)}, Exits: {m.get('exits', 0)}, "
        f"Size Δ: {m.get('size_changes', 0)}, Overlaps: {m.get('portfolio_overlaps', 0)}"
    )
    if result["errors"]:
        print(f"  Errors: {result['errors']}")
