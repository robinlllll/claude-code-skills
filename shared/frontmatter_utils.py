"""Shared frontmatter utilities for all skills.

Generates standardized YAML frontmatter per DATA_CONTRACT.md.
All auto-generated Obsidian notes must use these functions.
"""

import hashlib
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Paths ───────────────────────────────────────────────────

SHARED_DIR = Path(__file__).parent
DATA_DIR = SHARED_DIR / "data"
INGESTION_DB = DATA_DIR / "ingestion_state.db"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"


def get_db() -> sqlite3.Connection:
    """Get connection to ingestion state database, creating tables if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(INGESTION_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_state (
            canonical_key TEXT PRIMARY KEY,
            source_platform TEXT NOT NULL,
            stable_id TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            obsidian_path TEXT,
            metadata TEXT
        )
    """)
    conn.commit()
    return conn


def make_canonical_key(source_platform: str, stable_id: str) -> str:
    """Create canonical key for deduplication: {platform}_{stable_id}."""
    return f"{source_platform}_{stable_id}"


def make_url_hash(url: str) -> str:
    """Create a short hash from URL for use as stable_id."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def is_already_ingested(source_platform: str, stable_id: str) -> bool:
    """Check if content with this canonical key was already ingested."""
    key = make_canonical_key(source_platform, stable_id)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM ingestion_state WHERE canonical_key = ?", (key,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_ingestion(
    source_platform: str,
    stable_id: str,
    obsidian_path: Optional[str] = None,
    metadata: Optional[str] = None,
) -> str:
    """Record that content was ingested. Returns canonical key."""
    key = make_canonical_key(source_platform, stable_id)
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO ingestion_state
               (canonical_key, source_platform, stable_id, ingested_at, obsidian_path, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                key,
                source_platform,
                stable_id,
                datetime.now().isoformat(),
                obsidian_path,
                metadata,
            ),
        )
        conn.commit()
        return key
    finally:
        conn.close()


def build_frontmatter(
    *,
    id: str,
    type: str,
    source_platform: str,
    author: str = "",
    source_url: str = "",
    published_at: Optional[date] = None,
    tickers: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    extra: Optional[dict] = None,
) -> str:
    """Build standardized YAML frontmatter string per DATA_CONTRACT.

    Args:
        id: Canonical key (source_platform + stable_id)
        type: Note type (substack|x|transcript|thesis|passed|trade|backtest|supply-chain)
        source_platform: Origin platform
        author: Content author
        source_url: Original URL
        published_at: Original publication date
        tickers: List of ticker symbols mentioned
        tags: Obsidian tags
        extra: Additional frontmatter fields

    Returns:
        YAML frontmatter string including --- delimiters
    """
    pub_date = published_at.isoformat() if published_at else ""
    today = date.today().isoformat()
    ticker_list = tickers or []
    tag_list = tags or []

    lines = [
        "---",
        f'id: "{id}"',
        f"type: {type}",
        f"source_platform: {source_platform}",
        f'source_url: "{source_url}"',
        f'author: "{author}"',
        f"published_at: {pub_date}",
        f"ingested_at: {today}",
        f"tickers: [{', '.join(ticker_list)}]",
        f"tags: [{', '.join(tag_list)}]",
    ]

    if extra:
        for k, v in extra.items():
            if isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
            elif isinstance(v, list):
                lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
            else:
                lines.append(f'{k}: "{v}"')

    lines.append("---")
    return "\n".join(lines)


def safe_filename(name: str, max_length: int = 80) -> str:
    """Sanitize a string for use as a filename.

    Removes/replaces characters that are invalid on Windows/Mac.
    """
    # Replace problematic characters
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"]:
        name = name.replace(ch, " ")
    # Collapse multiple spaces
    name = " ".join(name.split())
    # Truncate
    if len(name) > max_length:
        name = name[:max_length].rstrip()
    return name.strip()
