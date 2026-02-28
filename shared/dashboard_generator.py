#!/usr/bin/env python3
"""
Dashboard Generator: Auto-schedule tasks into free calendar slots and generate HTML dashboard.

Reads pending/in-progress tasks from SQLite DB and calendar events from Google Calendar MCP,
performs priority-first bin packing into free time slots, and outputs a complete JSON payload
suitable for injecting into an HTML template.

Features:
- Auto-schedules tasks into free calendar slots using priority-first bin packing
- Generates comprehensive dashboard data with stats and scheduled blocks
- Injects JSON data into HTML template placeholders
"""

import json
import sqlite3
import sys
import argparse
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import io

# UTF-8 stdout wrapper (skip when imported by dashboard_server to avoid I/O crashes)
import os

if sys.version_info[0] >= 3 and not os.environ.get("DASHBOARD_NO_STDOUT_WRAP"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ============================================================================
# ICS File Parsing
# ============================================================================

import re

ICS_DEFAULT_DIR = Path.home() / "CALENDAR-CONVERTER"


def parse_ics_to_gcal_json(
    ics_dir: Path,
    week_start: datetime,
    week_end: datetime,
) -> str:
    """
    Parse all .ics files in a directory and return Google Calendar API-format JSON.
    Filters events to the given week range.

    Returns JSON string of events list (same format as Google Calendar MCP).
    """
    all_events = []
    ics_files = sorted(ics_dir.glob("*.ics"))

    for ics_file in ics_files:
        try:
            content = ics_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Split into VEVENT blocks
        vevent_blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.DOTALL)

        for block in vevent_blocks:
            event = _parse_vevent_block(block)
            if event is None:
                continue

            # Filter to target week
            evt_start = event.get("_start_dt")
            if evt_start is None:
                continue
            if evt_start.date() < week_start.date():
                continue
            if evt_start.date() > week_end.date():
                continue

            # Remove internal field
            event.pop("_start_dt", None)
            all_events.append(event)

    return json.dumps(all_events)


def _parse_vevent_block(block: str) -> Optional[Dict[str, Any]]:
    """Parse a single VEVENT block into Google Calendar API format."""
    lines = _unfold_ics_lines(block.strip().split("\n"))

    props = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Handle properties with params like DTSTART;VALUE=DATE:20260223
        if ":" in line:
            key_part, _, value = line.partition(":")
            # key_part may contain params: DTSTART;VALUE=DATE
            key = key_part.split(";")[0].upper()
            params = key_part.upper()
            props[key] = (value.strip(), params)

    if "DTSTART" not in props:
        return None

    dtstart_val, dtstart_params = props["DTSTART"]
    dtend_val, dtend_params = props.get("DTEND", (None, ""))
    summary = props.get("SUMMARY", ("(No title)", ""))[0]
    location = props.get("LOCATION", ("", ""))[0]
    description = props.get("DESCRIPTION", ("", ""))[0]
    uid = props.get("UID", ("", ""))[0]

    # Parse start
    start_obj, start_dt = _ics_dt_to_gcal(dtstart_val, dtstart_params)
    if start_dt is None:
        return None

    # Parse end
    if dtend_val:
        end_obj, _ = _ics_dt_to_gcal(dtend_val, dtend_params)
    else:
        # Default: 1 hour after start
        end_dt = start_dt + timedelta(hours=1)
        if "VALUE=DATE" in dtstart_params:
            end_obj = {"date": end_dt.strftime("%Y-%m-%d")}
        else:
            end_obj = {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S")}

    return {
        "id": uid,
        "summary": summary,
        "start": start_obj,
        "end": end_obj,
        "location": location,
        "description": description,
        "_start_dt": start_dt,
    }


def _ics_dt_to_gcal(
    value: str, params: str
) -> Tuple[Dict[str, str], Optional[datetime]]:
    """Convert an ICS datetime value to Google Calendar format dict + datetime."""
    if "VALUE=DATE" in params:
        # All-day: 20260223
        try:
            dt = datetime.strptime(value[:8], "%Y%m%d")
            return {"date": dt.strftime("%Y-%m-%d")}, dt
        except ValueError:
            return {}, None

    # DateTime: 20260223T090000 or 20260223T090000Z
    value = value.replace("Z", "")
    try:
        dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S")}, dt
    except ValueError:
        return {}, None


def _unfold_ics_lines(lines: List[str]) -> List[str]:
    """Unfold RFC 5545 continuation lines (lines starting with space/tab)."""
    result = []
    for line in lines:
        if line.startswith((" ", "\t")) and result:
            result[-1] += line[1:]
        else:
            result.append(line)
    return result


# ============================================================================
# Constants
# ============================================================================

WORK_START = time(7, 0)  # 7 AM
WORK_END = time(22, 0)  # 10 PM
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)
AFTERNOON_START = time(13, 0)
TASK_BUFFER_MINUTES = 10
DEEP_WORK_CATEGORIES = {"research", "thesis", "review", "analysis"}
PRIORITY_NAMES = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
STATUS_DISPLAY = {
    "pending": "Pending",
    "in_progress": "In Progress",
    "done": "Done",
    "cancelled": "Cancelled",
}


# ============================================================================
# Core Data Structures
# ============================================================================


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Create and return a database connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_tasks(db_path: str, statuses: List[str]) -> List[Dict[str, Any]]:
    """Load tasks from database with given statuses."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    placeholders = ",".join("?" * len(statuses))
    query = f"""
        SELECT * FROM tasks
        WHERE status IN ({placeholders})
        ORDER BY priority ASC, due_at ASC
    """
    cursor.execute(query, statuses)
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        task = dict(row)
        # Parse metadata if it's a string
        if isinstance(task.get("metadata"), str):
            try:
                task["metadata"] = json.loads(task["metadata"])
            except (json.JSONDecodeError, TypeError):
                task["metadata"] = {}
        else:
            task["metadata"] = task.get("metadata") or {}

        tasks.append(task)

    return tasks


def load_completed_tasks(db_path: str, days: int = 7) -> List[Dict[str, Any]]:
    """Load completed tasks from the last N days."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cutoff_date = datetime.now() - timedelta(days=days)

    query = """
        SELECT * FROM tasks
        WHERE status = 'done' AND completed_at >= ?
        ORDER BY completed_at DESC
    """
    cursor.execute(query, (cutoff_date.isoformat(),))
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        task = dict(row)
        if isinstance(task.get("metadata"), str):
            try:
                task["metadata"] = json.loads(task["metadata"])
            except (json.JSONDecodeError, TypeError):
                task["metadata"] = {}
        else:
            task["metadata"] = task.get("metadata") or {}

        tasks.append(task)

    return tasks


def normalize_calendar_events(events_json: str) -> List[Dict[str, Any]]:
    """
    Parse and normalize calendar events from JSON string.
    Expected format: Google Calendar events with start/end as dateTime or date.
    """
    try:
        events = json.loads(events_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(events, list):
        events = [events] if events else []

    normalized = []
    for event in events:
        start_obj = event.get("start", {})
        end_obj = event.get("end", {})
        start_dt = parse_event_time(start_obj)
        end_dt = parse_event_time(end_obj)
        all_day = "date" in start_obj and "dateTime" not in start_obj

        normalized_event = {
            "id": event.get("id", ""),
            "summary": event.get("summary", "(No title)"),
            "start_time": start_dt.isoformat() if start_dt else None,
            "end_time": end_dt.isoformat() if end_dt else None,
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "all_day": all_day,
            "color": event.get("colorId", ""),
        }
        normalized.append(normalized_event)

    return normalized


def parse_event_time(time_obj: Dict[str, Any]) -> Optional[datetime]:
    """Parse Google Calendar time object (dateTime or date) to datetime."""
    if not time_obj:
        return None

    if "dateTime" in time_obj:
        try:
            # Parse ISO 8601 with or without timezone
            dt_str = time_obj["dateTime"]
            # Remove timezone info for simplicity (assume local)
            if "T" in dt_str:
                if "+" in dt_str:
                    dt_str = dt_str.split("+")[0]
                elif "Z" in dt_str:
                    dt_str = dt_str.replace("Z", "")
            return datetime.fromisoformat(dt_str)
        except (ValueError, KeyError):
            return None

    if "date" in time_obj:
        try:
            return datetime.fromisoformat(time_obj["date"])
        except (ValueError, KeyError):
            return None

    return None


# ============================================================================
# Calendar Analysis & Scheduling
# ============================================================================


def build_busy_map(
    events: List[Dict[str, Any]], date_range: Tuple[datetime, datetime]
) -> Dict[str, List[Tuple[time, time]]]:
    """
    Build a map of busy time slots for each day.
    Returns: {date_str: [(start_time, end_time), ...]}
    """
    busy_map = {}

    start_date, end_date = date_range
    current = start_date.date()
    while current <= end_date.date():
        busy_map[current.isoformat()] = []
        current += timedelta(days=1)

    for event in events:
        # Events are already normalized with start_time/end_time as ISO strings
        start_str = event.get("start_time")
        end_str = event.get("end_time")
        if not start_str or not end_str:
            continue
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            continue

        # Handle all-day events by treating as 7am-10pm
        if start.time() == time(0, 0) and end.time() == time(0, 0):
            start = start.replace(hour=7, minute=0)
            end = end.replace(hour=22, minute=0)

        current = start.date()
        while current <= min(end.date(), end_date.date()):
            date_str = current.isoformat()
            if date_str in busy_map:
                if current == start.date():
                    slot_start = start.time()
                else:
                    slot_start = WORK_START

                if current == end.date():
                    slot_end = end.time()
                else:
                    slot_end = WORK_END

                busy_map[date_str].append((slot_start, slot_end))

            current += timedelta(days=1)

    # Sort and merge overlapping slots for each day
    for date_str in busy_map:
        slots = sorted(busy_map[date_str])
        merged = []
        for start, end in slots:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        busy_map[date_str] = merged

    return busy_map


def find_free_slots(
    busy_times: List[Tuple[time, time]], duration_minutes: int
) -> List[Tuple[time, time]]:
    """Find free slots in a day's schedule for a given task duration."""
    if not busy_times:
        return [(WORK_START, WORK_END)]

    # Sort busy times
    busy = sorted(busy_times)

    free_slots = []
    current = WORK_START

    for busy_start, busy_end in busy:
        if current < busy_start:
            free_slots.append((current, busy_start))
        current = max(current, busy_end)

    if current < WORK_END:
        free_slots.append((current, WORK_END))

    # Filter slots by duration
    duration = timedelta(minutes=duration_minutes)
    return [
        (start, end)
        for start, end in free_slots
        if (
            datetime.combine(datetime.today().date(), end)
            - datetime.combine(datetime.today().date(), start)
        )
        >= duration
    ]


def auto_schedule_tasks(
    tasks: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    week_start: datetime,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Auto-schedule tasks into free calendar slots using priority-first bin packing.
    Deep work (research/thesis/review) prefers morning, admin prefers afternoon.
    Lunch break 12:00-13:00 is always blocked.

    Returns:
        (scheduled_blocks, unscheduled_tasks)
    """
    week_end = week_start + timedelta(days=7)
    busy_map = build_busy_map(events, (week_start, week_end))

    # Add lunch break to every day in the week
    iter_date = week_start.date()
    while iter_date <= week_end.date():
        ds = iter_date.isoformat()
        if ds not in busy_map:
            busy_map[ds] = []
        busy_map[ds].append((LUNCH_START, LUNCH_END))
        slots = sorted(busy_map[ds])
        merged = []
        for s, e in slots:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        busy_map[ds] = merged
        iter_date += timedelta(days=1)

    scheduled_blocks = []
    unscheduled_tasks = []

    for task in tasks:
        estimated_minutes = task.get("estimated_minutes", 30)
        due_date = None

        # Try to parse due_at
        if task.get("due_at"):
            try:
                due_dt = datetime.fromisoformat(task["due_at"])
                due_date = due_dt.date()
            except (ValueError, TypeError):
                pass

        # Build list of preferred dates (due date first, then rest of week)
        preferred_dates = []
        if due_date and week_start.date() <= due_date <= week_end.date():
            preferred_dates.append(due_date)

        # Add remaining weekdays
        iter_date = week_start.date()
        while iter_date <= week_end.date():
            if iter_date not in preferred_dates and iter_date.weekday() < 5:
                preferred_dates.append(iter_date)
            iter_date += timedelta(days=1)

        # Determine preferred time-of-day based on category
        category = task.get("category", "general").lower()
        is_deep_work = category in DEEP_WORK_CATEGORIES

        scheduled = False
        for date in preferred_dates:
            date_str = date.isoformat()
            busy_times = busy_map.get(date_str, [])
            slot_duration = estimated_minutes + TASK_BUFFER_MINUTES
            free_slots = find_free_slots(busy_times, slot_duration)

            if not free_slots:
                continue

            # Choose slot based on task type
            chosen_slot = None
            if is_deep_work:
                morning_slots = [(s, e) for s, e in free_slots if s < LUNCH_START]
                chosen_slot = morning_slots[0] if morning_slots else None
            else:
                afternoon_slots = [
                    (s, e) for s, e in free_slots if s >= AFTERNOON_START
                ]
                chosen_slot = afternoon_slots[0] if afternoon_slots else None

            # Fallback: use any available slot
            if not chosen_slot:
                chosen_slot = free_slots[0]

            start_time = chosen_slot[0]
            end_time = (
                datetime.combine(date, start_time)
                + timedelta(minutes=estimated_minutes)
            ).time()

            scheduled_blocks.append(
                {
                    "id": task["id"],
                    "title": task["title"],
                    "priority": task["priority"],
                    "priority_name": PRIORITY_NAMES.get(task["priority"], "Unknown"),
                    "category": task.get("category", "general"),
                    "ticker": task.get("ticker"),
                    "estimated_minutes": estimated_minutes,
                    "scheduled_date": date_str,
                    "scheduled_start": start_time.isoformat(),
                    "scheduled_end": end_time.isoformat(),
                }
            )

            # Mark as busy (task + buffer) for subsequent tasks
            end_with_buffer = (
                datetime.combine(date, start_time) + timedelta(minutes=slot_duration)
            ).time()
            busy_map[date_str].append((start_time, end_with_buffer))
            busy_map[date_str] = sorted(busy_map[date_str])

            scheduled = True
            break

        if not scheduled:
            unscheduled_tasks.append(task)

    return scheduled_blocks, unscheduled_tasks


# ============================================================================
# Dashboard Data Building
# ============================================================================


def build_dashboard_data(
    db_path: str,
    calendar_json: str,
    week_start: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build complete dashboard data payload.

    Returns a dict with:
    - generated_at, today, week_start, week_end, month_start, month_end
    - calendar_events (normalized)
    - tasks (all pending/in_progress)
    - completed_tasks (done in last 7 days)
    - scheduled_blocks (auto-scheduled)
    - unscheduled_tasks
    - overdue_tasks, today_tasks
    - stats
    """
    now = datetime.now()

    # SQLite WAL mode doesn't work on FUSE filesystems — copy DB to /tmp if needed
    import shutil
    import tempfile

    original_db_path = db_path
    try:
        import sqlite3 as _sq

        _conn = _sq.connect(db_path, timeout=5)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("SELECT count(*) FROM tasks")
        _conn.close()
    except Exception:
        tmp_dir = tempfile.mkdtemp(prefix="dashboard_gen_")
        db_path = str(Path(tmp_dir) / "task_manager.db")
        shutil.copy2(original_db_path, db_path)

    if week_start is None:
        # Default to current week start (Monday)
        days_since_monday = now.weekday()
        week_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

    # Load tasks
    active_tasks = load_tasks(db_path, ["pending", "in_progress"])
    completed_tasks = load_completed_tasks(db_path, days=7)

    # Normalize calendar events
    events = normalize_calendar_events(calendar_json)

    # Auto-schedule tasks
    scheduled_blocks, unscheduled_tasks = auto_schedule_tasks(
        active_tasks, events, week_start
    )

    # Identify overdue and today tasks
    today = now.date()
    overdue_tasks = []
    today_tasks = []

    for task in active_tasks:
        if task.get("due_at"):
            try:
                due_dt = datetime.fromisoformat(task["due_at"])
                due_date = due_dt.date()

                if due_date < today:
                    overdue_tasks.append(task)
                elif due_date == today:
                    today_tasks.append(task)
            except (ValueError, TypeError):
                pass

    # Build stats
    total_pending = len([t for t in active_tasks if t["status"] == "pending"])
    in_progress = len([t for t in active_tasks if t["status"] == "in_progress"])
    scheduled_count = len(scheduled_blocks)
    unscheduled_count = len(unscheduled_tasks)

    stats = {
        "total_pending": total_pending,
        "in_progress": in_progress,
        "overdue": len(overdue_tasks),
        "due_today": len(today_tasks),
        "completed_this_week": len(completed_tasks),
        "scheduled": scheduled_count,
        "unscheduled": unscheduled_count,
        "total_active": len(active_tasks),
    }

    return {
        "generated_at": now.isoformat(),
        "today": today.isoformat(),
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "month_start": month_start.date().isoformat(),
        "month_end": month_end.date().isoformat(),
        "calendar_events": events,
        "tasks": [dict(t) for t in active_tasks],
        "completed_tasks": [dict(t) for t in completed_tasks],
        "scheduled_blocks": scheduled_blocks,
        "unscheduled_tasks": [dict(t) for t in unscheduled_tasks],
        "overdue_tasks": [dict(t) for t in overdue_tasks],
        "today_tasks": [dict(t) for t in today_tasks],
        "stats": stats,
    }


# ============================================================================
# HTML Template Injection
# ============================================================================


def inject_data_into_template(
    template_path: str, dashboard_data: Dict[str, Any]
) -> str:
    """Read HTML template and inject dashboard data JSON."""
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Serialize data to JSON
    data_json = json.dumps(dashboard_data, indent=2, default=str)

    # Replace placeholder
    html_content = html_content.replace("__DASHBOARD_DATA__", data_json)

    return html_content


# ============================================================================
# CLI Interface
# ============================================================================


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Dashboard generator: Auto-schedule tasks and generate HTML dashboard"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # 'generate' command
    gen_parser = subparsers.add_parser("generate", help="Generate dashboard")
    gen_parser.add_argument(
        "--calendar-json",
        type=str,
        default="[]",
        help="Calendar events as JSON string",
    )
    gen_parser.add_argument(
        "--week-start",
        type=str,
        default=None,
        help="Week start date (YYYY-MM-DD)",
    )
    gen_parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="Path to HTML template (if not provided, outputs JSON only)",
    )
    gen_parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output file path",
    )
    gen_parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to task_manager.db (auto-detected if not provided)",
    )
    gen_parser.add_argument(
        "--ics-dir",
        type=str,
        default=None,
        help="Directory containing .ics files (auto-detected: ~/CALENDAR-CONVERTER)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Auto-detect DB path if not provided
    if args.db is None:
        # Try common paths
        possible_paths = [
            Path.home() / ".claude" / "skills" / "shared" / "data" / "task_manager.db",
            Path(
                "/sessions/sharp-great-einstein/mnt/thisi/.claude/skills/shared/data/task_manager.db"
            ),
        ]
        args.db = None
        for p in possible_paths:
            if p.exists():
                args.db = p
                break
        if args.db is None:
            args.db = possible_paths[0]  # Default to first path if none exists
    else:
        args.db = Path(args.db)

    if not args.db.exists():
        print(f"Error: Database not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    # Parse week-start if provided
    week_start = None
    if args.week_start:
        try:
            week_start = datetime.fromisoformat(args.week_start)
        except ValueError:
            print("Error: Invalid date format. Use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

    # Auto-resolve calendar data: --calendar-json takes priority, then --ics-dir
    calendar_json = args.calendar_json
    if calendar_json == "[]":
        # No explicit calendar JSON — try .ics auto-parse
        ics_dir = Path(args.ics_dir) if args.ics_dir else ICS_DEFAULT_DIR
        if ics_dir.exists() and list(ics_dir.glob("*.ics")):
            ws = week_start or (
                datetime.now() - timedelta(days=datetime.now().weekday())
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            we = ws + timedelta(days=6, hours=23, minutes=59, seconds=59)
            calendar_json = parse_ics_to_gcal_json(ics_dir, ws, we)
            try:
                n = len(json.loads(calendar_json))
            except Exception:
                n = 0
            print(f"Auto-loaded {n} events from .ics files in {ics_dir}")

    # Build dashboard data
    try:
        dashboard_data = build_dashboard_data(
            str(args.db),
            calendar_json,
            week_start,
        )
    except Exception as e:
        print(f"Error building dashboard data: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Auto-detect template if not provided
    if not args.template:
        auto_template = (
            Path(__file__).parent / "dashboard_templates" / "dashboard_template.html"
        )
        if auto_template.exists():
            args.template = str(auto_template)

    try:
        if args.template:
            # Inject data into template
            template_path = Path(args.template)
            if not template_path.exists():
                print(f"Error: Template not found at {template_path}", file=sys.stderr)
                sys.exit(1)

            html_output = inject_data_into_template(str(template_path), dashboard_data)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_output)
            print(f"Dashboard HTML generated: {output_path}")
        else:
            # Output JSON only
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(dashboard_data, f, indent=2, default=str)
            print(f"Dashboard JSON generated: {output_path}")

    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
