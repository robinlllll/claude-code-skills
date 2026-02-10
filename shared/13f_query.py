"""
Query 13F institutional holdings data from CSV/JSON output files.

Searches across 70+ fund managers to find who holds a given ticker,
with quarter-over-quarter change tracking.

Usage:
    python 13f_query.py NVDA                    # Show all holders of NVDA
    python 13f_query.py PM --quarter 2025-Q3    # Specific quarter
    python 13f_query.py PM --summary            # One-line summary
"""

import csv
import re
import sys
from pathlib import Path

OUTPUT_DIR = Path.home() / "13F-CLAUDE" / "output"

# Load entity dictionary for ticker -> company name mapping
_entity_dict = None


def _load_entity_dict():
    global _entity_dict
    if _entity_dict is not None:
        return _entity_dict
    dict_path = Path.home() / ".claude" / "skills" / "shared" / "entity_dictionary.yaml"
    if dict_path.exists():
        try:
            import yaml
            _entity_dict = yaml.safe_load(dict_path.read_text(encoding="utf-8"))
            return _entity_dict
        except Exception:
            pass
    _entity_dict = {}
    return _entity_dict


def _get_search_terms(ticker: str) -> list[str]:
    """Get search terms for a ticker (company name variations)."""
    terms = [ticker.upper()]
    ed = _load_entity_dict()
    if ticker.upper() in ed:
        entry = ed[ticker.upper()]
        canonical = entry.get("canonical_name", "")
        if canonical:
            terms.append(canonical.upper())
            words = canonical.upper().split()
            if len(words) >= 2:
                terms.append(" ".join(words[:2]))
    return terms


def get_available_quarters() -> list[str]:
    """Get list of available quarters sorted descending."""
    quarters = set()
    if not OUTPUT_DIR.exists():
        return []
    for manager_dir in OUTPUT_DIR.iterdir():
        if not manager_dir.is_dir() or manager_dir.name.startswith("_"):
            continue
        for q_dir in manager_dir.iterdir():
            if q_dir.is_dir() and re.match(r"\d{4}-Q[1-4]", q_dir.name):
                quarters.add(q_dir.name)
    return sorted(quarters, reverse=True)


def find_holdings(ticker: str, quarter: str = None) -> list[dict]:
    """Find all fund managers holding a given ticker.

    Returns list of dicts with keys:
        manager, issuer, shares, value_millions, portfolio_pct,
        share_change, change_pct, first_owned, quarter
    """
    if quarter is None:
        quarters = get_available_quarters()
        if not quarters:
            return []
        quarter = quarters[0]

    search_terms = _get_search_terms(ticker)
    results = []

    for manager_dir in OUTPUT_DIR.iterdir():
        if not manager_dir.is_dir() or manager_dir.name.startswith("_"):
            continue

        csv_path = manager_dir / quarter / f"holdings_{quarter}.csv"
        if not csv_path.exists():
            continue

        manager_name = manager_dir.name.rsplit("_", 1)[0].replace("_", " ")

        try:
            with open(csv_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    issuer = (row.get("Issuer Name") or "").upper()
                    if not issuer:
                        continue

                    matched = any(term in issuer for term in search_terms)
                    if not matched:
                        continue

                    try:
                        value_k = float(row.get("Value ($K)", 0) or 0)
                    except (ValueError, TypeError):
                        value_k = 0

                    try:
                        shares = float(row.get("Shares", 0) or 0)
                    except (ValueError, TypeError):
                        shares = 0

                    try:
                        pct = float(row.get("Portfolio %", 0) or 0)
                    except (ValueError, TypeError):
                        pct = 0

                    try:
                        share_change = float(row.get("Share Change", 0) or 0)
                    except (ValueError, TypeError):
                        share_change = 0

                    change_pct_str = (row.get("Change %") or "0").replace("%", "")
                    try:
                        change_pct = float(change_pct_str)
                    except (ValueError, TypeError):
                        change_pct = 0

                    first_owned = row.get("1st Qtr Owned", "")

                    results.append({
                        "manager": manager_name,
                        "issuer": row.get("Issuer Name", ""),
                        "shares": int(shares),
                        "value_millions": round(value_k / 1000, 1),
                        "portfolio_pct": round(pct, 2),
                        "share_change": int(share_change),
                        "change_pct": round(change_pct, 2),
                        "first_owned": first_owned,
                        "quarter": quarter,
                    })
        except Exception:
            continue

    results.sort(key=lambda x: x["value_millions"], reverse=True)
    return results


def holdings_summary(ticker: str, quarter: str = None) -> str:
    """Return a markdown summary of institutional activity for a ticker."""
    holdings = find_holdings(ticker, quarter)
    if not holdings:
        q = quarter or "latest"
        return f"No 13F holdings data found for {ticker} ({q})."

    quarter = holdings[0]["quarter"]
    total_holders = len(holdings)
    new_positions = [h for h in holdings if h["first_owned"] == quarter]
    increased = [h for h in holdings if h["share_change"] > 0 and h["first_owned"] != quarter]
    decreased = [h for h in holdings if h["share_change"] < 0]

    lines = [
        f"### 13F Institutional Holdings: {ticker} ({quarter})",
        "",
        f"**{total_holders} fund managers** hold {ticker} | "
        f"{len(new_positions)} new | {len(increased)} increased | {len(decreased)} decreased",
        "",
        "| Manager | Shares | Value ($M) | Portfolio % | Change | Change % |",
        "|---------|--------|-----------|-------------|--------|----------|",
    ]

    for h in holdings[:15]:
        chg = f"{h['share_change']:+,}" if h['share_change'] != 0 else "—"
        chg_pct = f"{h['change_pct']:+.1f}%" if h['change_pct'] != 0 else "—"
        if h["first_owned"] == quarter:
            chg = "**NEW**"
            chg_pct = "—"
        lines.append(
            f"| {h['manager'][:35]} | {h['shares']:,} | {h['value_millions']:,.1f} | "
            f"{h['portfolio_pct']:.1f}% | {chg} | {chg_pct} |"
        )

    if total_holders > 15:
        lines.append(f"| ... and {total_holders - 15} more | | | | | |")

    return "\n".join(lines)


def one_line_summary(ticker: str, quarter: str = None) -> str:
    """Return a one-line summary for embedding in thesis/review."""
    holdings = find_holdings(ticker, quarter)
    if not holdings:
        return f"{ticker}: No 13F data"

    total = len(holdings)
    q = holdings[0]["quarter"]
    new = len([h for h in holdings if h["first_owned"] == q])
    inc = len([h for h in holdings if h["share_change"] > 0 and h["first_owned"] != q])
    dec = len([h for h in holdings if h["share_change"] < 0])
    top = holdings[0]["manager"] if holdings else "N/A"

    return (
        f"{ticker} ({q}): {total} holders "
        f"({new} new, {inc} up, {dec} down). "
        f"Top: {top} ({holdings[0]['portfolio_pct']:.1f}%)"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Query 13F institutional holdings")
    parser.add_argument("ticker", help="Ticker symbol to search")
    parser.add_argument("--quarter", help="Quarter (e.g., 2025-Q3)")
    parser.add_argument("--summary", action="store_true", help="One-line summary")
    args = parser.parse_args()

    if args.summary:
        print(one_line_summary(args.ticker.upper(), args.quarter))
    else:
        print(holdings_summary(args.ticker.upper(), args.quarter))
