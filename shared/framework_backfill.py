"""Backfill existing vault notes with framework_sections in frontmatter.

Scans all markdown files in the Obsidian Vault, tags them using keyword mode,
and adds framework_sections to their YAML frontmatter.

Usage:
    python framework_backfill.py --dry-run              # Preview changes
    python framework_backfill.py                         # Execute backfill
    python framework_backfill.py --folder "研究/研究笔记" # Only specific folder
    python framework_backfill.py --stats                 # Show current tagging stats
"""

import argparse
import re
import sys
from pathlib import Path

# Ensure shared imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.framework_tagger import tag_content

VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"

# Folders to scan (investment-relevant content only)
SCAN_FOLDERS = [
    "研究/研究笔记",
    "研究/财报分析",
    "研究/供应链",
    "研究/13F 持仓",
    "信息源/播客",
    "信息源/雪球",
    "信息源/剪藏",
    "信息源/Substack",
    "收件箱",
    "周会",
    "写作/投资回顾",
    "写作/思考性文章",
    "ChatGPT/Investment Research",
    "导航/NotebookLM",
]


def _has_frontmatter(content: str) -> bool:
    return content.startswith("---")


def _extract_frontmatter_end(content: str) -> int:
    """Return index of the closing --- delimiter, or -1."""
    if not content.startswith("---"):
        return -1
    end = content.find("---", 3)
    return end


def _has_framework_sections(content: str) -> bool:
    """Check if frontmatter already has framework_sections."""
    end = _extract_frontmatter_end(content)
    if end == -1:
        return False
    fm = content[3:end]
    return "framework_sections:" in fm


def backfill_file(filepath: Path, dry_run: bool = True) -> dict:
    """Backfill a single file with framework_sections.

    Returns dict with status info.
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    if len(content) < 100:
        return {"status": "skipped", "reason": "too_short"}

    if not _has_frontmatter(content):
        return {"status": "skipped", "reason": "no_frontmatter"}

    if _has_framework_sections(content):
        return {"status": "skipped", "reason": "already_tagged"}

    # Tag the content (keyword mode = fast, free)
    sections = tag_content(content, mode="keyword")
    if not sections:
        return {"status": "skipped", "reason": "no_sections_detected"}

    if dry_run:
        return {"status": "would_tag", "sections": sections}

    # Insert framework_sections into frontmatter (before closing ---)
    end = _extract_frontmatter_end(content)
    fm_section = content[:end]
    rest = content[end:]  # starts with "---"

    # Add framework_sections line before the closing ---
    sections_str = ", ".join(sections)
    new_line = f"framework_sections: [{sections_str}]"
    new_content = fm_section.rstrip() + "\n" + new_line + "\n" + rest

    filepath.write_text(new_content, encoding="utf-8")
    return {"status": "tagged", "sections": sections}


def run_backfill(folder: str | None = None, dry_run: bool = True):
    """Run backfill across vault folders."""
    import io

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if folder:
        folders = [folder]
    else:
        folders = SCAN_FOLDERS

    total = 0
    tagged = 0
    skipped = 0
    errors = 0
    already = 0

    for rel_folder in folders:
        folder_path = VAULT_DIR / rel_folder
        if not folder_path.exists():
            continue

        files = sorted(folder_path.glob("**/*.md"))
        out.write(f"\n[Folder] {rel_folder} ({len(files)} files)\n")

        for f in files:
            total += 1
            result = backfill_file(f, dry_run=dry_run)

            if result["status"] == "tagged" or result["status"] == "would_tag":
                tagged += 1
                sections = result.get("sections", [])
                action = "WOULD TAG" if dry_run else "TAGGED"
                out.write(f"  {action}: {f.name} -> [{', '.join(sections)}]\n")
            elif result["status"] == "skipped":
                if result["reason"] == "already_tagged":
                    already += 1
                else:
                    skipped += 1
            elif result["status"] == "error":
                errors += 1
                out.write(f"  ERROR: {f.name} -- {result['reason']}\n")

    out.write(f"\n{'=' * 60}\n")
    mode_str = "DRY RUN" if dry_run else "BACKFILL COMPLETE"
    out.write(f"{mode_str}\n")
    out.write(f"  Total files scanned: {total}\n")
    out.write(f"  {'Would tag' if dry_run else 'Tagged'}: {tagged}\n")
    out.write(f"  Already tagged: {already}\n")
    out.write(f"  Skipped (no match): {skipped}\n")
    out.write(f"  Errors: {errors}\n")

    if dry_run and tagged > 0:
        out.write(f"\nRun without --dry-run to apply changes to {tagged} files.\n")
    out.flush()


def show_stats():
    """Show current framework tagging statistics across vault."""
    total = 0
    tagged = 0
    section_counts = {}

    for rel_folder in SCAN_FOLDERS:
        folder_path = VAULT_DIR / rel_folder
        if not folder_path.exists():
            continue

        for f in sorted(folder_path.glob("**/*.md")):
            total += 1
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:1000]
            except Exception:
                continue

            if not _has_frontmatter(content):
                continue

            end = _extract_frontmatter_end(content)
            if end == -1:
                continue

            fm = content[3:end]
            match = re.search(r"framework_sections:\s*\[([^\]]*)\]", fm)
            if match:
                tagged += 1
                raw = match.group(1)
                for s in raw.split(","):
                    s = s.strip()
                    if s:
                        parent = s.split(".")[0]
                        section_counts[parent] = section_counts.get(parent, 0) + 1

    import io

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    out.write(f"Framework Tagging Stats\n")
    out.write(f"{'=' * 40}\n")
    out.write(f"Total files: {total}\n")
    out.write((f"Tagged: {tagged} ({tagged/total*100:.0f}%)\n" if total > 0 else "Tagged: 0\n"))
    out.write(f"Untagged: {total - tagged}\n")

    if section_counts:
        out.write(f"\nSection distribution:\n")
        for sid in sorted(section_counts.keys()):
            out.write(f"  {sid}: {section_counts[sid]} files\n")
    out.flush()


def main():
    parser = argparse.ArgumentParser(description="Backfill vault notes with framework_sections")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview changes without writing (default: off)")
    parser.add_argument("--folder", type=str, default=None,
                        help="Only backfill a specific vault subfolder")
    parser.add_argument("--stats", action="store_true",
                        help="Show current tagging statistics")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    run_backfill(folder=args.folder, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
