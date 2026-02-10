"""Core extraction pipeline for supply chain mentions.

Reads earnings transcript PDFs, chunks by speaker turn, calls Gemini 2.0 Flash
to extract company mentions, resolves entities, and stores in SQLite.

v0: Mention index only. No relationship classification.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Add skills root so shared imports work
sys.path.insert(0, r"C:\Users\thisi\.claude\skills")

import pdfplumber
from dotenv import load_dotenv
from google import genai

from shared.entity_resolver import resolve_entity, resolve_entity_fuzzy
from supply_chain_db import (
    add_mentions_batch,
    get_mentions_by,
    get_mentions_for,
    get_stats,
    init_db,
    is_transcript_processed,
    record_transcript_processed,
)

# ── Configuration ─────────────────────────────────────────────

TRANSCRIPT_DIR = Path(r"C:\Users\thisi\Downloads\Earnings Transcripts")
PROMPT_VERSION = "v0"
LLM_MODEL = "gemini-2.0-flash"
MAX_TOKENS_PER_CHUNK = 2000  # Approximate tokens per chunk
GEMINI_SEMAPHORE = asyncio.Semaphore(3)  # Limit concurrent Gemini calls

# Load API key from 13F-CLAUDE .env or environment
_env_path = Path(r"C:\Users\thisi\13F-CLAUDE\.env")
if _env_path.exists():
    load_dotenv(_env_path)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ── Gemini Prompt ─────────────────────────────────────────────

MENTION_EXTRACTION_PROMPT = """You are a financial analyst. Extract all mentions of OTHER companies from this earnings transcript segment.

For each mention, provide:
- mentioned_company: The company name as stated in the transcript
- context: The EXACT verbatim quote containing the mention (1-3 sentences)
- speaker_role: Who is speaking (CEO/CFO/analyst/other)

Rules:
- Only extract EXPLICIT company name mentions (not "a major customer" or "our partner")
- The context MUST be a verbatim quote from the transcript
- Do not include the company that is presenting (they are the source, not a mention)

Source company: {source_company} ({source_ticker})
Transcript date: {date}

Output as JSON array:
[{{"mentioned_company": "...", "context": "...", "speaker_role": "..."}}]

If no companies are mentioned, return: []

Transcript segment:
---
{chunk_text}
---"""


# ── PDF Text Extraction ──────────────────────────────────────


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract full text from a PDF using pdfplumber."""
    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


# ── Speaker-Based Chunking ───────────────────────────────────

# Common patterns for speaker turns in FactSet/Callstreet transcripts
SPEAKER_PATTERN = re.compile(
    r"^([A-Z][A-Za-z\.\-\' ]{2,40})\n"  # Name on its own line
    r"((?:Chief .+Officer|CEO|CFO|COO|CTO|CMO|President|"
    r"Vice President|VP|SVP|EVP|Director|Analyst|"
    r"Managing Director|Senior Vice President|"
    r"Head of .+|General Manager|Chairman|"
    r"Chief .+ & .+|Operator|Moderator).*)",
    re.MULTILINE,
)

# Simpler pattern: "Name, Title" on one line
SPEAKER_INLINE_PATTERN = re.compile(
    r"^([A-Z][A-Za-z\.\-\' ]{2,40}),\s*"
    r"((?:Chief .+Officer|CEO|CFO|COO|CTO|CMO|President|"
    r"Vice President|VP|SVP|EVP|Director|Analyst|"
    r"Managing Director|Senior Vice President|"
    r"Head of .+|General Manager|Chairman|Operator|Moderator).*)",
    re.MULTILINE,
)

# Q&A section header
QA_SECTION_PATTERN = re.compile(
    r"^(?:QUESTION AND ANSWER|Q&A|Questions? [Aa]nd [Aa]nswers?)",
    re.MULTILINE,
)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def _classify_speaker_role(title: str) -> str:
    """Classify a speaker title into a standard role."""
    title_lower = title.lower()
    if any(t in title_lower for t in ["ceo", "chief executive"]):
        return "CEO"
    if any(t in title_lower for t in ["cfo", "chief financial"]):
        return "CFO"
    if any(t in title_lower for t in ["coo", "chief operating"]):
        return "COO"
    if any(t in title_lower for t in ["cto", "chief technology"]):
        return "CTO"
    if "analyst" in title_lower:
        return "analyst"
    if any(t in title_lower for t in ["president", "vp", "vice president"]):
        return "executive"
    if any(t in title_lower for t in ["director", "head of", "manager"]):
        return "director"
    if any(t in title_lower for t in ["operator", "moderator"]):
        return "operator"
    return "other"


def chunk_by_speaker(text: str, source_ticker: str) -> list[dict]:
    """Split transcript text into chunks by speaker turn.

    Each chunk is approximately MAX_TOKENS_PER_CHUNK tokens.
    Returns list of {text, speaker_role, chunk_id}.
    """
    # Find all speaker transitions
    splits = []
    for pattern in [SPEAKER_PATTERN, SPEAKER_INLINE_PATTERN]:
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            title = match.group(2).strip()
            splits.append(
                {
                    "pos": match.start(),
                    "name": name,
                    "title": title,
                    "role": _classify_speaker_role(title),
                }
            )

    # Sort by position and deduplicate nearby splits
    splits.sort(key=lambda s: s["pos"])

    # If we found no speaker turns, fall back to fixed-size chunking
    if len(splits) < 2:
        return _chunk_fixed_size(text, source_ticker)

    # Build chunks from speaker segments
    chunks = []
    for i, split in enumerate(splits):
        start = split["pos"]
        end = splits[i + 1]["pos"] if i + 1 < len(splits) else len(text)
        segment_text = text[start:end].strip()

        if not segment_text or _estimate_tokens(segment_text) < 20:
            continue

        # If segment is too large, sub-chunk it
        if _estimate_tokens(segment_text) > MAX_TOKENS_PER_CHUNK * 1.5:
            sub_chunks = _split_large_segment(segment_text, MAX_TOKENS_PER_CHUNK)
            for j, sub in enumerate(sub_chunks):
                chunks.append(
                    {
                        "text": sub,
                        "speaker_role": split["role"],
                        "speaker_name": split["name"],
                        "chunk_id": f"{source_ticker}_chunk_{len(chunks):04d}",
                    }
                )
        else:
            chunks.append(
                {
                    "text": segment_text,
                    "speaker_role": split["role"],
                    "speaker_name": split["name"],
                    "chunk_id": f"{source_ticker}_chunk_{len(chunks):04d}",
                }
            )

    return chunks


def _chunk_fixed_size(text: str, source_ticker: str) -> list[dict]:
    """Fallback: chunk text into fixed-size pieces by paragraph."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_text = ""
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current_tokens + para_tokens > MAX_TOKENS_PER_CHUNK and current_text:
            chunks.append(
                {
                    "text": current_text.strip(),
                    "speaker_role": "unknown",
                    "speaker_name": "",
                    "chunk_id": f"{source_ticker}_chunk_{len(chunks):04d}",
                }
            )
            current_text = ""
            current_tokens = 0
        current_text += para + "\n\n"
        current_tokens += para_tokens

    if current_text.strip():
        chunks.append(
            {
                "text": current_text.strip(),
                "speaker_role": "unknown",
                "speaker_name": "",
                "chunk_id": f"{source_ticker}_chunk_{len(chunks):04d}",
            }
        )

    return chunks


def _split_large_segment(text: str, max_tokens: int) -> list[str]:
    """Split a large text segment into smaller pieces at sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces = []
    current = ""
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _estimate_tokens(sentence)
        if current_tokens + sent_tokens > max_tokens and current:
            pieces.append(current.strip())
            current = ""
            current_tokens = 0
        current += sentence + " "
        current_tokens += sent_tokens

    if current.strip():
        pieces.append(current.strip())

    return pieces


# ── Gemini Mention Extraction ─────────────────────────────────


def _init_gemini_client() -> genai.Client:
    """Initialize the Gemini client."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not found. Set it in environment or in "
            "C:\\Users\\thisi\\13F-CLAUDE\\.env"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def _parse_gemini_json(response_text: str) -> list[dict]:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove first line (```json or ```) and last line (```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []


async def extract_mentions_from_chunk(
    chunk: dict,
    source_company: str,
    source_ticker: str,
    transcript_date: str,
    client: genai.Client,
) -> list[dict]:
    """Extract company mentions from a single chunk using Gemini.

    Returns list of mention dicts ready for database insertion.
    """
    prompt = MENTION_EXTRACTION_PROMPT.format(
        source_company=source_company,
        source_ticker=source_ticker,
        date=transcript_date,
        chunk_text=chunk["text"],
    )

    async with GEMINI_SEMAPHORE:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=LLM_MODEL,
                contents=prompt,
            )
            raw_mentions = _parse_gemini_json(response.text)
        except Exception as e:
            print(f"    [ERROR] Gemini call failed for {chunk['chunk_id']}: {e}")
            return []

    # Process and validate each mention
    valid_mentions = []
    for raw in raw_mentions:
        mentioned_company = raw.get("mentioned_company", "").strip()
        context = raw.get("context", "").strip()
        speaker_role = raw.get("speaker_role", chunk.get("speaker_role", "unknown"))

        # Quality gate: must have both company name and verbatim quote
        if not mentioned_company or not context:
            continue

        # Skip if the mentioned company is the source company itself
        if mentioned_company.lower() == source_company.lower():
            continue
        if mentioned_company.upper() == source_ticker.upper():
            continue

        # Entity resolution via dictionary
        resolved = resolve_entity(mentioned_company)
        if resolved is None:
            resolved = resolve_entity_fuzzy(mentioned_company)

        mentioned_ticker = resolved["ticker"] if resolved else None
        mentioned_company_id = resolved["canonical_name"] if resolved else None
        confidence = resolved["confidence"] if resolved else 0.5
        needs_review = resolved["needs_review"] if resolved else True

        # Skip if resolved ticker is the source ticker
        if mentioned_ticker and mentioned_ticker.upper() == source_ticker.upper():
            continue

        valid_mentions.append(
            {
                "source_doc_id": chunk.get("source_doc_id", ""),
                "chunk_id": chunk["chunk_id"],
                "transcript_date": transcript_date,
                "transcript_quarter": chunk.get("transcript_quarter", ""),
                "source_company": source_company,
                "source_ticker": source_ticker,
                "mentioned_company": mentioned_company,
                "mentioned_company_id": mentioned_company_id,
                "mentioned_ticker": mentioned_ticker,
                "speaker_role": speaker_role,
                "context": context,
                "context_before": None,
                "context_after": None,
                "confidence": confidence,
                "needs_review": int(needs_review),
                "prompt_version": PROMPT_VERSION,
                "llm_model": LLM_MODEL,
            }
        )

    return valid_mentions


# ── Folder/File Parsing ───────────────────────────────────────


def parse_ticker_from_folder(folder_name: str) -> tuple[str, str]:
    """Parse company name and ticker from folder name.

    "AAON, Inc (AAON-US)" -> ("AAON, Inc", "AAON")
    "Advanced Micro Devices, Inc (AMD-US)" -> ("Advanced Micro Devices, Inc", "AMD")
    """
    match = re.match(r"^(.+?)\s*\(([A-Z0-9\.\-]+)-[A-Z]{2}\)$", folder_name)
    if match:
        company = match.group(1).strip()
        ticker = match.group(2).strip()
        return company, ticker

    # Fallback: try without country suffix
    match = re.match(r"^(.+?)\s*\(([A-Z0-9\.\-]+)\)$", folder_name)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    return folder_name, ""


def _parse_quarter_from_filename(filename: str) -> tuple[str, str]:
    """Extract quarter and date from transcript filename.

    "CORRECTED TRANSCRIPT_ AAON, Inc.(AAON-US), Q2 2025 Earnings Call, 11-August-2025 9_00 AM ET.pdf"
    -> ("Q2 2025", "2025-08-11")
    """
    # Quarter pattern
    q_match = re.search(r"(Q[1-4]\s+\d{4})", filename)
    quarter = q_match.group(1) if q_match else ""

    # Date pattern: "11-August-2025" or similar
    date_match = re.search(r"(\d{1,2})-(\w+)-(\d{4})", filename)
    if date_match:
        day = date_match.group(1).zfill(2)
        month_str = date_match.group(2)
        year = date_match.group(3)
        months = {
            "January": "01",
            "February": "02",
            "March": "03",
            "April": "04",
            "May": "05",
            "June": "06",
            "July": "07",
            "August": "08",
            "September": "09",
            "October": "10",
            "November": "11",
            "December": "12",
        }
        month = months.get(month_str, "01")
        transcript_date = f"{year}-{month}-{day}"
    else:
        transcript_date = ""

    return quarter, transcript_date


# ── Main Processing Functions ─────────────────────────────────


async def process_transcript(pdf_path: Path) -> dict:
    """Process a single transcript PDF. Returns summary dict."""
    file_path_str = str(pdf_path)

    # Check if already processed
    if is_transcript_processed(file_path_str):
        return {
            "status": "skipped",
            "reason": "already_processed",
            "path": file_path_str,
        }

    # Parse metadata from path
    folder_name = pdf_path.parent.name
    company, ticker = parse_ticker_from_folder(folder_name)
    quarter, transcript_date = _parse_quarter_from_filename(pdf_path.name)

    if not ticker:
        print(f"  [WARN] Could not parse ticker from: {folder_name}")
        return {"status": "skipped", "reason": "no_ticker", "path": file_path_str}

    print(f"  Processing: {ticker} {quarter} ({pdf_path.name})")

    # Extract text
    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as e:
        print(f"    [ERROR] PDF extraction failed: {e}")
        return {"status": "error", "reason": f"pdf_error: {e}", "path": file_path_str}

    if not text or len(text) < 100:
        print(f"    [WARN] Very short text ({len(text)} chars), skipping")
        return {"status": "skipped", "reason": "too_short", "path": file_path_str}

    # Chunk by speaker
    chunks = chunk_by_speaker(text, ticker)
    print(f"    Chunks: {len(chunks)}")

    # Add metadata to each chunk
    source_doc_id = f"{ticker}_{quarter}_{pdf_path.stem}"
    for chunk in chunks:
        chunk["source_doc_id"] = source_doc_id
        chunk["transcript_quarter"] = quarter

    # Extract mentions via Gemini
    client = _init_gemini_client()
    all_mentions = []

    for i, chunk in enumerate(chunks):
        mentions = await extract_mentions_from_chunk(
            chunk, company, ticker, transcript_date, client
        )
        all_mentions.extend(mentions)
        if mentions:
            print(f"    Chunk {i + 1}/{len(chunks)}: {len(mentions)} mentions")

    # Store in database
    if all_mentions:
        added = add_mentions_batch(all_mentions)
        print(f"    Total mentions stored: {added}")
    else:
        print("    No mentions found")

    # Record as processed
    record_transcript_processed(
        file_path=file_path_str,
        ticker=ticker,
        quarter=quarter,
        chunk_count=len(chunks),
        mention_count=len(all_mentions),
    )

    return {
        "status": "processed",
        "path": file_path_str,
        "ticker": ticker,
        "quarter": quarter,
        "chunks": len(chunks),
        "mentions": len(all_mentions),
    }


async def scan_all_transcripts(transcript_dir: Path | None = None) -> dict:
    """Process all new (unprocessed) transcripts.

    Returns summary dict with counts.
    """
    if transcript_dir is None:
        transcript_dir = TRANSCRIPT_DIR

    if not transcript_dir.exists():
        print(f"Transcript directory not found: {transcript_dir}")
        return {"error": "directory_not_found", "path": str(transcript_dir)}

    # Ensure DB is initialized
    init_db()

    # Collect all PDFs
    pdf_files = sorted(transcript_dir.rglob("*.pdf"))
    total = len(pdf_files)
    print(f"Found {total} PDF files in {transcript_dir}")

    # Filter to unprocessed only
    new_pdfs = [p for p in pdf_files if not is_transcript_processed(str(p))]
    print(f"New (unprocessed): {len(new_pdfs)} / {total}")

    if not new_pdfs:
        print("Nothing to process.")
        return {
            "total_pdfs": total,
            "new_pdfs": 0,
            "processed": 0,
            "mentions_found": 0,
            "errors": 0,
        }

    processed = 0
    total_mentions = 0
    errors = 0

    for i, pdf_path in enumerate(new_pdfs):
        print(f"\n[{i + 1}/{len(new_pdfs)}] {pdf_path.parent.name}")
        try:
            result = await process_transcript(pdf_path)
            if result["status"] == "processed":
                processed += 1
                total_mentions += result["mentions"]
            elif result["status"] == "error":
                errors += 1
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            errors += 1

    print(f"\n{'=' * 60}")
    print(
        f"Scan complete: {processed} processed, {total_mentions} mentions, {errors} errors"
    )

    return {
        "total_pdfs": total,
        "new_pdfs": len(new_pdfs),
        "processed": processed,
        "mentions_found": total_mentions,
        "errors": errors,
    }


# ── CLI Interface ─────────────────────────────────────────────


def _print_mentions_for(ticker: str):
    """Print all mentions OF a ticker (who mentions them)."""
    ticker = ticker.upper()
    mentions = get_mentions_for(ticker)
    print(f"\n{'=' * 70}")
    print(f"  Companies that mention {ticker}: {len(mentions)} mentions")
    print(f"{'=' * 70}")

    if not mentions:
        print("  No mentions found.")
        # Also check mentions BY this ticker
        by_mentions = get_mentions_by(ticker)
        if by_mentions:
            print(
                f"\n  (But {ticker} mentions {len(by_mentions)} other companies — see below)"
            )
        else:
            print(f"  (No mentions by {ticker} either. Has it been scanned?)")

    # Group by source company
    by_source: dict[str, list] = {}
    for m in mentions:
        key = f"{m['source_company']} ({m['source_ticker']})"
        by_source.setdefault(key, []).append(m)

    for source, source_mentions in sorted(by_source.items()):
        print(f"\n  --- {source} ({len(source_mentions)} mentions) ---")
        for m in source_mentions:
            quarter = m.get("transcript_quarter", "?")
            role = m.get("speaker_role", "?")
            context = m["context"][:200] + ("..." if len(m["context"]) > 200 else "")
            review = " [NEEDS REVIEW]" if m.get("needs_review") else ""
            print(f'    [{quarter}] ({role}) "{context}"{review}')

    # Also show who this ticker mentions
    by_mentions = get_mentions_by(ticker)
    if by_mentions:
        print(f"\n{'=' * 70}")
        print(f"  {ticker} mentions these companies: {len(by_mentions)} mentions")
        print(f"{'=' * 70}")

        by_mentioned: dict[str, list] = {}
        for m in by_mentions:
            mentioned_display = m.get("mentioned_ticker") or m["mentioned_company"]
            by_mentioned.setdefault(mentioned_display, []).append(m)

        for mentioned, mm_list in sorted(by_mentioned.items()):
            print(f"\n  --- {mentioned} ({len(mm_list)} mentions) ---")
            for m in mm_list:
                quarter = m.get("transcript_quarter", "?")
                role = m.get("speaker_role", "?")
                context = m["context"][:200] + (
                    "..." if len(m["context"]) > 200 else ""
                )
                print(f'    [{quarter}] ({role}) "{context}"')


def _print_stats():
    """Print database statistics."""
    stats = get_stats()
    print(f"\n{'=' * 60}")
    print("  Supply Chain Mention Database — Statistics")
    print(f"{'=' * 60}")
    print(f"  Total mentions:          {stats['total_mentions']}")
    print(f"  Transcripts processed:   {stats['total_transcripts']}")
    print(f"  Unique source tickers:   {stats['unique_source_tickers']}")
    print(f"  Unique mentioned tickers:{stats['unique_mentioned_tickers']}")
    print(f"  Needs review:            {stats['needs_review']}")

    if stats["top_mentioned"]:
        print("\n  Top 20 Most Mentioned Companies:")
        print(f"  {'Ticker':<10} {'Company':<35} {'Count':>5}")
        print(f"  {'-' * 10} {'-' * 35} {'-' * 5}")
        for r in stats["top_mentioned"]:
            ticker = r["mentioned_ticker"] or "?"
            print(f"  {ticker:<10} {r['mentioned_company']:<35} {r['cnt']:>5}")

    if stats["top_mentioners"]:
        print("\n  Top 20 Companies That Mention Others:")
        print(f"  {'Ticker':<10} {'Company':<35} {'Count':>5}")
        print(f"  {'-' * 10} {'-' * 35} {'-' * 5}")
        for r in stats["top_mentioners"]:
            print(f"  {r['source_ticker']:<10} {r['source_company']:<35} {r['cnt']:>5}")

    if stats["recent_transcripts"]:
        print("\n  Recently Processed Transcripts:")
        print(f"  {'Ticker':<10} {'Quarter':<12} {'Mentions':>8} {'Processed At'}")
        print(f"  {'-' * 10} {'-' * 12} {'-' * 8} {'-' * 20}")
        for r in stats["recent_transcripts"]:
            print(
                f"  {r['ticker']:<10} {r['quarter']:<12} {r['mention_count']:>8} {r['processed_at']}"
            )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Supply Chain Mention Extractor v0")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan and process new transcripts")
    scan_parser.add_argument(
        "--dir", type=str, default=None, help="Override transcript directory"
    )
    scan_parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Only process transcripts for a specific ticker",
    )

    # query command
    query_parser = subparsers.add_parser("query", help="Query mentions for a ticker")
    query_parser.add_argument("ticker", type=str, help="Ticker to look up")

    # stats command
    subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()

    if args.command == "scan":
        transcript_dir = Path(args.dir) if args.dir else TRANSCRIPT_DIR

        if args.ticker:
            # Find folder for specific ticker
            ticker_upper = args.ticker.upper()
            matching = [
                d
                for d in transcript_dir.iterdir()
                if d.is_dir() and f"({ticker_upper}-" in d.name
            ]
            if not matching:
                print(f"No transcript folder found for ticker: {ticker_upper}")
                sys.exit(1)
            # Process only PDFs in matching folders
            init_db()
            total_mentions = 0
            for folder in matching:
                print(f"\nScanning: {folder.name}")
                for pdf_path in sorted(folder.glob("*.pdf")):
                    if not is_transcript_processed(str(pdf_path)):
                        result = asyncio.run(process_transcript(pdf_path))
                        if result["status"] == "processed":
                            total_mentions += result["mentions"]
            print(f"\nDone. Total mentions: {total_mentions}")
        else:
            result = asyncio.run(scan_all_transcripts(transcript_dir))
            print(f"\nResult: {json.dumps(result, indent=2)}")

    elif args.command == "query":
        _print_mentions_for(args.ticker)

    elif args.command == "stats":
        _print_stats()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
