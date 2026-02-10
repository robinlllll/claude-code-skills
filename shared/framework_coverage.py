"""Framework coverage analysis for any ticker.

Scans all vault data sources, tags content with framework sections,
and generates a coverage matrix showing research gaps.

Usage:
    python framework_coverage.py scan NVDA              # Full coverage matrix
    python framework_coverage.py scan NVDA --format json # JSON output
    python framework_coverage.py scan NVDA --brief       # One-line summary
    python framework_coverage.py gaps NVDA              # Only gaps
    python framework_coverage.py questions NVDA         # Research questions for gaps
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# ── Paths ────────────────────────────────────────────────────

SKILLS_DIR = Path.home() / ".claude" / "skills"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
PORTFOLIO_DIR = Path.home() / "PORTFOLIO"
FRAMEWORK_PATH = SKILLS_DIR / "shared" / "analysis_framework.yaml"

# Ensure shared imports work
sys.path.insert(0, str(SKILLS_DIR))
try:
    from shared.framework_tagger import tag_content, get_all_sections, get_section_info
    from shared.entity_resolver import resolve_entity, _load_dictionary
    HAS_TAGGER = True
except ImportError:
    HAS_TAGGER = False

# ── Framework Loading ────────────────────────────────────────


def _load_framework() -> dict:
    with open(FRAMEWORK_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Entity Aliases ───────────────────────────────────────────


def _get_search_terms(ticker: str) -> list[str]:
    """Get all search terms for a ticker: ticker itself + company name + aliases."""
    terms = [ticker, ticker.lower()]
    try:
        entity_dict, alias_map = _load_dictionary()
        if ticker in entity_dict:
            entry = entity_dict[ticker]
            canonical = entry.get("canonical_name", "")
            if canonical:
                terms.append(canonical)
                terms.append(canonical.lower())
            for alias in entry.get("aliases", []):
                terms.append(alias)
                terms.append(alias.lower())
    except Exception:
        pass
    return list(dict.fromkeys(terms))  # Deduplicate preserving order


# ── Vault Source Scanning ────────────────────────────────────

# Maps data source type to vault path(s) — mirrors /moc search paths
def _earnings_dirs(ticker: str) -> list[Path]:
    """Find earnings analysis folders matching ticker (handles PM-US, UBER-US patterns)."""
    base = VAULT_DIR / "研究" / "财报分析"
    if not base.exists():
        return []
    return [d for d in base.iterdir() if d.is_dir() and d.name.upper().startswith(ticker)]


SOURCE_PATHS = {
    "thesis": lambda t: [PORTFOLIO_DIR / "research" / "companies" / t],
    "earnings_analysis": lambda t: _earnings_dirs(t),  # handles PM-US pattern
    "research_notes": lambda _: [VAULT_DIR / "研究" / "研究笔记"],
    "podcast": lambda _: [VAULT_DIR / "信息源" / "播客"],
    "meeting": lambda _: [VAULT_DIR / "周会"],
    "xueqiu": lambda _: [VAULT_DIR / "信息源" / "雪球"],
    "13f": lambda _: [VAULT_DIR / "研究" / "13F 持仓"],
    "wechat": lambda _: [VAULT_DIR / "信息源" / "剪藏"],
    "substack": lambda _: [VAULT_DIR / "信息源" / "Substack"],
    "chatgpt": lambda _: [VAULT_DIR / "ChatGPT" / "Investment Research"],
    "supply_chain": lambda _: [VAULT_DIR / "研究" / "供应链"],
    "review": lambda _: [VAULT_DIR / "写作" / "投资回顾"],
    "notebooklm": lambda _: [VAULT_DIR / "导航" / "NotebookLM"],
    "inbox": lambda _: [VAULT_DIR / "收件箱"],
}

# Source type classification for coverage assessment
PRIMARY_SOURCES = {"thesis", "earnings_analysis", "research_notes"}
SECONDARY_SOURCES = {"podcast", "meeting", "xueqiu", "13f", "wechat", "substack",
                     "chatgpt", "supply_chain", "review", "notebooklm", "inbox"}


def _file_mentions_ticker(filepath: Path, search_terms: list[str]) -> bool:
    """Check if a file mentions the ticker (filename or content).

    Strategy for accuracy:
    1. Filename contains ticker (e.g., PM_mentions.md, PM-US/) → always match
    2. Frontmatter ticker/tickers field → always match (structured data)
    3. Long search terms (>3 chars, e.g. "Philip Morris") → substring match
    4. Short tickers (≤3 chars) in body → require uppercase form (financial context)
    """
    ticker = search_terms[0]  # First term is always the uppercase ticker
    name_lower = filepath.stem.lower()

    # 1. Check filename — ticker at word boundary (handles PM_mentions, PM-US, etc.)
    if re.search(r"(?:^|[\W_])" + re.escape(ticker.lower()) + r"(?:$|[\W_])", name_lower):
        return True

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")[:3000]
    except Exception:
        return False

    # 2. Check frontmatter ticker/tickers field (most reliable)
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        if fm_end > 0:
            fm = content[3:fm_end]
            # Match ticker: PM or tickers: [PM, MO]
            if re.search(r"tickers?:\s*(?:\[?[^\]\n]*\b)?" + re.escape(ticker) + r"\b", fm):
                return True

    # 3. Long search terms (company names, aliases) — substring match in content
    content_lower = content.lower()
    for term in search_terms[2:]:  # Skip ticker and ticker.lower()
        if len(term) > 3 and term.lower() in content_lower:
            return True

    # 4. Short ticker in body — require UPPERCASE form to reduce false positives
    #    This catches "$PM", "PM stock", etc. but not "pm" in "3:45pm"
    if len(ticker) <= 3:
        if re.search(r"(?:^|[\s$(\[\"'])" + re.escape(ticker) + r"(?:$|[\s,.):\]\"'])", content):
            return True
    else:
        if ticker.lower() in content_lower:
            return True

    return False


def _extract_frontmatter_sections(filepath: Path) -> list[str]:
    """Extract framework_sections from file frontmatter if present."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")[:1000]
        if not content.startswith("---"):
            return []
        end = content.find("---", 3)
        if end == -1:
            return []
        fm_text = content[3:end]
        # Look for framework_sections: [S1, S3, ...]
        match = re.search(r"framework_sections:\s*\[([^\]]*)\]", fm_text)
        if match:
            raw = match.group(1)
            return [s.strip() for s in raw.split(",") if s.strip()]
    except Exception:
        pass
    return []


def _tag_file_content(filepath: Path) -> list[str]:
    """Tag a file's content with framework sections using keyword mode."""
    if not HAS_TAGGER:
        return []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        return tag_content(content, mode="keyword")
    except Exception:
        return []


def scan_sources(ticker: str) -> dict:
    """Scan all vault sources for a ticker and return coverage data.

    Returns:
        {
            "ticker": "PM",
            "sources": [
                {"file": "path", "source_type": "earnings_analysis", "sections": ["S1", "S4"]},
                ...
            ],
            "section_coverage": {
                "S1": {"primary": 3, "secondary": 1, "files": [...]},
                ...
            }
        }
    """
    search_terms = _get_search_terms(ticker)
    fw = _load_framework()
    all_sections = [s["id"] for s in fw["sections"].values()]

    sources_found = []
    section_coverage = {sid: {"primary": 0, "secondary": 0, "files": []} for sid in all_sections}

    for source_type, path_fn in SOURCE_PATHS.items():
        dirs = path_fn(ticker)
        for dir_path in dirs:
            if not dir_path.exists():
                continue
            # Collect matching files
            if dir_path.is_file():
                files = [dir_path]
            else:
                files = sorted(dir_path.glob("**/*.md"))

            for f in files:
                if not _file_mentions_ticker(f, search_terms):
                    continue

                # Get framework sections: frontmatter first, then keyword tagger
                sections = _extract_frontmatter_sections(f)
                if not sections:
                    sections = _tag_file_content(f)

                # Deduplicate to parent sections for coverage counting
                parent_sections = set()
                for s in sections:
                    parent_sections.add(s.split(".")[0])  # S1.2 → S1

                source_entry = {
                    "file": str(f.relative_to(Path.home())),
                    "source_type": source_type,
                    "sections": sorted(parent_sections),
                }
                sources_found.append(source_entry)

                # Update coverage counts
                is_primary = source_type in PRIMARY_SOURCES
                for sid in parent_sections:
                    if sid in section_coverage:
                        if is_primary:
                            section_coverage[sid]["primary"] += 1
                        else:
                            section_coverage[sid]["secondary"] += 1
                        section_coverage[sid]["files"].append(f.name)

    return {
        "ticker": ticker,
        "sources": sources_found,
        "section_coverage": section_coverage,
    }


# ── Coverage Assessment ──────────────────────────────────────


def assess_coverage(section_coverage: dict) -> dict[str, dict]:
    """Assess coverage level for each section.

    Returns dict: section_id → {level, icon, primary, secondary}
    - covered (✅): 2+ primary sources
    - partial (⚠️): 1 primary or 2+ secondary
    - gap (❌): 0 primary, 0-1 secondary
    """
    result = {}
    for sid, data in section_coverage.items():
        p, s = data["primary"], data["secondary"]
        if p >= 2:
            level, icon = "covered", "✅"
        elif p >= 1 or s >= 2:
            level, icon = "partial", "⚠️"
        else:
            level, icon = "gap", "❌"
        result[sid] = {"level": level, "icon": icon, "primary": p, "secondary": s,
                        "files": data.get("files", [])}
    return result


def coverage_score(assessment: dict) -> int:
    """Calculate overall coverage score as percentage."""
    total = len(assessment)
    if total == 0:
        return 0
    covered = sum(1 for v in assessment.values() if v["level"] == "covered")
    partial = sum(1 for v in assessment.values() if v["level"] == "partial")
    return round((covered + partial * 0.5) / total * 100)


# ── Output Formatters ────────────────────────────────────────


def format_matrix(ticker: str, scan_result: dict) -> str:
    """Format coverage matrix as markdown table."""
    fw = _load_framework()
    assessment = assess_coverage(scan_result["section_coverage"])
    score = coverage_score(assessment)

    lines = [f"## Framework Coverage: {ticker}\n"]
    lines.append("| # | Section | Sources | Level | Key Source |")
    lines.append("|---|---------|---------|-------|-----------|")

    for section_key, section in fw["sections"].items():
        sid = section["id"]
        a = assessment.get(sid, {"icon": "❌", "primary": 0, "secondary": 0, "files": []})
        total = a["primary"] + a["secondary"]
        key_source = ", ".join(a["files"][:2]) if a["files"] else "-"
        if len(key_source) > 40:
            key_source = key_source[:37] + "..."
        lines.append(
            f"| {sid} | {section['icon']} {section['name_en']} | "
            f"{total} ({a['primary']}p+{a['secondary']}s) | {a['icon']} | {key_source} |"
        )

    covered = sum(1 for v in assessment.values() if v["level"] == "covered")
    partial = sum(1 for v in assessment.values() if v["level"] == "partial")
    gaps = sum(1 for v in assessment.values() if v["level"] == "gap")
    lines.append(f"\n**Overall:** {covered}/9 covered, {partial} partial, {gaps} gap → Score: {score}%")
    lines.append(f"**Total sources found:** {len(scan_result['sources'])}")

    return "\n".join(lines)


def format_brief(ticker: str, scan_result: dict) -> str:
    """One-line coverage summary for embedding in other reports."""
    assessment = assess_coverage(scan_result["section_coverage"])
    score = coverage_score(assessment)
    covered = sum(1 for v in assessment.values() if v["level"] == "covered")
    gaps = sum(1 for v in assessment.values() if v["level"] == "gap")
    gap_sections = [sid for sid, v in assessment.items() if v["level"] == "gap"]
    gap_names = []
    fw = _load_framework()
    for section_key, section in fw["sections"].items():
        if section["id"] in gap_sections:
            gap_names.append(section["name_cn"])
    gap_str = f" 盲区: {', '.join(gap_names)}" if gap_names else ""
    return f"{ticker} 框架覆盖: {score}% ({covered}/9 covered, {gaps} gap).{gap_str}"


def format_gaps(ticker: str, scan_result: dict) -> str:
    """Show only gap and partial sections."""
    fw = _load_framework()
    assessment = assess_coverage(scan_result["section_coverage"])
    lines = [f"## Research Gaps: {ticker}\n"]

    has_gaps = False
    for section_key, section in fw["sections"].items():
        sid = section["id"]
        a = assessment.get(sid, {"level": "gap", "icon": "❌"})
        if a["level"] in ("gap", "partial"):
            has_gaps = True
            lines.append(f"### {a['icon']} {sid}: {section['icon']} {section['name_en']} ({section['name_cn']})")
            lines.append(f"Coverage: {a['level']} (primary: {a.get('primary', 0)}, secondary: {a.get('secondary', 0)})")
            lines.append("")

    if not has_gaps:
        lines.append("No gaps found — all 9 sections have adequate coverage.")

    return "\n".join(lines)


def format_questions(ticker: str, scan_result: dict) -> str:
    """Generate research questions for gap/partial sections."""
    fw = _load_framework()
    assessment = assess_coverage(scan_result["section_coverage"])
    dsm = fw.get("data_source_mapping", {})
    lines = [f"## Research Questions: {ticker}\n"]
    lines.append("Prioritized questions for framework gaps.\n")

    for section_key, section in fw["sections"].items():
        sid = section["id"]
        a = assessment.get(sid, {"level": "gap"})
        if a["level"] not in ("gap", "partial"):
            continue

        lines.append(f"### {section['icon']} {sid}: {section['name_en']}")
        # Collect key questions from subsections
        for sub in section.get("subsections", []):
            for q in sub.get("key_questions", [])[:2]:  # Top 2 per subsection
                lines.append(f"- {q}")

        # Suggest data sources
        sources = dsm.get(sid, {})
        primary = sources.get("primary", [])
        lines.append(f"\n**Suggested sources:** {', '.join(primary)}")
        lines.append(f"**Command:** `/research {ticker} \"{section['name_en']}\"`")
        lines.append("")

    return "\n".join(lines)


def format_json(ticker: str, scan_result: dict) -> str:
    """JSON output for programmatic consumption by other skills."""
    assessment = assess_coverage(scan_result["section_coverage"])
    output = {
        "ticker": ticker,
        "score": coverage_score(assessment),
        "total_sources": len(scan_result["sources"]),
        "sections": {},
    }
    fw = _load_framework()
    for section_key, section in fw["sections"].items():
        sid = section["id"]
        a = assessment.get(sid, {"level": "gap", "primary": 0, "secondary": 0})
        output["sections"][sid] = {
            "name": section["name_en"],
            "level": a["level"],
            "primary": a.get("primary", 0),
            "secondary": a.get("secondary", 0),
        }
    return json.dumps(output, indent=2, ensure_ascii=False)


# ── CLI ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Analysis Framework Coverage Scanner")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # scan
    scan_p = subparsers.add_parser("scan", help="Full coverage matrix")
    scan_p.add_argument("ticker", help="Ticker symbol")
    scan_p.add_argument("--format", choices=["table", "json", "brief"], default="table")

    # gaps
    gaps_p = subparsers.add_parser("gaps", help="Show only gaps")
    gaps_p.add_argument("ticker", help="Ticker symbol")

    # questions
    q_p = subparsers.add_parser("questions", help="Research questions for gaps")
    q_p.add_argument("ticker", help="Ticker symbol")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    ticker = args.ticker.upper()
    result = scan_sources(ticker)

    # Use UTF-8 wrapper to handle emoji on Windows GBK console
    import io

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if args.command == "scan":
        if args.format == "json":
            out.write(format_json(ticker, result) + "\n")
        elif args.format == "brief":
            out.write(format_brief(ticker, result) + "\n")
        else:
            out.write(format_matrix(ticker, result) + "\n")
    elif args.command == "gaps":
        out.write(format_gaps(ticker, result) + "\n")
    elif args.command == "questions":
        out.write(format_questions(ticker, result) + "\n")
    out.flush()


if __name__ == "__main__":
    main()
