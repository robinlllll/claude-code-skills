#!/usr/bin/env python3
"""
Earnings Transcript Organizer
Organizes transcript PDFs from Downloads into structured company folders.
Integrated with Transcript Browser for immediate visibility of new transcripts.
"""

import os
import sys
import re
import shutil
import json
import requests
from pathlib import Path
from datetime import datetime
import argparse

# Fix Unicode output on Windows consoles with non-UTF8 codepages (e.g. GBK)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', closefd=False)
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', errors='replace', closefd=False)

# Configuration
DOWNLOADS = Path.home() / "Downloads"
TRANSCRIPTS_ROOT = DOWNLOADS / "Earnings Transcripts"
REGISTRY_FILE = Path.home() / "ClaudeProjects" / "jobs_registry.json"
BROWSER_DATA_DIR = Path(__file__).parent / "browser" / "data"
RECENT_ADDITIONS_FILE = BROWSER_DATA_DIR / "recent_additions.json"
BROWSER_URL = "http://127.0.0.1:8008"


def extract_company(filename: str) -> str:
    """Extract company name from transcript filename."""
    # FactSet/Callstreet format: CORRECTED TRANSCRIPT_ Company Name(TICKER-EX)
    # Uses .+? (lazy) to skip parenthetical state names like (Rhode Island), (Cayman)
    # Includes \. in ticker pattern for dotted tickers like ASSA.B-SE, BF.B-US
    match = re.search(
        r'(?:CALLSTREET REPORT|CORRECTED TRANSCRIPT|RAW TRANSCRIPT)[_:\s]+(.+?)\(([A-Z0-9.]+-[A-Z]+)\)',
        filename
    )
    if match:
        company = match.group(1).strip()
        company = re.sub(r'\s+', ' ', company).rstrip('.')
        # Strip trailing jurisdiction parentheticals like (Rhode Island), (Michigan)
        company = re.sub(r'\s*\([^)]+\)\s*$', '', company).strip()
        return company

    # Format: TICKER-EX (Q1 2025 Earnings Call)
    match = re.match(r'^([A-Z0-9]+-[A-Z]+)\s+\(Q\d+\s+\d{4}\s+Earnings Call\)', filename)
    if match:
        return match.group(1)

    # Format: TICKER - Company...
    match = re.match(r'^([A-Z]+)\s+-\s+', filename)
    if match:
        return match.group(1)

    # Format: TICKER-EX at start
    match = re.match(r'^([A-Z0-9]+-[A-Z]+)', filename)
    if match:
        return match.group(1)

    # Fallback: first word
    parts = re.split(r'[\s_\-\(]', filename)
    if parts:
        return parts[0].upper()
    return "Unknown"


def extract_ticker(filename: str) -> str:
    """Extract ticker symbol from transcript filename."""
    # Ticker in parentheses: (AAPL-US) or (ASSA.B-SE)
    match = re.search(r'\(([A-Z0-9.]+-[A-Z]+)\)', filename)
    if match:
        return match.group(1)

    # Ticker at start: AAPL-US (Q1...
    match = re.match(r'^([A-Z0-9]+-[A-Z]+)\s+\(Q', filename)
    if match:
        return match.group(1)

    # Simple ticker: AAPL - ...
    match = re.match(r'^([A-Z]{2,6})\s+-\s+', filename)
    if match:
        return match.group(1)

    return None


def deduplicate_folder(folder: Path) -> list:
    """Remove duplicate transcripts in a company folder.

    Rules:
    1. CORRECTED > RAW for same event
    2. Remove browser download duplicates: file (1).pdf, file (2).pdf
    """
    removed = []
    pdfs = list(folder.glob("*.pdf"))
    if len(pdfs) <= 1:
        return removed

    # Group by normalized event key
    events = {}
    for pdf in pdfs:
        name = pdf.stem
        # Remove (1), (2) browser download suffixes for grouping
        normalized = re.sub(r'\s*\(\d+\)$', '', name)
        # Remove transcript type prefix for grouping
        event_key = re.sub(
            r'^(CORRECTED TRANSCRIPT|RAW TRANSCRIPT|CALLSTREET REPORT)[_:\s]+', '', normalized
        )
        if event_key not in events:
            events[event_key] = []
        events[event_key].append(pdf)

    for event_key, files in events.items():
        if len(files) <= 1:
            continue

        # Rank: CORRECTED > RAW, original > (N) copy
        def rank(f):
            name = f.stem
            score = 0
            if 'CORRECTED TRANSCRIPT' in name:
                score += 10
            elif 'CALLSTREET REPORT' in name:
                score += 5
            # RAW gets no bonus
            # Penalize browser download duplicates (1), (2)
            if re.search(r'\(\d+\)$', name):
                score -= 1
            return score

        files.sort(key=rank, reverse=True)
        # Keep the best, remove the rest
        for f in files[1:]:
            f.unlink()
            removed.append(f.name)

    return removed


def find_transcript_files(source_dir: Path) -> list:
    """Find all transcript PDFs in source directory."""
    transcript_files = []
    for f in source_dir.glob("*.pdf"):
        name = f.name.lower()
        if any(kw in name for kw in ["transcript", "earnings call", "earnings_call"]):
            transcript_files.append(f)
    return transcript_files


def organize_transcripts(source_dir: Path = None, dest_dir: Path = None, dry_run: bool = False):
    """
    Organize transcript files into company folders.

    Args:
        source_dir: Source directory (default: Downloads)
        dest_dir: Destination directory (default: Downloads/Earnings Transcripts)
        dry_run: If True, show what would happen without moving files
    """
    source_dir = source_dir or DOWNLOADS
    dest_dir = dest_dir or TRANSCRIPTS_ROOT

    print("=" * 50)
    print("  Earnings Transcript Organizer")
    print("=" * 50)
    print(f"\nSource: {source_dir}")
    print(f"Destination: {dest_dir}")
    if dry_run:
        print("Mode: DRY RUN (no files will be moved)")
    print()

    # Find transcript files
    transcript_files = find_transcript_files(source_dir)

    if not transcript_files:
        print("No transcript PDFs found in Downloads.")
        return 0

    print(f"Found {len(transcript_files)} transcript(s) to organize\n")

    # Group files by company
    company_files = {}
    for f in transcript_files:
        company = extract_company(f.name)
        ticker = extract_ticker(f.name)
        key = (company, ticker)
        if key not in company_files:
            company_files[key] = []
        company_files[key].append(f)

    # Create destination and organize
    if not dry_run:
        dest_dir.mkdir(exist_ok=True)

    moved = 0
    organized_files = []  # Track for browser integration
    affected_folders = set()  # Track folders for dedup

    for (company, ticker), files in company_files.items():
        # Sanitize folder name
        folder_name = re.sub(r'[<>:"/\\|?*]', '', company).strip() or "Unknown"

        # Add ticker to folder name if available
        if ticker:
            full_folder_name = f"{folder_name} ({ticker})"
        else:
            full_folder_name = folder_name

        # Check for existing folder by ticker first (prevents duplicates from name variants)
        company_folder = None
        if ticker:
            existing_by_ticker = list(dest_dir.glob(f"* ({ticker})"))
            if not existing_by_ticker:
                # Also check for bare ticker folder
                bare_ticker_folder = dest_dir / ticker
                if bare_ticker_folder.is_dir():
                    existing_by_ticker = [bare_ticker_folder]
            if existing_by_ticker:
                company_folder = existing_by_ticker[0]

        # Fallback: match by company name
        if not company_folder:
            existing = list(dest_dir.glob(f"{folder_name} (*-*)")) + list(dest_dir.glob(folder_name))
            if existing:
                company_folder = existing[0]
            else:
                company_folder = dest_dir / full_folder_name

        if not dry_run:
            company_folder.mkdir(exist_ok=True)

        for f in files:
            dest = company_folder / f.name
            if not dest.exists():
                if dry_run:
                    print(f"  Would move: {f.name[:50]}...")
                    print(f"         to: {company_folder.name}/")
                else:
                    shutil.move(str(f), str(dest))
                    print(f"  Moved: {f.name[:50]}...")
                    print(f"     to: {company_folder.name}/")
                    # Track for browser
                    organized_files.append({
                        "ticker": ticker,
                        "company": company,
                        "filename": f.name,
                        "path": str(dest)
                    })
                    affected_folders.add(company_folder)
                moved += 1

    # Add tickers to folders that don't have them
    if not dry_run:
        for folder in dest_dir.iterdir():
            if not folder.is_dir():
                continue
            folder_name = folder.name

            # Skip if already has ticker
            if re.search(r'\([A-Z0-9.]+-[A-Z]+\)$', folder_name):
                continue
            if re.search(r'\([A-Z]{2,6}\)$', folder_name):
                continue
            if re.match(r'^[A-Z0-9]+-[A-Z]+$', folder_name):
                continue
            if re.match(r'^[A-Z]{2,6}$', folder_name):
                continue

            # Extract ticker from files in folder
            ticker = None
            for f in folder.glob("*.pdf"):
                ticker = extract_ticker(f.name)
                if ticker:
                    break

            if ticker:
                new_name = f"{folder_name} ({ticker})"
                new_path = dest_dir / new_name
                if not new_path.exists():
                    folder.rename(new_path)

    # Deduplicate affected folders (CORRECTED > RAW, remove (1) copies)
    deduped_total = 0
    if not dry_run and affected_folders:
        for folder in affected_folders:
            if folder.exists():
                removed = deduplicate_folder(folder)
                if removed:
                    deduped_total += len(removed)
                    for name in removed:
                        print(f"  Dedup: removed {name[:60]}...")

    # Print summary
    print("\n" + "=" * 50)
    print("  Summary")
    print("=" * 50)
    print(f"{'Would organize' if dry_run else 'Organized'}: {moved} files")

    if not dry_run:
        total_folders = len([d for d in dest_dir.iterdir() if d.is_dir()])
        total_pdfs = len(list(dest_dir.rglob("*.pdf")))
        print(f"Total folders: {total_folders}")
        print(f"Total PDFs: {total_pdfs}")
        if deduped_total:
            print(f"Duplicates removed: {deduped_total}")

        # Update registry
        update_registry(moved, total_folders)

        # Browser integration
        if organized_files:
            track_recent_additions(organized_files)
            browser_running = refresh_browser()

            # Get unique tickers that were just organized
            new_tickers = list(set(f["ticker"] for f in organized_files if f["ticker"]))
            if new_tickers:
                print(f"\n📋 New transcripts for: {', '.join(new_tickers)}")

            if browser_running:
                print(f"🌐 View at: {BROWSER_URL}")

    return moved


def update_registry(files_processed: int, total_companies: int):
    """Update the jobs registry with run statistics."""
    REGISTRY_FILE.parent.mkdir(exist_ok=True)

    registry = {}
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
            registry = json.load(f)

    registry["OrganizeTranscripts"] = {
        "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files_processed": files_processed,
        "total_companies": total_companies
    }

    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)


def track_recent_additions(organized_files: list):
    """
    Track recently organized files for the browser to highlight.

    Args:
        organized_files: List of dicts with {ticker, filename, path, timestamp}
    """
    BROWSER_DATA_DIR.mkdir(exist_ok=True)

    # Load existing recent additions
    recent = []
    if RECENT_ADDITIONS_FILE.exists():
        try:
            recent = json.loads(RECENT_ADDITIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            recent = []

    # Add new files at the beginning
    timestamp = datetime.now().isoformat()
    for f in organized_files:
        f["added_at"] = timestamp
        recent.insert(0, f)

    # Keep only last 50 additions (to avoid file growing indefinitely)
    recent = recent[:50]

    RECENT_ADDITIONS_FILE.write_text(
        json.dumps(recent, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return recent


def refresh_browser():
    """Trigger browser index refresh and optionally open it."""
    try:
        response = requests.get(f"{BROWSER_URL}/api/refresh", timeout=2)
        if response.status_code == 200:
            print(f"\n✓ Browser index refreshed")
            return True
    except requests.exceptions.ConnectionError:
        print(f"\n○ Browser not running (start with: python browser/app.py)")
    except Exception as e:
        print(f"\n○ Could not refresh browser: {e}")
    return False


def open_browser_to_company(ticker: str = None):
    """Open browser, optionally to a specific company."""
    import webbrowser
    url = BROWSER_URL
    if ticker:
        url = f"{BROWSER_URL}?highlight={ticker}"
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(
        description='Organize earnings transcript PDFs into company folders'
    )
    parser.add_argument(
        '--source', '-s',
        type=Path,
        default=DOWNLOADS,
        help='Source directory (default: Downloads)'
    )
    parser.add_argument(
        '--dest', '-d',
        type=Path,
        default=TRANSCRIPTS_ROOT,
        help='Destination directory (default: Downloads/Earnings Transcripts)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would happen without moving files'
    )

    args = parser.parse_args()
    organize_transcripts(args.source, args.dest, args.dry_run)


if __name__ == "__main__":
    main()
