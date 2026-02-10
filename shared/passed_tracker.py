"""Passed Tracker with NLM-Assisted Discovery for Phase 4 Decision Audit.

Monthly auto-check of passed companies + NLM-based discovery of tickers
discussed in weekly meetings but not yet in portfolio or passed records.

Usage:
    python passed_tracker.py discover              # NLM-discover passed candidates
    python passed_tracker.py price-check            # Update prices on all passed records
    python passed_tracker.py price-check --save     # Save report to Obsidian
    python passed_tracker.py report --save          # Full monthly passed review
"""

import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, r"C:\Users\thisi\.claude\skills")

from shared.nlm_attribution import query_passed_candidates, DEFAULT_NOTEBOOK_ID

# ── Paths ──────────────────────────────────────────────────────
PORTFOLIO_DIR = Path.home() / "PORTFOLIO"
RESEARCH_DIR = PORTFOLIO_DIR / "research" / "companies"
TRADES_JSON = PORTFOLIO_DIR / "portfolio_monitor" / "data" / "trades.json"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
REVIEWS_DIR = VAULT_DIR / "Reviews"


def get_current_portfolio_tickers() -> set[str]:
    """Get tickers currently in portfolio from trades.json or portfolio API."""
    tickers = set()

    # From trades.json — tickers with net long position
    if TRADES_JSON.exists():
        try:
            with open(TRADES_JSON, encoding="utf-8") as f:
                data = json.load(f)
            trades = data if isinstance(data, list) else data.get("trades", [])
            for t in trades:
                ticker = (t.get("ticker") or t.get("symbol") or "").upper()
                if ticker:
                    tickers.add(ticker)
        except Exception:
            pass

    # From research directories with thesis.yaml (active theses)
    if RESEARCH_DIR.exists():
        for d in RESEARCH_DIR.iterdir():
            if d.is_dir() and (d / "thesis.yaml").exists():
                tickers.add(d.name.upper())

    return tickers


def get_existing_passed_tickers() -> set[str]:
    """Get tickers with existing passed.md records."""
    passed = set()
    if RESEARCH_DIR.exists():
        for d in RESEARCH_DIR.iterdir():
            if d.is_dir() and (d / "passed.md").exists():
                passed.add(d.name.upper())
    return passed


def scan_passed_records() -> list[dict]:
    """Scan all passed.md files and extract data.

    Returns list of dicts with: ticker, passed_date, source, reason, price_at_pass, revisit_trigger.
    """
    records = []
    if not RESEARCH_DIR.exists():
        return records

    for d in sorted(RESEARCH_DIR.iterdir()):
        if not d.is_dir():
            continue
        passed_md = d / "passed.md"
        if not passed_md.exists():
            continue

        ticker = d.name.upper()
        record = {
            "ticker": ticker,
            "passed_date": None,
            "source": None,
            "reason": "",
            "price_at_pass": None,
            "revisit_trigger": "",
        }

        try:
            with open(passed_md, encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    fm = content[3:end].strip()
                    for line in fm.split("\n"):
                        if ":" in line:
                            k, _, v = line.partition(":")
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k == "first_seen":
                                record["passed_date"] = v
                            elif k == "source":
                                record["source"] = v
                            elif k == "price_at_pass":
                                try:
                                    record["price_at_pass"] = float(v)
                                except (ValueError, TypeError):
                                    pass

            # Extract reason from body
            if "## Why I Passed" in content:
                after = content.split("## Why I Passed", 1)[1]
                # Take text until next ## section
                next_section = after.find("\n## ")
                reason_text = after[:next_section] if next_section > 0 else after
                record["reason"] = reason_text.strip().strip("-").strip()[:200]

            # Extract revisit trigger
            if "## Revisit Trigger" in content:
                after = content.split("## Revisit Trigger", 1)[1]
                next_section = after.find("\n## ")
                trigger_text = after[:next_section] if next_section > 0 else after
                record["revisit_trigger"] = trigger_text.strip().strip("-").strip()[:200]

        except Exception:
            pass

        records.append(record)

    return records


def fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of tickers via yfinance."""
    prices = {}
    if not tickers:
        return prices

    try:
        import yfinance as yf
        for ticker in tickers:
            try:
                info = yf.Ticker(ticker).info
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                if price:
                    prices[ticker] = float(price)
            except Exception:
                continue
    except ImportError:
        print("Warning: yfinance not installed. Price checks skipped.", file=sys.stderr)

    return prices


def discover_passed_candidates(
    months: int = 3,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
) -> dict:
    """Use NLM to discover tickers discussed but not in portfolio/passed.

    Returns:
        {
            "candidates": [
                {"ticker": str, "context": str, "date": str, "status": "new"},
            ],
            "excluded": {"portfolio": [...], "already_passed": [...]},
            "nlm_success": bool,
            "nlm_error": str or None,
        }
    """
    portfolio_tickers = get_current_portfolio_tickers()
    passed_tickers = get_existing_passed_tickers()
    all_known = portfolio_tickers | passed_tickers

    # Query NLM
    result = query_passed_candidates(
        months=months,
        notebook_id=notebook_id,
        exclude_tickers=sorted(all_known),
    )

    # Filter out any that slipped through
    filtered = []
    for c in result.get("candidates", []):
        ticker = (c.get("ticker") or "").upper()
        if ticker and ticker not in all_known:
            c["status"] = "new"
            filtered.append(c)

    return {
        "candidates": filtered,
        "excluded": {
            "portfolio": sorted(portfolio_tickers),
            "already_passed": sorted(passed_tickers),
        },
        "nlm_success": result.get("success", False),
        "nlm_error": result.get("error"),
    }


def generate_price_check_report(save: bool = False) -> str:
    """Generate monthly price check on all passed records.

    Compares price_at_pass with current price.
    """
    records = scan_passed_records()
    if not records:
        return "No passed records found."

    # Fetch current prices
    tickers = [r["ticker"] for r in records if r["price_at_pass"] is not None]
    current_prices = fetch_current_prices(tickers)

    today = date.today().isoformat()
    lines = [
        "---",
        f"created: {today}",
        "type: passed-review",
        "tags: [review, passed, phase4]",
        "---",
        "",
        f"# Passed Ticker Price Check — {today}",
        "",
        "> 追踪 passed 公司的后续表现，评估筛选直觉的准确性。",
        "",
        "## Price Tracking",
        "",
        "| Ticker | Passed Date | Reason (brief) | Price Then | Price Now | Change | Decision |",
        "|--------|------------|-----------------|------------|-----------|--------|----------|",
    ]

    correct_decisions = 0
    wrong_decisions = 0
    no_data = 0

    for r in records:
        price_then = r["price_at_pass"]
        price_now = current_prices.get(r["ticker"])
        reason = r["reason"][:40] + ("..." if len(r["reason"]) > 40 else "")

        if price_then and price_now:
            change_pct = (price_now - price_then) / price_then * 100
            change_str = f"{change_pct:+.1f}%"

            # "Correct" pass = stock went down or flat (<5% up)
            if change_pct < 5:
                decision = "Correct pass"
                correct_decisions += 1
            else:
                decision = "Missed opportunity"
                wrong_decisions += 1

            lines.append(
                f"| {r['ticker']} | {r['passed_date'] or '?'} | {reason} "
                f"| ${price_then:.2f} | ${price_now:.2f} | {change_str} | {decision} |"
            )
        else:
            no_data += 1
            lines.append(
                f"| {r['ticker']} | {r['passed_date'] or '?'} | {reason} "
                f"| {'$'+f'{price_then:.2f}' if price_then else '—'} | {'$'+f'{price_now:.2f}' if price_now else '—'} | — | No data |"
            )

    # Summary
    total = correct_decisions + wrong_decisions
    lines.extend([
        "",
        "## Summary",
        "",
        f"- **Total passed records:** {len(records)}",
        f"- **With price data:** {total}",
        f"- **Correct passes (stock <5% up):** {correct_decisions} ({correct_decisions/total*100:.0f}%)" if total > 0 else "",
        f"- **Missed opportunities (stock >5% up):** {wrong_decisions} ({wrong_decisions/total*100:.0f}%)" if total > 0 else "",
    ])

    if total > 0:
        accuracy = correct_decisions / total * 100
        if accuracy >= 70:
            lines.append(f"\n**Assessment:** Your filtering instinct is strong ({accuracy:.0f}% accuracy). Keep trusting your pass decisions.")
        elif accuracy >= 50:
            lines.append(f"\n**Assessment:** Mixed results ({accuracy:.0f}%). Review the missed opportunities for patterns — are you too conservative on a particular sector/style?")
        else:
            lines.append(f"\n**Assessment:** Low accuracy ({accuracy:.0f}%). You may be systematically missing opportunities. Consider lowering your entry threshold or revisiting your pass criteria.")

    lines.extend([
        "",
        "---",
        f"*Generated by passed tracker on {today}*",
    ])

    report = "\n".join(lines)

    if save:
        REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = REVIEWS_DIR / f"{today}_passed_review.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Saved to {filepath}")

    return report


def generate_full_report(save: bool = False) -> str:
    """Generate the full monthly passed review: price check + NLM discovery."""
    parts = []

    # Part 1: Price check
    parts.append(generate_price_check_report(save=False))

    # Part 2: NLM discovery
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## NLM Discovery: Potential Passed Candidates")
    parts.append("")

    discovery = discover_passed_candidates()

    if discovery["nlm_success"]:
        if discovery["candidates"]:
            parts.append(
                f"Found {len(discovery['candidates'])} tickers discussed in weekly meetings "
                f"but not in portfolio or passed records:"
            )
            parts.append("")
            parts.append("| Ticker | Date Discussed | Context | Action |")
            parts.append("|--------|---------------|---------|--------|")
            for c in discovery["candidates"]:
                ctx = c["context"][:60] + ("..." if len(c["context"]) > 60 else "")
                parts.append(
                    f"| {c['ticker']} | {c['date'] or '?'} | {ctx} "
                    f"| `/thesis {c['ticker']} passed` |"
                )
            parts.append("")
            parts.append("Review each candidate: was this a conscious pass, or still under research?")
        else:
            parts.append("No new candidates found. All discussed tickers are either in portfolio or already have passed records.")
    else:
        parts.append(f"NLM query failed: {discovery.get('nlm_error', 'unknown error')}")
        parts.append("Run discovery manually: `python passed_tracker.py discover`")

    parts.append("")
    parts.append(f"*Excluded: {len(discovery['excluded']['portfolio'])} portfolio tickers, "
                 f"{len(discovery['excluded']['already_passed'])} already-passed tickers*")

    report = "\n".join(parts)

    if save:
        REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        filepath = REVIEWS_DIR / f"{today}_passed_review.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Saved to {filepath}")

    return report


# ── CLI ────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Passed Tracker with NLM Discovery")
    sub = parser.add_subparsers(dest="command")

    disc = sub.add_parser("discover", help="Discover passed candidates via NLM")
    disc.add_argument("--months", type=int, default=3, help="Lookback months")
    disc.add_argument("--notebook", default=DEFAULT_NOTEBOOK_ID, help="Notebook ID")

    pc = sub.add_parser("price-check", help="Check current prices of passed tickers")
    pc.add_argument("--save", action="store_true", help="Save to Obsidian")

    rpt = sub.add_parser("report", help="Full monthly passed review")
    rpt.add_argument("--save", action="store_true", help="Save to Obsidian")

    sub.add_parser("list", help="List all passed records")

    args = parser.parse_args()

    if args.command == "discover":
        result = discover_passed_candidates(months=args.months, notebook_id=args.notebook)
        print(f"\n=== Passed Candidate Discovery ===")
        print(f"NLM status: {'OK' if result['nlm_success'] else 'FAILED'}")
        if result["nlm_error"]:
            print(f"Error: {result['nlm_error']}")
        print(f"Portfolio tickers excluded: {len(result['excluded']['portfolio'])}")
        print(f"Already-passed excluded: {len(result['excluded']['already_passed'])}")
        print(f"\nCandidates found: {len(result['candidates'])}")
        for c in result["candidates"]:
            print(f"  {c['ticker']:8s} [{c['date'] or '?'}] {c['context'][:80]}")

    elif args.command == "price-check":
        report = generate_price_check_report(save=args.save)
        print(report)

    elif args.command == "report":
        report = generate_full_report(save=args.save)
        print(report)

    elif args.command == "list":
        records = scan_passed_records()
        if not records:
            print("No passed records found.")
        else:
            print(f"\n=== Passed Records ({len(records)}) ===")
            for r in records:
                price = f"${r['price_at_pass']:.2f}" if r["price_at_pass"] else "—"
                print(f"  {r['ticker']:8s} | {r['passed_date'] or '?':12s} | {price:>10s} | {r['reason'][:50]}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
