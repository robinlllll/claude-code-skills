from __future__ import annotations

import sqlite3
from pathlib import Path

from schemas import DecisionRecord, OutcomeRecord

DB_PATH = Path.home() / ".claude" / "data" / "investments.db"


def get_db(path=None) -> sqlite3.Connection:
    """Get a SQLite connection. Creates parent dirs and enables WAL mode."""
    if path is None:
        path = DB_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    return conn


def init_db(conn=None):
    """Create tables and indexes if they don't exist."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                date TEXT,
                ticker TEXT,
                decision_type TEXT,
                reasoning TEXT,
                alternatives TEXT,
                conviction INTEGER,
                thesis_link TEXT,
                trigger TEXT
            );

            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                decision_id TEXT REFERENCES decisions(id),
                date TEXT,
                result TEXT,
                pnl REAL,
                pnl_pct REAL,
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_ticker ON decisions(ticker);
            CREATE INDEX IF NOT EXISTS idx_decisions_date ON decisions(date);
            CREATE INDEX IF NOT EXISTS idx_outcomes_decision_id ON outcomes(decision_id);
        """)
        conn.commit()
    finally:
        if _close:
            conn.close()


def insert_decision(record: DecisionRecord, conn=None) -> str:
    """Insert a DecisionRecord into the decisions table. Returns the UUID string."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        data = record.to_db_dict()
        conn.execute(
            """
            INSERT INTO decisions
                (id, created_at, date, ticker, decision_type, reasoning,
                 alternatives, conviction, thesis_link, trigger)
            VALUES
                (:id, :created_at, :date, :ticker, :decision_type, :reasoning,
                 :alternatives, :conviction, :thesis_link, :trigger)
            """,
            data,
        )
        conn.commit()
        return data["id"]
    finally:
        if _close:
            conn.close()


def insert_outcome(record: OutcomeRecord, conn=None) -> str:
    """Insert an OutcomeRecord into the outcomes table. Returns the UUID string.

    Raises ValueError if the referenced decision_id does not exist.
    """
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        # Verify decision exists
        row = conn.execute(
            "SELECT id FROM decisions WHERE id = ?", (str(record.decision_id),)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"decision_id '{record.decision_id}' not found in decisions table"
            )

        data = record.to_db_dict()
        conn.execute(
            """
            INSERT INTO outcomes
                (id, created_at, decision_id, date, result, pnl, pnl_pct, notes)
            VALUES
                (:id, :created_at, :decision_id, :date, :result, :pnl, :pnl_pct, :notes)
            """,
            data,
        )
        conn.commit()
        return data["id"]
    finally:
        if _close:
            conn.close()


def query_decisions(
    ticker=None,
    decision_type=None,
    start_date=None,
    end_date=None,
    limit=100,
    conn=None,
) -> list[dict]:
    """Query decisions with optional filters. Returns list of dicts, ordered by date DESC."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        clauses = []
        params = []

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)
        if decision_type is not None:
            clauses.append("decision_type = ?")
            params.append(decision_type)
        if start_date is not None:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("date <= ?")
            params.append(end_date)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM decisions {where} ORDER BY date DESC LIMIT ?",
            params,
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        if _close:
            conn.close()


def get_pending_outcomes(days=30, conn=None) -> list[dict]:
    """Return decisions that have no matching outcome and are older than `days` days."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        rows = conn.execute(
            f"""
            SELECT d.*
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
            WHERE o.id IS NULL
              AND d.date < date('now', '-{days} days')
            ORDER BY d.date DESC
            """,
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        if _close:
            conn.close()


def get_decision_stats(start_date=None, end_date=None, conn=None) -> dict:
    """Return aggregate stats for decisions joined with outcomes."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        clauses = []
        params = []

        if start_date is not None:
            clauses.append("d.date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("d.date <= ?")
            params.append(end_date)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        row = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT d.id)                                            AS total,
                COUNT(DISTINCT o.id)                                            AS with_outcome,
                COUNT(DISTINCT CASE WHEN o.result = 'win'     THEN d.id END)   AS win,
                COUNT(DISTINCT CASE WHEN o.result = 'loss'    THEN d.id END)   AS loss,
                COUNT(DISTINCT CASE WHEN o.result = 'neutral' THEN d.id END)   AS neutral,
                COUNT(DISTINCT CASE WHEN o.id IS NULL         THEN d.id END)   AS pending,
                AVG(CASE WHEN o.result = 'win'  THEN d.conviction END)         AS avg_conviction_win,
                AVG(CASE WHEN o.result = 'loss' THEN d.conviction END)         AS avg_conviction_loss
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
            {where}
            """,
            params,
        ).fetchone()

        return {
            "total": row["total"] or 0,
            "with_outcome": row["with_outcome"] or 0,
            "win": row["win"] or 0,
            "loss": row["loss"] or 0,
            "neutral": row["neutral"] or 0,
            "pending": row["pending"] or 0,
            "avg_conviction_win": row["avg_conviction_win"],
            "avg_conviction_loss": row["avg_conviction_loss"],
        }
    finally:
        if _close:
            conn.close()


def get_decisions_for_ticker(ticker: str, conn=None) -> list[dict]:
    """Return all decisions + outcomes (if any) for a ticker, ordered chronologically."""
    _close = False
    if conn is None:
        conn = get_db()
        _close = True

    try:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.created_at,
                d.date,
                d.ticker,
                d.decision_type,
                d.reasoning,
                d.alternatives,
                d.conviction,
                d.thesis_link,
                d.trigger,
                o.result   AS outcome_result,
                o.pnl      AS outcome_pnl,
                o.date     AS outcome_date
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
            WHERE d.ticker = ?
            ORDER BY d.date ASC
            """,
            (ticker,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        if _close:
            conn.close()
