"""NotebookLM Attribution Helper for Phase 4 Decision Audit.

Wraps the NotebookLM skill's ask_question.py to provide structured
idea attribution queries: first-mention, perception arc, passed discovery.

Usage:
    from shared.nlm_attribution import query_first_mention, query_perception_arc

Design:
    - Calls NLM via subprocess (respects the skill's venv isolation)
    - Parses stdout for answer text, citations, conversation_id
    - Returns structured dicts for easy integration into thesis/flashback/review
    - Graceful degradation: returns empty results on NLM failure (never blocks)
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────
NLM_SKILL_DIR = Path.home() / ".claude" / "skills" / "notebooklm"
NLM_RUN_PY = NLM_SKILL_DIR / "scripts" / "run.py"
NLM_LIBRARY_JSON = NLM_SKILL_DIR / "data" / "library.json"

# Python executable
PYTHON = r"C:\Users\thisi\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not Path(PYTHON).exists():
    # macOS / Linux fallback
    PYTHON = sys.executable

# Default notebook for weekly meeting notes
DEFAULT_NOTEBOOK_ID = "投资观点周报-2025"


# ── Library helpers ────────────────────────────────────────────

def load_library() -> dict:
    """Load the NotebookLM library.json."""
    if not NLM_LIBRARY_JSON.exists():
        return {"notebooks": {}, "active_notebook_id": None}
    with open(NLM_LIBRARY_JSON, encoding="utf-8") as f:
        return json.load(f)


def get_notebook_ids() -> list[str]:
    """Return all registered notebook IDs."""
    lib = load_library()
    return list(lib.get("notebooks", {}).keys())


def get_notebook_name(notebook_id: str) -> str:
    """Get human-readable name for a notebook ID."""
    lib = load_library()
    nb = lib.get("notebooks", {}).get(notebook_id, {})
    return nb.get("name", notebook_id)


# ── Core NLM query ─────────────────────────────────────────────

def _run_nlm_query(
    question: str,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
    conversation_id: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """Run a NotebookLM query via subprocess and parse the output.

    Returns:
        {
            "answer": str,          # Full answer text
            "citations": [          # List of citation dicts
                {"numbers": [1,2], "text": "...", "source_id": "..."},
            ],
            "conversation_id": str or None,
            "success": bool,
            "error": str or None,
        }
    """
    if not NLM_RUN_PY.exists():
        return {
            "answer": "",
            "citations": [],
            "conversation_id": None,
            "success": False,
            "error": f"NotebookLM skill not found at {NLM_RUN_PY}",
        }

    cmd = [
        PYTHON,
        str(NLM_RUN_PY),
        "ask_question.py",
        "--question", question,
        "--notebook-id", notebook_id,
    ]
    if conversation_id:
        cmd.extend(["--conversation-id", conversation_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=str(NLM_SKILL_DIR),
        )

        # Decode with replacement to handle mixed encodings from Windows console
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        if result.returncode != 0:
            return {
                "answer": "",
                "citations": [],
                "conversation_id": None,
                "success": False,
                "error": stderr.strip() or f"Exit code {result.returncode}",
            }

        return _parse_nlm_output(stdout)

    except subprocess.TimeoutExpired:
        return {
            "answer": "",
            "citations": [],
            "conversation_id": None,
            "success": False,
            "error": f"NLM query timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "answer": "",
            "citations": [],
            "conversation_id": None,
            "success": False,
            "error": str(e),
        }


def _parse_nlm_output(stdout: str) -> dict:
    """Parse the stdout from ask_question.py into structured data."""
    lines = stdout.split("\n")

    # Find answer section (between the two === separator lines)
    sep_indices = [i for i, line in enumerate(lines) if line.strip().startswith("=" * 20)]
    answer_text = ""
    if len(sep_indices) >= 2:
        # Answer is between first two separators, after the "Question:" line
        answer_start = sep_indices[0] + 1
        answer_end = sep_indices[1] if len(sep_indices) > 1 else len(lines)
        answer_lines = []
        skip_question = True
        for line in lines[answer_start:answer_end]:
            if skip_question and line.strip().startswith("Question:"):
                skip_question = False
                continue
            if skip_question:
                continue
            # Stop at citations section
            if line.strip() == "--- Citations ---":
                break
            answer_lines.append(line)
        answer_text = "\n".join(answer_lines).strip()
    elif len(sep_indices) == 2:
        # Fallback: everything between separators
        answer_text = "\n".join(lines[sep_indices[0]+1:sep_indices[1]]).strip()

    # Parse citations
    citations = []
    in_citations = False
    current_citation = None
    for line in lines:
        if line.strip() == "--- Citations ---":
            in_citations = True
            continue
        if not in_citations:
            continue
        if line.strip().startswith("EXTREMELY IMPORTANT"):
            break

        # Citation line: [1,2] text...
        cite_match = re.match(r"\s+\[([^\]]+)\]\s+(.*)", line)
        if cite_match:
            if current_citation:
                citations.append(current_citation)
            nums_str = cite_match.group(1)
            nums = [int(n.strip()) for n in nums_str.split(",") if n.strip().isdigit()]
            current_citation = {
                "numbers": nums,
                "text": cite_match.group(2).strip(),
                "source_id": None,
            }
        elif line.strip().startswith("source:") and current_citation:
            current_citation["source_id"] = line.strip().replace("source:", "").strip()

    if current_citation:
        citations.append(current_citation)

    # Parse conversation_id
    conv_id = None
    for line in lines:
        if line.strip().startswith("conversation_id:"):
            conv_id = line.strip().replace("conversation_id:", "").strip()
            break

    return {
        "answer": answer_text,
        "citations": citations,
        "conversation_id": conv_id,
        "success": bool(answer_text),
        "error": None,
    }


# ── Query templates ────────────────────────────────────────────

def query_first_mention(
    ticker: str,
    company_name: str = "",
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
) -> dict:
    """Query NLM for when a ticker was first discussed.

    Returns:
        {
            "first_seen": str or None,       # Date string if found
            "source_detail": str,             # Human-readable source description
            "citation_text": str,             # Verbatim quote from NLM
            "initial_sentiment": str,         # bullish/bearish/neutral/unknown
            "answer": str,                    # Full NLM answer
            "citations": list,
            "conversation_id": str or None,
            "success": bool,
            "error": str or None,
        }
    """
    name_clause = f" (also known as {company_name})" if company_name else ""
    question = (
        f"When was {ticker}{name_clause} first discussed in these documents? "
        f"What was the initial view — bullish, bearish, or neutral? "
        f"Who brought it up and what was the specific context? "
        f"Please include the exact date if available and quote the relevant passage."
    )

    raw = _run_nlm_query(question, notebook_id=notebook_id)

    # Extract structured fields from the answer
    first_seen = _extract_date(raw["answer"])
    sentiment = _extract_sentiment(raw["answer"])
    citation_text = raw["citations"][0]["text"] if raw["citations"] else ""

    source_name = get_notebook_name(notebook_id)
    source_detail = f"{source_name}"
    if first_seen:
        source_detail = f"{source_name}, {first_seen}"

    return {
        "first_seen": first_seen,
        "source_detail": source_detail,
        "citation_text": citation_text,
        "initial_sentiment": sentiment,
        "answer": raw["answer"],
        "citations": raw["citations"],
        "conversation_id": raw["conversation_id"],
        "success": raw["success"],
        "error": raw["error"],
    }


def query_perception_arc(
    ticker: str,
    company_name: str = "",
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
) -> dict:
    """Query NLM for chronological discussion history of a ticker.

    Returns:
        {
            "mentions": [                    # Chronological list
                {"date": str, "sentiment": str, "summary": str},
            ],
            "answer": str,
            "citations": list,
            "conversation_id": str or None,
            "success": bool,
            "error": str or None,
        }
    """
    name_clause = f" (also known as {company_name})" if company_name else ""
    question = (
        f"List every time {ticker}{name_clause} was discussed in these documents, "
        f"in chronological order. For each mention, provide: "
        f"(1) the date, (2) whether the sentiment was bullish/bearish/neutral, "
        f"(3) a one-sentence summary of what was said. "
        f"Format as a numbered list."
    )

    raw = _run_nlm_query(question, notebook_id=notebook_id)

    # Parse numbered list from answer
    mentions = _parse_mention_list(raw["answer"])

    return {
        "mentions": mentions,
        "answer": raw["answer"],
        "citations": raw["citations"],
        "conversation_id": raw["conversation_id"],
        "success": raw["success"],
        "error": raw["error"],
    }


def query_passed_candidates(
    months: int = 3,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
    exclude_tickers: Optional[list[str]] = None,
) -> dict:
    """Query NLM for tickers discussed but possibly not acted on.

    Returns:
        {
            "candidates": [                  # Tickers discussed but infrequent
                {"ticker": str, "context": str, "date": str},
            ],
            "answer": str,
            "citations": list,
            "conversation_id": str or None,
            "success": bool,
            "error": str or None,
        }
    """
    exclude_str = ""
    if exclude_tickers:
        exclude_str = (
            f" Exclude these tickers (already in portfolio or tracked): "
            f"{', '.join(exclude_tickers)}."
        )

    question = (
        f"Which company tickers or stocks were discussed in the last {months} months "
        f"but only mentioned once or twice (not frequently discussed)?{exclude_str} "
        f"For each, provide the ticker symbol, the date it was mentioned, "
        f"and a brief context of the discussion. "
        f"Format as a numbered list with ticker, date, and context."
    )

    raw = _run_nlm_query(question, notebook_id=notebook_id, timeout=120)

    # Parse candidates from answer
    candidates = _parse_candidate_list(raw["answer"])

    return {
        "candidates": candidates,
        "answer": raw["answer"],
        "citations": raw["citations"],
        "conversation_id": raw["conversation_id"],
        "success": raw["success"],
        "error": raw["error"],
    }


def query_multi_notebook(
    ticker: str,
    company_name: str = "",
    notebook_ids: Optional[list[str]] = None,
) -> dict:
    """Query multiple NLM notebooks for a ticker and merge results.

    Useful for /flashback — queries weekly reports + ticker-specific notebooks.

    Returns:
        {
            "results": {notebook_id: query_result, ...},
            "combined_mentions": list,       # Merged and sorted by date
            "success": bool,
        }
    """
    if notebook_ids is None:
        # Default: weekly report + any notebook whose topics mention the ticker
        notebook_ids = [DEFAULT_NOTEBOOK_ID]
        lib = load_library()
        for nb_id, nb in lib.get("notebooks", {}).items():
            if nb_id == DEFAULT_NOTEBOOK_ID:
                continue
            topics = [t.upper() for t in nb.get("topics", [])]
            if ticker.upper() in topics or (company_name and company_name.upper() in " ".join(topics).upper()):
                notebook_ids.append(nb_id)

    results = {}
    all_mentions = []
    any_success = False

    for nb_id in notebook_ids:
        arc = query_perception_arc(ticker, company_name, notebook_id=nb_id)
        results[nb_id] = arc
        if arc["success"]:
            any_success = True
            for m in arc["mentions"]:
                m["notebook"] = get_notebook_name(nb_id)
                all_mentions.append(m)

    # Sort combined mentions by date
    all_mentions.sort(key=lambda m: m.get("date", "9999"))

    return {
        "results": results,
        "combined_mentions": all_mentions,
        "success": any_success,
    }


# ── Parsing helpers ────────────────────────────────────────────

def _extract_date(text: str) -> Optional[str]:
    """Extract the first date-like pattern from text."""
    # Try YYYY-MM-DD
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    # Try Month DD, YYYY
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        text,
    )
    if match:
        month_map = {
            "January": "01", "February": "02", "March": "03", "April": "04",
            "May": "05", "June": "06", "July": "07", "August": "08",
            "September": "09", "October": "10", "November": "11", "December": "12",
        }
        m = month_map[match.group(1)]
        d = match.group(2).zfill(2)
        y = match.group(3)
        return f"{y}-{m}-{d}"
    return None


def _extract_sentiment(text: str) -> str:
    """Extract sentiment from NLM answer text."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["bullish", "positive", "optimistic", "看多", "偏多"]):
        return "bullish"
    if any(w in text_lower for w in ["bearish", "negative", "pessimistic", "看空", "偏空"]):
        return "bearish"
    if any(w in text_lower for w in ["neutral", "mixed", "cautious", "中性"]):
        return "neutral"
    return "unknown"


def _parse_mention_list(text: str) -> list[dict]:
    """Parse a numbered list of mentions from NLM answer."""
    mentions = []
    # Match patterns like: 1. 2025-12-15 — bullish — "Some summary"
    # or: 1. On December 15, 2025, the sentiment was bullish: ...
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if it's a numbered list item
        if not re.match(r"^\d+[\.\)]\s", line):
            continue

        entry = {"date": None, "sentiment": "unknown", "summary": line}

        # Extract date
        date = _extract_date(line)
        if date:
            entry["date"] = date

        # Extract sentiment
        entry["sentiment"] = _extract_sentiment(line)

        # Clean summary (remove number prefix)
        entry["summary"] = re.sub(r"^\d+[\.\)]\s*", "", line).strip()

        mentions.append(entry)

    return mentions


def _parse_candidate_list(text: str) -> list[dict]:
    """Parse a list of ticker candidates from NLM answer."""
    candidates = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^\d+[\.\)]\s", line):
            continue

        entry = {"ticker": None, "context": line, "date": None}

        # Try to extract a ticker symbol ($TICKER or standalone UPPER)
        ticker_match = re.search(r"\$([A-Z]{1,5})\b", line)
        if ticker_match:
            entry["ticker"] = ticker_match.group(1)
        else:
            ticker_match = re.search(r"\b([A-Z]{2,5})\b", line)
            if ticker_match:
                # Quick filter for common non-ticker words
                candidate = ticker_match.group(1)
                skip_words = {"THE", "AND", "FOR", "ARE", "NOT", "BUT", "ALL", "WAS", "HAS"}
                if candidate not in skip_words:
                    entry["ticker"] = candidate

        entry["date"] = _extract_date(line)
        entry["context"] = re.sub(r"^\d+[\.\)]\s*", "", line).strip()

        if entry["ticker"]:
            candidates.append(entry)

    return candidates


# ── CLI ────────────────────────────────────────────────────────

def main():
    """CLI interface for testing NLM attribution queries."""
    import argparse

    parser = argparse.ArgumentParser(description="NLM Attribution Helper")
    sub = parser.add_subparsers(dest="command")

    # first-mention
    fm = sub.add_parser("first-mention", help="Query when a ticker was first discussed")
    fm.add_argument("ticker", help="Ticker symbol")
    fm.add_argument("--name", default="", help="Company name")
    fm.add_argument("--notebook", default=DEFAULT_NOTEBOOK_ID, help="Notebook ID")

    # perception-arc
    pa = sub.add_parser("perception-arc", help="Query discussion history")
    pa.add_argument("ticker", help="Ticker symbol")
    pa.add_argument("--name", default="", help="Company name")
    pa.add_argument("--notebook", default=DEFAULT_NOTEBOOK_ID, help="Notebook ID")

    # passed-candidates
    pc = sub.add_parser("passed-candidates", help="Discover passed candidates")
    pc.add_argument("--months", type=int, default=3, help="Lookback months")
    pc.add_argument("--notebook", default=DEFAULT_NOTEBOOK_ID, help="Notebook ID")
    pc.add_argument("--exclude", default="", help="Comma-separated tickers to exclude")

    # multi-notebook
    mn = sub.add_parser("multi-notebook", help="Query multiple notebooks")
    mn.add_argument("ticker", help="Ticker symbol")
    mn.add_argument("--name", default="", help="Company name")

    args = parser.parse_args()

    if args.command == "first-mention":
        result = query_first_mention(args.ticker, args.name, args.notebook)
        print(f"\n=== First Mention: {args.ticker} ===")
        print(f"Date: {result['first_seen'] or 'Not found'}")
        print(f"Sentiment: {result['initial_sentiment']}")
        print(f"Source: {result['source_detail']}")
        if result["citation_text"]:
            print(f"\nCitation: {result['citation_text'][:200]}")
        if not result["success"]:
            print(f"\nError: {result['error']}")

    elif args.command == "perception-arc":
        result = query_perception_arc(args.ticker, args.name, args.notebook)
        print(f"\n=== Perception Arc: {args.ticker} ===")
        for i, m in enumerate(result["mentions"], 1):
            print(f"  {i}. [{m['date'] or '?'}] {m['sentiment']} — {m['summary'][:100]}")
        if not result["mentions"]:
            print("  No mentions found.")
        if not result["success"]:
            print(f"\nError: {result['error']}")

    elif args.command == "passed-candidates":
        exclude = [t.strip() for t in args.exclude.split(",") if t.strip()] if args.exclude else None
        result = query_passed_candidates(args.months, args.notebook, exclude)
        print(f"\n=== Passed Candidates (last {args.months} months) ===")
        for i, c in enumerate(result["candidates"], 1):
            print(f"  {i}. {c['ticker']} [{c['date'] or '?'}] — {c['context'][:100]}")
        if not result["candidates"]:
            print("  No candidates found.")
        if not result["success"]:
            print(f"\nError: {result['error']}")

    elif args.command == "multi-notebook":
        result = query_multi_notebook(args.ticker, args.name)
        print(f"\n=== Multi-Notebook: {args.ticker} ===")
        print(f"Queried {len(result['results'])} notebooks")
        for m in result["combined_mentions"]:
            print(f"  [{m.get('date', '?')}] ({m.get('notebook', '?')}) {m['sentiment']} — {m['summary'][:80]}")
        if not result["combined_mentions"]:
            print("  No mentions found across any notebook.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
