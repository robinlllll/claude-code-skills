"""Agent 1: Vault Hygiene Checks & Fixes.

Scans vault for missing frontmatter, missing date prefixes, empty files,
and orphan notes. Builds a backlink index for efficient orphan detection.
Auto-fixes missing frontmatter when enabled. Reports all issues.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n", re.MULTILINE)

# Folder → default tag mapping for auto-generated frontmatter
FOLDER_TAG_MAP = {
    "收件箱": "inbox",
    "研究": "research",
    "信息源": "source",
    "周会": "meeting",
    "写作": "writing",
}


def safe_write(path: Path, content: str, retries: int = 3):
    """Atomic write with Windows PermissionError retry."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    for i in range(retries):
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.5 * (i + 1))
    raise PermissionError(f"Cannot write to {path} after {retries} retries")


def _build_backlink_index(vault_path: Path, scan_folders: list[str],
                          ignore_folders: list[str]) -> dict[str, set[str]]:
    """Build {note_stem: set(referencing_file_paths)} from all wikilinks.

    Single pass over all .md files to find [[...]] references.
    Returns lowercase stems for case-insensitive matching.
    """
    index: dict[str, set[str]] = {}
    all_folders = [vault_path]  # Scan entire vault for backlinks

    for md_file in vault_path.rglob("*.md"):
        # Skip ignored folders
        rel = md_file.relative_to(vault_path)
        if any(part in ignore_folders for part in rel.parts):
            continue

        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        links = WIKILINK_RE.findall(content)
        for link in links:
            # Normalize: strip path prefixes, lowercase
            stem = link.strip().split("/")[-1].lower()
            if stem not in index:
                index[stem] = set()
            index[stem].add(str(md_file))

    return index


def _has_frontmatter(content: str) -> bool:
    """Check if content starts with YAML frontmatter."""
    return content.startswith("---")


def _get_creation_date(filepath: Path) -> str:
    """Get file creation date as YYYY-MM-DD string."""
    try:
        # On Windows, st_ctime is creation time
        ctime = filepath.stat().st_ctime
        return datetime.fromtimestamp(ctime).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _get_folder_tag(filepath: Path, vault_path: Path) -> str:
    """Determine tag based on which scan folder the file is in."""
    try:
        rel = filepath.relative_to(vault_path)
        top_folder = rel.parts[0] if rel.parts else ""
        return FOLDER_TAG_MAP.get(top_folder, "note")
    except Exception:
        return "note"


def _build_minimal_frontmatter(filepath: Path, vault_path: Path) -> str:
    """Build minimal frontmatter for a file missing it."""
    created = _get_creation_date(filepath)
    tag = _get_folder_tag(filepath, vault_path)
    return f"---\ncreated: {created}\ntags: [{tag}]\n---\n\n"


def _suggest_directory(filepath: Path, vault_path: Path) -> str | None:
    """Heuristic: suggest moving research-like notes out of 收件箱."""
    try:
        rel = filepath.relative_to(vault_path)
        if rel.parts[0] != "收件箱":
            return None

        content = filepath.read_text(encoding="utf-8", errors="replace")[:500].lower()
        # If it has multiple tickers or research keywords, suggest 研究
        research_signals = ["thesis", "earnings", "revenue", "margin", "valuation",
                            "bull case", "bear case", "kill criteria"]
        matches = sum(1 for s in research_signals if s in content)
        if matches >= 2:
            return "研究/研究笔记"
    except Exception:
        pass
    return None


def run(config: dict, dry_run: bool = False, **kwargs) -> dict:
    """Run the vault hygiene agent."""
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "agent": "hygiene",
        "status": "success",
        "started_at": started,
        "metrics": {},
        "issues": [],
        "actions_taken": [],
        "errors": [],
    }

    vault_path = config["vault_path"]
    h_cfg = config.get("hygiene", {})
    scan_folders = h_cfg.get("scan_folders", ["收件箱", "研究", "信息源", "周会", "写作"])
    ignore_folders = h_cfg.get("ignore_folders", [".obsidian", ".trash", "归档"])
    min_bytes = h_cfg.get("min_content_bytes", 50)
    auto_fix_fm = h_cfg.get("auto_fix_frontmatter", True)
    auto_fix_date = h_cfg.get("auto_fix_date_prefix", False)
    max_renames = config.get("safety", {}).get("max_renames_per_run", 0)

    # Stage 1: Build backlink index (single pass over entire vault)
    print("  Building backlink index...")
    backlink_index = _build_backlink_index(vault_path, scan_folders, ignore_folders)

    # Stage 2: Scan configured folders
    missing_frontmatter = []
    missing_date_prefix = []
    empty_files = []
    orphan_notes = []
    wrong_directory = []
    actions_taken = []

    files_scanned = 0

    for folder_name in scan_folders:
        folder_path = vault_path / folder_name
        if not folder_path.exists():
            continue

        for md_file in folder_path.rglob("*.md"):
            # Skip ignored subfolders
            rel = md_file.relative_to(vault_path)
            if any(part in ignore_folders for part in rel.parts):
                continue

            files_scanned += 1

            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                result["errors"].append(f"Cannot read {md_file}: {e}")
                continue

            file_path_str = str(rel)

            # Check 1: Frontmatter
            if not _has_frontmatter(content):
                created = _get_creation_date(md_file)
                missing_frontmatter.append({
                    "type": "missing_frontmatter",
                    "path": file_path_str,
                    "severity": "P2",
                    "created_date": created,
                })

                # Auto-fix: add minimal frontmatter
                if auto_fix_fm and not dry_run:
                    try:
                        new_content = _build_minimal_frontmatter(md_file, vault_path) + content
                        safe_write(md_file, new_content)
                        actions_taken.append({
                            "type": "frontmatter_added",
                            "path": file_path_str,
                            "details": f"Added minimal frontmatter (created: {created})",
                        })
                    except Exception as e:
                        result["errors"].append(f"Failed to fix frontmatter for {file_path_str}: {e}")

            # Check 2: Date prefix in filename
            if not DATE_PREFIX_RE.match(md_file.stem):
                missing_date_prefix.append({
                    "type": "missing_date_prefix",
                    "path": file_path_str,
                    "severity": "P3",
                    "created_date": _get_creation_date(md_file),
                })
                # auto_fix_date_prefix is OFF by default — renaming breaks wikilinks

            # Check 3: Empty/stub files
            content_bytes = len(content.encode("utf-8"))
            # Subtract frontmatter from byte count
            if _has_frontmatter(content):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2]
                    content_bytes = len(body.strip().encode("utf-8"))

            if content_bytes < min_bytes:
                empty_files.append({
                    "type": "empty_file",
                    "path": file_path_str,
                    "severity": "P3",
                    "size": content_bytes,
                })

            # Check 4: Orphan notes (no incoming wikilinks)
            stem_lower = md_file.stem.lower()
            if stem_lower not in backlink_index:
                orphan_notes.append({
                    "type": "orphan_note",
                    "path": file_path_str,
                    "severity": "P3",
                    "last_modified": datetime.fromtimestamp(
                        md_file.stat().st_mtime
                    ).strftime("%Y-%m-%d"),
                })

            # Check 5: Wrong directory heuristic
            suggested = _suggest_directory(md_file, vault_path)
            if suggested:
                wrong_directory.append({
                    "type": "wrong_directory",
                    "path": file_path_str,
                    "severity": "P3",
                    "suggested_dir": suggested,
                })

    # Compile issues (P-sorted)
    all_issues = missing_frontmatter + missing_date_prefix + empty_files + orphan_notes + wrong_directory
    result["issues"] = all_issues
    result["actions_taken"] = actions_taken

    result["metrics"] = {
        "files_scanned": files_scanned,
        "issues_found": len(all_issues),
        "missing_frontmatter": len(missing_frontmatter),
        "missing_date_prefix": len(missing_date_prefix),
        "empty_files": len(empty_files),
        "orphan_notes": len(orphan_notes),
        "wrong_directory": len(wrong_directory),
        "auto_fixed": len(actions_taken),
        "backlink_index_size": len(backlink_index),
    }

    # Save backlink index for linker agent to reuse
    backlink_export = {k: list(v) for k, v in backlink_index.items()}
    backlink_path = OUTPUT_DIR / "backlink_index.json"
    backlink_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(backlink_path, "w", encoding="utf-8") as f:
            json.dump(backlink_export, f, ensure_ascii=False)
    except Exception as e:
        result["errors"].append(f"Failed to save backlink index: {e}")

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vault Hygiene Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    result = run(cfg, dry_run=args.dry_run)

    out_path = OUTPUT_DIR / "hygiene_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Status: {result['status']}")
    m = result["metrics"]
    print(f"  Scanned: {m['files_scanned']}, Issues: {m['issues_found']}, Fixed: {m['auto_fixed']}")
    print(f"  Missing FM: {m['missing_frontmatter']}, No date: {m['missing_date_prefix']}, "
          f"Empty: {m['empty_files']}, Orphans: {m['orphan_notes']}")
    if result["errors"]:
        print(f"  Errors: {result['errors']}")
