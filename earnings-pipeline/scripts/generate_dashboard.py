#!/usr/bin/env python3
"""
Generate a pipeline dashboard note in Obsidian.

Reads all result.json files from the run directory and creates
a summary dashboard with results table, quality metrics, and cross-ticker themes.
"""

import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Configuration
OBSIDIAN_VAULT = Path.home() / "Documents" / "Obsidian Vault"
DASHBOARD_FOLDER = OBSIDIAN_VAULT / "研究" / "财报分析" / "_Pipeline Dashboards"


def sanitize_filename(name: str) -> str:
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, "", name).strip()


def load_results(run_dir: Path) -> list[dict]:
    """Load all result.json files from ticker subdirectories."""
    results = []
    for subdir in sorted(run_dir.iterdir()):
        if not subdir.is_dir():
            continue
        result_file = subdir / "result.json"
        if result_file.exists():
            try:
                with open(result_file, encoding="utf-8") as f:
                    data = json.load(f)
                data["_dir"] = subdir.name
                results.append(data)
            except (json.JSONDecodeError, OSError) as e:
                results.append({
                    "_dir": subdir.name,
                    "ticker": subdir.name,
                    "status": "error",
                    "error": f"Failed to read result.json: {e}",
                })
        else:
            # Check if manifest exists (ticker was dispatched but didn't finish)
            manifest = run_dir / f"manifest_{subdir.name}.json"
            if manifest.exists():
                results.append({
                    "_dir": subdir.name,
                    "ticker": subdir.name,
                    "status": "stalled",
                    "error": "No result.json found — agent may have stalled",
                })
    return results


def generate_dashboard(results: list[dict], quarter: str, run_dir: Path) -> str:
    """Generate dashboard markdown content."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M")
    run_id = run_dir.name

    # Count statuses
    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = sum(1 for r in results if r.get("status") in ("failed", "error"))
    stalled_count = sum(1 for r in results if r.get("status") == "stalled")
    total = len(results)

    lines = []
    lines.append(f"""---
created: {date_str} {time_str}
type: pipeline-dashboard
quarter: {quarter}
run_id: "{run_id}"
tickers: [{', '.join(r.get('ticker', r['_dir']) for r in results)}]
tags: [earnings-pipeline, dashboard, {quarter.replace(' ', '-')}]
---""")

    lines.append("")
    lines.append(f"# {quarter} Earnings Pipeline Dashboard")
    lines.append("")
    lines.append(f"**Run:** `{run_id}` | **Date:** {date_str} {time_str}")
    lines.append(f"**Results:** {success_count}/{total} success, {failed_count} failed, {stalled_count} stalled")
    lines.append("")

    # Results table
    lines.append("## Results")
    lines.append("")
    lines.append("| Ticker | Status | AI Provider | Sections | Citations | Unique Pages | Q&A Qs | Link |")
    lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|")

    for r in results:
        ticker = r.get("ticker", r["_dir"])
        status = r.get("status", "unknown")
        status_icon = {"success": "✅", "failed": "❌", "error": "❌", "stalled": "⏳"}.get(status, "❓")

        if status == "success":
            scores = r.get("validation_scores", {})
            ai_provider = "claude+gemini" if r.get("gemini_status") == "success" else "claude"
            sections = f"{scores.get('sections_found', '?')}/{scores.get('sections_total', '?')}"
            citations = scores.get("citations", {})
            total_cites = citations.get("total_citations", "?")
            unique_pages = citations.get("unique_pages", "?")
            qa_qs = scores.get("qa_questions", "?")

            # Build wikilink
            analysis_path = r.get("analysis_path", "")
            if analysis_path:
                note_name = Path(analysis_path).stem
                link = f"[[{note_name}]]"
            else:
                link = "—"

            lines.append(f"| {ticker} | {status_icon} | {ai_provider} | {sections} | {total_cites} | {unique_pages} | {qa_qs} | {link} |")
        else:
            error = r.get("error", "Unknown error")[:60]
            lines.append(f"| {ticker} | {status_icon} {status} | — | — | — | — | — | {error} |")

    lines.append("")

    # Summaries section
    successful = [r for r in results if r.get("status") == "success"]
    if successful:
        lines.append("## Key Findings Summary")
        lines.append("")
        for r in successful:
            ticker = r.get("ticker", "")
            summary = r.get("summary", "No summary available")
            lines.append(f"**{ticker}:** {summary}")
            lines.append("")

    # Quality metrics
    if successful:
        lines.append("## Quality Metrics")
        lines.append("")

        avg_chars = sum(r.get("validation_scores", {}).get("total_chars", 0) for r in successful) / len(successful)
        avg_citations = sum(
            r.get("validation_scores", {}).get("citations", {}).get("total_citations", 0)
            for r in successful
        ) / len(successful)
        avg_qa = sum(r.get("validation_scores", {}).get("qa_questions", 0) for r in successful) / len(successful)
        gemini_success = sum(1 for r in successful if r.get("gemini_status") == "success")

        lines.append(f"- **Avg analysis length:** {avg_chars:,.0f} chars")
        lines.append(f"- **Avg citations:** {avg_citations:.0f}")
        lines.append(f"- **Avg Q&A questions:** {avg_qa:.0f}")
        lines.append(f"- **Gemini success rate:** {gemini_success}/{len(successful)}")
        lines.append("")

    # Dual-AI agreement
    dual_ai = [r for r in successful if r.get("gemini_status") == "success"]
    if dual_ai:
        lines.append("## Dual-AI Coverage")
        lines.append("")
        lines.append("Tickers with Claude + Gemini analysis (check 双AI对比笔记 for divergences):")
        for r in dual_ai:
            ticker = r.get("ticker", "")
            analysis_path = r.get("analysis_path", "")
            note_name = Path(analysis_path).stem if analysis_path else ticker
            lines.append(f"- [[{note_name}|{ticker}]]")
        lines.append("")

    # Failed tickers
    failed = [r for r in results if r.get("status") in ("failed", "error", "stalled")]
    if failed:
        lines.append("## Failed / Stalled")
        lines.append("")
        for r in failed:
            ticker = r.get("ticker", r["_dir"])
            error = r.get("error", "Unknown")
            lines.append(f"- **{ticker}:** {error}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate pipeline dashboard")
    parser.add_argument("--run-dir", required=True, help="Run workspace directory")
    parser.add_argument("--quarter", required=True, help='Quarter string (e.g., "Q4 2025")')
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    results = load_results(run_dir)

    if not results:
        print("ERROR: No results found in run directory")
        return 1

    # Generate dashboard content
    content = generate_dashboard(results, args.quarter, run_dir)

    # Save to Obsidian
    DASHBOARD_FOLDER.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d %H%M')} {args.quarter} Pipeline Dashboard.md"
    filename = sanitize_filename(filename)
    filepath = DASHBOARD_FOLDER / filename

    filepath.write_text(content, encoding="utf-8")

    # Print path for caller
    try:
        rel_path = filepath.relative_to(OBSIDIAN_VAULT)
        print(str(rel_path).replace("\\", "/"))
    except ValueError:
        print(str(filepath).replace("\\", "/"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
