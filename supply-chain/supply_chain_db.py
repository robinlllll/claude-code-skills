"""SQLite database layer for supply chain mention index.

v0 schema: company_mentions + processed_transcripts.
No relationship classification yet — just who mentions whom + verbatim quote.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "supply_chain.db"


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS company_mentions (
                id INTEGER PRIMARY KEY,
                source_doc_id TEXT,
                chunk_id TEXT,
                transcript_date TEXT,
                transcript_quarter TEXT,
                source_company TEXT,
                source_ticker TEXT,
                mentioned_company TEXT,
                mentioned_company_id TEXT,
                mentioned_ticker TEXT,
                speaker_role TEXT,
                context TEXT NOT NULL,
                context_before TEXT,
                context_after TEXT,
                confidence REAL,
                needs_review INTEGER DEFAULT 0,
                prompt_version TEXT,
                llm_model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS processed_transcripts (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                ticker TEXT,
                quarter TEXT,
                processed_at TEXT DEFAULT (datetime('now')),
                chunk_count INTEGER,
                mention_count INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_mentions_source_ticker
                ON company_mentions(source_ticker);
            CREATE INDEX IF NOT EXISTS idx_mentions_mentioned_ticker
                ON company_mentions(mentioned_ticker);
            CREATE INDEX IF NOT EXISTS idx_mentions_transcript_quarter
                ON company_mentions(transcript_quarter);
            CREATE INDEX IF NOT EXISTS idx_processed_file_path
                ON processed_transcripts(file_path);
        """)
        conn.commit()
    finally:
        conn.close()


def add_mention(
    source_doc_id: str,
    chunk_id: str,
    transcript_date: str,
    transcript_quarter: str,
    source_company: str,
    source_ticker: str,
    mentioned_company: str,
    mentioned_company_id: str | None,
    mentioned_ticker: str | None,
    speaker_role: str,
    context: str,
    context_before: str | None = None,
    context_after: str | None = None,
    confidence: float = 1.0,
    needs_review: bool = False,
    prompt_version: str = "v0",
    llm_model: str = "gemini-2.0-flash",
) -> int:
    """Insert a company mention record. Returns the row id."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO company_mentions (
                source_doc_id, chunk_id, transcript_date, transcript_quarter,
                source_company, source_ticker, mentioned_company,
                mentioned_company_id, mentioned_ticker, speaker_role,
                context, context_before, context_after,
                confidence, needs_review, prompt_version, llm_model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_doc_id,
                chunk_id,
                transcript_date,
                transcript_quarter,
                source_company,
                source_ticker,
                mentioned_company,
                mentioned_company_id,
                mentioned_ticker,
                speaker_role,
                context,
                context_before,
                context_after,
                confidence,
                int(needs_review),
                prompt_version,
                llm_model,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def add_mentions_batch(mentions: list[dict]) -> int:
    """Insert multiple mentions in a single transaction. Returns count inserted."""
    if not mentions:
        return 0
    conn = get_db()
    try:
        conn.executemany(
            """INSERT INTO company_mentions (
                source_doc_id, chunk_id, transcript_date, transcript_quarter,
                source_company, source_ticker, mentioned_company,
                mentioned_company_id, mentioned_ticker, speaker_role,
                context, context_before, context_after,
                confidence, needs_review, prompt_version, llm_model
            ) VALUES (
                :source_doc_id, :chunk_id, :transcript_date, :transcript_quarter,
                :source_company, :source_ticker, :mentioned_company,
                :mentioned_company_id, :mentioned_ticker, :speaker_role,
                :context, :context_before, :context_after,
                :confidence, :needs_review, :prompt_version, :llm_model
            )""",
            mentions,
        )
        conn.commit()
        return len(mentions)
    finally:
        conn.close()


def get_mentions_for(ticker: str) -> list[dict]:
    """Get all mentions OF a ticker (i.e., other companies mentioning this ticker).

    Returns list of dicts sorted by transcript_date desc.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM company_mentions
               WHERE mentioned_ticker = ?
               ORDER BY transcript_date DESC, source_company""",
            (ticker.upper(),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_mentions_by(ticker: str) -> list[dict]:
    """Get all mentions FROM a ticker (i.e., companies this ticker mentions).

    Returns list of dicts sorted by transcript_date desc.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM company_mentions
               WHERE source_ticker = ?
               ORDER BY transcript_date DESC, mentioned_company""",
            (ticker.upper(),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def is_transcript_processed(file_path: str) -> bool:
    """Check if a transcript file has already been processed."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM processed_transcripts WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_transcript_processed(
    file_path: str,
    ticker: str,
    quarter: str,
    chunk_count: int,
    mention_count: int,
):
    """Record that a transcript has been processed."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO processed_transcripts
               (file_path, ticker, quarter, chunk_count, mention_count)
               VALUES (?, ?, ?, ?, ?)""",
            (file_path, ticker, quarter, chunk_count, mention_count),
        )
        conn.commit()
    finally:
        conn.close()


def get_stats() -> dict:
    """Get database statistics."""
    conn = get_db()
    try:
        total_mentions = conn.execute(
            "SELECT COUNT(*) FROM company_mentions"
        ).fetchone()[0]

        total_transcripts = conn.execute(
            "SELECT COUNT(*) FROM processed_transcripts"
        ).fetchone()[0]

        unique_source_tickers = conn.execute(
            "SELECT COUNT(DISTINCT source_ticker) FROM company_mentions"
        ).fetchone()[0]

        unique_mentioned_tickers = conn.execute(
            "SELECT COUNT(DISTINCT mentioned_ticker) FROM company_mentions WHERE mentioned_ticker IS NOT NULL"
        ).fetchone()[0]

        needs_review = conn.execute(
            "SELECT COUNT(*) FROM company_mentions WHERE needs_review = 1"
        ).fetchone()[0]

        # Top mentioned companies
        top_mentioned = conn.execute(
            """SELECT mentioned_ticker, mentioned_company, COUNT(*) as cnt
               FROM company_mentions
               WHERE mentioned_ticker IS NOT NULL
               GROUP BY mentioned_ticker
               ORDER BY cnt DESC
               LIMIT 20""",
        ).fetchall()

        # Top mentioning companies
        top_mentioners = conn.execute(
            """SELECT source_ticker, source_company, COUNT(*) as cnt
               FROM company_mentions
               GROUP BY source_ticker
               ORDER BY cnt DESC
               LIMIT 20""",
        ).fetchall()

        # Recent transcripts processed
        recent = conn.execute(
            """SELECT ticker, quarter, mention_count, processed_at
               FROM processed_transcripts
               ORDER BY processed_at DESC
               LIMIT 10""",
        ).fetchall()

        return {
            "total_mentions": total_mentions,
            "total_transcripts": total_transcripts,
            "unique_source_tickers": unique_source_tickers,
            "unique_mentioned_tickers": unique_mentioned_tickers,
            "needs_review": needs_review,
            "top_mentioned": [dict(r) for r in top_mentioned],
            "top_mentioners": [dict(r) for r in top_mentioners],
            "recent_transcripts": [dict(r) for r in recent],
        }
    finally:
        conn.close()


# Auto-initialize on import
init_db()
