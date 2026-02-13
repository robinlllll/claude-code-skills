#!/usr/bin/env python3
"""
Validate earnings analysis quality.

Uses fuzzy section matching — checks if any keyword from each required group
appears in the content. Not exact header regex.
"""

import sys
import re
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Load config
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def count_citations(text: str) -> dict:
    """
    Count citation references like (p.X), (p.X-Y), (transcript p.X).

    Returns dict with total_citations, unique_pages, density.
    """
    # Match patterns like (p.5), (p.15), (p.5-6), (Q4 2025 transcript p.12)
    page_refs = re.findall(r'p\.(\d+)', text)
    unique_pages = set(int(p) for p in page_refs)
    total_citations = len(page_refs)
    total_chars = len(text)
    density = total_citations / total_chars if total_chars > 0 else 0

    return {
        "total_citations": total_citations,
        "unique_pages": len(unique_pages),
        "density": round(density, 4),
    }


def count_qa_questions(text: str) -> int:
    """
    Count Q&A questions in the analysis.
    Looks for table rows in Q&A section with question content.
    """
    # Find Q&A section
    qa_section = ""
    in_qa = False
    for line in text.split("\n"):
        if "Q&A" in line and ("透视" in line or "Deep Dive" in line or "分析师" in line):
            in_qa = True
            continue
        if in_qa:
            # Stop at next major section header
            if re.match(r'^#{1,3}\s+\d+\.', line) and "Q&A" not in line:
                break
            qa_section += line + "\n"

    # Count table rows (excluding header and separator rows)
    question_count = 0
    for line in qa_section.split("\n"):
        line = line.strip()
        if line.startswith("|") and not line.startswith("|:") and not line.startswith("| 问题") and not line.startswith("| ---"):
            # Filter out separator rows (|---|---|)
            if not re.match(r'^\|[\s\-:|]+\|$', line):
                # Check it has actual content (not just pipes and dashes)
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if any(len(c) > 3 for c in cells):
                    question_count += 1

    return question_count


def validate_analysis(content: str, config: dict) -> dict:
    """
    Validate analysis content against quality criteria.

    Returns dict with valid (bool), issues (list), scores (dict).
    """
    val_config = config["validation"]
    issues = []
    scores = {}

    # 1. Total character count
    total_chars = len(content)
    min_chars = val_config["min_total_chars"]
    scores["total_chars"] = total_chars
    if total_chars < min_chars:
        issues.append(f"Content too short: {total_chars} chars (min: {min_chars})")

    # 2. Fuzzy section matching
    section_keywords = val_config["required_section_keywords"]
    sections_found = 0
    sections_missing = []

    for keyword_group in section_keywords:
        found = False
        for keyword in keyword_group:
            if keyword.lower() in content.lower():
                found = True
                break
        if found:
            sections_found += 1
        else:
            sections_missing.append(keyword_group)

    scores["sections_found"] = sections_found
    scores["sections_total"] = len(section_keywords)
    if sections_missing:
        for group in sections_missing:
            issues.append(f"Missing section (none of these keywords found): {group}")

    # 3. Citation density
    citation_stats = count_citations(content)
    scores["citations"] = citation_stats

    if citation_stats["density"] < val_config["min_citation_density"]:
        issues.append(
            f"Citation density too low: {citation_stats['density']:.4f} "
            f"(min: {val_config['min_citation_density']})"
        )

    if citation_stats["unique_pages"] < val_config["min_unique_pages_cited"]:
        issues.append(
            f"Too few unique pages cited: {citation_stats['unique_pages']} "
            f"(min: {val_config['min_unique_pages_cited']})"
        )

    # 4. Q&A question count
    qa_count = count_qa_questions(content)
    scores["qa_questions"] = qa_count
    if qa_count < val_config["min_qa_questions"]:
        issues.append(
            f"Too few Q&A questions listed: {qa_count} "
            f"(min: {val_config['min_qa_questions']})"
        )

    # Overall
    valid = len(issues) == 0

    return {
        "valid": valid,
        "issues": issues,
        "scores": scores,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate earnings analysis quality")
    parser.add_argument("--content-file", required=True, help="Path to analysis content file")
    args = parser.parse_args()

    content_path = Path(args.content_file)
    if not content_path.exists():
        result = {"valid": False, "issues": [f"File not found: {content_path}"], "scores": {}}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    content = content_path.read_text(encoding="utf-8")
    config = load_config()

    result = validate_analysis(content, config)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
