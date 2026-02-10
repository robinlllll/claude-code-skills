"""
NotebookLM Auto-Source Sync.

Maintains ticker → notebook mapping. Scans Obsidian vault and project
directories for new ticker-related content. Adds new sources to the
corresponding NotebookLM notebook via source_manager.py.

Usage:
    python notebooklm_sync.py register PM --notebook-id pm-philip-morris-2025-transcripts
    python notebooklm_sync.py status
    python notebooklm_sync.py scan PM              # Preview what would be synced
    python notebooklm_sync.py sync PM              # Add new sources
    python notebooklm_sync.py sync PM --dry-run    # Preview only
    python notebooklm_sync.py sync-all             # Sync all registered tickers
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SKILL_DIR = HOME / ".claude" / "skills"
STATE_FILE = SKILL_DIR / "shared" / "data" / "notebooklm_sync.json"
NLM_RUN_PY = SKILL_DIR / "notebooklm" / "scripts" / "run.py"

VAULT_DIR = HOME / "Documents" / "Obsidian Vault"
PORTFOLIO_DIR = HOME / "PORTFOLIO"
TRANSCRIPTS_DIR = HOME / "Downloads" / "Earnings Transcripts"

# Python executable
if sys.platform == "win32" or "MSYS" in os.environ.get("MSYSTEM", ""):
    PYTHON = str(
        HOME / "AppData" / "Local" / "Python" / "pythoncore-3.14-64" / "python.exe"
    )
else:
    PYTHON = "python3"

# File extensions to sync
SYNC_EXTENSIONS = {".md", ".pdf", ".txt", ".docx"}

# Max text file size (NLM ~500K limit, leave margin)
MAX_TEXT_CHARS = 400_000

# Max sources per notebook (NLM limit is 50)
MAX_SOURCES = 50

# Sleep between adds (rate limiting)
ADD_SLEEP = 3


# --- State management ---


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_entity_dict() -> dict:
    dict_path = SKILL_DIR / "shared" / "entity_dictionary.yaml"
    if dict_path.exists():
        try:
            import yaml

            return yaml.safe_load(dict_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_nlm_library() -> dict:
    lib_path = SKILL_DIR / "notebooklm" / "data" / "library.json"
    if lib_path.exists():
        return json.loads(lib_path.read_text(encoding="utf-8"))
    return {"notebooks": {}}


def get_search_terms(ticker: str) -> list[str]:
    """Get search terms for a ticker (ticker + company name variations)."""
    terms = [ticker.upper()]
    ed = load_entity_dict()
    if ticker.upper() in ed:
        canonical = ed[ticker.upper()].get("canonical_name", "")
        if canonical:
            terms.append(canonical.upper())
            # First word of company name (e.g., "Philip" from "Philip Morris")
            words = canonical.upper().split()
            if len(words) >= 2:
                terms.append(words[0])
    return terms


def matches_ticker(name: str, terms: list[str]) -> bool:
    """Check if a name matches any search term using word boundaries.

    Prevents 'PM' from matching 'JPM' or 'RPM'.
    """
    name_upper = name.upper()
    for term in terms:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, name_upper):
            return True
    return False


# --- File discovery ---


def get_scan_paths(ticker: str, state_entry: dict) -> list[Path]:
    """Get all directories to scan for a ticker's content."""
    paths = []
    search_terms = get_search_terms(ticker)

    # 1. Earnings Analysis (研究/财报分析) — find ticker-matching subfolders
    ea_dir = VAULT_DIR / "研究" / "财报分析"
    if ea_dir.exists():
        for d in ea_dir.iterdir():
            if d.is_dir() and matches_ticker(d.name, search_terms):
                paths.append(d)

    # 2. Research Notes (研究/研究笔记) — will filter by filename later
    rn_dir = VAULT_DIR / "研究" / "研究笔记"
    if rn_dir.exists():
        paths.append(rn_dir)

    # 3. Supply Chain (研究/供应链)
    sc_file = VAULT_DIR / "研究" / "供应链" / f"{ticker.upper()}_mentions.md"
    if sc_file.exists():
        paths.append(sc_file)

    # 5. Portfolio research
    company_dir = PORTFOLIO_DIR / "research" / "companies" / ticker.upper()
    if company_dir.exists():
        paths.append(company_dir)

    # 6. Earnings Transcripts (PDFs)
    if TRANSCRIPTS_DIR.exists():
        for d in TRANSCRIPTS_DIR.iterdir():
            if d.is_dir() and matches_ticker(d.name, search_terms):
                paths.append(d)

    # 7. Custom scan paths from state
    for custom in state_entry.get("scan_paths", []):
        p = Path(custom).expanduser()
        if p.exists():
            paths.append(p)

    return list(set(paths))


def is_ticker_owned_dir(scan_path: Path, search_terms: list[str]) -> bool:
    """Check if a directory is specifically about this ticker (all files relevant)."""
    if not scan_path.is_dir():
        return False
    name_upper = scan_path.name.upper()
    # Earnings Analysis/PM-US, Earnings Transcripts/Philip Morris (PM), etc.
    return matches_ticker(scan_path.name, search_terms)


def discover_files(ticker: str, scan_paths: list[Path]) -> list[Path]:
    """Discover files related to a ticker in scan paths."""
    files = []
    search_terms = get_search_terms(ticker)

    for scan_path in scan_paths:
        if not scan_path.exists():
            continue

        # Single file (e.g., Supply Chain/PM_mentions.md)
        if scan_path.is_file():
            if scan_path.suffix.lower() in SYNC_EXTENSIONS:
                files.append(scan_path)
            continue

        # Ticker-owned directory: all files are relevant
        owned = is_ticker_owned_dir(scan_path, search_terms)

        for f in scan_path.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in SYNC_EXTENSIONS:
                continue
            if f.name.startswith("."):
                continue

            if owned:
                files.append(f)
                continue

            # Generic directory: match by filename or frontmatter
            if matches_ticker(f.name, search_terms):
                files.append(f)
                continue

            # Check frontmatter for .md files
            if f.suffix.lower() == ".md":
                try:
                    head = f.read_text(encoding="utf-8", errors="ignore")[:500]
                    if any(t in head.upper() for t in search_terms):
                        files.append(f)
                except Exception:
                    pass

    return sorted(set(files))


# --- Source management ---


def add_source(notebook_id: str, file_path: Path) -> bool:
    """Add a single source to a NotebookLM notebook via source_manager.py."""
    suffix = file_path.suffix.lower()

    # Check text file size
    if suffix in (".md", ".txt"):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if len(content) > MAX_TEXT_CHARS:
                print(f"SKIP ({len(content):,} chars > {MAX_TEXT_CHARS:,} limit)")
                return False
            if len(content) < 100:
                print(f"SKIP (too small: {len(content)} chars)")
                return False
        except Exception as e:
            print(f"ERROR reading: {e}")
            return False

    cmd = [
        PYTHON,
        str(NLM_RUN_PY),
        "source_manager.py",
        "--notebook-id",
        notebook_id,
        "add-file",
        "--file",
        str(file_path),
        "--wait",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            return True
        else:
            err = (result.stderr or result.stdout or "unknown error")[:200]
            print(f"ERROR: {err}")
            return False
    except subprocess.TimeoutExpired:
        print("TIMEOUT (180s)")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


# --- Commands ---


def cmd_register(ticker: str, notebook_id: str, scan_paths: list[str] = None):
    """Register a ticker → notebook mapping."""
    state = load_state()

    # Verify notebook exists in library
    lib = load_nlm_library()
    if notebook_id not in lib.get("notebooks", {}):
        available = ", ".join(lib.get("notebooks", {}).keys())
        print(f"WARNING: '{notebook_id}' not in NLM library.")
        print(f"Available: {available}")
        print("Registering anyway — run 'notebook_manager.py sync' to refresh.")
        print()

    entry = state.get(ticker.upper(), {})
    entry["notebook_id"] = notebook_id
    entry["registered_at"] = datetime.now().isoformat()
    if scan_paths:
        entry["scan_paths"] = scan_paths
    if "synced_sources" not in entry:
        entry["synced_sources"] = {}

    state[ticker.upper()] = entry
    save_state(state)

    # Show auto-discovered scan paths
    discovered = get_scan_paths(ticker, entry)
    all_files = discover_files(ticker, discovered)

    print(f"Registered: {ticker.upper()} → {notebook_id}")
    print(f"Scan locations: {len(discovered)}")
    for p in discovered:
        print(f"  {p}")
    print(f"Discoverable files: {len(all_files)}")


def cmd_status():
    """Show sync status for all registered tickers."""
    state = load_state()
    if not state:
        print("No tickers registered.")
        print("Usage: python notebooklm_sync.py register TICKER --notebook-id ID")
        return

    print(f"{'Ticker':<8} {'Notebook':<42} {'Synced':<8} {'Last Sync'}")
    print("-" * 80)
    for ticker, entry in sorted(state.items()):
        nb = entry.get("notebook_id", "?")[:40]
        synced = len(entry.get("synced_sources", {}))
        last = entry.get("last_sync", "never")
        if last != "never":
            last = last[:16]
        print(f"{ticker:<8} {nb:<42} {synced:<8} {last}")


def cmd_scan(ticker: str):
    """Preview what would be synced (dry run)."""
    state = load_state()
    entry = state.get(ticker.upper(), {})

    if not entry.get("notebook_id"):
        print(f"{ticker} not registered. Use: register {ticker} --notebook-id ID")
        return

    scan_paths = get_scan_paths(ticker, entry)
    files = discover_files(ticker, scan_paths)
    synced = set(entry.get("synced_sources", {}).keys())

    new_files = [f for f in files if str(f) not in synced]
    already = [f for f in files if str(f) in synced]

    print(f"Scan: {ticker.upper()} → {entry['notebook_id']}")
    print(f"Found {len(files)} files ({len(new_files)} new, {len(already)} synced)")

    if new_files:
        print("\nNew files to sync:")
        for f in new_files:
            size_kb = f.stat().st_size / 1024
            print(f"  + {f.name} ({size_kb:.0f} KB)")

    if already:
        print(f"\nAlready synced: {len(already)} files")

    if new_files and len(synced) + len(new_files) > MAX_SOURCES:
        over = len(synced) + len(new_files) - MAX_SOURCES
        print(f"\nWARNING: {over} files would exceed {MAX_SOURCES}-source limit")


def cmd_sync(ticker: str, dry_run: bool = False):
    """Sync new sources for a ticker."""
    state = load_state()
    entry = state.get(ticker.upper(), {})

    if not entry.get("notebook_id"):
        print(f"{ticker} not registered. Use: register {ticker} --notebook-id ID")
        return

    notebook_id = entry["notebook_id"]
    scan_paths = get_scan_paths(ticker, entry)
    files = discover_files(ticker, scan_paths)
    synced = entry.get("synced_sources", {})

    new_files = [f for f in files if str(f) not in synced]

    if not new_files:
        print(f"{ticker}: No new files to sync.")
        return

    # Check source count limit
    current_count = len(synced)
    if current_count + len(new_files) > MAX_SOURCES:
        limit = MAX_SOURCES - current_count
        print(f"WARNING: {len(new_files)} new files would exceed {MAX_SOURCES} limit.")
        print(f"Current: {current_count} synced. Limiting to {limit} new files.")
        new_files = new_files[:limit]

    print(f"Syncing {len(new_files)} new files → {notebook_id}")

    if dry_run:
        for f in new_files:
            print(f"  [DRY RUN] Would add: {f.name}")
        return

    added = 0
    failed = 0
    skipped = 0
    for i, f in enumerate(new_files, 1):
        print(f"  [{i}/{len(new_files)}] {f.name}... ", end="", flush=True)
        ok = add_source(notebook_id, f)
        if ok:
            print("OK")
            synced[str(f)] = {
                "added_at": datetime.now().isoformat(),
                "file_type": f.suffix.lower(),
            }
            added += 1
        elif "SKIP" in (getattr(sys.stdout, "_last_write", "") or ""):
            skipped += 1
        else:
            failed += 1

        # Rate limiting between adds
        if i < len(new_files) and ok:
            time.sleep(ADD_SLEEP)

    # Update state
    entry["synced_sources"] = synced
    entry["last_sync"] = datetime.now().isoformat()
    state[ticker.upper()] = entry
    save_state(state)

    print(f"\nDone: {added} added, {failed} failed, {skipped} skipped")
    print(f"Total synced for {ticker}: {len(synced)}")


def cmd_sync_all(dry_run: bool = False):
    """Sync all registered tickers."""
    state = load_state()
    if not state:
        print("No tickers registered.")
        return

    for ticker in sorted(state.keys()):
        print(f"\n{'=' * 50}")
        print(f"  {ticker}")
        print(f"{'=' * 50}")
        cmd_sync(ticker, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description="NotebookLM Auto-Source Sync")
    sub = parser.add_subparsers(dest="command")

    # register
    p_reg = sub.add_parser("register", help="Register ticker → notebook mapping")
    p_reg.add_argument("ticker", help="Ticker symbol")
    p_reg.add_argument("--notebook-id", required=True, help="NLM library notebook ID")
    p_reg.add_argument("--scan-path", action="append", help="Additional scan paths")

    # status
    sub.add_parser("status", help="Show sync status for all tickers")

    # scan (preview)
    p_scan = sub.add_parser("scan", help="Preview files to sync (dry run)")
    p_scan.add_argument("ticker", help="Ticker symbol")

    # sync
    p_sync = sub.add_parser("sync", help="Sync new sources for a ticker")
    p_sync.add_argument("ticker", help="Ticker symbol")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview only")

    # sync-all
    p_all = sub.add_parser("sync-all", help="Sync all registered tickers")
    p_all.add_argument("--dry-run", action="store_true", help="Preview only")

    args = parser.parse_args()

    if args.command == "register":
        cmd_register(args.ticker, args.notebook_id, args.scan_path)
    elif args.command == "status":
        cmd_status()
    elif args.command == "scan":
        cmd_scan(args.ticker)
    elif args.command == "sync":
        cmd_sync(args.ticker, dry_run=args.dry_run)
    elif args.command == "sync-all":
        cmd_sync_all(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
