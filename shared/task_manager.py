"""Task Manager & Ingestion Pipeline Tracker.

Centralized task management for the investment workflow:
- Task CRUD with priority-urgency scoring
- Daily plan generation with time blocks
- Weekly scheduling with auto bin-packing
- ICS calendar export with VALARM reminders
- Ingestion pipeline stage tracking
- Auto-task generation with dedup

Usage:
    python task_manager.py add "Review PM thesis" --priority 1 --ticker PM --due 2026-02-15 --est 45
    python task_manager.py list [--status pending] [--ticker PM] [--category research]
    python task_manager.py done 3
    python task_manager.py cancel 5
    python task_manager.py plan [--date 2026-02-10] [--ics]
    python task_manager.py calendar [--recurring]
    python task_manager.py pipeline [--type podcast] [--attention wikilinks] [--days 30]
    python task_manager.py week [--start YYYY-MM-DD]
    python task_manager.py week schedule TASK_ID DATE|FLOAT
    python task_manager.py week clear [--start YYYY-MM-DD]
"""

import argparse
import io
import json
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────

SHARED_DIR = Path(__file__).parent
DATA_DIR = SHARED_DIR / "data"
TASK_DB = DATA_DIR / "task_manager.db"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
CALENDAR_DIR = Path.home() / "CALENDAR-CONVERTER"

# ── Database ─────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    """Get connection to task manager database, creating tables if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TASK_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 2,
            status TEXT NOT NULL DEFAULT 'pending',
            category TEXT DEFAULT 'general',
            ticker TEXT,
            due_at TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            source TEXT DEFAULT 'manual',
            recurrence TEXT,
            estimated_minutes INTEGER DEFAULT 30,
            dedup_key TEXT,
            metadata TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
            ON tasks(status, priority, due_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_ticker ON tasks(ticker);
        CREATE INDEX IF NOT EXISTS idx_tasks_dedup ON tasks(dedup_key, created_at);

        CREATE TABLE IF NOT EXISTS ingestion_pipeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_key TEXT NOT NULL UNIQUE,
            note_id TEXT,
            item_type TEXT NOT NULL,
            item_title TEXT DEFAULT '',
            source_platform TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            obsidian_path TEXT,
            has_frontmatter INTEGER NOT NULL DEFAULT 0,
            has_tickers INTEGER NOT NULL DEFAULT 0,
            has_framework_tags INTEGER NOT NULL DEFAULT 0,
            has_wikilinks INTEGER NOT NULL DEFAULT 0,
            is_reviewed INTEGER NOT NULL DEFAULT 0,
            frontmatter_at TEXT,
            tickers_at TEXT,
            framework_at TEXT,
            wikilinks_at TEXT,
            reviewed_at TEXT,
            tickers_found TEXT DEFAULT '[]',
            framework_sections TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_type
            ON ingestion_pipeline(item_type);
        CREATE INDEX IF NOT EXISTS idx_pipeline_reviewed
            ON ingestion_pipeline(is_reviewed);
        CREATE INDEX IF NOT EXISTS idx_pipeline_ingested
            ON ingestion_pipeline(ingested_at);
        CREATE INDEX IF NOT EXISTS idx_pipeline_note_id
            ON ingestion_pipeline(note_id);

        CREATE TABLE IF NOT EXISTS open_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            question TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            context TEXT,
            source_note TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            answered_at TEXT,
            answered_in TEXT,
            answer_summary TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_questions_ticker
            ON open_questions(ticker, status);
        CREATE INDEX IF NOT EXISTS idx_questions_status
            ON open_questions(status);

        CREATE TABLE IF NOT EXISTS knowledge_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            ticker TEXT,
            tickers_mentioned TEXT,
            title TEXT NOT NULL,
            author TEXT,
            source_org TEXT,
            publish_date TEXT,
            ingested_at TEXT NOT NULL,
            file_path TEXT NOT NULL,
            summary TEXT,
            framework_tags TEXT,
            canonical_hash TEXT UNIQUE,
            embedding_id TEXT,
            word_count INTEGER,
            language TEXT,
            nlm_synced BOOLEAN DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_ticker
            ON knowledge_index(ticker);
        CREATE INDEX IF NOT EXISTS idx_knowledge_tickers_mentioned
            ON knowledge_index(tickers_mentioned);
        CREATE INDEX IF NOT EXISTS idx_knowledge_source_type
            ON knowledge_index(source_type);
        CREATE INDEX IF NOT EXISTS idx_knowledge_ingested
            ON knowledge_index(ingested_at);
        CREATE INDEX IF NOT EXISTS idx_knowledge_hash
            ON knowledge_index(canonical_hash);
    """)

    # Migration: add scheduled_date column if missing
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "scheduled_date" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN scheduled_date TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_date)"
        )
    conn.commit()
    return conn


# ── Task CRUD ────────────────────────────────────────────────


def add_task(
    title,
    *,
    priority=2,
    category="general",
    ticker=None,
    due_at=None,
    source="manual",
    recurrence=None,
    estimated_minutes=30,
    dedup_key=None,
    description="",
    metadata=None,
) -> int:
    """Create a task. Returns task ID.

    Args:
        due_at: ISO datetime string (e.g. '2026-02-15T09:00:00') or date-only '2026-02-15'
        dedup_key: if provided, checks for existing task with same key in last 7 days.
    """
    if dedup_key:
        existing = _check_dedup(dedup_key)
        if existing is not None:
            return existing

    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO tasks
               (title, description, priority, category, ticker, due_at,
                created_at, source, recurrence, estimated_minutes, dedup_key, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                description,
                priority,
                category,
                ticker,
                due_at,
                datetime.now().isoformat(),
                source,
                recurrence,
                estimated_minutes,
                dedup_key,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_tasks(
    *, status=None, category=None, ticker=None, priority=None, due_before=None, limit=50
) -> list[dict]:
    """List tasks with optional filters."""
    conn = get_db()
    try:
        clauses = []
        params = []

        if status:
            clauses.append("status = ?")
            params.append(status)
        else:
            clauses.append("status NOT IN ('done', 'cancelled')")

        if category:
            clauses.append("category = ?")
            params.append(category)
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if due_before:
            clauses.append("due_at <= ?")
            params.append(due_before)

        where = " AND ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE {where} ORDER BY priority, due_at LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id: int) -> dict | None:
    """Get a single task by ID."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def complete_task(task_id: int) -> bool:
    """Mark done. For recurring tasks: advance due_at, keep pending."""
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return False

        now = datetime.now().isoformat()

        if task["recurrence"]:
            next_due = _next_recurrence(task["due_at"], task["recurrence"])
            conn.execute(
                "UPDATE tasks SET due_at = ?, metadata = ? WHERE id = ?",
                (
                    next_due,
                    json.dumps(
                        {**json.loads(task["metadata"] or "{}"), "last_completed": now}
                    ),
                    task_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def update_task(task_id: int, **kwargs) -> bool:
    """Update any task field."""
    allowed = {
        "title",
        "description",
        "priority",
        "status",
        "category",
        "ticker",
        "due_at",
        "recurrence",
        "estimated_minutes",
        "metadata",
        "scheduled_date",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    conn = get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [task_id]
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        conn.commit()
        return True
    finally:
        conn.close()


def cancel_task(task_id: int) -> bool:
    """Mark cancelled."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE tasks SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def start_task(task_id: int) -> bool:
    """Mark in_progress with started_at timestamp."""
    conn = get_db()
    try:
        now = datetime.now().isoformat()
        task = conn.execute(
            "SELECT metadata FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not task:
            return False
        meta = json.loads(task["metadata"] or "{}")
        meta["started_at"] = now
        conn.execute(
            "UPDATE tasks SET status = 'in_progress', metadata = ? WHERE id = ?",
            (json.dumps(meta), task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ── Auto-Task with Dedup ─────────────────────────────────────


def _check_dedup(dedup_key: str) -> int | None:
    """Check if task with this dedup_key exists in last 7 days. Returns task ID or None."""
    conn = get_db()
    try:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        row = conn.execute(
            """SELECT id FROM tasks
               WHERE dedup_key = ? AND created_at > ? AND status != 'cancelled'
               LIMIT 1""",
            (dedup_key, cutoff),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def auto_create_task(
    title,
    *,
    source,
    category="general",
    ticker=None,
    priority=3,
    due_at=None,
    estimated_minutes=15,
    dedup_key=None,
    description="",
) -> int | None:
    """Create task from another skill, with 7-day dedup protection.

    Returns task ID, or None if dedup prevented creation.
    """
    if dedup_key:
        existing = _check_dedup(dedup_key)
        if existing is not None:
            return None

    return add_task(
        title,
        priority=priority,
        category=category,
        ticker=ticker,
        due_at=due_at,
        source=source,
        estimated_minutes=estimated_minutes,
        dedup_key=dedup_key,
        description=description,
    )


# ── Priority-Urgency Scoring ────────────────────────────────


def _urgency_score(task: dict) -> float:
    """Urgency multiplier based on deadline proximity."""
    due = task.get("due_at")
    if not due:
        return 1.0

    try:
        due_dt = datetime.fromisoformat(due)
    except (ValueError, TypeError):
        return 1.0

    now = datetime.now()
    days_until = (due_dt - now).total_seconds() / 86400

    if days_until < -7:
        return 5.0  # Very overdue
    elif days_until < 0:
        return 3.0 + min(abs(days_until) * 0.3, 2.0)  # Overdue
    elif days_until < 1:
        return 3.0  # Due today
    elif days_until < 7:
        return 2.0  # This week
    elif days_until < 14:
        return 1.5  # Next week
    else:
        return 1.0


def _sort_score(task: dict) -> float:
    """Combined score = (5 - priority) * urgency_score."""
    priority = task.get("priority", 3)
    return (5 - priority) * _urgency_score(task)


def sorted_tasks(tasks: list[dict]) -> list[dict]:
    """Sort by combined score, descending."""
    return sorted(tasks, key=_sort_score, reverse=True)


# ── Recurrence ───────────────────────────────────────────────


def _next_recurrence(due_at: str | None, recurrence: str) -> str:
    """Calculate next occurrence after today."""
    today = date.today()

    if due_at:
        try:
            base = datetime.fromisoformat(due_at)
        except (ValueError, TypeError):
            base = datetime.now()
    else:
        base = datetime.now()

    deltas = {
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
        "quarterly": timedelta(days=91),
    }
    delta = deltas.get(recurrence, timedelta(days=7))

    next_dt = base + delta
    while next_dt.date() <= today:
        next_dt += delta

    return next_dt.isoformat()


# ── Daily Plan & Time Blocks ────────────────────────────────


def suggest_daily_plan(target_date=None) -> dict:
    """Generate prioritized daily plan with time blocks."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)

    target_end = (
        datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)
    ).isoformat()

    # Collect tasks: pending/in_progress, due <= target OR no due date
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE status IN ('pending', 'in_progress')
               AND (due_at IS NULL OR due_at <= ?)
               ORDER BY priority, due_at""",
            (target_end,),
        ).fetchall()
        tasks = [dict(r) for r in rows]
    finally:
        conn.close()

    tasks = sorted_tasks(tasks)
    overdue = [
        t for t in tasks if t.get("due_at") and t["due_at"] < target_date.isoformat()
    ]
    blocks = generate_time_blocks(tasks, target_date)
    total_minutes = sum(t.get("estimated_minutes", 30) for t in tasks)

    return {
        "date": target_date.isoformat(),
        "tasks": tasks,
        "time_blocks": blocks,
        "total_minutes": total_minutes,
        "overdue_count": len(overdue),
        "capacity_hours": 8,
        "utilization_pct": round(total_minutes / 480 * 100) if total_minutes else 0,
    }


def generate_time_blocks(tasks: list[dict], target_date=None) -> list[dict]:
    """Convert tasks into time blocks (08:00-12:00, 13:00-18:00)."""
    if target_date is None:
        target_date = date.today()

    blocks = []
    # Morning: 08:00-12:00, Afternoon: 13:00-18:00
    slots = [
        (
            datetime.combine(target_date, datetime.min.time().replace(hour=8)),
            datetime.combine(target_date, datetime.min.time().replace(hour=12)),
        ),
        (
            datetime.combine(target_date, datetime.min.time().replace(hour=13)),
            datetime.combine(target_date, datetime.min.time().replace(hour=18)),
        ),
    ]

    current_slot = 0
    current_time = slots[0][0]
    buffer = timedelta(minutes=5)

    for task in tasks:
        duration = timedelta(minutes=task.get("estimated_minutes", 30))

        # Check if fits in current slot
        if current_slot >= len(slots):
            blocks.append(
                {
                    "task_id": task["id"],
                    "title": task["title"],
                    "priority": task["priority"],
                    "category": task.get("category", "general"),
                    "ticker": task.get("ticker"),
                    "duration_minutes": task.get("estimated_minutes", 30),
                    "start": None,
                    "end": None,
                    "deferred": True,
                }
            )
            continue

        slot_start, slot_end = slots[current_slot]
        if current_time < slot_start:
            current_time = slot_start

        end_time = current_time + duration

        # Overflow to next slot
        if end_time > slot_end:
            current_slot += 1
            if current_slot < len(slots):
                current_time = slots[current_slot][0]
                end_time = current_time + duration
                if end_time > slots[current_slot][1]:
                    blocks.append(
                        {
                            "task_id": task["id"],
                            "title": task["title"],
                            "priority": task["priority"],
                            "category": task.get("category", "general"),
                            "ticker": task.get("ticker"),
                            "duration_minutes": task.get("estimated_minutes", 30),
                            "start": None,
                            "end": None,
                            "deferred": True,
                        }
                    )
                    continue
            else:
                blocks.append(
                    {
                        "task_id": task["id"],
                        "title": task["title"],
                        "priority": task["priority"],
                        "category": task.get("category", "general"),
                        "ticker": task.get("ticker"),
                        "duration_minutes": task.get("estimated_minutes", 30),
                        "start": None,
                        "end": None,
                        "deferred": True,
                    }
                )
                continue

        blocks.append(
            {
                "task_id": task["id"],
                "title": task["title"],
                "priority": task["priority"],
                "category": task.get("category", "general"),
                "ticker": task.get("ticker"),
                "duration_minutes": task.get("estimated_minutes", 30),
                "start": current_time.strftime("%H:%M"),
                "end": end_time.strftime("%H:%M"),
                "deferred": False,
            }
        )
        current_time = end_time + buffer

    return blocks


# ── Weekly Scheduling ────────────────────────────────────────


def get_week_tasks(week_start: str) -> dict:
    """Get tasks scheduled for Mon-Sun of given week.

    Returns: {
        'YYYY-MM-DD': [task, ...],
        'FLOAT': [tasks with scheduled_date='FLOAT'],
        'ROLLOVER': [tasks where scheduled_date < today and status not done]
    }
    """
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)
    today_str = date.today().isoformat()

    conn = get_db()
    try:
        # Tasks scheduled in this week range
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE scheduled_date IS NOT NULL
               AND status NOT IN ('done', 'cancelled')""",
        ).fetchall()

        result = {}
        rollovers = []
        for row in rows:
            t = dict(row)
            sd = t["scheduled_date"]
            if sd == "FLOAT":
                result.setdefault("FLOAT", []).append(t)
            elif sd < today_str and t["status"] not in ("done", "cancelled"):
                rollovers.append(t)
                # Also place in today's bucket
                result.setdefault(today_str, []).append(t)
            elif ws.isoformat() <= sd <= we.isoformat():
                result.setdefault(sd, []).append(t)

        if rollovers:
            result["ROLLOVER"] = rollovers

        # Sort each day's tasks by priority
        for key in result:
            result[key] = sorted(result[key], key=lambda t: t.get("priority", 3))

        return result
    finally:
        conn.close()


def schedule_task(task_id: int, scheduled_date: str) -> bool:
    """Set scheduled_date for a task.

    Accepts: 'YYYY-MM-DD', 'FLOAT', or None (unschedule).
    Validates: scheduled_date <= due_at if due exists (skip for FLOAT).
    """
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return False

        if scheduled_date and scheduled_date != "FLOAT" and task["due_at"]:
            due_date = task["due_at"][:10]
            if scheduled_date > due_date:
                return False  # Can't schedule after deadline

        val = scheduled_date if scheduled_date else None
        conn.execute("UPDATE tasks SET scheduled_date = ? WHERE id = ?", (val, task_id))
        conn.commit()
        return True
    finally:
        conn.close()


def batch_schedule(assignments: list[tuple[int, str]]) -> int:
    """Schedule multiple tasks at once. Returns count scheduled."""
    conn = get_db()
    try:
        count = 0
        for task_id, sched_date in assignments:
            task = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if not task:
                continue
            if sched_date and sched_date != "FLOAT" and task["due_at"]:
                if sched_date > task["due_at"][:10]:
                    continue
            conn.execute(
                "UPDATE tasks SET scheduled_date = ? WHERE id = ?",
                (sched_date, task_id),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def reschedule_task(task_id: int, new_date: str) -> bool:
    """Move a task to a different day or FLOAT."""
    return schedule_task(task_id, new_date)


def clear_week_schedule(week_start: str) -> int:
    """Clear all scheduled_dates for a week (for replanning)."""
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)

    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE tasks SET scheduled_date = NULL
               WHERE scheduled_date IS NOT NULL
               AND scheduled_date != 'FLOAT'
               AND scheduled_date >= ? AND scheduled_date <= ?
               AND status NOT IN ('done', 'cancelled')""",
            (ws.isoformat(), we.isoformat()),
        )
        # Also clear FLOAT tasks — they belong to current planning
        conn.execute(
            """UPDATE tasks SET scheduled_date = NULL
               WHERE scheduled_date = 'FLOAT'
               AND status NOT IN ('done', 'cancelled')"""
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def week_summary(week_start: str) -> dict:
    """Per-day capacity and utilization.

    Returns dict with days, floating, rollovers, unscheduled_pending.
    Weekdays = 480m capacity, Weekends = 240m capacity.
    """
    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)
    today_str = date.today().isoformat()

    week_tasks = get_week_tasks(week_start)

    # Build per-day summary
    days = {}
    for i in range(7):
        d = ws + timedelta(days=i)
        ds = d.isoformat()
        is_weekend = d.weekday() >= 5
        cap = 240 if is_weekend else 480
        day_tasks = week_tasks.get(ds, [])
        sched_min = sum(t.get("estimated_minutes", 30) for t in day_tasks)
        days[ds] = {
            "scheduled_minutes": sched_min,
            "capacity": cap,
            "tasks": day_tasks,
            "is_weekend": is_weekend,
        }

    # Unscheduled pending tasks
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE status IN ('pending', 'in_progress')
               AND (scheduled_date IS NULL OR scheduled_date = '')
               ORDER BY priority, due_at"""
        ).fetchall()
        unscheduled = [dict(r) for r in rows]
    finally:
        conn.close()

    # ISO week ID
    week_id = ws.strftime("%G-W%V")

    return {
        "week_start": ws.isoformat(),
        "week_end": we.isoformat(),
        "week_id": week_id,
        "days": days,
        "floating": week_tasks.get("FLOAT", []),
        "rollovers": week_tasks.get("ROLLOVER", []),
        "unscheduled_pending": sorted_tasks(unscheduled),
    }


def auto_schedule_week(
    task_ids: list[int],
    week_start: str,
    constraints: dict | None = None,
) -> dict:
    """Python-based scheduler — deterministic bin-packing.

    Args:
        task_ids: Tasks to schedule (in priority order)
        week_start: Monday of target week (YYYY-MM-DD)
        constraints: {
            'blocked_slots': {'2026-02-12': ['afternoon']},
            'capacity_overrides': {'2026-02-14': 240},
            'fixed_assignments': {42: '2026-02-10'},
            'float_ids': [7, 14],
            'earnings_events': [{'ticker': 'AMAT', 'date': '2026-02-12'}]
        }

    Returns: {
        'schedule': {'2026-02-10': [blocks], ...},
        'deferred': [tasks that don't fit],
        'floating': [float_id tasks],
        'per_day_utilization': {...},
        'total_utilization_pct': 42
    }
    """
    constraints = constraints or {}
    ws = date.fromisoformat(week_start)
    today = date.today()

    blocked_slots = constraints.get("blocked_slots", {})
    capacity_overrides = constraints.get("capacity_overrides", {})
    fixed_assignments = constraints.get("fixed_assignments", {})
    float_ids = set(constraints.get("float_ids", []))
    earnings_events = constraints.get("earnings_events", [])
    buffer_per_day = constraints.get("buffer_per_day", 60)

    # Deep work categories (prefer morning)
    DEEP_WORK = {"research", "thesis", "review"}

    # Build day capacity map
    day_caps = {}
    day_used = {}
    day_blocks = {}
    for i in range(7):
        d = ws + timedelta(days=i)
        ds = d.isoformat()
        if d < today:
            continue  # Skip past days
        is_weekend = d.weekday() >= 5
        base_cap = 240 if is_weekend else 480
        cap = capacity_overrides.get(ds, base_cap)
        # Subtract buffer
        effective = max(cap - buffer_per_day, 0)
        # Apply blocked slots
        if ds in blocked_slots:
            for slot in blocked_slots[ds]:
                if slot == "morning":
                    effective -= min(240, effective)
                elif slot == "afternoon":
                    effective -= min(240, effective)
        day_caps[ds] = effective
        day_used[ds] = 0
        day_blocks[ds] = []

    if not day_caps:
        return {
            "schedule": {},
            "deferred": [],
            "floating": [],
            "per_day_utilization": {},
            "total_utilization_pct": 0,
        }

    # Fetch all tasks
    conn = get_db()
    try:
        tasks_by_id = {}
        for tid in task_ids:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
            if row:
                tasks_by_id[tid] = dict(row)
    finally:
        conn.close()

    schedule_result = {}  # date -> [(task_id, date)]
    deferred = []
    floating = []

    def _place_task(tid, target_date):
        """Try to place a task on target_date. Returns True if placed."""
        if tid not in tasks_by_id:
            return False
        task = tasks_by_id[tid]
        est = task.get("estimated_minutes", 30)
        if target_date not in day_caps:
            return False
        if day_used[target_date] + est > day_caps[target_date]:
            return False
        day_used[target_date] += est
        day_blocks[target_date].append(tid)
        schedule_result.setdefault(target_date, []).append((tid, target_date))
        return True

    def _find_earliest_day(tid, prefer_morning=False):
        """Find earliest day with capacity for this task."""
        task = tasks_by_id.get(tid)
        if not task:
            return None
        est = task.get("estimated_minutes", 30)
        due = task.get("due_at", "")[:10] if task.get("due_at") else None
        available = sorted(day_caps.keys())
        for ds in available:
            if due and ds > due:
                break
            if day_used[ds] + est <= day_caps[ds]:
                return ds
        return None

    # 1. Place fixed assignments first
    placed_ids = set()
    for tid_str, target in fixed_assignments.items():
        tid = int(tid_str) if isinstance(tid_str, str) else tid_str
        if tid in tasks_by_id and _place_task(tid, target):
            placed_ids.add(tid)

    # 2. Place earnings-related tasks (prep day-before)
    for ev in earnings_events:
        ev_date = ev["date"]
        ev_d = date.fromisoformat(ev_date)
        prep_date = (ev_d - timedelta(days=1)).isoformat()
        # Find any tasks related to this ticker
        ticker = ev.get("ticker", "").upper()
        for tid in task_ids:
            if tid in placed_ids or tid in float_ids:
                continue
            task = tasks_by_id.get(tid)
            if task and task.get("ticker") and task["ticker"].upper() == ticker:
                if _place_task(tid, prep_date):
                    placed_ids.add(tid)
                elif _place_task(tid, ev_date):
                    placed_ids.add(tid)

    # 3. Separate float tasks
    for tid in task_ids:
        if tid in float_ids and tid not in placed_ids:
            if tid in tasks_by_id:
                floating.append(tasks_by_id[tid])
                placed_ids.add(tid)

    # 4. Place remaining tasks by priority order (task_ids already priority-sorted)
    for tid in task_ids:
        if tid in placed_ids:
            continue
        task = tasks_by_id.get(tid)
        if not task:
            continue
        prefer_morning = task.get("category") in DEEP_WORK
        target = _find_earliest_day(tid, prefer_morning)
        if target:
            _place_task(tid, target)
            placed_ids.add(tid)
        else:
            deferred.append(task)
            placed_ids.add(tid)

    # 5. Build output schedule with time blocks per day
    schedule = {}
    available_days = sorted(day_caps.keys())
    for ds in available_days:
        tids = day_blocks.get(ds, [])
        if not tids:
            schedule[ds] = []
            continue

        # Sort: deep work first (morning), then admin/ingestion (afternoon)
        deep = [tid for tid in tids if tasks_by_id[tid].get("category") in DEEP_WORK]
        other = [tid for tid in tids if tid not in deep]
        ordered = deep + other

        blocks = []
        # Determine available time slots based on blocked_slots
        morning_blocked = ds in blocked_slots and "morning" in blocked_slots[ds]
        afternoon_blocked = ds in blocked_slots and "afternoon" in blocked_slots[ds]

        slots = []
        if not morning_blocked:
            d_obj = date.fromisoformat(ds)
            slots.append(
                (
                    datetime.combine(d_obj, datetime.min.time().replace(hour=8)),
                    datetime.combine(d_obj, datetime.min.time().replace(hour=12)),
                )
            )
        if not afternoon_blocked:
            d_obj = date.fromisoformat(ds)
            slots.append(
                (
                    datetime.combine(d_obj, datetime.min.time().replace(hour=13)),
                    datetime.combine(d_obj, datetime.min.time().replace(hour=18)),
                )
            )

        current_slot = 0
        current_time = slots[0][0] if slots else None
        buf = timedelta(minutes=5)

        for tid in ordered:
            task = tasks_by_id[tid]
            est = task.get("estimated_minutes", 30)
            dur = timedelta(minutes=est)

            if current_time is None:
                blocks.append(
                    {
                        "task_id": tid,
                        "title": task["title"],
                        "priority": task["priority"],
                        "category": task.get("category", "general"),
                        "ticker": task.get("ticker"),
                        "duration_minutes": est,
                        "start": None,
                        "end": None,
                    }
                )
                continue

            end_time = current_time + dur
            # Check if fits in current slot
            if current_slot < len(slots) and end_time > slots[current_slot][1]:
                current_slot += 1
                if current_slot < len(slots):
                    current_time = slots[current_slot][0]
                    end_time = current_time + dur
                else:
                    blocks.append(
                        {
                            "task_id": tid,
                            "title": task["title"],
                            "priority": task["priority"],
                            "category": task.get("category", "general"),
                            "ticker": task.get("ticker"),
                            "duration_minutes": est,
                            "start": None,
                            "end": None,
                        }
                    )
                    continue

            blocks.append(
                {
                    "task_id": tid,
                    "title": task["title"],
                    "priority": task["priority"],
                    "category": task.get("category", "general"),
                    "ticker": task.get("ticker"),
                    "duration_minutes": est,
                    "start": current_time.strftime("%H:%M"),
                    "end": end_time.strftime("%H:%M"),
                }
            )
            current_time = end_time + buf

        schedule[ds] = blocks

    # 6. Per-day utilization
    total_cap = sum(day_caps.values())
    total_used = sum(day_used.values())
    per_day = {}
    for ds in available_days:
        cap = day_caps[ds] + buffer_per_day  # Show full capacity
        used = day_used[ds]
        per_day[ds] = {
            "used": used,
            "capacity": cap,
            "pct": round(used / cap * 100) if cap else 0,
        }

    return {
        "schedule": schedule,
        "deferred": deferred,
        "floating": floating,
        "per_day_utilization": per_day,
        "total_utilization_pct": round(total_used / total_cap * 100)
        if total_cap
        else 0,
    }


# ── ICS Calendar Export ──────────────────────────────────────


def generate_ics(tasks: list[dict], *, reminder_minutes=15, output_path=None) -> Path:
    """Generate .ics file with deadline reminders.

    Each task with due_at becomes a VEVENT with VALARM.
    """
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = CALENDAR_DIR / f"tasks_{date.today().isoformat()}.ics"
    else:
        output_path = Path(output_path)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Task Manager//EN",
        "X-WR-CALNAME:Investment Tasks",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for task in tasks:
        due = task.get("due_at")
        if not due:
            continue

        try:
            due_dt = datetime.fromisoformat(due)
        except (ValueError, TypeError):
            continue

        # Format datetime for ICS
        if due_dt.hour == 0 and due_dt.minute == 0:
            dtstart = due_dt.strftime("%Y%m%dT090000")
            dtend = (
                (due_dt + timedelta(minutes=task.get("estimated_minutes", 30)))
                .replace(hour=9, minute=task.get("estimated_minutes", 30))
                .strftime("%Y%m%dT%H%M00")
            )
        else:
            dtstart = due_dt.strftime("%Y%m%dT%H%M00")
            end_dt = due_dt + timedelta(minutes=task.get("estimated_minutes", 30))
            dtend = end_dt.strftime("%Y%m%dT%H%M00")

        category = task.get("category", "general")
        priority_label = f"P{task.get('priority', 3)}"
        ticker_str = f" [{task.get('ticker')}]" if task.get("ticker") else ""
        summary = _ics_escape(
            f"[{priority_label} {category}]{ticker_str} {task['title']}"
        )
        description = _ics_escape(
            f"Priority: {task.get('priority', 3)}\\n"
            f"Category: {category}\\n"
            f"Task ID: {task.get('id', '?')}"
        )

        lines.extend(
            [
                "",
                "BEGIN:VEVENT",
                f"UID:{uuid.uuid4()}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"CATEGORIES:{category}",
                "STATUS:TENTATIVE",
                "BEGIN:VALARM",
                "TRIGGER:-PT60M",
                "ACTION:DISPLAY",
                "DESCRIPTION:Task due in 1 hour",
                "END:VALARM",
                "BEGIN:VALARM",
                f"TRIGGER:-PT{reminder_minutes}M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:Task due in {reminder_minutes} minutes",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    lines.append("")
    lines.append("END:VCALENDAR")

    output_path.write_text("\r\n".join(lines), encoding="utf-8")
    return output_path


def export_recurring_reminders(tasks: list[dict], output_path=None) -> Path:
    """Export recurring tasks with RRULE."""
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = CALENDAR_DIR / "recurring_tasks.ics"
    else:
        output_path = Path(output_path)

    freq_map = {
        "daily": "FREQ=DAILY",
        "weekly": "FREQ=WEEKLY",
        "monthly": "FREQ=MONTHLY",
        "quarterly": "FREQ=MONTHLY;INTERVAL=3",
    }

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Task Manager//EN",
        "X-WR-CALNAME:Recurring Tasks",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for task in tasks:
        if not task.get("recurrence"):
            continue

        due = task.get("due_at")
        if not due:
            continue

        try:
            due_dt = datetime.fromisoformat(due)
        except (ValueError, TypeError):
            continue

        dtstart = (
            due_dt.strftime("%Y%m%dT%H%M00")
            if due_dt.hour
            else due_dt.strftime("%Y%m%dT090000")
        )
        rrule = freq_map.get(task["recurrence"], "FREQ=WEEKLY")
        summary = _ics_escape(f"[recurring] {task['title']}")

        lines.extend(
            [
                "",
                "BEGIN:VEVENT",
                f"UID:{uuid.uuid4()}",
                f"DTSTART:{dtstart}",
                f"RRULE:{rrule}",
                f"SUMMARY:{summary}",
                f"CATEGORIES:{task.get('category', 'general')}",
                "BEGIN:VALARM",
                "TRIGGER:-PT15M",
                "ACTION:DISPLAY",
                "DESCRIPTION:Recurring task reminder",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    lines.append("")
    lines.append("END:VCALENDAR")

    output_path.write_text("\r\n".join(lines), encoding="utf-8")
    return output_path


def _ics_escape(text: str) -> str:
    """Escape text for ICS format."""
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


# ── Ingestion Pipeline ───────────────────────────────────────


def record_pipeline_entry(
    canonical_key,
    item_type,
    item_title,
    source_platform,
    obsidian_path=None,
    *,
    note_id=None,
    has_frontmatter=False,
    has_tickers=False,
    has_framework_tags=False,
    has_wikilinks=False,
    tickers_found=None,
    framework_sections=None,
) -> int:
    """Record pipeline entry. Called by ingestion skills after record_ingestion()."""
    now = datetime.now().isoformat()
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO ingestion_pipeline
               (canonical_key, note_id, item_type, item_title, source_platform,
                ingested_at, obsidian_path,
                has_frontmatter, has_tickers, has_framework_tags, has_wikilinks,
                frontmatter_at, tickers_at, framework_at,
                tickers_found, framework_sections)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                canonical_key,
                note_id,
                item_type,
                item_title,
                source_platform,
                now,
                obsidian_path,
                int(has_frontmatter),
                int(has_tickers),
                int(has_framework_tags),
                int(has_wikilinks),
                now if has_frontmatter else None,
                now if has_tickers else None,
                now if has_framework_tags else None,
                json.dumps(tickers_found or []),
                json.dumps(framework_sections or []),
            ),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM ingestion_pipeline WHERE canonical_key = ?",
            (canonical_key,),
        ).fetchone()["id"]
    finally:
        conn.close()


def update_pipeline_stage(canonical_key, **stage_bools) -> bool:
    """Update specific stages: has_tickers=True, has_wikilinks=True, etc."""
    valid_stages = {
        "has_frontmatter",
        "has_tickers",
        "has_framework_tags",
        "has_wikilinks",
        "is_reviewed",
    }
    timestamp_map = {
        "has_frontmatter": "frontmatter_at",
        "has_tickers": "tickers_at",
        "has_framework_tags": "framework_at",
        "has_wikilinks": "wikilinks_at",
        "is_reviewed": "reviewed_at",
    }

    updates = {}
    now = datetime.now().isoformat()
    for k, v in stage_bools.items():
        if k in valid_stages and v:
            updates[k] = 1
            updates[timestamp_map[k]] = now

    if not updates:
        return False

    conn = get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [canonical_key]
        conn.execute(
            f"UPDATE ingestion_pipeline SET {sets} WHERE canonical_key = ?", vals
        )
        conn.commit()
        return True
    finally:
        conn.close()


def update_pipeline_stage_by_path(obsidian_path, **stage_bools) -> bool:
    """Update by file path. Tries to extract note_id from frontmatter first."""
    note_id = _extract_note_id(obsidian_path)

    conn = get_db()
    try:
        # Try note_id first, then path
        row = None
        if note_id:
            row = conn.execute(
                "SELECT canonical_key FROM ingestion_pipeline WHERE note_id = ?",
                (note_id,),
            ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT canonical_key FROM ingestion_pipeline WHERE obsidian_path = ?",
                (obsidian_path,),
            ).fetchone()
        if not row:
            return False
    finally:
        conn.close()

    return update_pipeline_stage(row["canonical_key"], **stage_bools)


def _extract_note_id(filepath: str) -> str | None:
    """Extract frontmatter id: field from a file."""
    try:
        path = Path(filepath)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8", errors="ignore")[:500]
        if not content.startswith("---"):
            return None
        end = content.find("---", 3)
        if end == -1:
            return None
        fm = content[3:end]
        match = re.search(r'^id:\s*"?([^"\n]+)"?', fm, re.MULTILINE)
        return match.group(1).strip() if match else None
    except Exception:
        return None


def pipeline_status(*, item_type=None, since_days=30) -> dict:
    """Pipeline health metrics."""
    conn = get_db()
    try:
        cutoff = (datetime.now() - timedelta(days=since_days)).isoformat()
        base_where = "ingested_at >= ?"
        params = [cutoff]
        if item_type:
            base_where += " AND item_type = ?"
            params.append(item_type)

        rows = conn.execute(
            f"SELECT * FROM ingestion_pipeline WHERE {base_where}", params
        ).fetchall()

        total = len(rows)
        if total == 0:
            return {
                "total_items": 0,
                "by_type": {},
                "completion_rates": {},
                "bottleneck": None,
                "unreviewed_count": 0,
            }

        by_type = {}
        stages = [
            "has_frontmatter",
            "has_tickers",
            "has_framework_tags",
            "has_wikilinks",
            "is_reviewed",
        ]
        stage_totals = {s: 0 for s in stages}

        for row in rows:
            r = dict(row)
            t = r["item_type"]
            if t not in by_type:
                by_type[t] = {"total": 0}
                for s in stages:
                    by_type[t][s] = 0
            by_type[t]["total"] += 1
            for s in stages:
                if r[s]:
                    by_type[t][s] += 1
                    stage_totals[s] += 1

        completion_rates = {s: round(stage_totals[s] / total, 2) for s in stages}

        # Find bottleneck: stage with biggest drop from previous
        bottleneck = None
        prev_rate = 1.0
        for s in stages:
            rate = completion_rates[s]
            if prev_rate - rate > 0.1 and rate < prev_rate:
                bottleneck = s
            prev_rate = rate

        unreviewed = total - stage_totals["is_reviewed"]

        return {
            "total_items": total,
            "by_type": by_type,
            "completion_rates": completion_rates,
            "bottleneck": bottleneck,
            "unreviewed_count": unreviewed,
        }
    finally:
        conn.close()


def pipeline_items_needing_attention(stage="wikilinks", limit=20) -> list[dict]:
    """Items missing a specific pipeline stage."""
    VALID_STAGE_COLS = {
        "has_frontmatter",
        "has_tickers",
        "has_framework_tags",
        "has_wikilinks",
        "is_reviewed",
    }

    stage_col = f"has_{stage}" if not stage.startswith("has_") else stage
    if stage_col == "has_reviewed":
        stage_col = "is_reviewed"

    if stage_col not in VALID_STAGE_COLS:
        raise ValueError(f"Invalid pipeline stage: {stage!r}")

    conn = get_db()
    try:
        rows = conn.execute(
            f"""SELECT canonical_key, item_type, item_title, obsidian_path, ingested_at
                FROM ingestion_pipeline
                WHERE {stage_col} = 0
                ORDER BY ingested_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def backfill_pipeline_from_ingestion_state(days=180) -> int:
    """One-time: populate pipeline table from existing ingestion_state records."""
    from shared.frontmatter_utils import INGESTION_DB

    if not INGESTION_DB.exists():
        return 0

    ingestion_conn = sqlite3.connect(str(INGESTION_DB))
    ingestion_conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    try:
        rows = ingestion_conn.execute(
            "SELECT * FROM ingestion_state WHERE ingested_at >= ?", (cutoff,)
        ).fetchall()
    finally:
        ingestion_conn.close()

    count = 0
    for row in rows:
        r = dict(row)
        canonical_key = r["canonical_key"]
        platform = r["source_platform"]
        obs_path = r.get("obsidian_path", "")

        # Check if already in pipeline
        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT 1 FROM ingestion_pipeline WHERE canonical_key = ?",
                (canonical_key,),
            ).fetchone()
        finally:
            conn.close()

        if existing:
            continue

        # Scan the actual file to determine pipeline stages
        has_fm, has_tickers, has_fw, has_links = False, False, False, False
        note_id = None
        tickers_found = []
        fw_sections = []

        if obs_path:
            path = Path(obs_path)
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if content.startswith("---"):
                        has_fm = True
                        # Extract note_id
                        end = content.find("---", 3)
                        if end > 0:
                            fm = content[3:end]
                            id_match = re.search(
                                r'^id:\s*"?([^"\n]+)"?', fm, re.MULTILINE
                            )
                            note_id = id_match.group(1).strip() if id_match else None

                            ticker_match = re.search(
                                r"^tickers?:\s*\[([^\]]*)\]", fm, re.MULTILINE
                            )
                            if ticker_match and ticker_match.group(1).strip():
                                tickers_found = [
                                    t.strip()
                                    for t in ticker_match.group(1).split(",")
                                    if t.strip()
                                ]
                                has_tickers = bool(tickers_found)

                            fw_match = re.search(
                                r"^framework_sections:\s*\[([^\]]*)\]", fm, re.MULTILINE
                            )
                            if fw_match and fw_match.group(1).strip():
                                fw_sections = [
                                    s.strip()
                                    for s in fw_match.group(1).split(",")
                                    if s.strip()
                                ]
                                has_fw = bool(fw_sections)

                    # Check for wikilinks in body
                    body = (
                        content[content.find("---", 3) + 3 :]
                        if content.startswith("---")
                        else content
                    )
                    has_links = bool(re.search(r"\[\[.+?\]\]", body))
                except Exception:
                    pass

        record_pipeline_entry(
            canonical_key=canonical_key,
            item_type=platform,
            item_title=r.get("metadata", ""),
            source_platform=platform,
            obsidian_path=obs_path,
            note_id=note_id,
            has_frontmatter=has_fm,
            has_tickers=has_tickers,
            has_framework_tags=has_fw,
            has_wikilinks=has_links,
            tickers_found=tickers_found,
            framework_sections=fw_sections,
        )
        count += 1

    return count


# ── Open Questions ───────────────────────────────────────────


def add_open_question(
    ticker, question, priority="medium", context=None, source_note=None
):
    """Add an open research question."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO open_questions (ticker, question, priority, context, source_note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                ticker.upper(),
                question,
                priority,
                context,
                source_note,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_open_questions(ticker=None, status="open"):
    """Get open questions, optionally filtered by ticker."""
    conn = get_db()
    try:
        if ticker:
            cur = conn.execute(
                "SELECT id, ticker, question, priority, context, source_note, created_at FROM open_questions WHERE ticker = ? AND status = ? ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END",
                (ticker.upper(), status),
            )
        else:
            cur = conn.execute(
                "SELECT id, ticker, question, priority, context, source_note, created_at FROM open_questions WHERE status = ? ORDER BY ticker, CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END",
                (status,),
            )
        return cur.fetchall()
    finally:
        conn.close()


def answer_question(question_id, answered_in=None, answer_summary=None):
    """Mark a question as answered."""
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE open_questions SET status = 'answered', answered_at = ?, answered_in = ?, answer_summary = ? WHERE id = ?",
            (datetime.now().isoformat(), answered_in, answer_summary, question_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def obsolete_question(question_id):
    """Mark a question as obsolete."""
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE open_questions SET status = 'obsolete' WHERE id = ?", (question_id,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def open_questions_summary():
    """Get summary of open questions by ticker."""
    conn = get_db()
    try:
        cur = conn.execute("""
            SELECT ticker, COUNT(*) as count,
                   SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high_count,
                   MIN(created_at) as oldest
            FROM open_questions WHERE status = 'open'
            GROUP BY ticker ORDER BY high_count DESC, count DESC
        """)
        return cur.fetchall()
    finally:
        conn.close()


# ── Knowledge Index ──────────────────────────────────────────


def add_to_knowledge_index(
    source_type,
    title,
    file_path,
    ticker=None,
    tickers_mentioned=None,
    author=None,
    source_org=None,
    publish_date=None,
    summary=None,
    framework_tags=None,
    canonical_hash=None,
    word_count=None,
    language=None,
):
    """Add a document to the knowledge index."""
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO knowledge_index
               (source_type, ticker, tickers_mentioned, title, author, source_org,
                publish_date, ingested_at, file_path, summary, framework_tags,
                canonical_hash, word_count, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_type,
                ticker,
                json.dumps(tickers_mentioned) if tickers_mentioned else None,
                title,
                author,
                source_org,
                publish_date,
                datetime.now().isoformat(),
                file_path,
                summary,
                json.dumps(framework_tags) if framework_tags else None,
                canonical_hash,
                word_count,
                language,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return None  # Duplicate
        raise
    finally:
        conn.close()


def search_knowledge_index(query=None, ticker=None, source_type=None, days=None):
    """Search the knowledge index."""
    conn = get_db()
    try:
        conditions = []
        params = []
        if ticker:
            conditions.append("(ticker = ? OR tickers_mentioned LIKE ?)")
            params.extend([ticker.upper(), f'%"{ticker.upper()}"%'])
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if query:
            conditions.append("(title LIKE ? OR summary LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if days:
            conditions.append("ingested_at >= datetime('now', ?)")
            params.append(f"-{days} days")
        where = " AND ".join(conditions) if conditions else "1=1"
        cur = conn.execute(
            f"SELECT * FROM knowledge_index WHERE {where} ORDER BY ingested_at DESC",
            params,
        )
        return cur.fetchall()
    finally:
        conn.close()


def knowledge_index_stats(ticker=None):
    """Get knowledge index statistics."""
    conn = get_db()
    try:
        if ticker:
            cur = conn.execute(
                "SELECT source_type, COUNT(*) FROM knowledge_index WHERE ticker = ? OR tickers_mentioned LIKE ? GROUP BY source_type",
                (ticker.upper(), f'%"{ticker.upper()}"%'),
            )
        else:
            cur = conn.execute(
                "SELECT source_type, COUNT(*) FROM knowledge_index GROUP BY source_type"
            )
        return cur.fetchall()
    finally:
        conn.close()


# ── Formatters ───────────────────────────────────────────────


def format_task_list(tasks: list[dict]) -> str:
    """Format tasks as a table."""
    if not tasks:
        return "No tasks found."

    priority_icons = {1: "P1", 2: "P2", 3: "P3", 4: "P4"}
    lines = [
        "| # | Pri | Category | Title | Ticker | Due | Est |",
        "|---|-----|----------|-------|--------|-----|-----|",
    ]
    for t in tasks:
        due = t.get("due_at", "")
        if due:
            due = due[:10]
        ticker = t.get("ticker") or ""
        pri = priority_icons.get(t["priority"], f"P{t['priority']}")
        est = f"{t.get('estimated_minutes', 30)}m"
        lines.append(
            f"| {t['id']} | {pri} | {t.get('category', '')} | "
            f"{t['title'][:50]} | {ticker} | {due} | {est} |"
        )
    return "\n".join(lines)


def format_plan(plan: dict) -> str:
    """Format daily plan as markdown."""
    lines = [
        f"## Daily Plan: {plan['date']}",
        f"Capacity: {plan['total_minutes']}m / {plan['capacity_hours'] * 60}m "
        f"({plan['utilization_pct']}%)",
        "",
    ]

    if plan["overdue_count"] > 0:
        lines.append(f"**Overdue:** {plan['overdue_count']} tasks\n")

    for b in plan["time_blocks"]:
        if b.get("deferred"):
            lines.append(f"- [ ] [DEFERRED] [{b['category']}] {b['title']}")
        else:
            ticker_str = f" {b['ticker']}" if b.get("ticker") else ""
            lines.append(
                f"- [ ] {b['start']}-{b['end']} "
                f"[P{b['priority']} {b['category']}]{ticker_str} {b['title']}"
            )

    return "\n".join(lines)


def format_pipeline_status(status: dict) -> str:
    """Format pipeline status as a table."""
    if status["total_items"] == 0:
        return "No pipeline items found in the specified period."

    stages = [
        "has_frontmatter",
        "has_tickers",
        "has_framework_tags",
        "has_wikilinks",
        "is_reviewed",
    ]
    stage_labels = {
        "has_frontmatter": "FM",
        "has_tickers": "Tickers",
        "has_framework_tags": "Framework",
        "has_wikilinks": "Links",
        "is_reviewed": "Reviewed",
    }

    lines = [
        "| Source | Total | FM | Tickers | Framework | Links | Reviewed |",
        "|--------|-------|----|---------|-----------|-------|----------|",
    ]

    for t, data in sorted(status["by_type"].items()):
        total = data["total"]
        vals = [str(data.get(s, 0)) for s in stages]
        lines.append(f"| {t} | {total} | {' | '.join(vals)} |")

    rates = status["completion_rates"]
    rate_vals = [f"{int(rates.get(s, 0) * 100)}%" for s in stages]
    lines.append(
        f"| **Rate** | **{status['total_items']}** | {' | '.join(rate_vals)} |"
    )

    if status.get("bottleneck"):
        bn = stage_labels.get(status["bottleneck"], status["bottleneck"])
        lines.append(
            f"\nBottleneck: **{bn}** ({int(rates.get(status['bottleneck'], 0) * 100)}%)"
        )
    lines.append(f"Unreviewed: {status['unreviewed_count']}")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────


def main():
    # UTF-8 output for Windows
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Task Manager & Pipeline Tracker")
    subparsers = parser.add_subparsers(dest="command")

    # add
    add_p = subparsers.add_parser("add", help="Add a task")
    add_p.add_argument("title", help="Task title")
    add_p.add_argument("-p", "--priority", type=int, default=2, choices=[1, 2, 3, 4])
    add_p.add_argument("-t", "--ticker", help="Ticker symbol")
    add_p.add_argument("-d", "--due", help="Due date/time (ISO format)")
    add_p.add_argument(
        "-c",
        "--category",
        default="general",
        choices=[
            "research",
            "trade",
            "thesis",
            "review",
            "ingestion",
            "admin",
            "meeting",
            "general",
        ],
    )
    add_p.add_argument("-e", "--est", type=int, default=30, help="Estimated minutes")
    add_p.add_argument(
        "-r", "--recurrence", choices=["daily", "weekly", "monthly", "quarterly"]
    )
    add_p.add_argument("--desc", default="", help="Description")

    # list
    list_p = subparsers.add_parser("list", help="List tasks")
    list_p.add_argument(
        "--status", choices=["pending", "in_progress", "done", "cancelled"]
    )
    list_p.add_argument("--ticker")
    list_p.add_argument("--category")
    list_p.add_argument("--all", action="store_true", help="Include done/cancelled")

    # done
    done_p = subparsers.add_parser("done", help="Complete a task")
    done_p.add_argument("task_id", type=int)

    # cancel
    cancel_p = subparsers.add_parser("cancel", help="Cancel a task")
    cancel_p.add_argument("task_id", type=int)

    # start
    start_p = subparsers.add_parser("start", help="Start a task")
    start_p.add_argument("task_id", type=int)

    # plan
    plan_p = subparsers.add_parser("plan", help="Daily plan")
    plan_p.add_argument("--date", help="Target date (YYYY-MM-DD)")
    plan_p.add_argument("--ics", action="store_true", help="Export to .ics")

    # calendar
    cal_p = subparsers.add_parser("calendar", help="Export to .ics")
    cal_p.add_argument("--recurring", action="store_true")

    # pipeline
    pipe_p = subparsers.add_parser("pipeline", help="Pipeline health")
    pipe_p.add_argument("--type", help="Filter by item type")
    pipe_p.add_argument("--attention", help="Stage needing attention")
    pipe_p.add_argument("--days", type=int, default=30)
    pipe_p.add_argument(
        "--backfill", action="store_true", help="Backfill from ingestion_state"
    )

    # week
    week_p = subparsers.add_parser("week", help="Weekly scheduling")
    week_p.add_argument("--start", help="Week start (Monday, YYYY-MM-DD)")
    week_p.add_argument(
        "action",
        nargs="?",
        default="summary",
        choices=["summary", "schedule", "clear"],
        help="Action: summary, schedule TASK_ID DATE, clear",
    )
    week_p.add_argument("schedule_args", nargs="*", help="TASK_ID DATE|FLOAT")

    # questions
    questions_p = subparsers.add_parser("questions", help="Open research questions")
    questions_p.add_argument("ticker", nargs="?", help="Ticker symbol (optional)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "add":
        task_id = add_task(
            args.title,
            priority=args.priority,
            category=args.category,
            ticker=args.ticker.upper() if args.ticker else None,
            due_at=args.due,
            estimated_minutes=args.est,
            recurrence=args.recurrence,
            description=args.desc,
        )
        out.write(f"Created task #{task_id}: {args.title}\n")

    elif args.command == "list":
        status = args.status
        if args.all:
            tasks = list_tasks(
                status=status, category=args.category, ticker=args.ticker, limit=100
            )
        else:
            tasks = list_tasks(
                status=status, category=args.category, ticker=args.ticker
            )
        tasks = sorted_tasks(tasks)
        out.write(format_task_list(tasks) + "\n")

    elif args.command == "done":
        if complete_task(args.task_id):
            task = get_task(args.task_id)
            label = task["title"] if task else f"#{args.task_id}"
            out.write(f"Completed: {label}\n")
        else:
            out.write(f"Task #{args.task_id} not found.\n")

    elif args.command == "cancel":
        if cancel_task(args.task_id):
            out.write(f"Cancelled task #{args.task_id}\n")
        else:
            out.write(f"Task #{args.task_id} not found.\n")

    elif args.command == "start":
        if start_task(args.task_id):
            out.write(f"Started task #{args.task_id}\n")
        else:
            out.write(f"Task #{args.task_id} not found.\n")

    elif args.command == "plan":
        plan = suggest_daily_plan(args.date)
        out.write(format_plan(plan) + "\n")
        if args.ics:
            path = generate_ics(plan["tasks"])
            out.write(f"\nCalendar exported: {path}\n")

    elif args.command == "calendar":
        tasks = list_tasks(status="pending", limit=100)
        if args.recurring:
            recurring = [t for t in tasks if t.get("recurrence")]
            path = export_recurring_reminders(recurring)
            out.write(f"Recurring calendar exported: {path}\n")
        else:
            due_tasks = [t for t in tasks if t.get("due_at")]
            path = generate_ics(due_tasks)
            out.write(f"Calendar exported: {path}\n")

    elif args.command == "pipeline":
        if args.backfill:
            count = backfill_pipeline_from_ingestion_state(days=args.days * 6)
            out.write(f"Backfilled {count} items from ingestion_state.\n")
        elif args.attention:
            items = pipeline_items_needing_attention(args.attention)
            if items:
                out.write(f"Items needing {args.attention} ({len(items)}):\n")
                for item in items:
                    out.write(f"  - [{item['item_type']}] {item['item_title'][:60]}\n")
                    if item.get("obsidian_path"):
                        out.write(f"    Path: {item['obsidian_path']}\n")
            else:
                out.write(f"No items need {args.attention}.\n")
        else:
            status = pipeline_status(item_type=args.type, since_days=args.days)
            out.write(format_pipeline_status(status) + "\n")

    elif args.command == "week":
        # Default week start: Monday of current week
        if args.start:
            ws = args.start
        else:
            today = date.today()
            ws = (today - timedelta(days=today.weekday())).isoformat()

        if args.action == "summary":
            summary = week_summary(ws)
            out.write(
                json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n"
            )

        elif args.action == "schedule":
            if len(args.schedule_args) != 2:
                out.write("Usage: week schedule TASK_ID DATE|FLOAT\n")
            else:
                tid = int(args.schedule_args[0])
                sdate = args.schedule_args[1]
                if schedule_task(tid, sdate):
                    out.write(f"Scheduled task #{tid} → {sdate}\n")
                else:
                    out.write(f"Failed to schedule task #{tid}.\n")

        elif args.action == "clear":
            count = clear_week_schedule(ws)
            out.write(f"Cleared {count} scheduled tasks for week {ws}.\n")

    elif args.command == "questions":
        if len(sys.argv) > 2:
            ticker = sys.argv[2].upper()
            rows = get_open_questions(ticker=ticker)
            out.write(f"\n📌 Open Questions for {ticker}:\n")
            for r in rows:
                out.write(f"  [{r[3].upper()}] Q{r[0]}: {r[2]}\n")
                if r[4]:
                    out.write(f"         Context: {r[4]}\n")
        else:
            rows = open_questions_summary()
            out.write("\n📌 Open Questions Summary:\n")
            out.write(f"{'Ticker':<8} {'Count':<6} {'High':<6} {'Oldest'}\n")
            for r in rows:
                out.write(f"{r[0]:<8} {r[1]:<6} {r[2]:<6} {r[3][:10]}\n")

    out.flush()


if __name__ == "__main__":
    main()
