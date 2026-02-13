#!/usr/bin/env python3
"""
Find earnings transcript PDFs and create per-ticker manifest JSON files.

Reuses indexer.scan_transcripts() from organizer-transcript skill.
"""

import sys
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Add skills to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import indexer from organizer-transcript
ORGANIZER_DIR = (
    Path(__file__).resolve().parent.parent.parent / "organizer-transcript" / "browser"
)
sys.path.insert(0, str(ORGANIZER_DIR))
from indexer import scan_transcripts, TRANSCRIPTS_ROOT

# Load config
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_prev_quarter(quarter_str: str, config: dict) -> tuple[str, int]:
    """
    Compute previous quarter from current quarter string.

    Args:
        quarter_str: e.g., "Q4 2025"
        config: config dict with quarters.prev_map

    Returns:
        (prev_quarter_label, prev_year) e.g., ("Q3", 2025)
    """
    parts = quarter_str.strip().split()
    q_label = parts[0]  # "Q4"
    year = int(parts[1])  # 2025

    prev_map = config["quarters"]["prev_map"]
    prev_q, year_offset = prev_map[q_label]  # e.g., ["Q3", 0]

    prev_year = year + year_offset
    return prev_q, prev_year


def find_best_transcript(
    transcripts: list[dict], quarter: str, year: int
) -> str | None:
    """
    Find the best matching transcript for a given quarter and year.
    Prefers CORRECTED over RAW over CALLSTREET. Only matches Earnings Calls.
    """
    candidates = []
    for t in transcripts:
        if (
            t.get("quarter") == quarter
            and t.get("year") == year
            and t.get("event_type") == "Earnings Call"
        ):
            candidates.append(t)

    if not candidates:
        return None

    # Rank by transcript type preference
    type_rank = {"CORRECTED": 0, "RAW": 1, "CALLSTREET": 2, "UNKNOWN": 3}
    candidates.sort(
        key=lambda t: type_rank.get(t.get("transcript_type", "UNKNOWN"), 99)
    )

    return candidates[0]["path"]


def main():
    parser = argparse.ArgumentParser(
        description="Find transcript PDFs and create manifests"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="List of tickers (e.g., HOOD-US META-US)",
    )
    parser.add_argument(
        "--quarter", required=True, help='Quarter string (e.g., "Q4 2025")'
    )
    parser.add_argument("--run-dir", required=True, help="Run workspace directory")
    args = parser.parse_args()

    config = load_config()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Parse quarter
    q_parts = args.quarter.strip().split()
    curr_q = q_parts[0]  # "Q4"
    curr_year = int(q_parts[1])  # 2025

    prev_q, prev_year = compute_prev_quarter(args.quarter, config)

    # Scan all transcripts
    print(f"Scanning transcripts at {TRANSCRIPTS_ROOT}...")
    companies = scan_transcripts()
    print(f"Found {len(companies)} companies in transcript library")

    results = {"found": [], "missing": []}

    for ticker in args.tickers:
        ticker = ticker.upper()

        # Look up company in transcript index
        # Try exact match first, then try with common exchange suffixes
        company_data = companies.get(ticker)
        resolved_ticker = ticker

        if not company_data:
            # Try appending common exchange suffixes
            for suffix in [
                "-US",
                "-HK",
                "-KR",
                "-TW",
                "-JP",
                "-PA",
                "-L",
                "-MI",
                "-SE",
                "-DK",
            ]:
                candidate = ticker + suffix
                if candidate in companies:
                    company_data = companies[candidate]
                    resolved_ticker = candidate
                    print(f"NOTE: Resolved {ticker} → {resolved_ticker}")
                    break

        if not company_data:
            print(f"WARNING: No transcript folder found for {ticker}")
            results["missing"].append(
                {"ticker": ticker, "reason": "No transcript folder found"}
            )
            continue

        ticker = resolved_ticker

        company_name = company_data.company
        transcripts = company_data.transcripts

        # Find current quarter transcript
        curr_pdf = find_best_transcript(transcripts, curr_q, curr_year)
        if not curr_pdf:
            print(f"WARNING: No {args.quarter} earnings call transcript for {ticker}")
            results["missing"].append(
                {
                    "ticker": ticker,
                    "reason": f"No {args.quarter} earnings call transcript found",
                }
            )
            continue

        # Find previous quarter transcript
        prev_pdf = find_best_transcript(transcripts, prev_q, prev_year)
        if not prev_pdf:
            print(
                f"NOTE: No {prev_q} {prev_year} transcript for {ticker} — will use single-quarter mode"
            )

        # Create ticker workdir
        ticker_workdir = run_dir / ticker
        ticker_workdir.mkdir(parents=True, exist_ok=True)

        # Build manifest
        manifest = {
            "ticker": ticker,
            "company": company_name,
            "quarter": args.quarter,
            "prev_quarter": f"{prev_q} {prev_year}",
            "curr_pdf": curr_pdf.replace("\\", "/"),
            "prev_pdf": prev_pdf.replace("\\", "/") if prev_pdf else None,
            "workdir": str(ticker_workdir).replace("\\", "/"),
            "insights": None,  # Filled by load_insights.py
        }

        # Write manifest
        manifest_path = run_dir / f"manifest_{ticker}.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"OK: {ticker} — curr={Path(curr_pdf).name[:60]}...")
        if prev_pdf:
            print(f"     prev={Path(prev_pdf).name[:60]}...")
        else:
            print("     prev=None (single-quarter mode)")

        results["found"].append(
            {
                "ticker": ticker,
                "manifest": str(manifest_path).replace("\\", "/"),
            }
        )

    # Summary
    print("\n--- Summary ---")
    print(f"Found: {len(results['found'])} tickers")
    print(f"Missing: {len(results['missing'])} tickers")

    if results["missing"]:
        print("\nMissing tickers:")
        for m in results["missing"]:
            print(f"  - {m['ticker']}: {m['reason']}")

    # Write summary to run dir
    summary_path = run_dir / "find_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return 0 if results["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
