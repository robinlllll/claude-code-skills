"""Dashboard Server — Live interactive scheduling dashboard.

Serves the dashboard HTML and provides REST API endpoints
for task management (done, cancel, reschedule, add).
The dashboard auto-refreshes after each action.

Usage:
    python dashboard_server.py [--port 5555] [--calendar-json '...']
"""

import io
import json
import sqlite3
import sys
import os
from datetime import date, datetime, timedelta
from pathlib import Path

# Prevent dashboard_generator from wrapping stdout when imported
os.environ["DASHBOARD_NO_STDOUT_WRAP"] = "1"

from flask import Flask, jsonify, request, send_file, Response

SHARED_DIR = Path(__file__).resolve().parent
DATA_DIR = SHARED_DIR / "data"
TASK_DB_SOURCE = DATA_DIR / "task_manager.db"
TEMPLATE_PATH = SHARED_DIR / "dashboard_templates" / "dashboard_template.html"

# SQLite needs a local (non-FUSE) path for WAL mode to work reliably.
# Copy the DB to /tmp on startup; sync back after every write operation.
import shutil
import tempfile

_LOCAL_DB_DIR = Path(tempfile.mkdtemp(prefix="dashboard_"))
TASK_DB = _LOCAL_DB_DIR / "task_manager.db"

def _init_local_db():
    """Copy source DB to local temp path for reliable SQLite access."""
    if TASK_DB_SOURCE.exists():
        shutil.copy2(str(TASK_DB_SOURCE), str(TASK_DB))

def _sync_db_back():
    """Copy local DB back to the FUSE-mounted source after writes."""
    try:
        shutil.copy2(str(TASK_DB), str(TASK_DB_SOURCE))
    except Exception:
        pass  # Best-effort sync

app = Flask(__name__)

# Store calendar JSON in memory (passed at startup or via API)
_calendar_json = "[]"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(TASK_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


# ── Import the generator functions ──────────────────────────────

from dashboard_generator import build_dashboard_data, inject_data_into_template


# ── API Routes ──────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve the live dashboard with current data."""
    try:
        week_start = _get_week_start()
        data = build_dashboard_data(str(TASK_DB), _calendar_json, week_start)
        html = inject_data_into_template(str(TEMPLATE_PATH), data)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return f"<h1>Error generating dashboard</h1><pre>{e}</pre>", 500


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    """List all active tasks."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status NOT IN ('done', 'cancelled') ORDER BY priority, due_at"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/task/<int:task_id>/done", methods=["POST"])
def complete_task(task_id):
    """Mark a task as done."""
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return jsonify({"error": "Task not found"}), 404

        now = datetime.now().isoformat()

        if task["recurrence"]:
            # Advance recurring task to next occurrence
            next_due = _next_recurrence(task["due_at"], task["recurrence"])
            conn.execute(
                "UPDATE tasks SET due_at = ? WHERE id = ?",
                (next_due, task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
        conn.commit()
        _sync_db_back()
        return jsonify({"ok": True, "id": task_id, "action": "done"})
    finally:
        conn.close()


@app.route("/api/task/<int:task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """Cancel a task."""
    conn = get_db()
    try:
        now = datetime.now().isoformat()
        result = conn.execute(
            "UPDATE tasks SET status = 'cancelled', completed_at = ? WHERE id = ? AND status NOT IN ('done', 'cancelled')",
            (now, task_id),
        )
        conn.commit()
        _sync_db_back()
        if result.rowcount == 0:
            return jsonify({"error": "Task not found or already completed"}), 404
        return jsonify({"ok": True, "id": task_id, "action": "cancelled"})
    finally:
        conn.close()


@app.route("/api/task/<int:task_id>/reschedule", methods=["POST"])
def reschedule_task(task_id):
    """Reschedule a task to a new date."""
    data = request.get_json() or {}
    new_date = data.get("date")
    if not new_date:
        return jsonify({"error": "Missing 'date' field"}), 400

    conn = get_db()
    try:
        result = conn.execute(
            "UPDATE tasks SET due_at = ? WHERE id = ? AND status NOT IN ('done', 'cancelled')",
            (new_date, task_id),
        )
        conn.commit()
        _sync_db_back()
        if result.rowcount == 0:
            return jsonify({"error": "Task not found or already completed"}), 404
        return jsonify({"ok": True, "id": task_id, "action": "rescheduled", "new_date": new_date})
    finally:
        conn.close()


@app.route("/api/task/<int:task_id>/start", methods=["POST"])
def start_task(task_id):
    """Mark a task as in_progress."""
    conn = get_db()
    try:
        result = conn.execute(
            "UPDATE tasks SET status = 'in_progress' WHERE id = ? AND status = 'pending'",
            (task_id,),
        )
        conn.commit()
        _sync_db_back()
        if result.rowcount == 0:
            return jsonify({"error": "Task not found or not pending"}), 404
        return jsonify({"ok": True, "id": task_id, "action": "started"})
    finally:
        conn.close()


@app.route("/api/task/add", methods=["POST"])
def add_task():
    """Add a new task."""
    data = request.get_json() or {}
    title = data.get("title")
    if not title:
        return jsonify({"error": "Missing 'title' field"}), 400

    conn = get_db()
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """INSERT INTO tasks (title, priority, category, ticker, due_at, estimated_minutes, status, created_at, source)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 'dashboard')""",
            (
                title,
                data.get("priority", 2),
                data.get("category", "general"),
                data.get("ticker"),
                data.get("due_at"),
                data.get("estimated_minutes", 30),
                now,
            ),
        )
        conn.commit()
        _sync_db_back()
        return jsonify({"ok": True, "id": cursor.lastrowid})
    finally:
        conn.close()


@app.route("/api/calendar", methods=["POST"])
def update_calendar():
    """Update calendar events JSON (for refresh without restart)."""
    global _calendar_json
    data = request.get_json() or {}
    _calendar_json = json.dumps(data.get("events", []))
    return jsonify({"ok": True})


# ── Helpers ─────────────────────────────────────────────────────


def _get_week_start() -> datetime:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return datetime.combine(monday, datetime.min.time())


def _next_recurrence(due_at_str: str, recurrence: str) -> str:
    if not due_at_str:
        due_at_str = date.today().isoformat()
    try:
        due = datetime.fromisoformat(due_at_str)
    except ValueError:
        due = datetime.now()

    if recurrence == "daily":
        due += timedelta(days=1)
    elif recurrence == "weekly":
        due += timedelta(weeks=1)
    elif recurrence == "monthly":
        due = due.replace(month=due.month % 12 + 1)
    elif recurrence == "quarterly":
        due = due.replace(month=((due.month - 1 + 3) % 12) + 1)
    return due.isoformat()


# ── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dashboard Server")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--calendar-json", default="[]")
    args = parser.parse_args()

    _calendar_json = args.calendar_json
    _init_local_db()

    import sys as _sys
    try:
        _sys.stderr.write(f"\n  Dashboard server running at http://localhost:{args.port}\n")
        _sys.stderr.write(f"  Tasks DB: {TASK_DB}\n")
        _sys.stderr.write(f"  Template: {TEMPLATE_PATH}\n\n")
    except Exception:
        pass

    app.run(host="0.0.0.0", port=args.port, debug=False)
