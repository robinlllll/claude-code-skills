#!/usr/bin/env python3
"""
Save analysis to Obsidian vault with pipeline-specific frontmatter.

Adapts the pattern from organizer-transcript/browser/obsidian.py
with additional fields: pipeline_run, ai_provider, pipeline_batch.
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
EARNINGS_FOLDER = OBSIDIAN_VAULT / "研究" / "财报分析"


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, "", name).strip()


def detect_gemini_status(content: str) -> str:
    """Detect whether the analysis includes Gemini divergence notes."""
    if "双AI对比笔记" in content or "Dual-AI Divergence" in content:
        return "claude+gemini"
    return "claude"


def save_pipeline_analysis(manifest: dict, content: str) -> str:
    """
    Save analysis to Obsidian vault.

    Returns the saved file path (relative to vault).
    """
    ticker = manifest["ticker"]
    company = manifest["company"]
    quarter = manifest["quarter"]
    prev_quarter = manifest["prev_quarter"]

    # Ensure company folder exists
    folder = EARNINGS_FOLDER / ticker.upper()
    folder.mkdir(parents=True, exist_ok=True)

    # Generate filename
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M")
    quarters_str = f"{quarter} vs {prev_quarter}" if manifest.get("prev_pdf") else quarter
    filename = f"{date_str} {time_str} {ticker} {quarters_str} Analysis.md"
    filename = sanitize_filename(filename)
    filepath = folder / filename

    # Determine AI provider
    ai_provider = detect_gemini_status(content)

    # Extract pipeline batch from workdir (the timestamp part)
    workdir = manifest.get("workdir", "")
    batch_id = ""
    parts = workdir.replace("\\", "/").split("/")
    for i, p in enumerate(parts):
        if p == "runs" and i + 1 < len(parts):
            batch_id = parts[i + 1]
            break

    # Build YAML frontmatter
    quarters = [quarter, prev_quarter] if manifest.get("prev_pdf") else [quarter]
    quarters_yaml = ", ".join(quarters)
    tags = ["earnings", ticker.upper()] + [q.replace(" ", "-") for q in quarters[:2]]
    tags_yaml = ", ".join(tags)

    frontmatter = f"""---
created: {date_str} {time_str}
ticker: {ticker.upper()}
company: {company}
quarters: [{quarters_yaml}]
source: earnings-pipeline
ai_provider: {ai_provider}
pipeline_run: true
pipeline_batch: "{batch_id}"
tags: [{tags_yaml}]
---"""

    # Build content
    content_parts = [frontmatter, ""]
    content_parts.append(f"# {ticker.upper()} {quarters_str} Analysis\n")
    content_parts.append(content)
    content_parts.append("")

    # Research questions section
    content_parts.append("## Research Questions\n")
    content_parts.append(f"> 添加问题格式: `- [?] 问题内容`。运行 `/rq {ticker.upper()}` 发送至 ChatGPT。\n")

    # Source transcripts section
    content_parts.append("## Source Transcripts\n")
    if manifest.get("curr_pdf"):
        content_parts.append(f"- {quarter}: `{Path(manifest['curr_pdf']).name}`")
    if manifest.get("prev_pdf"):
        content_parts.append(f"- {prev_quarter}: `{Path(manifest['prev_pdf']).name}`")
    content_parts.append("")

    # Write file
    filepath.write_text("\n".join(content_parts), encoding="utf-8")

    # Return relative path from vault root
    try:
        rel_path = filepath.relative_to(OBSIDIAN_VAULT)
        return str(rel_path).replace("\\", "/")
    except ValueError:
        return str(filepath).replace("\\", "/")


def main():
    parser = argparse.ArgumentParser(description="Save analysis to Obsidian vault")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file")
    parser.add_argument("--content-file", required=True, help="Path to analysis content file")
    args = parser.parse_args()

    # Load manifest
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    # Load content
    content = Path(args.content_file).read_text(encoding="utf-8")

    # Save
    saved_path = save_pipeline_analysis(manifest, content)
    print(saved_path)


if __name__ == "__main__":
    main()
