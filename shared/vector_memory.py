"""
Vector Memory Layer — lightweight semantic search over earnings analyses and meeting briefings.

Uses SQLite + numpy for cosine similarity. OpenAI text-embedding-3-small for embeddings.
Total expected volume: ~1,400 embeddings, growth ~50/month. No heavy deps needed.

Usage:
    from shared.vector_memory import query_similar, embed_and_store, upsert_from_file
    from shared.vector_memory import format_memories_for_context, get_stats

    # Store
    embed_and_store("chunk text", source_type="earnings", ticker="HOOD-US",
                    date="2026-02-10", section_id="1_synthesis",
                    source_file="/path/to/analysis.md")

    # Query
    results = query_similar("management shifted to aggressive investment", top_k=5)
    print(format_memories_for_context(results))
"""

import json
import logging
import os
import re
import sqlite3
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import frontmatter
import numpy as np

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path.home() / ".claude" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "vector_memory.log"

logger = logging.getLogger("vector_memory")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_DIR = Path.home() / ".claude" / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "vector_memory.db"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Vault paths
VAULT = Path.home() / "Documents" / "Obsidian Vault"
EARNINGS_DIR = VAULT / "研究" / "财报分析"
MEETING_DIR = Path.home() / "Documents" / "会议实录"

# Regex patterns for earnings section extraction (flexible # level)
RE_SECTION_1 = re.compile(
    r"^(#{1,6})\s*1\.\s*综合评估与投资启示.*$", re.MULTILINE
)
RE_SECTION_4 = re.compile(
    r"^(#{1,6})\s*4\.\s*管理层叙事演变.*$", re.MULTILINE
)
# Generic section header: any "## N." pattern
RE_SECTION_HEADER = re.compile(r"^#{1,6}\s*\d+\.\s*", re.MULTILINE)

# Meeting briefing per-ticker header: ### **$TICKER (Company Name)**
RE_MEETING_TICKER = re.compile(
    r"^#{1,4}\s*\*{0,2}\$?([A-Z][A-Z0-9.\-]{0,9})\s*[\(（](.+?)[\)）]\*{0,2}\s*$",
    re.MULTILINE,
)

# Filename pattern for earnings analysis
RE_EARNINGS_FILENAME = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:\s+\d{4})?\s+([A-Z0-9.\-]+-[A-Z]{2})\s+"
    r"(Q\d\s+(?:FY)?\d{4})\s+vs\s+(Q\d\s+(?:FY)?\d{4})\s+Analysis\.md$"
)

# Meeting briefing filename
RE_MEETING_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-周会分析\.md$")

# ---------------------------------------------------------------------------
# OpenAI client (lazy init)
# ---------------------------------------------------------------------------
_openai_client = None


def _get_openai_client():
    """Lazy-init OpenAI client with API key from env files."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    # Load env
    from dotenv import load_dotenv
    load_dotenv(Path.home() / "Screenshots" / ".env")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment")

    from openai import OpenAI
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------
def _embed_text(text: str) -> np.ndarray:
    """Get embedding vector for a text chunk. Returns float32 numpy array (1536,)."""
    client = _get_openai_client()
    # Truncate to ~8000 tokens (~32000 chars) to stay within model limits
    if len(text) > 32000:
        text = text[:32000]
    resp = client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    vec = np.array(resp.data[0].embedding, dtype=np.float32)
    return vec


def _vec_to_blob(vec: np.ndarray) -> bytes:
    """Serialize float32 numpy array to bytes."""
    return vec.tobytes()


def _blob_to_vec(blob: bytes) -> np.ndarray:
    """Deserialize bytes to float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _get_db() -> sqlite3.Connection:
    """Get a database connection, creating schema if needed."""
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type     TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            quarter         TEXT,
            date            DATE NOT NULL,
            section_id      TEXT NOT NULL,
            chunk_text      TEXT NOT NULL,
            embedding       BLOB NOT NULL,
            embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
            source_file     TEXT NOT NULL,
            metadata_json   TEXT DEFAULT '{}',
            created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_file, section_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON embeddings(ticker)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_type_ticker "
        "ON embeddings(source_type, ticker)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_file ON embeddings(source_file)"
    )
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Public API: Store
# ---------------------------------------------------------------------------
def embed_and_store(
    chunk_text: str,
    source_type: str,
    ticker: str,
    date: str,
    section_id: str,
    source_file: str,
    quarter: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """Embed a text chunk and store in the database.

    Returns True if inserted, False if skipped (duplicate).
    """
    try:
        vec = _embed_text(chunk_text)
        blob = _vec_to_blob(vec)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        db = _get_db()
        db.execute(
            """INSERT OR IGNORE INTO embeddings
               (source_type, ticker, quarter, date, section_id,
                chunk_text, embedding, embedding_model, source_file, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_type, ticker, quarter, date, section_id,
             chunk_text, blob, EMBEDDING_MODEL, source_file, meta_json),
        )
        inserted = db.total_changes
        db.commit()
        db.close()
        if inserted:
            logger.info(f"Stored: {ticker} / {section_id} from {source_file}")
        return bool(inserted)
    except Exception as e:
        logger.error(f"embed_and_store failed: {e}")
        raise


def delete_by_source_file(source_file: str) -> int:
    """Delete all embeddings for a given source file. Returns count deleted."""
    db = _get_db()
    cursor = db.execute(
        "DELETE FROM embeddings WHERE source_file = ?", (source_file,)
    )
    count = cursor.rowcount
    db.commit()
    db.close()
    if count:
        logger.info(f"Deleted {count} embeddings for {source_file}")
    return count


def upsert_from_file(file_path: str) -> dict:
    """Convenience: delete old embeddings for this file, then re-extract and store.

    Handles both earnings analysis and meeting briefing formats.
    Returns {"deleted": N, "inserted": N, "chunks": [...]}.
    """
    file_path = str(file_path)
    p = Path(file_path)

    # Delete old
    deleted = delete_by_source_file(file_path)

    # Determine type and extract
    chunks = extract_chunks_from_file(p)
    inserted = 0
    for chunk in chunks:
        try:
            ok = embed_and_store(
                chunk_text=chunk["text"],
                source_type=chunk["source_type"],
                ticker=chunk["ticker"],
                date=chunk["date"],
                section_id=chunk["section_id"],
                source_file=file_path,
                quarter=chunk.get("quarter"),
                metadata=chunk.get("metadata"),
            )
            if ok:
                inserted += 1
        except Exception as e:
            logger.error(f"upsert chunk failed ({chunk.get('section_id')}): {e}")

    logger.info(
        f"upsert_from_file: {p.name} → deleted={deleted}, inserted={inserted}"
    )
    return {"deleted": deleted, "inserted": inserted, "chunks": chunks}


# ---------------------------------------------------------------------------
# Public API: Query
# ---------------------------------------------------------------------------
def query_similar(
    query_text: str,
    top_k: int = 5,
    ticker: Optional[str] = None,
    source_type: Optional[str] = None,
    min_score: float = 0.70,
) -> list[dict]:
    """Semantic search. Returns list of dicts sorted by similarity desc.

    Each dict: {id, source_type, ticker, quarter, date, section_id,
                chunk_text, source_file, metadata, score}
    """
    query_vec = _embed_text(query_text)

    db = _get_db()
    # Build WHERE clause
    conditions = ["embedding_model = ?"]
    params: list = [EMBEDDING_MODEL]
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"SELECT id, source_type, ticker, quarter, date, section_id, "
        f"chunk_text, embedding, source_file, metadata_json "
        f"FROM embeddings WHERE {where}",
        params,
    ).fetchall()
    db.close()

    # Score all rows
    results = []
    for row in rows:
        (rid, stype, tick, qtr, dt, sid, text, blob, sf, meta_json) = row
        vec = _blob_to_vec(blob)
        score = _cosine_similarity(query_vec, vec)
        if score >= min_score:
            results.append({
                "id": rid,
                "source_type": stype,
                "ticker": tick,
                "quarter": qtr,
                "date": dt,
                "section_id": sid,
                "chunk_text": text,
                "source_file": sf,
                "metadata": json.loads(meta_json) if meta_json else {},
                "score": round(score, 4),
            })

    # Sort by score desc, return top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def query_ticker(ticker: str, top_k: int = 10) -> list[dict]:
    """Get all memories for a ticker, sorted by date desc."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, source_type, ticker, quarter, date, section_id, "
        "chunk_text, source_file, metadata_json "
        "FROM embeddings WHERE ticker = ? ORDER BY date DESC LIMIT ?",
        (ticker, top_k),
    ).fetchall()
    db.close()

    return [
        {
            "id": r[0],
            "source_type": r[1],
            "ticker": r[2],
            "quarter": r[3],
            "date": r[4],
            "section_id": r[5],
            "chunk_text": r[6],
            "source_file": r[7],
            "metadata": json.loads(r[8]) if r[8] else {},
        }
        for r in rows
    ]


def format_memories_for_context(memories: list[dict], max_chars: int = 3000) -> str:
    """Format memory results into a markdown block for Claude context injection."""
    if not memories:
        return ""

    lines = ["## Prior Context (Vector Memory)\n"]
    total = 0
    for m in memories:
        score_str = f" (score: {m['score']:.2f})" if "score" in m else ""
        header = (
            f"### {m['ticker']} — {m.get('quarter', m['date'])} "
            f"[{m['section_id']}]{score_str}"
        )
        # Truncate chunk if needed
        text = m["chunk_text"]
        remaining = max_chars - total - len(header) - 10
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + "..."
        lines.append(header)
        lines.append(text)
        lines.append("")
        total += len(header) + len(text) + 2

    return "\n".join(lines)


def get_stats() -> dict:
    """Return database statistics."""
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    tickers = db.execute(
        "SELECT COUNT(DISTINCT ticker) FROM embeddings"
    ).fetchone()[0]
    by_type = dict(
        db.execute(
            "SELECT source_type, COUNT(*) FROM embeddings GROUP BY source_type"
        ).fetchall()
    )
    date_range = db.execute(
        "SELECT MIN(date), MAX(date) FROM embeddings"
    ).fetchone()
    models = dict(
        db.execute(
            "SELECT embedding_model, COUNT(*) FROM embeddings "
            "GROUP BY embedding_model"
        ).fetchall()
    )
    db.close()

    return {
        "total_embeddings": total,
        "unique_tickers": tickers,
        "by_source_type": by_type,
        "date_range": {"min": date_range[0], "max": date_range[1]} if date_range[0] else None,
        "by_model": models,
        "db_path": str(DB_PATH),
    }


# ---------------------------------------------------------------------------
# Extraction: Earnings Analysis
# ---------------------------------------------------------------------------
def _extract_section(content: str, start_re: re.Pattern, end_re_or_none=None) -> Optional[str]:
    """Extract a section from markdown between start_re match and the next section header."""
    m = start_re.search(content)
    if not m:
        return None

    start = m.end()
    # Find next section header of same or higher level
    hash_level = len(m.group(1))  # number of # chars
    # Look for next header at same or fewer # level
    rest = content[start:]
    next_header = None
    for nm in RE_SECTION_HEADER.finditer(rest):
        # Check if this header's level is <= our level (same or higher heading)
        hashes = len(nm.group().split()[0])  # count # chars
        if hashes <= hash_level:
            next_header = nm.start()
            break

    if next_header is not None:
        text = rest[:next_header].strip()
    else:
        text = rest.strip()

    # Limit to reasonable length (first ~4000 chars)
    if len(text) > 4000:
        text = text[:4000]
    return text if len(text) > 50 else None


def extract_earnings_chunks(file_path: Path) -> list[dict]:
    """Extract Section 1 (综合评估) and Section 4 (管理层叙事) from an earnings analysis file.

    Returns list of chunk dicts ready for embed_and_store.
    """
    content = file_path.read_text(encoding="utf-8")

    # Parse filename for metadata
    m = RE_EARNINGS_FILENAME.match(file_path.name)
    if not m:
        # Try relaxed match: just get date and ticker from filename
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
        ticker_m = re.search(r"([A-Z0-9.\-]+-[A-Z]{2})", file_path.name)
        if not date_m or not ticker_m:
            logger.warning(f"Cannot parse filename: {file_path.name}")
            return []
        date_str = date_m.group(1)
        ticker = ticker_m.group(1)
        # Try to get quarter from filename
        q_m = re.search(r"(Q\d\s+(?:FY)?\d{4})\s+vs\s+(Q\d\s+(?:FY)?\d{4})", file_path.name)
        quarter = q_m.group(1) if q_m else None
    else:
        date_str = m.group(1)
        ticker = m.group(2)
        quarter = m.group(3)

    # Also try getting ticker/quarter from YAML frontmatter
    fm_ticker = None
    fm_quarter = None
    fm_company = None
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_block = content[3:end]
            tm = re.search(r"^ticker:\s*(.+)$", fm_block, re.MULTILINE)
            if tm:
                fm_ticker = tm.group(1).strip()
            qm = re.search(r"^quarters:\s*\[(.+?)\]", fm_block, re.MULTILINE)
            if qm:
                quarters = [q.strip() for q in qm.group(1).split(",")]
                if quarters:
                    fm_quarter = quarters[0]
            cm = re.search(r"^company:\s*(.+)$", fm_block, re.MULTILINE)
            if cm:
                fm_company = cm.group(1).strip()

    ticker = fm_ticker or ticker
    quarter = fm_quarter or quarter

    chunks = []

    # Section 1: 综合评估与投资启示
    sec1 = _extract_section(content, RE_SECTION_1)
    if sec1:
        chunks.append({
            "text": sec1,
            "source_type": "earnings",
            "ticker": ticker,
            "date": date_str,
            "section_id": "1_synthesis",
            "quarter": quarter,
            "metadata": {"company": fm_company} if fm_company else {},
        })

    # Section 4: 管理层叙事演变
    sec4 = _extract_section(content, RE_SECTION_4)
    if sec4:
        chunks.append({
            "text": sec4,
            "source_type": "earnings",
            "ticker": ticker,
            "date": date_str,
            "section_id": "4_narrative",
            "quarter": quarter,
            "metadata": {"company": fm_company} if fm_company else {},
        })

    return chunks


# ---------------------------------------------------------------------------
# Extraction: Meeting Briefings
# ---------------------------------------------------------------------------
def extract_meeting_chunks(file_path: Path) -> list[dict]:
    """Extract per-ticker chunks from a meeting briefing file.

    Looks for per-company sections with headers like:
        ### **$TICKER (Company Name)**
    Combines 核心观点摘要 + 潜在行动提示 into one chunk per ticker.
    """
    content = file_path.read_text(encoding="utf-8")

    # Parse date from filename
    m = RE_MEETING_FILENAME.match(file_path.name)
    if not m:
        # Try relaxed date extraction
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
        if not dm:
            logger.warning(f"Cannot parse meeting filename: {file_path.name}")
            return []
        date_str = dm.group(1)
    else:
        date_str = m.group(1)

    # Find all per-ticker sections
    matches = list(RE_MEETING_TICKER.finditer(content))
    if not matches:
        logger.debug(f"No per-ticker sections found in {file_path.name}")
        return []

    chunks = []
    for i, match in enumerate(matches):
        ticker_raw = match.group(1)
        company = match.group(2).strip()

        # Normalize ticker (add -US if no region suffix)
        if "-" not in ticker_raw:
            ticker = f"{ticker_raw}-US"
        else:
            ticker = ticker_raw

        # Get section text until next ticker section
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_text = content[start:end].strip()

        if len(section_text) < 50:
            continue

        # Try to detect stance from text
        stance = "中性"
        if re.search(r"偏多|看多|加仓|建仓", section_text):
            stance = "偏多"
        elif re.search(r"偏空|看空|减仓|卖出", section_text):
            stance = "偏空"

        # Truncate to ~4000 chars
        if len(section_text) > 4000:
            section_text = section_text[:4000]

        chunks.append({
            "text": section_text,
            "source_type": "meeting",
            "ticker": ticker,
            "date": date_str,
            "section_id": "meeting_stance",
            "quarter": None,
            "metadata": {
                "company": company,
                "stance": stance,
            },
        })

    return chunks


def extract_sellside_chunks(file_path: Path) -> list[dict]:
    """Extract key thesis + rating from sellside tracking notes."""
    try:
        post = frontmatter.load(str(file_path))
    except Exception:
        return []

    content = post.content
    metadata = post.metadata
    ticker = metadata.get("ticker", "")
    if not ticker:
        return []

    doc_date = str(metadata.get("date", datetime.now().strftime("%Y-%m-%d")))
    quarter = metadata.get("quarter")
    chunks = []

    # Extract 核心观点 section
    view_match = re.search(r"^###?\s*(核心观点|Key Takeaway|Summary|Investment Thesis)", content, re.MULTILINE | re.IGNORECASE)
    if view_match:
        start = view_match.end()
        next_section = re.search(r"^###?\s+", content[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else min(start + 2000, len(content))
        view_text = content[start:end].strip()

        # Grab rating + target price
        rating_match = re.search(r"(Buy|Sell|Hold|Overweight|Underweight|Neutral|Equal.?Weight)", content, re.IGNORECASE)
        target_match = re.search(r"(?:目标价|target\s*price|TP)[:\s]*\$?([\d,.]+)", content, re.IGNORECASE)

        meta_parts = []
        if rating_match:
            meta_parts.append(f"Rating: {rating_match.group(1)}")
        if target_match:
            meta_parts.append(f"Target: ${target_match.group(1)}")
        if meta_parts:
            view_text = " | ".join(meta_parts) + "\n\n" + view_text

        if len(view_text) > 100:
            chunks.append({
                "text": view_text[:4000],
                "source_type": "sellside",
                "ticker": ticker,
                "date": doc_date,
                "section_id": "sellside_view",
                "quarter": quarter,
                "metadata": {
                    "rating": rating_match.group(1) if rating_match else None,
                    "target_price": target_match.group(1) if target_match else None,
                },
            })
    return chunks


def extract_news_chunks(file_path: Path) -> list[dict]:
    """Extract ticker-relevant paragraphs from news articles."""
    try:
        post = frontmatter.load(str(file_path))
    except Exception:
        return []

    metadata = post.metadata
    content = post.content
    tickers = metadata.get("tickers", [])
    if not tickers:
        return []

    doc_date = str(metadata.get("published_at") or metadata.get("date") or metadata.get("ingested_at", datetime.now().strftime("%Y-%m-%d")))
    chunks = []

    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if len(p.strip()) > 50]

    ALIAS_MAP = {
        "GOOG": ["Google", "Alphabet"], "META": ["Meta", "Facebook"],
        "MSFT": ["Microsoft"], "AAPL": ["Apple"], "AMZN": ["Amazon"],
        "NVDA": ["Nvidia"], "TSLA": ["Tesla"],
    }

    for ticker in tickers:
        if isinstance(ticker, str):
            ticker = ticker.strip()
        else:
            continue
        aliases = [ticker] + ALIAS_MAP.get(ticker, [])

        relevant = []
        for i, para in enumerate(paragraphs):
            if any(alias.lower() in para.lower() for alias in aliases):
                context_paras = []
                if i > 0:
                    context_paras.append(paragraphs[i - 1])
                context_paras.append(para)
                if i < len(paragraphs) - 1:
                    context_paras.append(paragraphs[i + 1])
                relevant.append("\n\n".join(context_paras))

        if relevant:
            chunk_text = "\n\n---\n\n".join(relevant[:3])
            chunks.append({
                "text": chunk_text[:4000],
                "source_type": "news",
                "ticker": ticker,
                "date": doc_date,
                "section_id": "news_insight",
                "quarter": None,
                "metadata": {"source_file_type": "news_article"},
            })
    return chunks


def extract_generic_chunks(file_path: Path) -> list[dict]:
    """Extract summary from KB imports, podcasts, and other content."""
    try:
        post = frontmatter.load(str(file_path))
    except Exception:
        return []

    metadata = post.metadata
    content = post.content
    tickers = metadata.get("tickers", [])
    if not tickers:
        return []

    doc_date = str(metadata.get("published_at") or metadata.get("date") or metadata.get("ingested_at", datetime.now().strftime("%Y-%m-%d")))
    source_type = metadata.get("type", metadata.get("source_type", "research"))

    # Extract summary section
    summary_match = re.search(r"^##\s*摘要\s*\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.MULTILINE)
    if summary_match:
        summary_text = summary_match.group(1).strip()
    else:
        summary_text = content[:2000].strip()

    if len(summary_text) < 50:
        return []

    chunks = []
    for ticker in tickers:
        if isinstance(ticker, str):
            ticker = ticker.strip()
        else:
            continue
        chunks.append({
            "text": summary_text[:4000],
            "source_type": source_type,
            "ticker": ticker,
            "date": doc_date,
            "section_id": "research_summary",
            "quarter": None,
            "metadata": {"original_type": source_type},
        })
    return chunks


# ---------------------------------------------------------------------------
# Unified extraction
# ---------------------------------------------------------------------------
def extract_chunks_from_file(file_path: Path) -> list[dict]:
    """Route file to appropriate chunk extractor based on filename and frontmatter."""
    file_path = Path(file_path)
    if not file_path.exists():
        logger.warning("File not found: %s", file_path)
        return []

    fname = file_path.name

    # Skip files
    if fname.startswith("_"):
        return []
    skip_keywords = ["Peer", "Pipeline", "Dashboard", "Insight Ledger", "券商观点汇总"]
    if any(kw in fname for kw in skip_keywords):
        return []

    # Route by filename pattern (existing types first)
    if "Analysis" in fname and re.search(r"Q\d", fname):
        return extract_earnings_chunks(file_path)
    elif "周会分析" in fname:
        return extract_meeting_chunks(file_path)
    elif "卖方跟踪" in fname or "卖方跟踪" in str(file_path):
        return extract_sellside_chunks(file_path)

    # Route by frontmatter type
    try:
        post = frontmatter.load(str(file_path))
        ftype = post.metadata.get("type", "")
        if ftype == "news_article":
            return extract_news_chunks(file_path)
        elif ftype in ("research_report", "expert_call", "article", "podcast", "substack"):
            return extract_generic_chunks(file_path)
    except Exception as e:
        logger.warning("Error reading frontmatter from %s: %s", file_path, e)

    # Path-based fallback for files with no recognized frontmatter type
    file_str = str(file_path)
    if "研报摘要" in file_str or "信息源" in file_str:
        return extract_generic_chunks(file_path)

    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import pprint

    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        pprint.pprint(get_stats())
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        # Quick self-test: embed a string, store it, query it
        print("Running self-test...")
        test_text = "Management shifted focus to aggressive reinvestment, expense growth accelerating significantly."
        embed_and_store(
            chunk_text=test_text,
            source_type="test",
            ticker="TEST-US",
            date="2026-01-01",
            section_id="test_chunk",
            source_file="__test__",
            metadata={"test": True},
        )
        results = query_similar(test_text, top_k=1)
        if results and results[0]["score"] > 0.95:
            print(f"PASS: Self-test passed. Score: {results[0]['score']}")
        else:
            print(f"FAIL: Self-test failed. Results: {results}")
        # Cleanup
        delete_by_source_file("__test__")
        print("PASS: Cleanup done")
    else:
        print("Usage: python vector_memory.py [stats|test]")
