"""Agent 6: Vector Memory Incremental Backfill.

Scans earnings analyses and meeting briefings for new files not yet
embedded in the vector memory DB. Inserts new embeddings (INSERT OR IGNORE).
Runs in ~2s when no new files exist, ~1s per new file when there are additions.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

SKILLS_DIR = r"C:\Users\thisi\.claude\skills"
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)


def run(config: dict = None, dry_run: bool = False, **kwargs) -> dict:
    """Run incremental vector memory backfill.

    Returns standard agent result dict.
    """
    started = datetime.now(timezone.utc).isoformat()
    errors = []
    actions = []

    try:
        from shared.vector_memory import get_stats
        from shared.vector_memory_backfill import find_earnings_files, find_meeting_files
        from shared.vector_memory import extract_chunks_from_file, embed_and_store, logger

        before_stats = get_stats()
        before_total = before_stats["total_embeddings"]

        # Collect all eligible files
        earnings_files = find_earnings_files()
        meeting_files = find_meeting_files()
        all_files = earnings_files + meeting_files

        inserted = 0
        skipped = 0
        new_files = 0

        for f in all_files:
            chunks = extract_chunks_from_file(f)
            if not chunks:
                continue

            source_file = str(f)
            file_had_new = False

            for chunk in chunks:
                if dry_run:
                    skipped += 1
                    continue

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
                        inserted += 1
                        file_had_new = True
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(f"{f.name}: {e}")
                    logger.error(f"agent_vector_memory error {f.name}: {e}")

            if file_had_new:
                new_files += 1
                actions.append(f"Embedded {f.name}")

        after_stats = get_stats()
        after_total = after_stats["total_embeddings"]

        metrics = {
            "files_scanned": len(all_files),
            "new_files": new_files,
            "inserted": inserted,
            "skipped": skipped,
            "total_embeddings": after_total,
            "unique_tickers": after_stats["unique_tickers"],
        }

        if dry_run:
            actions.append(f"[DRY RUN] Would scan {len(all_files)} files")

        status = "success" if not errors else "partial"

    except ImportError as e:
        metrics = {}
        status = "failed"
        errors.append(f"Import error: {e}")
    except Exception as e:
        metrics = {}
        status = "failed"
        errors.append(f"{type(e).__name__}: {e}")

    return {
        "agent": "vector_memory",
        "status": status,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "issues": [],
        "actions_taken": actions,
        "errors": errors,
    }


if __name__ == "__main__":
    import json
    result = run(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, indent=2, ensure_ascii=False))
