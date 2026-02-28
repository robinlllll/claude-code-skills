"""SQLite database layer for Memory Cycle Tracker.

Tables:
- price_signals: time-series data from all collectors (Group A + B)
- composite_scores: monthly z-scores, group scores, divergence, cycle phase
- fetch_log: audit trail for data collection runs
"""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "memory_cycle.db"


def get_db() -> sqlite3.Connection:
    """Get database connection with WAL mode and row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            unit TEXT,
            signal_group TEXT CHECK(signal_group IN ('A', 'B')),
            sub_cycle TEXT CHECK(sub_cycle IN ('HBM', 'DRAM', 'NAND', 'ALL')),
            metadata TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, source, metric)
        );

        CREATE INDEX IF NOT EXISTS idx_ps_date ON price_signals(date);
        CREATE INDEX IF NOT EXISTS idx_ps_source ON price_signals(source);
        CREATE INDEX IF NOT EXISTS idx_ps_metric ON price_signals(metric);
        CREATE INDEX IF NOT EXISTS idx_ps_group ON price_signals(signal_group);
        CREATE INDEX IF NOT EXISTS idx_ps_date_metric ON price_signals(date, metric);

        CREATE TABLE IF NOT EXISTS composite_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            group_a_zscore REAL,
            group_b_zscore REAL,
            divergence REAL,
            hbm_score REAL,
            dram_score REAL,
            nand_score REAL,
            cycle_phase TEXT,
            phase_confidence REAL,
            korean_export_yoy REAL,
            gross_margin REAL,
            inventory_days REAL,
            capex_ratio REAL,
            alert_flags TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_cs_date ON composite_scores(date);
        CREATE INDEX IF NOT EXISTS idx_cs_phase ON composite_scores(cycle_phase);

        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            fetch_date TEXT NOT NULL,
            status TEXT CHECK(status IN ('success', 'partial', 'failed')),
            rows_added INTEGER DEFAULT 0,
            error_message TEXT,
            duration_seconds REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_fl_source ON fetch_log(source);
        CREATE INDEX IF NOT EXISTS idx_fl_date ON fetch_log(fetch_date);
        """)
        conn.commit()
    finally:
        conn.close()


# --- CRUD Operations ---


def upsert_signal(
    date: str,
    source: str,
    metric: str,
    value: float,
    unit: str = None,
    signal_group: str = None,
    sub_cycle: str = "ALL",
    metadata: str = None,
) -> bool:
    """Insert or update a price signal. Returns True on success."""
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO price_signals (date, source, metric, value, unit, signal_group, sub_cycle, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source, metric) DO UPDATE SET
                value=excluded.value, unit=excluded.unit,
                signal_group=excluded.signal_group, sub_cycle=excluded.sub_cycle,
                metadata=excluded.metadata, created_at=datetime('now')
        """,
            (date, source, metric, value, unit, signal_group, sub_cycle, metadata),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] Error upserting signal: {e}")
        return False
    finally:
        conn.close()


def upsert_signals_batch(signals: list[dict]) -> int:
    """Batch upsert signals. Returns count of rows affected."""
    conn = get_db()
    try:
        conn.executemany(
            """
            INSERT INTO price_signals (date, source, metric, value, unit, signal_group, sub_cycle, metadata)
            VALUES (:date, :source, :metric, :value, :unit, :signal_group, :sub_cycle, :metadata)
            ON CONFLICT(date, source, metric) DO UPDATE SET
                value=excluded.value, unit=excluded.unit,
                signal_group=excluded.signal_group, sub_cycle=excluded.sub_cycle,
                metadata=excluded.metadata, created_at=datetime('now')
        """,
            signals,
        )
        conn.commit()
        return len(signals)
    except Exception as e:
        print(f"  [DB] Batch upsert error: {e}")
        return 0
    finally:
        conn.close()


def upsert_composite(date: str, **kwargs) -> bool:
    """Insert or update composite score for a month."""
    cols = ["date"] + list(kwargs.keys())
    placeholders = ", ".join(["?"] * len(cols))
    updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs.keys())
    values = [date] + list(kwargs.values())

    conn = get_db()
    try:
        conn.execute(
            f"""
            INSERT INTO composite_scores ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {updates}, created_at=datetime('now')
        """,
            values,
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] Composite upsert error: {e}")
        return False
    finally:
        conn.close()


def log_fetch(
    source: str,
    status: str,
    rows_added: int = 0,
    error_message: str = None,
    duration_seconds: float = None,
) -> None:
    """Log a data collection run."""
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO fetch_log (source, fetch_date, status, rows_added, error_message, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                source,
                datetime.now().strftime("%Y-%m-%d"),
                status,
                rows_added,
                error_message,
                duration_seconds,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# --- Query Operations ---


def get_signals(
    metric: str = None,
    source: str = None,
    signal_group: str = None,
    sub_cycle: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = None,
) -> list[dict]:
    """Query price signals with optional filters."""
    conditions = []
    params = []

    if metric:
        conditions.append("metric = ?")
        params.append(metric)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if signal_group:
        conditions.append("signal_group = ?")
        params.append(signal_group)
    if sub_cycle:
        conditions.append("sub_cycle = ?")
        params.append(sub_cycle)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = f"LIMIT {limit}" if limit else ""

    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT * FROM price_signals {where} ORDER BY date ASC {limit_clause}",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_composites(
    start_date: str = None, end_date: str = None, limit: int = None
) -> list[dict]:
    """Query composite scores."""
    conditions = []
    params = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = f"LIMIT {limit}" if limit else ""

    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT * FROM composite_scores {where} ORDER BY date ASC {limit_clause}",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_composite() -> dict | None:
    """Get the most recent composite score."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM composite_scores ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_latest_signals_by_metric() -> dict[str, dict]:
    """Get the latest value for each metric. Returns {metric: {date, value, ...}}."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT ps.* FROM price_signals ps
            INNER JOIN (
                SELECT metric, MAX(date) as max_date FROM price_signals GROUP BY metric
            ) latest ON ps.metric = latest.metric AND ps.date = latest.max_date
            ORDER BY ps.metric
        """).fetchall()
        return {r["metric"]: dict(r) for r in rows}
    finally:
        conn.close()


def get_fetch_history(source: str = None, limit: int = 20) -> list[dict]:
    """Get recent fetch log entries."""
    conn = get_db()
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM fetch_log WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM fetch_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats() -> dict:
    """Get database statistics."""
    conn = get_db()
    try:
        total_signals = conn.execute("SELECT COUNT(*) FROM price_signals").fetchone()[0]
        total_composites = conn.execute(
            "SELECT COUNT(*) FROM composite_scores"
        ).fetchone()[0]

        date_range = conn.execute(
            "SELECT MIN(date), MAX(date) FROM price_signals"
        ).fetchone()

        sources = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM price_signals GROUP BY source ORDER BY cnt DESC"
        ).fetchall()

        metrics = conn.execute(
            "SELECT metric, COUNT(*) as cnt FROM price_signals GROUP BY metric ORDER BY cnt DESC"
        ).fetchall()

        recent_fetches = conn.execute(
            "SELECT source, status, rows_added, created_at FROM fetch_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        return {
            "total_signals": total_signals,
            "total_composites": total_composites,
            "date_range": {"min": date_range[0], "max": date_range[1]}
            if date_range[0]
            else None,
            "sources": [dict(r) for r in sources],
            "metrics": [dict(r) for r in metrics],
            "recent_fetches": [dict(r) for r in recent_fetches],
        }
    finally:
        conn.close()


# Auto-initialize on import
init_db()
