"""Agent 2: Research Cross-Reference & Linking.

Scans recent notes for ticker mentions, adds wikilinks to thesis/MOC files,
and detects narrative changes between new earnings analysis and existing theses.
Conservative: exact matches only, links in ## Related section only, never mid-paragraph.
"""

import json
import re
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


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


def _load_entity_dictionary() -> dict[str, dict]:
    """Load entity dictionary for ticker → aliases mapping."""
    dict_path = Path(r"C:\Users\thisi\.claude\skills\shared\entity_dictionary.yaml")
    if not dict_path.exists():
        return {}
    with open(dict_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _find_recent_notes(vault_path: Path, lookback_days: int) -> list[Path]:
    """Find notes modified in the last N days from research-relevant folders."""
    cutoff = datetime.now().timestamp() - (lookback_days * 86400)
    folders = [
        vault_path / "研究" / "财报分析",
        vault_path / "研究" / "研究笔记",
        vault_path / "收件箱",
    ]

    recent = []
    for folder in folders:
        if not folder.exists():
            continue
        for md_file in folder.rglob("*.md"):
            try:
                if md_file.stat().st_mtime >= cutoff:
                    recent.append(md_file)
            except Exception:
                continue
    return recent


def _extract_tickers_from_note(filepath: Path, entity_dict: dict,
                                blocklist: set[str]) -> list[str]:
    """Extract tickers from a note using frontmatter + entity dictionary matching."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    tickers = set()

    # 1. Check frontmatter for explicit tickers field
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                fm_tickers = fm.get("tickers", [])
                if isinstance(fm_tickers, list):
                    tickers.update(t.upper() for t in fm_tickers if t)
                elif isinstance(fm_tickers, str):
                    tickers.add(fm_tickers.upper())
            except Exception:
                pass

    # 2. Check filename for ticker patterns (e.g., "HOOD-US Q4 2025")
    stem = filepath.stem.upper()
    for ticker in entity_dict:
        if ticker in stem and ticker not in blocklist:
            tickers.add(ticker)

    # 3. Exact match against entity dictionary aliases in content
    content_upper = content.upper()
    for ticker, info in entity_dict.items():
        if ticker in blocklist:
            continue
        # Check ticker itself (must be word boundary)
        if re.search(rf"\b{re.escape(ticker)}\b", content_upper):
            tickers.add(ticker)

    return sorted(tickers)


def _existing_wikilinks(content: str) -> set[str]:
    """Extract all wikilink targets (lowercased) from content."""
    return {m.lower() for m in WIKILINK_RE.findall(content)}


def _find_related_section(content: str) -> int | None:
    """Find the line index of '## Related' section. Returns None if not found."""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## related"):
            return i
    return None


def _insert_links_in_related(content: str, links: list[str]) -> str:
    """Insert wikilinks into the ## Related section. Creates section if missing."""
    lines = content.split("\n")
    related_idx = _find_related_section(content)

    link_lines = [f"- [[{link}]]" for link in links]

    if related_idx is not None:
        # Insert after the ## Related heading
        insert_at = related_idx + 1
        # Skip any existing content in the section until next heading or EOF
        while insert_at < len(lines) and lines[insert_at].strip().startswith("- [["):
            insert_at += 1
        for i, link_line in enumerate(link_lines):
            lines.insert(insert_at + i, link_line)
    else:
        # Append ## Related section at the end
        lines.append("")
        lines.append("## Related")
        lines.extend(link_lines)

    return "\n".join(lines)


def _detect_narrative_change(thesis_path: Path, new_analysis_path: Path,
                              ticker: str) -> dict | None:
    """Compare new earnings analysis with thesis for narrative changes.

    Simple heuristic: check if sentiment keywords in analysis contradict thesis.
    """
    try:
        thesis_content = thesis_path.read_text(encoding="utf-8", errors="replace").lower()
        analysis_content = new_analysis_path.read_text(encoding="utf-8", errors="replace").lower()
    except Exception:
        return None

    # Simple sentiment signals
    bull_signals = ["beat", "exceeded", "accelerat", "upside", "strong growth",
                    "raised guidance", "market share gain"]
    bear_signals = ["miss", "below", "decelerat", "downside", "weak",
                    "lowered guidance", "market share loss", "margin compression"]

    # Count signals in the new analysis
    bull_count = sum(1 for s in bull_signals if s in analysis_content)
    bear_count = sum(1 for s in bear_signals if s in analysis_content)

    # Check thesis stance
    thesis_has_bull = "bull" in thesis_content
    thesis_has_bear = "bear" in thesis_content or "short" in thesis_content

    # Detect contradiction
    if bear_count >= 3 and not thesis_has_bear and thesis_has_bull:
        return {
            "ticker": ticker,
            "type": "bearish_shift",
            "detail": f"{ticker}: New analysis has {bear_count} bearish signals vs bullish thesis",
            "analysis_path": str(new_analysis_path),
        }
    elif bull_count >= 3 and thesis_has_bear and not thesis_has_bull:
        return {
            "ticker": ticker,
            "type": "bullish_shift",
            "detail": f"{ticker}: New analysis has {bull_count} bullish signals vs bearish thesis",
            "analysis_path": str(new_analysis_path),
        }

    return None


def run(config: dict, dry_run: bool = False, **kwargs) -> dict:
    """Run the research linker agent."""
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "agent": "linker",
        "status": "success",
        "started_at": started,
        "metrics": {},
        "issues": [],
        "actions_taken": [],
        "errors": [],
    }

    vault_path = config["vault_path"]
    portfolio_path = config["portfolio_path"]
    l_cfg = config.get("linker", {})
    lookback_days = l_cfg.get("lookback_days", 7)
    blocklist = set(l_cfg.get("ticker_blocklist", []))

    entity_dict = _load_entity_dictionary()
    recent_notes = _find_recent_notes(vault_path, lookback_days)

    links_added = 0
    cross_references = 0
    narrative_changes = []
    notes_scanned = len(recent_notes)

    for note_path in recent_notes:
        tickers = _extract_tickers_from_note(note_path, entity_dict, blocklist)
        if not tickers:
            continue

        try:
            content = note_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result["errors"].append(f"Cannot read {note_path}: {e}")
            continue

        existing_links = _existing_wikilinks(content)
        new_links = []

        for ticker in tickers:
            # Check if thesis.md exists → add wikilink
            thesis_md = portfolio_path / "research" / "companies" / ticker / "thesis.md"
            link_target = f"{ticker} Thesis"
            if thesis_md.exists() and link_target.lower() not in existing_links:
                new_links.append(link_target)

            # Check if MOC exists → add wikilink
            moc_path = vault_path / "导航" / "MOC" / f"{ticker} MOC.md"
            link_target_moc = f"{ticker} MOC"
            if moc_path.exists() and link_target_moc.lower() not in existing_links:
                new_links.append(link_target_moc)

            # Cross-reference: check for other recent earnings notes for same ticker
            for other_note in recent_notes:
                if other_note == note_path:
                    continue
                if ticker in other_note.stem.upper():
                    other_stem = other_note.stem
                    if other_stem.lower() not in existing_links:
                        new_links.append(other_stem)
                        cross_references += 1

            # Narrative tracking
            thesis_yaml = portfolio_path / "research" / "companies" / ticker / "thesis.yaml"
            if thesis_yaml.exists() and "财报分析" in str(note_path):
                change = _detect_narrative_change(thesis_yaml, note_path, ticker)
                if change:
                    narrative_changes.append(change)

        # Deduplicate
        new_links = list(dict.fromkeys(new_links))  # preserve order, remove dupes

        if new_links:
            if not dry_run:
                try:
                    updated_content = _insert_links_in_related(content, new_links)
                    safe_write(note_path, updated_content)
                    for link in new_links:
                        result["actions_taken"].append({
                            "type": "link_added",
                            "path": str(note_path.relative_to(vault_path)),
                            "details": f"Added [[{link}]]",
                        })
                        links_added += 1
                except Exception as e:
                    result["errors"].append(f"Failed to update {note_path}: {e}")
            else:
                for link in new_links:
                    links_added += 1
                    result["actions_taken"].append({
                        "type": "link_preview",
                        "path": str(note_path.relative_to(vault_path)),
                        "details": f"[DRY RUN] Would add [[{link}]]",
                    })

    # Report narrative changes as issues
    for change in narrative_changes:
        result["issues"].append({
            "type": "narrative_change",
            "ticker": change["ticker"],
            "severity": "P2",
            "detail": change["detail"],
        })

    result["metrics"] = {
        "notes_scanned": notes_scanned,
        "links_added": links_added,
        "cross_references": cross_references,
        "narrative_changes": len(narrative_changes),
    }
    result["narrative_changes_detail"] = narrative_changes

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Research Linker Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    result = run(cfg, dry_run=args.dry_run)

    out_path = OUTPUT_DIR / "linker_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Status: {result['status']}")
    m = result["metrics"]
    print(f"  Scanned: {m['notes_scanned']}, Links: {m['links_added']}, "
          f"Cross-refs: {m['cross_references']}, Narratives: {m['narrative_changes']}")
    if result["errors"]:
        print(f"  Errors: {result['errors']}")
