#!/usr/bin/env python3
"""
Backfill vector memory from existing earnings analyses and meeting briefings.

Usage:
    python vector_memory_backfill.py              # Full backfill (INSERT OR IGNORE)
    python vector_memory_backfill.py --dry-run    # Count files/chunks without embedding
    python vector_memory_backfill.py --ticker HOOD-US  # Single ticker
    python vector_memory_backfill.py --stats      # Show DB stats
    python vector_memory_backfill.py --rebuild    # DELETE + re-INSERT everything
"""

import argparse
import io
import sys
import time
from pathlib import Path

# Force UTF-8 stdout on Windows to handle Chinese filenames
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    pass  # already wrapped
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure shared modules are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.vector_memory import (
    VAULT,
    EARNINGS_DIR,
    MEETING_DIR,
    extract_chunks_from_file,
    embed_and_store,
    delete_by_source_file,
    get_stats,
    logger,
)


def find_earnings_files(ticker: str = None) -> list[Path]:
    """Find all earnings analysis files, optionally filtered by ticker."""
    if not EARNINGS_DIR.exists():
        print(f"WARNING: Earnings dir not found: {EARNINGS_DIR}")
        return []

    files = []
    if ticker:
        ticker_dir = EARNINGS_DIR / ticker
        if ticker_dir.exists():
            files = sorted(ticker_dir.glob("*Analysis*.md"))
        else:
            print(f"WARNING: Ticker dir not found: {ticker_dir}")
    else:
        files = sorted(EARNINGS_DIR.glob("*/*Analysis*.md"))

    # Filter out unwanted files
    filtered = []
    for f in files:
        name = f.name
        if name.startswith("_"):
            continue
        if "Peer" in name or "peer" in name:
            continue
        if "Pipeline" in name or "pipeline" in name:
            continue
        if "Dashboard" in name or "dashboard" in name:
            continue
        if "Insight Ledger" in name:
            continue
        # Must have Q in the name (quarter indicator)
        if "Q" not in name:
            continue
        filtered.append(f)

    return filtered


def find_meeting_files() -> list[Path]:
    """Find all meeting briefing files."""
    if not MEETING_DIR.exists():
        print(f"WARNING: Meeting dir not found: {MEETING_DIR}")
        return []

    # Meeting briefings have suffix -周会分析.md
    files = sorted(MEETING_DIR.glob("*-周会分析.md"))
    return files


def find_sellside_files() -> list[Path]:
    """Find all sellside tracking reports in the vault."""
    sellside_dir = VAULT / "研究" / "卖方跟踪"
    if not sellside_dir.exists():
        print(f"WARNING: Sellside dir not found: {sellside_dir}")
        return []

    files = sorted(sellside_dir.glob("**/*.md"))
    # Filter out underscore-prefixed and known skip patterns
    return [f for f in files if not f.name.startswith("_")]


def find_kb_import_files() -> list[Path]:
    """Find all KB import / research summary files in the vault."""
    kb_dir = VAULT / "研究" / "研报摘要"
    if not kb_dir.exists():
        print(f"WARNING: KB imports dir not found: {kb_dir}")
        return []

    files = sorted(kb_dir.glob("*.md"))
    return [f for f in files if not f.name.startswith("_")]


def find_info_source_files() -> list[Path]:
    """Find all information source files (substack, wechat, xueqiu, podcasts)."""
    info_dir = VAULT / "信息源"
    if not info_dir.exists():
        print(f"WARNING: Info sources dir not found: {info_dir}")
        return []

    files = sorted(info_dir.glob("**/*.md"))
    return [f for f in files if not f.name.startswith("_")]


def backfill(
    dry_run: bool = False,
    ticker: str = None,
    rebuild: bool = False,
) -> dict:
    """Run the backfill process.

    Returns summary dict.
    """
    # Collect files
    earnings_files = find_earnings_files(ticker)
    meeting_files = [] if ticker else find_meeting_files()
    sellside_files = [] if ticker else find_sellside_files()
    kb_import_files = [] if ticker else find_kb_import_files()
    info_source_files = [] if ticker else find_info_source_files()
    all_files = (
        earnings_files
        + meeting_files
        + sellside_files
        + kb_import_files
        + info_source_files
    )

    print(f"\nFiles found:")
    print(f"  Earnings analyses: {len(earnings_files)}")
    print(f"  Meeting briefings: {len(meeting_files)}")
    print(f"  Sellside reports:  {len(sellside_files)}")
    print(f"  KB imports:        {len(kb_import_files)}")
    print(f"  Info sources:      {len(info_source_files)}")
    print(f"  Total: {len(all_files)}")

    if dry_run:
        print(f"\n--- DRY RUN: extracting chunks (no embedding) ---\n")
        total_chunks = 0
        tickers_seen = set()
        for f in all_files:
            chunks = extract_chunks_from_file(f)
            if chunks:
                for c in chunks:
                    tickers_seen.add(c["ticker"])
                total_chunks += len(chunks)
                print(f"  {f.name}: {len(chunks)} chunks "
                      f"({', '.join(c['section_id'] for c in chunks)})")
            else:
                print(f"  {f.name}: 0 chunks (no matching sections)")

        print(f"\n--- DRY RUN SUMMARY ---")
        print(f"  Total chunks: {total_chunks}")
        print(f"  Unique tickers: {len(tickers_seen)}")
        print(f"  Estimated API cost: ~${total_chunks * 500 * 0.02 / 1_000_000:.4f}")
        return {
            "files": len(all_files),
            "chunks": total_chunks,
            "tickers": len(tickers_seen),
        }

    print(f"\n--- BACKFILL START ---\n")
    start_time = time.time()
    total_inserted = 0
    total_skipped = 0
    total_errors = 0
    total_deleted = 0

    for i, f in enumerate(all_files, 1):
        print(f"[{i}/{len(all_files)}] {f.name}...", end=" ", flush=True)

        chunks = extract_chunks_from_file(f)
        if not chunks:
            print("0 chunks")
            continue

        source_file = str(f)

        if rebuild:
            deleted = delete_by_source_file(source_file)
            total_deleted += deleted

        file_inserted = 0
        file_skipped = 0
        for chunk in chunks:
            try:
                ok = embed_and_store(
                    chunk_text=chunk["text"],
                    source_type=chunk["source_type"],
                    ticker=chunk["ticker"],
                    date=chunk["date"],
                    section_id=chunk["section_id"],
                    source_file=source_file,
                    quarter=chunk.get("quarter"),
                    metadata=chunk.get("metadata"),
                )
                if ok:
                    file_inserted += 1
                else:
                    file_skipped += 1
            except Exception as e:
                total_errors += 1
                print(f"\n  ERROR ({chunk['section_id']}): {e}")
                logger.error(f"Backfill error {f.name}/{chunk['section_id']}: {e}")

        total_inserted += file_inserted
        total_skipped += file_skipped
        print(f"{file_inserted} inserted, {file_skipped} skipped")

    elapsed = time.time() - start_time

    print(f"\n--- BACKFILL COMPLETE ---")
    print(f"  Duration: {elapsed:.0f}s")
    if rebuild:
        print(f"  Deleted (rebuild): {total_deleted}")
    print(f"  Inserted: {total_inserted}")
    print(f"  Skipped (duplicate): {total_skipped}")
    print(f"  Errors: {total_errors}")

    # Show final stats
    print(f"\n--- DB STATS ---")
    stats = get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return {
        "duration_s": elapsed,
        "deleted": total_deleted,
        "inserted": total_inserted,
        "skipped": total_skipped,
        "errors": total_errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill vector memory DB")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count files/chunks without embedding")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Process only this ticker (e.g., HOOD-US)")
    parser.add_argument("--stats", action="store_true",
                        help="Show DB statistics and exit")
    parser.add_argument("--rebuild", action="store_true",
                        help="Delete and re-insert all embeddings")

    args = parser.parse_args()

    if args.stats:
        stats = get_stats()
        print("Vector Memory DB Statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    backfill(
        dry_run=args.dry_run,
        ticker=args.ticker,
        rebuild=args.rebuild,
    )


if __name__ == "__main__":
    main()
