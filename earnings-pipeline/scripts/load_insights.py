#!/usr/bin/env python3
"""
Load insight ledger data and patch manifest JSON files.

Reuses insight_ledger from organizer-transcript skill.
"""

import sys
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Add organizer-transcript browser to path
ORGANIZER_DIR = (
    Path(__file__).resolve().parent.parent.parent / "organizer-transcript" / "browser"
)
sys.path.insert(0, str(ORGANIZER_DIR))

from insight_ledger import get_active_insights, get_resolved_insights, format_for_prompt


def main():
    parser = argparse.ArgumentParser(
        description="Load insights and patch manifest files"
    )
    parser.add_argument("--tickers", nargs="+", required=True, help="List of tickers")
    parser.add_argument("--run-dir", required=True, help="Run workspace directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    for ticker in args.tickers:
        ticker = ticker.upper()
        manifest_path = run_dir / f"manifest_{ticker}.json"

        if not manifest_path.exists():
            print(f"SKIP: No manifest for {ticker} (file not found)")
            continue

        # Load manifest
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # Load insights
        try:
            active = get_active_insights(ticker)
            resolved = get_resolved_insights(ticker)
            insight_text = format_for_prompt(active, resolved)

            if insight_text:
                manifest["insights"] = insight_text
                print(
                    f"OK: {ticker} — {len(active)} active, {len(resolved)} resolved insights loaded"
                )
            else:
                manifest["insights"] = None
                print(f"OK: {ticker} — no insights found")

        except Exception as e:
            manifest["insights"] = None
            print(f"WARN: {ticker} — error loading insights: {e}")

        # Write back
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\nInsight loading complete.")


if __name__ == "__main__":
    main()
