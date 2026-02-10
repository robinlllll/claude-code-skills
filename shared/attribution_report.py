"""Source Attribution Report for Phase 4 Decision Audit.

Reads thesis files to collect idea_source tags, cross-references with
trade data for return calculations, generates the /review attribution table.

Usage:
    python attribution_report.py generate
    python attribution_report.py generate --save
    python attribution_report.py stats
"""

import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────
PORTFOLIO_DIR = Path.home() / "PORTFOLIO"
RESEARCH_DIR = PORTFOLIO_DIR / "research" / "companies"
TRADES_JSON = PORTFOLIO_DIR / "portfolio_monitor" / "data" / "trades.json"
PORTFOLIO_DB = PORTFOLIO_DIR / "portfolio_monitor" / "data" / "portfolio.db"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
REVIEWS_DIR = VAULT_DIR / "Reviews"

# Valid idea sources (matches thesis SKILL.md Info Source options + NLM additions)
VALID_SOURCES = [
    "self-research",
    "sell-side",
    "social-media",
    "podcast",
    "13f",
    "friend",
    "earnings",
    "weekly-meeting",
    "substack",
    "x",
    "supply-chain",
    "chatgpt",
    "other",
]


def scan_thesis_files() -> list[dict]:
    """Scan all thesis files and extract idea_source attribution data.

    Returns list of dicts with: ticker, idea_source, source_detail, first_seen,
    first_position, status (active/passed/closed), nlm_citation.
    """
    results = []

    if not RESEARCH_DIR.exists():
        return results

    for ticker_dir in sorted(RESEARCH_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name.upper()
        entry = {
            "ticker": ticker,
            "idea_source": None,
            "source_detail": "",
            "source_link": "",
            "nlm_citation": "",
            "first_seen": None,
            "first_position": None,
            "status": "unknown",
            "conviction": None,
            "framework_coverage_score": None,
        }

        # Check thesis.md for idea_source in frontmatter
        thesis_md = ticker_dir / "thesis.md"
        if thesis_md.exists():
            fm = _parse_frontmatter(thesis_md)
            entry["idea_source"] = fm.get("idea_source") or fm.get("info_source")
            entry["source_detail"] = fm.get("source_detail", "")
            entry["source_link"] = fm.get("source_link", "")
            entry["nlm_citation"] = fm.get("nlm_citation", "")
            entry["first_seen"] = fm.get("first_seen")
            entry["first_position"] = fm.get("first_position")
            entry["status"] = "active"

        # Check thesis.yaml for additional fields
        thesis_yaml = ticker_dir / "thesis.yaml"
        if thesis_yaml.exists():
            yaml_data = _parse_yaml_simple(thesis_yaml)
            if not entry["idea_source"]:
                entry["idea_source"] = yaml_data.get("idea_source")
            if not entry["first_seen"]:
                entry["first_seen"] = yaml_data.get("first_seen") or yaml_data.get("created_date")
            entry["conviction"] = yaml_data.get("conviction")
            entry["framework_coverage_score"] = yaml_data.get("framework_coverage.score")
            entry["status"] = "active"

        # Check passed.md
        passed_md = ticker_dir / "passed.md"
        if passed_md.exists():
            fm = _parse_frontmatter(passed_md)
            if not entry["idea_source"]:
                entry["idea_source"] = fm.get("source") or fm.get("idea_source")
            if not entry["first_seen"]:
                entry["first_seen"] = fm.get("first_seen")
            entry["status"] = "passed"
            entry["price_at_pass"] = fm.get("price_at_pass")

        # Normalize idea_source
        if entry["idea_source"]:
            entry["idea_source"] = _normalize_source(entry["idea_source"])

        results.append(entry)

    return results


def load_trades() -> list[dict]:
    """Load trade records from trades.json."""
    if not TRADES_JSON.exists():
        return []
    try:
        with open(TRADES_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "trades" in data:
            return data["trades"]
        return []
    except Exception:
        return []


def compute_returns(trades: list[dict]) -> dict:
    """Compute per-ticker return metrics from trade records.

    Tries stock-summary API first (best data), falls back to trades.json parsing.
    Returns: {TICKER: {total_return_pct, realized_pnl, win}}
    """
    # Try stock-summary API first
    api_returns = _fetch_stock_summary_returns()
    if api_returns:
        return api_returns

    # Fallback: parse trades.json
    by_ticker = defaultdict(list)
    for t in trades:
        ticker = (t.get("ticker") or t.get("symbol") or "").upper()
        if ticker:
            by_ticker[ticker].append(t)

    returns = {}
    for ticker, ticker_trades in by_ticker.items():
        total_pnl = 0
        total_cost = 0
        for t in ticker_trades:
            # Support both field naming conventions
            pnl = t.get("pnl_usd") or t.get("realized_pnl") or t.get("realizedPnl") or 0
            if isinstance(pnl, str):
                try:
                    pnl = float(pnl.replace(",", ""))
                except ValueError:
                    pnl = 0
            total_pnl += float(pnl)

            # Estimate cost basis from buys
            action = (t.get("direction") or t.get("action") or t.get("buySell") or "").upper()
            if action in ("BUY", "B"):
                qty = abs(float(t.get("quantity", 0) or 0))
                price = float(t.get("exit_price") or t.get("price") or t.get("tradePrice") or 0)
                total_cost += qty * price

        return_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        returns[ticker] = {
            "total_return_pct": round(return_pct, 1),
            "realized_pnl": round(total_pnl, 2),
            "win": total_pnl > 0,
        }

    return returns


def _fetch_stock_summary_returns() -> Optional[dict]:
    """Fetch return data from portfolio monitor stock-summary API."""
    try:
        import urllib.request
        req = urllib.request.urlopen("http://localhost:8000/api/trades/stock-summary", timeout=5)
        data = json.loads(req.read().decode("utf-8"))
        stocks = data.get("stocks", [])
        if not stocks:
            return None

        # Also load trades.json for cost basis computation
        trades = load_trades()
        cost_by_ticker = defaultdict(float)
        for t in trades:
            ticker = (t.get("ticker") or "").upper()
            direction = (t.get("direction") or "").upper()
            if direction in ("BUY", "B") and ticker:
                qty = abs(float(t.get("quantity", 0) or 0))
                price = float(t.get("exit_price") or t.get("price") or 0)
                cost_by_ticker[ticker] += qty * price

        returns = {}
        for s in stocks:
            ticker = (s.get("ticker") or "").upper()
            if not ticker:
                continue
            total_pnl = float(s.get("totalPnl") or 0)
            win_rate = float(s.get("winRate") or 0)
            cost = cost_by_ticker.get(ticker, 0)
            return_pct = (total_pnl / cost * 100) if cost > 0 else 0
            returns[ticker] = {
                "total_return_pct": round(return_pct, 1),
                "realized_pnl": round(total_pnl, 2),
                "win": total_pnl > 0,
            }
        return returns
    except Exception:
        return None


def compute_conviction_calibration(theses: list[dict], returns: dict) -> str:
    """Conviction Calibration: do high-conviction bets actually earn more?

    Groups active positions by conviction level (1-5), computes avg return and win rate.
    """
    by_conviction = defaultdict(lambda: {"positions": 0, "total_return": 0, "wins": 0, "with_data": 0})

    for t in theses:
        if t["status"] != "active":
            continue
        conviction = t.get("conviction")
        if not conviction:
            continue
        try:
            conv = int(conviction)
        except (ValueError, TypeError):
            continue
        bucket = by_conviction[conv]
        bucket["positions"] += 1
        if t["ticker"] in returns:
            r = returns[t["ticker"]]
            bucket["total_return"] += r["total_return_pct"]
            bucket["with_data"] += 1
            if r["win"]:
                bucket["wins"] += 1

    if not by_conviction:
        return ""

    conv_labels = {1: "1 (Min)", 2: "2 (Low)", 3: "3 (Medium)", 4: "4 (High)", 5: "5 (Max)"}
    lines = [
        "",
        "### Conviction Calibration",
        "",
        "> 高 conviction 是否真的赚更多？",
        "",
        "| Conviction | Positions | Avg Return | Win Rate |",
        "|------------|-----------|------------|----------|",
    ]
    for conv in sorted(by_conviction.keys(), reverse=True):
        b = by_conviction[conv]
        avg = f"{b['total_return'] / b['with_data']:+.1f}%" if b["with_data"] > 0 else "—"
        wr = f"{b['wins'] / b['with_data'] * 100:.0f}%" if b["with_data"] > 0 else "—"
        label = conv_labels.get(conv, str(conv))
        lines.append(f"| {label} | {b['positions']} | {avg} | {wr} |")

    return "\n".join(lines)


def compute_coverage_correlation(theses: list[dict], returns: dict) -> str:
    """Coverage vs Returns: does deeper research lead to better outcomes?

    Groups by framework_coverage.score into 3 tiers: 0-40%, 41-70%, 71-100%.
    """
    tiers = {
        "71-100%": {"positions": 0, "total_return": 0, "wins": 0, "with_data": 0},
        "41-70%": {"positions": 0, "total_return": 0, "wins": 0, "with_data": 0},
        "0-40%": {"positions": 0, "total_return": 0, "wins": 0, "with_data": 0},
    }

    for t in theses:
        if t["status"] != "active":
            continue
        score = t.get("framework_coverage_score")
        if score is None:
            continue
        try:
            s = int(score)
        except (ValueError, TypeError):
            continue

        if s >= 71:
            tier = "71-100%"
        elif s >= 41:
            tier = "41-70%"
        else:
            tier = "0-40%"

        tiers[tier]["positions"] += 1
        if t["ticker"] in returns:
            r = returns[t["ticker"]]
            tiers[tier]["total_return"] += r["total_return_pct"]
            tiers[tier]["with_data"] += 1
            if r["win"]:
                tiers[tier]["wins"] += 1

    has_data = any(v["positions"] > 0 for v in tiers.values())
    if not has_data:
        return ""

    lines = [
        "",
        "### Coverage vs Returns",
        "",
        "> 研究越深入，回报越好吗？",
        "",
        "| Coverage | Positions | Avg Return | Win Rate |",
        "|----------|-----------|------------|----------|",
    ]
    for tier_name in ["71-100%", "41-70%", "0-40%"]:
        b = tiers[tier_name]
        if b["positions"] == 0:
            continue
        avg = f"{b['total_return'] / b['with_data']:+.1f}%" if b["with_data"] > 0 else "—"
        wr = f"{b['wins'] / b['with_data'] * 100:.0f}%" if b["with_data"] > 0 else "—"
        lines.append(f"| {tier_name} | {b['positions']} | {avg} | {wr} |")

    return "\n".join(lines)


def generate_attribution_report(save: bool = False) -> str:
    """Generate the source attribution report.

    Returns markdown string of the report.
    """
    theses = scan_thesis_files()
    trades = load_trades()
    returns = compute_returns(trades)

    # Aggregate by source
    by_source = defaultdict(lambda: {
        "ideas": 0,
        "positions": 0,
        "passed": 0,
        "tickers": [],
        "total_return": 0,
        "wins": 0,
        "with_return_data": 0,
    })

    unattributed = []

    for t in theses:
        source = t["idea_source"] or "unattributed"
        if source == "unattributed":
            unattributed.append(t["ticker"])
            continue

        by_source[source]["ideas"] += 1
        by_source[source]["tickers"].append(t["ticker"])

        if t["status"] == "active":
            by_source[source]["positions"] += 1
            # Add return data if available
            if t["ticker"] in returns:
                r = returns[t["ticker"]]
                by_source[source]["total_return"] += r["total_return_pct"]
                by_source[source]["with_return_data"] += 1
                if r["win"]:
                    by_source[source]["wins"] += 1
        elif t["status"] == "passed":
            by_source[source]["passed"] += 1

    # Build report
    today = date.today().isoformat()
    lines = [
        "---",
        f"created: {today}",
        "type: attribution-report",
        "tags: [review, attribution, phase4]",
        "---",
        "",
        f"# Source Attribution Report — {today}",
        "",
        "> 信息来源 → 研究想法 → 持仓/放弃 → 收益追踪",
        "",
        "## Attribution Table",
        "",
        "| Source | Ideas | Positions | Passed | Avg Return | Win Rate | Best/Worst |",
        "|--------|-------|-----------|--------|------------|----------|------------|",
    ]

    for source in sorted(by_source.keys()):
        s = by_source[source]
        avg_ret = (
            f"{s['total_return'] / s['with_return_data']:.1f}%"
            if s["with_return_data"] > 0
            else "—"
        )
        win_rate = (
            f"{s['wins'] / s['with_return_data'] * 100:.0f}%"
            if s["with_return_data"] > 0
            else "—"
        )

        # Find best/worst
        best_worst = "—"
        if s["tickers"] and any(t in returns for t in s["tickers"]):
            ticker_returns = [(t, returns[t]["total_return_pct"]) for t in s["tickers"] if t in returns]
            if ticker_returns:
                ticker_returns.sort(key=lambda x: x[1])
                best = ticker_returns[-1]
                worst = ticker_returns[0]
                if best[0] == worst[0]:
                    best_worst = f"{best[0]} ({best[1]:+.1f}%)"
                else:
                    best_worst = f"{best[0]} ({best[1]:+.1f}%) / {worst[0]} ({worst[1]:+.1f}%)"

        lines.append(
            f"| {source} | {s['ideas']} | {s['positions']} | {s['passed']} "
            f"| {avg_ret} | {win_rate} | {best_worst} |"
        )

    # Totals
    total_ideas = sum(s["ideas"] for s in by_source.values())
    total_positions = sum(s["positions"] for s in by_source.values())
    total_passed = sum(s["passed"] for s in by_source.values())
    lines.append(f"| **Total** | **{total_ideas}** | **{total_positions}** | **{total_passed}** | | | |")

    # Unattributed section
    if unattributed:
        lines.extend([
            "",
            "## Unattributed Tickers",
            "",
            f"The following {len(unattributed)} tickers have thesis/passed records but no `idea_source` tag:",
            "",
        ])
        for t in sorted(unattributed):
            lines.append(f"- {t}")
        lines.append("")
        lines.append("Use `/thesis TICKER` to add attribution (NLM will auto-suggest the source).")

    # Insights
    lines.extend([
        "",
        "## Insights",
        "",
        f"- **Coverage:** {total_ideas} ideas tracked, {len(unattributed)} unattributed",
        f"- **Conversion rate:** {total_positions}/{total_ideas} ideas became positions ({total_positions/total_ideas*100:.0f}%)" if total_ideas > 0 else "- **Conversion rate:** No data yet",
        f"- **Pass rate:** {total_passed}/{total_ideas} ideas passed ({total_passed/total_ideas*100:.0f}%)" if total_ideas > 0 else "",
    ])

    # Source efficiency ranking
    if by_source:
        ranked = sorted(
            [(src, s) for src, s in by_source.items() if s["with_return_data"] > 0],
            key=lambda x: x[1]["total_return"] / x[1]["with_return_data"],
            reverse=True,
        )
        if ranked:
            lines.extend([
                "",
                "### Source Efficiency Ranking (by avg return)",
                "",
            ])
            for i, (src, s) in enumerate(ranked, 1):
                avg = s["total_return"] / s["with_return_data"]
                lines.append(f"{i}. **{src}** — {avg:+.1f}% avg return ({s['with_return_data']} positions)")

    # Conviction Calibration
    conviction_text = compute_conviction_calibration(theses, returns)
    if conviction_text:
        lines.append(conviction_text)

    # Coverage vs Returns
    coverage_text = compute_coverage_correlation(theses, returns)
    if coverage_text:
        lines.append(coverage_text)

    lines.extend([
        "",
        "---",
        f"*Generated by `/review attribution` on {today}*",
    ])

    report = "\n".join(lines)

    if save:
        REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{today}_attribution_report.md"
        filepath = REVIEWS_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Saved to {filepath}")

    return report


def show_stats():
    """Show quick stats about attribution coverage."""
    theses = scan_thesis_files()
    total = len(theses)
    attributed = sum(1 for t in theses if t["idea_source"])
    sources = defaultdict(int)
    for t in theses:
        if t["idea_source"]:
            sources[t["idea_source"]] += 1

    print(f"\n=== Attribution Stats ===")
    print(f"Total tickers with thesis/passed: {total}")
    print(f"Attributed: {attributed}/{total} ({attributed/total*100:.0f}%)" if total else "No thesis files found")
    print()
    if sources:
        print("By source:")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"  {src}: {count}")
    print()


# ── Helpers ────────────────────────────────────────────────────

def _parse_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a markdown file (simple parser, no PyYAML needed)."""
    result = {}
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return result

    if not content.startswith("---"):
        return result

    end = content.find("---", 3)
    if end == -1:
        return result

    fm_text = content[3:end].strip()
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Handle lists like [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
        result[key] = value

    return result


def _parse_yaml_simple(filepath: Path) -> dict:
    """Parse a simple YAML file with support for nested keys.

    Handles flat key-value pairs and reads nested structures like:
      framework_coverage:
        score: 83
    Returns flattened keys like 'framework_coverage.score': '83'.
    Also reads kill_criteria list items.
    """
    result = {}
    current_parent = ""
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # Detect indentation level
                indent = len(line) - len(line.lstrip())
                if stripped.startswith("-"):
                    continue  # Skip list items for flat parsing
                if ":" not in stripped:
                    continue
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if indent == 0:
                    if value:
                        result[key] = value
                        current_parent = ""
                    else:
                        current_parent = key
                elif indent > 0 and current_parent and value:
                    result[f"{current_parent}.{key}"] = value
    except Exception:
        pass
    return result


def _normalize_source(source: str) -> str:
    """Normalize idea source string to standard form."""
    source = source.lower().strip()
    mapping = {
        "self-research": "self-research",
        "self research": "self-research",
        "selfresearch": "self-research",
        "sell-side": "sell-side",
        "sell side": "sell-side",
        "social-media": "social-media",
        "social media": "social-media",
        "twitter": "x",
        "x": "x",
        "podcast": "podcast",
        "13f": "13f",
        "friend": "friend",
        "earnings": "earnings",
        "weekly-meeting": "weekly-meeting",
        "weekly meeting": "weekly-meeting",
        "周会": "weekly-meeting",
        "substack": "substack",
        "supply-chain": "supply-chain",
        "supply chain": "supply-chain",
        "chatgpt": "chatgpt",
        "other": "other",
    }
    return mapping.get(source, source)


# ── CLI ────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Source Attribution Report")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate attribution report")
    gen.add_argument("--save", action="store_true", help="Save to Obsidian vault")

    sub.add_parser("stats", help="Show attribution stats")
    sub.add_parser("scan", help="List all thesis files with attribution data")

    args = parser.parse_args()

    if args.command == "generate":
        report = generate_attribution_report(save=args.save)
        print(report)
    elif args.command == "stats":
        show_stats()
    elif args.command == "scan":
        theses = scan_thesis_files()
        for t in theses:
            src = t["idea_source"] or "[none]"
            print(f"  {t['ticker']:8s} | {t['status']:8s} | source: {src}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
