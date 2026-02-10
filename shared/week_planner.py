"""Week Planner — Data aggregation + scheduling for /week command.

Gathers tasks, calendar events, thesis staleness, pipeline health,
and portfolio context into a single JSON context. Also runs the
auto-scheduler via task_manager.auto_schedule_week().

Usage:
    python week_planner.py context [--week-start YYYY-MM-DD]
    python week_planner.py status [--week-start YYYY-MM-DD]
    python week_planner.py schedule --week-start YYYY-MM-DD
        --task-ids 1,2,3 [--blocked "Wed:afternoon"]
        [--capacity "Fri:240"] [--fixed "42:2026-02-10"]
        [--float "7,14"] [--earnings "AMAT:2026-02-12"]
"""

import argparse
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# UTF-8 output for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SHARED_DIR = Path(__file__).parent
HOME = Path.home()
VAULT = HOME / "Documents" / "Obsidian Vault"
CALENDAR_DIR = HOME / "CALENDAR-CONVERTER"
PORTFOLIO_DIR = HOME / "PORTFOLIO" / "research" / "companies"

sys.path.insert(0, str(HOME / ".claude" / "skills"))

from shared.task_manager import (
    auto_schedule_week,
    batch_schedule,
    get_week_tasks,
    list_tasks,
    pipeline_status,
    sorted_tasks,
    week_summary,
    _sort_score,
    _urgency_score,
)


# ── ICS Parsing ──────────────────────────────────────────────


def parse_ics_events(week_start: date, week_end: date) -> dict[str, list]:
    """Parse .ics files in CALENDAR-CONVERTER, filter for target week.

    Returns: {'YYYY-MM-DD': [{'time': 'HH:MM', 'summary': '...', 'category': '...', 'ticker': '...'}]}
    """
    result = {}
    if not CALENDAR_DIR.exists():
        return result

    for ics_file in CALENDAR_DIR.glob("*.ics"):
        try:
            content = ics_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Split into VEVENT blocks
        events = content.split("BEGIN:VEVENT")
        for event_block in events[1:]:  # Skip preamble
            end_idx = event_block.find("END:VEVENT")
            if end_idx == -1:
                continue
            block = event_block[:end_idx]

            # Parse DTSTART
            event_date = None
            event_time = None

            # All-day event
            m = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
            if m:
                event_date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
                event_time = "ALL_DAY"

            # Timed event
            if not event_date:
                m = re.search(r"DTSTART:(\d{8})T(\d{6})", block)
                if m:
                    ds = m.group(1)
                    ts = m.group(2)
                    event_date = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
                    event_time = f"{ts[:2]}:{ts[2:4]}"

            if not event_date:
                continue

            # Filter to target week
            try:
                ed = date.fromisoformat(event_date)
            except ValueError:
                continue
            if ed < week_start or ed > week_end:
                continue

            # Parse SUMMARY
            summary = ""
            m = re.search(r"SUMMARY:(.*?)(?:\r?\n(?!\s)|\Z)", block, re.DOTALL)
            if m:
                summary = m.group(1).strip().replace("\r\n ", "").replace("\n ", "")

            # Parse CATEGORIES
            category = ""
            m = re.search(r"CATEGORIES:(.*?)(?:\r?\n(?!\s)|\Z)", block, re.DOTALL)
            if m:
                category = m.group(1).strip()

            # Extract ticker from SUMMARY: [Type] TICKER-US [tag]
            ticker = None
            m_ticker = re.search(r"\]\s+([A-Z]{1,5})-(?:US|HK|CN)", summary)
            if m_ticker:
                ticker = m_ticker.group(1)

            event = {
                "time": event_time,
                "summary": summary,
                "category": category,
            }
            if ticker:
                event["ticker"] = ticker

            result.setdefault(event_date, []).append(event)

    # Sort each day by time
    for ds in result:
        result[ds] = sorted(result[ds], key=lambda e: e.get("time") or "99:99")

    return result


# ── Thesis Staleness ─────────────────────────────────────────


def scan_thesis_files() -> list[dict]:
    """Scan thesis files and return staleness info."""
    results = []
    if not PORTFOLIO_DIR.exists():
        return results

    for company_dir in PORTFOLIO_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        thesis_path = company_dir / "thesis.md"
        if not thesis_path.exists():
            continue

        ticker = company_dir.name
        mtime = datetime.fromtimestamp(thesis_path.stat().st_mtime)
        days_stale = (datetime.now() - mtime).days

        # Try to extract conviction from frontmatter
        conviction = None
        try:
            content = thesis_path.read_text(encoding="utf-8", errors="replace")[:500]
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    fm = content[3:end]
                    m = re.search(r"conviction:\s*(\w+)", fm, re.IGNORECASE)
                    if m:
                        conviction = m.group(1)
        except Exception:
            pass

        results.append({
            "ticker": ticker,
            "days_stale": days_stale,
            "path": str(thesis_path),
            "mtime": mtime.strftime("%Y-%m-%d"),
            "conviction": conviction,
        })

    return sorted(results, key=lambda x: x["days_stale"], reverse=True)


# ── Portfolio Tickers ────────────────────────────────────────


def get_portfolio_tickers() -> list[str]:
    """Get tickers from PORTFOLIO/research/companies/ directory."""
    if not PORTFOLIO_DIR.exists():
        return []
    return sorted([
        d.name for d in PORTFOLIO_DIR.iterdir()
        if d.is_dir() and d.name.isalpha() and d.name.isupper()
    ])


# ── Context Command ──────────────────────────────────────────


def gather_context(week_start: str) -> dict:
    """Full context JSON for /week plan."""
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)
    today = date.today()
    today_str = today.isoformat()

    working_days = []
    weekend_days = []
    for i in range(7):
        d = ws + timedelta(days=i)
        if d.weekday() < 5:
            working_days.append(d.isoformat())
        else:
            weekend_days.append(d.isoformat())

    # ── Tasks ──
    pending = list_tasks(status="pending", limit=200)
    in_progress = list_tasks(status="in_progress", limit=50)
    all_active = sorted_tasks(pending + in_progress)

    # Add sort_score to each task
    for t in all_active:
        t["sort_score"] = round(_sort_score(t), 2)

    overdue = [
        t for t in all_active
        if t.get("due_at") and t["due_at"][:10] < today_str
    ]

    # Already-scheduled tasks for this week
    already_scheduled = get_week_tasks(week_start)

    # Recurring tasks: those with recurrence field
    recurring = [t for t in all_active if t.get("recurrence")]

    # ── Calendar Events ──
    calendar_events = parse_ics_events(ws, we)

    # ── Thesis Staleness ──
    thesis_files = scan_thesis_files()

    # ── Pipeline Health ──
    pipe = pipeline_status(since_days=7)
    pipeline_health = {
        "total": pipe.get("total_items", 0),
        "unreviewed": pipe.get("unreviewed_count", 0),
        "bottleneck": pipe.get("bottleneck"),
        "bottleneck_rate": int(
            pipe.get("completion_rates", {}).get(pipe.get("bottleneck", ""), 0) * 100
        ) if pipe.get("bottleneck") else None,
        "by_source": pipe.get("by_type", {}),
    }

    # ── Portfolio ──
    portfolio_tickers = get_portfolio_tickers()

    # ── Signals ──
    thesis_alerts = [
        {
            "ticker": t["ticker"],
            "days_stale": t["days_stale"],
            "conviction": t.get("conviction"),
            "alert": "stale" if t["days_stale"] > 30 else None,
        }
        for t in thesis_files
        if t["days_stale"] > 30
    ]

    # Earnings relevance: cross-ref calendar tickers with portfolio/thesis
    thesis_tickers = {t["ticker"] for t in thesis_files}
    port_set = set(portfolio_tickers)
    earnings_relevance = []
    for ds, events in calendar_events.items():
        for ev in events:
            if ev.get("ticker") and "Earnings" in ev.get("category", ""):
                tk = ev["ticker"]
                in_port = tk in port_set
                has_thesis = tk in thesis_tickers
                rel = "HIGH" if in_port else ("MEDIUM" if has_thesis else "LOW")
                if rel != "LOW":
                    earnings_relevance.append({
                        "ticker": tk,
                        "date": ds,
                        "in_portfolio": in_port,
                        "has_thesis": has_thesis,
                        "relevance": rel,
                    })

    # Key deadlines (13F)
    key_deadlines = []
    q_deadlines = {
        "13F Q1": f"{ws.year}-05-15",
        "13F Q2": f"{ws.year}-08-14",
        "13F Q3": f"{ws.year}-11-14",
        "13F Q4": f"{ws.year}-02-14",
    }
    for label, dl_str in q_deadlines.items():
        try:
            dl = date.fromisoformat(dl_str)
            days_until = (dl - today).days
            if 0 <= days_until <= 14:
                key_deadlines.append({
                    "label": label,
                    "date": dl_str,
                    "days_until": days_until,
                })
        except ValueError:
            pass

    return {
        "week_start": ws.isoformat(),
        "week_end": we.isoformat(),
        "week_id": ws.strftime("%G-W%V"),
        "working_days": working_days,
        "weekend_days": weekend_days,
        "raw": {
            "tasks": {
                "pending": [t for t in all_active if t["status"] == "pending"],
                "in_progress": [t for t in all_active if t["status"] == "in_progress"],
                "overdue": overdue,
                "already_scheduled": already_scheduled,
                "rollovers": already_scheduled.get("ROLLOVER", []),
                "recurring_this_week": recurring,
            },
            "calendar_events": calendar_events,
            "thesis_files": thesis_files,
            "pipeline_health": pipeline_health,
            "portfolio_tickers": portfolio_tickers,
        },
        "signals": {
            "thesis_alerts": thesis_alerts,
            "earnings_relevance": earnings_relevance,
            "key_deadlines": key_deadlines,
        },
        "capacity": {
            "weekday_minutes": 480,
            "weekend_minutes": 240,
            "total_minutes": 480 * len(working_days) + 240 * len(weekend_days),
            "buffer_per_day": 60,
        },
    }


# ── Status Command ───────────────────────────────────────────


def gather_status(week_start: str) -> dict:
    """Current week progress: completed, remaining, rollovers."""
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)
    today = date.today()

    summary = week_summary(week_start)

    # Count completed tasks that were scheduled this week
    from shared.task_manager import get_db
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE status = 'done'
               AND scheduled_date >= ? AND scheduled_date <= ?""",
            (ws.isoformat(), we.isoformat()),
        ).fetchall()
        completed = [dict(r) for r in rows]
    finally:
        conn.close()

    # Remaining = scheduled but not done for today and future
    remaining = []
    for ds, day_info in summary["days"].items():
        if ds >= today.isoformat():
            for t in day_info["tasks"]:
                if t["status"] not in ("done", "cancelled"):
                    remaining.append(t)

    total_scheduled = len(completed) + len(remaining) + len(summary.get("rollovers", []))
    completion_pct = round(len(completed) / total_scheduled * 100) if total_scheduled else 0

    return {
        "week_start": week_start,
        "week_id": ws.strftime("%G-W%V"),
        "completed": completed,
        "completed_count": len(completed),
        "remaining": remaining,
        "remaining_count": len(remaining),
        "rollovers": summary.get("rollovers", []),
        "rollover_count": len(summary.get("rollovers", [])),
        "floating": summary.get("floating", []),
        "total_scheduled": total_scheduled,
        "completion_pct": completion_pct,
        "days": summary["days"],
    }


# ── Schedule Command ─────────────────────────────────────────


def run_schedule(
    week_start: str,
    task_ids: list[int],
    blocked: dict | None = None,
    capacity_overrides: dict | None = None,
    fixed: dict | None = None,
    float_ids: list[int] | None = None,
    earnings: list[dict] | None = None,
) -> dict:
    """Run auto_schedule_week and return results."""
    constraints = {}
    if blocked:
        constraints["blocked_slots"] = blocked
    if capacity_overrides:
        constraints["capacity_overrides"] = capacity_overrides
    if fixed:
        constraints["fixed_assignments"] = fixed
    if float_ids:
        constraints["float_ids"] = float_ids
    if earnings:
        constraints["earnings_events"] = earnings

    return auto_schedule_week(task_ids, week_start, constraints)


# ── ICS Export ───────────────────────────────────────────────


def generate_week_ics(
    week_start: str,
    schedule: dict,
    calendar_events: dict | None = None,
) -> Path:
    """Generate merged .ics with financial events + scheduled task blocks.

    Task UIDs: weekplan-{task_id}-{week_start}@robin-weekplanner
    """
    from shared.task_manager import get_task

    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CALENDAR_DIR / f"week_plan_{week_start}.ics"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Week Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Week Plan {week_start}",
        "X-WR-TIMEZONE:America/New_York",
    ]

    # Add financial events (passthrough from parsed ICS)
    if calendar_events:
        for ds, events in sorted(calendar_events.items()):
            for ev in events:
                uid = f"weekplan-event-{ds}-{hash(ev['summary']) & 0xFFFFFF:06x}@robin-weekplanner"
                ds_compact = ds.replace("-", "")
                if ev["time"] == "ALL_DAY":
                    lines.extend([
                        "",
                        "BEGIN:VEVENT",
                        f"UID:{uid}",
                        f"DTSTART;VALUE=DATE:{ds_compact}",
                        f"SUMMARY:{ev['summary']}",
                        f"CATEGORIES:{ev.get('category', '')}",
                        "END:VEVENT",
                    ])
                else:
                    time_compact = ev["time"].replace(":", "") + "00"
                    end_time = (
                        datetime.strptime(ev["time"], "%H:%M") + timedelta(hours=1)
                    ).strftime("%H%M00")
                    lines.extend([
                        "",
                        "BEGIN:VEVENT",
                        f"UID:{uid}",
                        f"DTSTART:{ds_compact}T{time_compact}",
                        f"DTEND:{ds_compact}T{end_time}",
                        f"SUMMARY:{ev['summary']}",
                        f"CATEGORIES:{ev.get('category', '')}",
                        "END:VEVENT",
                    ])

    # Add scheduled task blocks
    for ds, blocks in sorted(schedule.items()):
        ds_compact = ds.replace("-", "")
        for block in blocks:
            if not block.get("start"):
                continue
            tid = block["task_id"]
            uid = f"weekplan-{tid}-{week_start}@robin-weekplanner"
            start_compact = block["start"].replace(":", "") + "00"
            end_compact = block["end"].replace(":", "") + "00"

            task = get_task(tid)
            desc_parts = [f"Task ID: {tid}"]
            if task:
                desc_parts.append(f"Priority: P{task.get('priority', 3)}")
                desc_parts.append(f"Category: {task.get('category', 'general')}")
                if task.get("ticker"):
                    desc_parts.append(f"Ticker: {task['ticker']}")
            description = "\\n".join(desc_parts)

            ticker_str = f" [{block.get('ticker')}]" if block.get("ticker") else ""
            summary = f"[P{block['priority']} {block['category']}]{ticker_str} {block['title']}"

            lines.extend([
                "",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART:{ds_compact}T{start_compact}",
                f"DTEND:{ds_compact}T{end_compact}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"CATEGORIES:{block.get('category', 'general')}",
                "STATUS:TENTATIVE",
                "BEGIN:VALARM",
                "TRIGGER:-PT15M",
                "ACTION:DISPLAY",
                "DESCRIPTION:Task starting in 15 minutes",
                "END:VALARM",
                "BEGIN:VALARM",
                "TRIGGER:-PT60M",
                "ACTION:DISPLAY",
                "DESCRIPTION:Task starting in 1 hour",
                "END:VALARM",
                "END:VEVENT",
            ])

    lines.append("")
    lines.append("END:VCALENDAR")

    output_path.write_text("\r\n".join(lines), encoding="utf-8")
    return output_path


# ── Obsidian Export ──────────────────────────────────────────


def generate_week_markdown(
    week_start: str,
    context: dict,
    schedule_result: dict,
    revision: int = 1,
    focus_note: str = "",
) -> Path:
    """Generate Obsidian markdown for the week plan."""
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)
    week_id = ws.strftime("%G-W%V")

    plan_dir = VAULT / "写作" / "周计划"
    plan_dir.mkdir(parents=True, exist_ok=True)
    output_path = plan_dir / f"{week_start}_week_plan.md"

    schedule = schedule_result.get("schedule", {})
    deferred = schedule_result.get("deferred", [])
    floating = schedule_result.get("floating", [])
    per_day = schedule_result.get("per_day_utilization", {})
    total_pct = schedule_result.get("total_utilization_pct", 0)

    # Count total scheduled tasks
    total_tasks = sum(len(blocks) for blocks in schedule.values())
    total_est = sum(
        b.get("duration_minutes", 30)
        for blocks in schedule.values()
        for b in blocks
    )

    lines = [
        "---",
        f"created: {date.today().isoformat()}",
        "type: week-plan",
        f"week_id: {week_id}",
        f"week_start: {week_start}",
        f"week_end: {we.isoformat()}",
        "status: active",
        f"total_tasks: {total_tasks + len(floating)}",
        f"revision: {revision}",
        f"tags: [week-plan, {week_id}]",
        "---",
        "",
        f"# 周计划：{week_start} ~ {we.strftime('%m-%d')} ({week_id})",
        "",
    ]

    if focus_note:
        lines.append(f"> 本周重点：{focus_note}")
        lines.append("")

    # Overview table
    total_cap = context.get("capacity", {}).get("total_minutes", 2880)
    lines.extend([
        "## 本周概览",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 排程任务 | {total_tasks} (+ {len(floating)} floating) |",
        f"| 总预估 | {total_est // 60}h{total_est % 60}m / {total_cap // 60}h capacity ({total_pct}%) |",
        f"| Deferred | {len(deferred)} |",
        "",
    ])

    # Per-day schedules
    day_names = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    calendar_events = context.get("raw", {}).get("calendar_events", {})

    for ds in sorted(schedule.keys()):
        d = date.fromisoformat(ds)
        day_name = day_names.get(d.weekday(), "")
        blocks = schedule[ds]
        util = per_day.get(ds, {})
        used = util.get("used", 0)
        cap = util.get("capacity", 480)
        pct = util.get("pct", 0)

        lines.append(f"## {day_name} {d.strftime('%b %d')} ({ds})")
        lines.append("")
        lines.append(f"**负荷: {used}m / {cap}m ({pct}%) · buffer 保留 60m**")
        lines.append("")

        if blocks:
            lines.append("| 时间 | # | 任务 | 类别 | Ticker | 预估 |")
            lines.append("|------|---|------|------|--------|------|")
            for b in blocks:
                time_str = f"{b['start']}-{b['end']}" if b.get("start") else "TBD"
                ticker = b.get("ticker") or ""
                lines.append(
                    f"| {time_str} | {b['task_id']} | {b['title'][:45]} | "
                    f"{b.get('category', '')} | {ticker} | {b['duration_minutes']}m |"
                )

        # Add calendar events for this day
        day_events = calendar_events.get(ds, [])
        if day_events:
            lines.append(f"| **日历** | | | | | |")
            for ev in day_events:
                time_str = ev["time"] if ev["time"] != "ALL_DAY" else "全天"
                ticker = ev.get("ticker", "")
                lines.append(
                    f"| {time_str} | - | {ev['summary'][:45]} | "
                    f"{ev.get('category', '')} | {ticker} | - |"
                )

        if not blocks and not day_events:
            lines.append("*无安排*")

        lines.append("")

    # Floating tasks
    if floating:
        lines.extend([
            "## Floating Tasks (any day)",
            "",
            "| # | 任务 | 类别 | 预估 |",
            "|---|------|------|------|",
        ])
        for t in floating:
            lines.append(
                f"| {t['id']} | {t['title'][:45]} | {t.get('category', '')} | "
                f"{t.get('estimated_minutes', 30)}m |"
            )
        lines.append("")

    # Deferred tasks
    if deferred:
        lines.extend([
            "## Deferred (not this week)",
            "",
            "| # | 任务 | 预估 | 原因 |",
            "|---|------|------|------|",
        ])
        for t in deferred:
            lines.append(
                f"| {t['id']} | {t['title'][:45]} | "
                f"{t.get('estimated_minutes', 30)}m | capacity exceeded |"
            )
        lines.append("")

    # Revision history
    lines.extend([
        "## Revision History",
        "",
        f"### v{revision} ({date.today().isoformat()})",
        focus_note or "初始计划。",
        "",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ── CLI ──────────────────────────────────────────────────────


def _default_week_start() -> str:
    """Monday of current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _parse_blocked(s: str) -> dict:
    """Parse 'Wed:afternoon,Thu:morning' → {'YYYY-MM-DD': ['afternoon'], ...}"""
    if not s:
        return {}
    day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    result = {}
    for part in s.split(","):
        parts = part.strip().split(":")
        if len(parts) != 2:
            continue
        day_name, slot = parts[0].strip(), parts[1].strip()
        # If it's a date already, use it
        if "-" in day_name:
            result.setdefault(day_name, []).append(slot)
        elif day_name in day_map:
            # Resolve to date relative to week start (set later)
            result.setdefault(day_name, []).append(slot)
    return result


def _resolve_day_names(blocked: dict, week_start: str) -> dict:
    """Convert day names to actual dates."""
    day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    ws = date.fromisoformat(week_start)
    resolved = {}
    for key, slots in blocked.items():
        if key in day_map:
            d = ws + timedelta(days=day_map[key])
            resolved[d.isoformat()] = slots
        else:
            resolved[key] = slots
    return resolved


def _parse_capacity(s: str) -> dict:
    """Parse 'Fri:240,Thu:360' → {'YYYY-MM-DD': 240, ...}"""
    if not s:
        return {}
    result = {}
    for part in s.split(","):
        parts = part.strip().split(":")
        if len(parts) != 2:
            continue
        result[parts[0].strip()] = int(parts[1].strip())
    return result


def _parse_fixed(s: str) -> dict:
    """Parse '42:2026-02-10,15:2026-02-14' → {42: '2026-02-10', ...}"""
    if not s:
        return {}
    result = {}
    for part in s.split(","):
        parts = part.strip().split(":")
        if len(parts) >= 2:
            tid = int(parts[0].strip())
            # Rejoin remaining parts (date has colons... actually no, dates use -)
            d = ":".join(parts[1:]).strip()
            result[tid] = d
    return result


def _parse_earnings(s: str) -> list[dict]:
    """Parse 'AMAT:2026-02-12,NVDA:2026-02-13' → [{'ticker': 'AMAT', 'date': '...'}]"""
    if not s:
        return []
    result = []
    for part in s.split(","):
        parts = part.strip().split(":")
        if len(parts) >= 2:
            result.append({"ticker": parts[0].strip(), "date": ":".join(parts[1:]).strip()})
    return result


def main():
    parser = argparse.ArgumentParser(description="Week Planner")
    subparsers = parser.add_subparsers(dest="command")

    # context
    ctx_p = subparsers.add_parser("context", help="Full context JSON")
    ctx_p.add_argument("--week-start", help="Monday (YYYY-MM-DD)")

    # status
    stat_p = subparsers.add_parser("status", help="Week progress")
    stat_p.add_argument("--week-start", help="Monday (YYYY-MM-DD)")

    # schedule
    sched_p = subparsers.add_parser("schedule", help="Auto-schedule")
    sched_p.add_argument("--week-start", help="Monday (YYYY-MM-DD)")
    sched_p.add_argument("--task-ids", required=True, help="Comma-separated task IDs")
    sched_p.add_argument("--blocked", default="", help="Blocked slots: Wed:afternoon")
    sched_p.add_argument("--capacity", default="", help="Capacity overrides: Fri:240")
    sched_p.add_argument("--fixed", default="", help="Fixed assignments: 42:2026-02-10")
    sched_p.add_argument("--float", default="", help="Floating task IDs: 7,14")
    sched_p.add_argument("--earnings", default="", help="Earnings events: AMAT:2026-02-12")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    ws = getattr(args, "week_start", None) or _default_week_start()

    if args.command == "context":
        ctx = gather_context(ws)
        print(json.dumps(ctx, ensure_ascii=False, indent=2, default=str))

    elif args.command == "status":
        status = gather_status(ws)
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))

    elif args.command == "schedule":
        task_ids = [int(x.strip()) for x in args.task_ids.split(",") if x.strip()]
        blocked = _resolve_day_names(_parse_blocked(args.blocked), ws)
        capacity = _resolve_day_names(
            {k: int(v) for k, v in _parse_capacity(args.capacity).items()}, ws
        ) if args.capacity else {}
        fixed = _parse_fixed(args.fixed)
        float_ids = [int(x.strip()) for x in args.float.split(",") if x.strip()] if args.float else []
        earnings = _parse_earnings(args.earnings)

        result = run_schedule(
            ws, task_ids,
            blocked=blocked,
            capacity_overrides=capacity,
            fixed=fixed,
            float_ids=float_ids,
            earnings=earnings,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
