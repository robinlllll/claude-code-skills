"""Agent 3: Kill Criteria Monitor.

Checks all thesis.yaml files for kill criteria status, staleness,
and cross-references with current portfolio positions for health alerts.
"""

import json
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_portfolio(config: dict) -> dict[str, dict]:
    """Load portfolio_data.json into {symbol: position_data} map."""
    pf_path = (
        config["portfolio_path"] / "portfolio_monitor" / "data" / "portfolio_data.json"
    )
    if not pf_path.exists():
        return {}
    with open(pf_path, encoding="utf-8") as f:
        data = json.load(f)
    return {p["symbol"]: p for p in data.get("positions", []) if p.get("symbol")}


def _load_all_theses(config: dict) -> list[dict]:
    """Load all thesis.yaml files with their paths."""
    companies_dir = config["portfolio_path"] / "research" / "companies"
    theses = []
    if not companies_dir.exists():
        return theses
    for thesis_path in companies_dir.glob("*/thesis.yaml"):
        try:
            with open(thesis_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["_path"] = str(thesis_path)
            data["_ticker"] = thesis_path.parent.name
            theses.append(data)
        except Exception:
            continue
    return theses


def run(config: dict, dry_run: bool = False, **kwargs) -> dict:
    """Run the kill criteria monitoring agent."""
    started = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    result = {
        "agent": "killcriteria",
        "status": "success",
        "started_at": started,
        "metrics": {},
        "issues": [],
        "actions_taken": [],
        "errors": [],
    }

    kc_cfg = config.get("kill_criteria", {})
    stale_days = kc_cfg.get("stale_check_days", 14)
    violation_hours = kc_cfg.get("violation_hours", 48)
    pnl_alert_pct = kc_cfg.get("pnl_alert_pct", -10)
    position_alert_pct = kc_cfg.get("position_alert_pct", 5)

    portfolio = _load_portfolio(config)
    theses = _load_all_theses(config)

    total_theses = len(theses)
    active_positions = len(portfolio)
    positions_with_thesis = 0
    positions_without_thesis = []

    p1_violations = []
    stale_kc = []
    drawdown_alerts = []
    concentration_alerts = []
    invalidation_breaches = []
    incomplete_theses = []
    tasks_created = []

    # Check each portfolio position has a thesis
    for symbol in portfolio:
        sym_str = str(symbol).upper()
        matching = [
            t
            for t in theses
            if str(t.get("_ticker", "")).upper() == sym_str
            or str(t.get("ticker", "")).upper() == sym_str
        ]
        if matching:
            positions_with_thesis += 1
        else:
            positions_without_thesis.append(symbol)

    # Check each thesis
    for thesis in theses:
        ticker = thesis.get("_ticker", "")
        thesis_path = thesis.get("_path", "")

        # Check if in active portfolio
        pos = None
        for sym, pdata in portfolio.items():
            sym_up = str(sym).upper()
            ticker_up = str(ticker).upper()
            thesis_ticker_up = str(thesis.get("ticker", "")).upper()
            if sym_up == ticker_up or thesis_ticker_up == sym_up:
                pos = pdata
                break

        # Staleness check: use file modification time as proxy for last_checked
        try:
            mtime = datetime.fromtimestamp(
                Path(thesis_path).stat().st_mtime, tz=timezone.utc
            )
            days_since_update = (now - mtime).days
        except Exception:
            days_since_update = 999

        if days_since_update > stale_days and pos:
            stale_kc.append(
                {
                    "type": "stale_kc",
                    "ticker": ticker,
                    "severity": "P2",
                    "days_since_update": days_since_update,
                    "path": thesis_path,
                    "detail": f"{ticker} thesis not updated in {days_since_update} days (active position)",
                }
            )

        # Incomplete thesis check (TODO placeholders)
        todo_fields = []
        for field in ["bear_case_1", "bear_case_2", "bull_case"]:
            val = thesis.get(field, "")
            if isinstance(val, str) and "TODO" in val.upper():
                todo_fields.append(field)
        if todo_fields and pos:
            incomplete_theses.append(
                {
                    "type": "incomplete_thesis",
                    "ticker": ticker,
                    "severity": "P2",
                    "fields": todo_fields,
                    "detail": f"{ticker} has TODO in: {', '.join(todo_fields)} (active position)",
                }
            )

        # Kill criteria status check
        kc_status = thesis.get("kill_criteria_status")
        if kc_status == "fail":
            fail_at = thesis.get("fail_detected_at")
            hours_since = 999
            if fail_at:
                try:
                    fail_dt = datetime.fromisoformat(str(fail_at)).replace(
                        tzinfo=timezone.utc
                    )
                    hours_since = (now - fail_dt).total_seconds() / 3600
                except Exception:
                    pass
            if hours_since > violation_hours:
                p1_violations.append(
                    {
                        "type": "P1_violation",
                        "ticker": ticker,
                        "severity": "P1",
                        "hours_since_fail": round(hours_since, 1),
                        "detail": f"{ticker} KC fail unresolved for {round(hours_since)}h (limit: {violation_hours}h)",
                    }
                )

        # Position health checks (only for active positions)
        if pos:
            # Drawdown alert
            pnl_pct = pos.get("total_pnl_pct", 0)
            if pnl_pct < pnl_alert_pct:
                drawdown_alerts.append(
                    {
                        "type": "drawdown_alert",
                        "ticker": ticker,
                        "severity": "P1",
                        "pnl_pct": pnl_pct,
                        "detail": f"{ticker} down {pnl_pct:.1f}% (threshold: {pnl_alert_pct}%)",
                    }
                )

            # Concentration alert
            nav_pct = pos.get("pct_of_nav", pos.get("ibkr_pct_of_nav", 0))
            if nav_pct > position_alert_pct:
                concentration_alerts.append(
                    {
                        "type": "concentration_alert",
                        "ticker": ticker,
                        "severity": "P2",
                        "pct_of_nav": nav_pct,
                        "detail": f"{ticker} is {nav_pct:.1f}% of NAV (threshold: {position_alert_pct}%)",
                    }
                )

            # Invalidation price breach
            inv_price = thesis.get("invalidation_price", 0)
            current_price = pos.get("mark_price", 0)
            if inv_price and current_price and current_price < inv_price:
                invalidation_breaches.append(
                    {
                        "type": "invalidation_breach",
                        "ticker": ticker,
                        "severity": "P1",
                        "invalidation_price": inv_price,
                        "current_price": current_price,
                        "detail": f"{ticker} at {current_price} below invalidation {inv_price}",
                    }
                )

    # Collect all issues
    all_issues = (
        p1_violations
        + invalidation_breaches
        + drawdown_alerts
        + stale_kc
        + concentration_alerts
        + incomplete_theses
    )
    result["issues"] = all_issues

    # Auto-create tasks for P1 items (if not dry run)
    if not dry_run:
        try:
            from shared.task_manager import auto_create_task

            for issue in p1_violations + invalidation_breaches + drawdown_alerts:
                task_id = auto_create_task(
                    title=f"[vault-intel] {issue['detail']}",
                    source="vault-intel",
                    category="research",
                    ticker=issue["ticker"],
                    priority=1 if issue["severity"] == "P1" else 2,
                    dedup_key=f"vault-intel-{issue['type']}-{issue['ticker']}",
                    description="Auto-detected by vault-intel kill criteria monitor",
                )
                if task_id:
                    tasks_created.append(
                        {
                            "type": "task_created",
                            "task_id": task_id,
                            "detail": issue["detail"],
                        }
                    )
        except Exception as e:
            result["errors"].append(f"Task creation failed: {e}")

    result["actions_taken"] = tasks_created
    result["metrics"] = {
        "total_theses": total_theses,
        "active_positions": active_positions,
        "positions_with_thesis": positions_with_thesis,
        "positions_without_thesis": len(positions_without_thesis),
        "p1_violations": len(p1_violations),
        "stale_kc": len(stale_kc),
        "drawdown_alerts": len(drawdown_alerts),
        "concentration_alerts": len(concentration_alerts),
        "invalidation_breaches": len(invalidation_breaches),
        "incomplete_theses": len(incomplete_theses),
        "tasks_created": len(tasks_created),
    }
    result["positions_without_thesis"] = positions_without_thesis

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kill Criteria Monitor Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    result = run(cfg, dry_run=args.dry_run)

    out_path = OUTPUT_DIR / "killcriteria_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Status: {result['status']}")
    m = result["metrics"]
    print(f"  Theses: {m['total_theses']}, Active positions: {m['active_positions']}")
    print(
        f"  P1 violations: {m['p1_violations']}, Stale: {m['stale_kc']}, "
        f"Drawdowns: {m['drawdown_alerts']}, Breaches: {m['invalidation_breaches']}"
    )
    if result["errors"]:
        print(f"  Errors: {result['errors']}")
