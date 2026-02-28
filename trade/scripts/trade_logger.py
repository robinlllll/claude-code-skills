"""Trade Logger — deterministic trade recording script.

Usage:
    python trade_logger.py BUY AAPL 100 185.50 --reason "AI services growth thesis"
    python trade_logger.py SELL NVDA 50 140 --reason "Taking profits"
    python trade_logger.py ADD TSM 200 330 --reason "Buying the dip"

Outputs JSON to stdout with all trade details.
"""

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Encoding ────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Paths ───────────────────────────────────────────────────
SHARED_DIR = Path(r"C:\Users\thisi\.claude\skills\shared")
PORTFOLIO_DIR = Path(r"C:\Users\thisi\PORTFOLIO")
TRADES_DIR = PORTFOLIO_DIR / "decisions" / "trades"
RESEARCH_DIR = PORTFOLIO_DIR / "research" / "companies"

# ── Shared imports ──────────────────────────────────────────
sys.path.insert(0, str(SHARED_DIR))

VALID_ACTIONS = {"BUY", "SELL", "SHORT", "COVER", "ADD", "TRIM"}

# Map trade actions → DecisionType enum values
ACTION_TO_DECISION_TYPE = {
    "BUY": "buy",
    "SELL": "sell",
    "SHORT": "buy",
    "COVER": "sell",
    "ADD": "add",
    "TRIM": "trim",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Trade Logger")
    parser.add_argument("action", type=str.upper, choices=sorted(VALID_ACTIONS))
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("qty", type=float)
    parser.add_argument("price", type=float)
    parser.add_argument("--reason", default="", type=str)
    parser.add_argument(
        "--portfolio-url",
        default="http://localhost:8000/api/portfolio",
        type=str,
    )
    return parser.parse_args()


# ── Step 1: Fetch portfolio ─────────────────────────────────


def fetch_portfolio(url, ticker):
    """Fetch portfolio data. Returns dict with position info or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        nav = None
        if "summary" in data and "nav_usd" in data["summary"]:
            nav = data["summary"]["nav_usd"]

        position = None
        positions = data.get("positions", [])
        for p in positions:
            sym = p.get("symbol", "").upper()
            if sym == ticker or sym.startswith(ticker + " "):
                position = p
                break

        return {
            "nav": nav,
            "current_shares": position.get("quantity", 0) if position else 0,
            "avg_cost": position.get("avg_cost", 0) if position else 0,
            "market_value": position.get("market_value_usd", 0) if position else 0,
        }
    except Exception as e:
        return {
            "nav": None,
            "current_shares": 0,
            "avg_cost": 0,
            "market_value": 0,
            "error": str(e),
        }


# ── Step 2: Calculate ───────────────────────────────────────


def calculate_trade(action, qty, price, portfolio_data):
    """Calculate trade total, position after, % of NAV."""
    trade_total = qty * price
    nav = portfolio_data.get("nav")
    current_shares = portfolio_data.get("current_shares", 0)
    avg_cost = portfolio_data.get("avg_cost", 0)

    pct_nav = (trade_total / nav * 100) if nav else None

    # New position after trade
    if action in ("BUY", "ADD", "SHORT"):
        new_shares = current_shares + qty
        if current_shares > 0 and avg_cost > 0:
            new_avg_cost = (current_shares * avg_cost + qty * price) / new_shares
        else:
            new_avg_cost = price
    elif action in ("SELL", "COVER", "TRIM"):
        new_shares = max(current_shares - qty, 0)
        new_avg_cost = avg_cost  # avg cost unchanged on sells
    else:
        new_shares = current_shares
        new_avg_cost = avg_cost

    new_position_value = new_shares * price
    new_position_pct = (new_position_value / nav * 100) if nav else None

    # Realized P&L for exits
    realized_pnl = None
    if action in ("SELL", "COVER", "TRIM") and avg_cost > 0:
        realized_pnl = (price - avg_cost) * qty

    return {
        "trade_total": trade_total,
        "pct_nav": pct_nav,
        "new_shares": new_shares,
        "new_avg_cost": round(new_avg_cost, 2) if new_avg_cost else 0,
        "new_position_pct": new_position_pct,
        "realized_pnl": round(realized_pnl, 2) if realized_pnl is not None else None,
        "is_full_exit": new_shares == 0 and action in ("SELL", "COVER", "TRIM"),
    }


# ── Step 3: Create trade .md file ──────────────────────────


def create_trade_file(
    action, ticker, qty, price, reason, calc, portfolio_data, decision_id=None
):
    """Write trade markdown file. Returns the file path."""
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Determine filename with sequence number for duplicates
    base_name = f"{today}_{action}_{ticker}"
    file_path = TRADES_DIR / f"{base_name}.md"
    seq = 2
    while file_path.exists():
        file_path = TRADES_DIR / f"{base_name}_{seq}.md"
        seq += 1

    # Format values
    def fmt(v, prefix="$", decimals=2):
        if v is None:
            return "N/A"
        return f"{prefix}{v:,.{decimals}f}" if prefix else f"{v:,.{decimals}f}"

    nav = portfolio_data.get("nav")
    thesis_path = RESEARCH_DIR / ticker / "thesis.md"
    thesis_exists = thesis_path.exists()

    # Build frontmatter
    frontmatter_lines = [
        "---",
        f"date: {today}",
        f"action: {action}",
        f"ticker: {ticker}",
        f"qty: {qty}",
        f"price: {price}",
        f"total: {calc['trade_total']:.2f}",
    ]
    if decision_id:
        frontmatter_lines.append(f"decision_id: {decision_id}")
    frontmatter_lines.append("---")

    content_lines = [
        *frontmatter_lines,
        "",
        f"# Trade: {action} {ticker}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Date | {now} |",
        f"| Action | {action} |",
        f"| Ticker | {ticker} |",
        f"| Qty | {fmt(qty, prefix='', decimals=0)} |",
        f"| Price | {fmt(price)} |",
        f"| Total | {fmt(calc['trade_total'])} |",
        f"| % of NAV | {fmt(calc['pct_nav'], prefix='', decimals=2) + '%' if calc['pct_nav'] is not None else 'N/A'} |",
        "",
        "## Position After Trade",
        f"- Shares: {fmt(calc['new_shares'], prefix='', decimals=0)}",
        f"- Avg Cost: {fmt(calc['new_avg_cost'])}",
        f"- % of NAV: {fmt(calc['new_position_pct'], prefix='', decimals=2) + '%' if calc['new_position_pct'] is not None else 'N/A'}",
    ]

    if calc.get("realized_pnl") is not None:
        content_lines.append(f"- Realized P&L: {fmt(calc['realized_pnl'])}")

    content_lines.extend(
        [
            "",
            "## Rationale",
            reason if reason else "(no reason provided)",
            "",
            "## Thesis Link",
            f"[{ticker} Thesis](../../research/companies/{ticker}/thesis.md)",
        ]
    )

    if not thesis_exists:
        content_lines.append(
            f"\n> **Note:** No thesis file exists for {ticker}. Consider creating one with `/thesis {ticker}`"
        )

    content_lines.extend(
        [
            "",
            "## Risk (fill manually)",
            "- Stop: $___",
            "- Target: $___",
            "",
            "---",
            "*Logged via /trade command*",
            "",
        ]
    )

    file_path.write_text("\n".join(content_lines), encoding="utf-8")
    return file_path


# ── Step 4: Update thesis.md Position History ───────────────


def update_thesis_md(ticker, action, qty, price, calc):
    """Append entry to Position History table in thesis.md. Returns status string."""
    thesis_path = RESEARCH_DIR / ticker / "thesis.md"
    if not thesis_path.exists():
        return "no_thesis_md"

    content = thesis_path.read_text(encoding="utf-8")
    today = date.today().isoformat()
    new_row = f"| {today} | {action} | {qty:.0f} | ${price:.2f} | ${calc['trade_total']:,.0f} | {calc['new_shares']:.0f} |"

    # Look for Position History section
    if "## Position History" in content:
        # Append row after the last table line
        lines = content.split("\n")
        insert_idx = None
        in_section = False
        for i, line in enumerate(lines):
            if "## Position History" in line:
                in_section = True
            elif in_section:
                if line.startswith("|"):
                    insert_idx = i + 1
                elif line.startswith("##") or (
                    line.strip() == "" and insert_idx is not None
                ):
                    break

        if insert_idx is not None:
            lines.insert(insert_idx, new_row)
            thesis_path.write_text("\n".join(lines), encoding="utf-8")
            return "updated"
        else:
            # Section exists but no table rows yet — add header + row
            for i, line in enumerate(lines):
                if "## Position History" in line:
                    table_header = [
                        "",
                        "| Date | Action | Qty | Price | Total | Shares After |",
                        "|------|--------|-----|-------|-------|-------------|",
                        new_row,
                    ]
                    lines[i] = lines[i] + "\n" + "\n".join(table_header)
                    break
            thesis_path.write_text("\n".join(lines), encoding="utf-8")
            return "created_table"
    else:
        # No Position History section — append one at end
        section = "\n\n## Position History\n\n"
        section += "| Date | Action | Qty | Price | Total | Shares After |\n"
        section += "|------|--------|-----|-------|-------|-------------|\n"
        section += new_row + "\n"
        thesis_path.write_text(content.rstrip() + section, encoding="utf-8")
        return "added_section"


# ── Step 5: Check/update thesis.yaml ────────────────────────


def update_thesis_yaml(ticker, action, calc):
    """Read conviction, auto-transition status. Returns dict with yaml info."""
    yaml_path = RESEARCH_DIR / ticker / "thesis.yaml"
    result = {
        "conviction": 5,
        "thesis_status": None,
        "status_changed": False,
        "old_status": None,
    }

    if not yaml_path.exists():
        return result

    try:
        import yaml
    except ImportError:
        result["warning"] = "PyYAML not installed, skipping thesis.yaml"
        return result

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        result["warning"] = f"Failed to read thesis.yaml: {e}"
        return result

    result["conviction"] = data.get("conviction", 5)
    result["thesis_status"] = data.get("thesis_status", data.get("status"))

    old_status = result["thesis_status"]
    result["old_status"] = old_status
    today_str = date.today().isoformat()
    changed = False

    if action in ("BUY", "ADD", "SHORT"):
        if old_status in ("watching", "past", None):
            data["thesis_status"] = "active"
            data["status_changed_at"] = today_str
            data["status_reason"] = f"Auto: Position opened via /trade {action}"
            changed = True

    elif action in ("SELL", "COVER"):
        if calc.get("is_full_exit") and old_status == "active":
            data["thesis_status"] = "past"
            data["status_changed_at"] = today_str
            data["status_reason"] = "Auto: Full position exit"
            changed = True

    # TRIM does not change status

    if changed:
        result["status_changed"] = True
        result["thesis_status"] = data["thesis_status"]
        try:
            yaml.dump(
                data,
                yaml_path.open("w", encoding="utf-8"),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        except Exception as e:
            result["warning"] = f"Failed to write thesis.yaml: {e}"

    return result


# ── Step 6: Record to SQLite ────────────────────────────────


def record_to_sqlite(ticker, action, reason, yaml_info, trigger="other"):
    """Insert decision record into investments.db. Returns decision_id or None."""
    try:
        from schemas import DecisionRecord
        from db_utils import init_db, insert_decision

        init_db()

        record = DecisionRecord(
            date=date.today().isoformat(),
            ticker=ticker,
            decision_type=ACTION_TO_DECISION_TYPE.get(action, "buy"),
            reasoning=reason,
            conviction=yaml_info.get("conviction", 5),
            thesis_link=f"PORTFOLIO/research/companies/{ticker}/thesis.md",
            trigger=trigger,
        )
        decision_id = insert_decision(record)
        return decision_id
    except Exception as e:
        return None, str(e)


# ── Step 7: Create follow-up task ───────────────────────────


def create_followup_task(action, ticker):
    """Create auto-task for thesis update. Returns task_id or None."""
    try:
        from task_manager import auto_create_task

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        task_id = auto_create_task(
            f"Update thesis after {action} {ticker}",
            source="post-trade",
            category="thesis",
            ticker=ticker,
            priority=2,
            due_at=tomorrow,
            estimated_minutes=20,
            dedup_key=f"post-trade-thesis-{ticker}-{date.today().isoformat()}",
        )
        return task_id
    except Exception:
        return None


# ── Main ────────────────────────────────────────────────────


def main():
    args = parse_args()

    warnings = []

    # 1. Fetch portfolio
    portfolio_data = fetch_portfolio(args.portfolio_url, args.ticker)
    if "error" in portfolio_data:
        warnings.append(f"Portfolio API: {portfolio_data['error']}")

    # 2. Calculate
    calc = calculate_trade(args.action, args.qty, args.price, portfolio_data)

    # 3. Check/update thesis.yaml (need conviction before SQLite)
    yaml_info = update_thesis_yaml(args.ticker, args.action, calc)
    if "warning" in yaml_info:
        warnings.append(yaml_info["warning"])

    # 4. Record to SQLite
    decision_id = None
    db_result = record_to_sqlite(args.ticker, args.action, args.reason, yaml_info)
    if isinstance(db_result, tuple):
        # Error case: (None, error_msg)
        warnings.append(f"SQLite: {db_result[1]}")
        decision_id = None
    else:
        decision_id = db_result

    # 5. Create trade .md file (with decision_id if available)
    trade_file = create_trade_file(
        args.action,
        args.ticker,
        args.qty,
        args.price,
        args.reason,
        calc,
        portfolio_data,
        decision_id,
    )

    # 6. Update thesis.md Position History
    thesis_md_status = update_thesis_md(
        args.ticker, args.action, args.qty, args.price, calc
    )

    # 7. Create follow-up task
    task_id = create_followup_task(args.action, args.ticker)

    # 8. Build JSON output
    output = {
        "status": "ok",
        "trade": {
            "action": args.action,
            "ticker": args.ticker,
            "qty": args.qty,
            "price": args.price,
            "total": calc["trade_total"],
            "pct_nav": round(calc["pct_nav"], 2)
            if calc["pct_nav"] is not None
            else None,
        },
        "position_after": {
            "shares": calc["new_shares"],
            "avg_cost": calc["new_avg_cost"],
            "pct_nav": round(calc["new_position_pct"], 2)
            if calc["new_position_pct"] is not None
            else None,
            "is_full_exit": calc["is_full_exit"],
        },
        "realized_pnl": calc.get("realized_pnl"),
        "thesis": {
            "md_status": thesis_md_status,
            "yaml_conviction": yaml_info.get("conviction", 5),
            "status": yaml_info.get("thesis_status"),
            "status_changed": yaml_info.get("status_changed", False),
            "old_status": yaml_info.get("old_status"),
        },
        "decision_id": str(decision_id)[:8] if decision_id else None,
        "decision_id_full": str(decision_id) if decision_id else None,
        "task_id": task_id,
        "trade_file": str(trade_file),
        "warnings": warnings,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
