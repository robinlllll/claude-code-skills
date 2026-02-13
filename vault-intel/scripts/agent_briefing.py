"""Agent 5: Daily Briefing Generator.

Consumes results from all 4 other agents and produces a daily intelligence
briefing as an Obsidian note in 导航/Nightly-Intel/.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

# Health score: each category can deduct up to its max_penalty.
# Deduction = max_penalty * min(1, count / threshold) where threshold = "concerning" count
HEALTH_CATEGORIES = {
    #                    max_penalty, concerning_threshold
    "missing_frontmatter": (15, 50),
    "missing_date_prefix": (10, 100),
    "orphan_notes": (10, 200),
    "empty_files": (5, 50),
    "P1_violations": (30, 1),  # Even 1 P1 = full 30pt penalty
    "stale_kc": (15, 3),
    "incomplete_theses": (15, 5),
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


def _compute_health_score(hygiene: dict, kc: dict) -> int:
    """Compute vault health score: 100 - scaled penalties.

    Each category deducts up to max_penalty points.
    Deduction scales linearly from 0 to max_penalty as count goes from 0 to threshold.
    """
    score = 100.0
    h_metrics = hygiene.get("metrics", {})
    k_metrics = kc.get("metrics", {})

    counts = {
        "missing_frontmatter": h_metrics.get("missing_frontmatter", 0),
        "missing_date_prefix": h_metrics.get("missing_date_prefix", 0),
        "orphan_notes": h_metrics.get("orphan_notes", 0),
        "empty_files": h_metrics.get("empty_files", 0),
        "P1_violations": k_metrics.get("p1_violations", 0),
        "stale_kc": k_metrics.get("stale_kc", 0),
        "incomplete_theses": k_metrics.get("incomplete_theses", 0),
    }

    for category, (max_penalty, threshold) in HEALTH_CATEGORIES.items():
        count = counts.get(category, 0)
        ratio = min(1.0, count / threshold) if threshold > 0 else 0
        score -= max_penalty * ratio

    return max(0, min(100, int(score)))


def _section_action_items(results: dict, max_items: int = 10) -> str:
    """Generate ## Action Items section."""
    lines = ["## Action Items\n"]
    items = []

    # P1 from kill criteria
    kc = results.get("killcriteria", {})
    for issue in kc.get("issues", []):
        if issue.get("severity") == "P1":
            items.append(f"- **P1** {issue['detail']}")

    # Tasks auto-created
    for action in kc.get("actions_taken", []):
        if action.get("type") == "task_created":
            items.append(f"- Task #{action['task_id']}: {action['detail']}")

    # P2 from hygiene (summarized)
    hygiene = results.get("hygiene", {})
    fm_count = hygiene.get("metrics", {}).get("missing_frontmatter", 0)
    if fm_count > 0:
        fixed = hygiene.get("metrics", {}).get("auto_fixed", 0)
        items.append(
            f"- **P2** {fm_count} files missing frontmatter ({fixed} auto-fixed)"
        )

    if not items:
        lines.append("No action items today.\n")
    else:
        lines.extend(items[:max_items])
        if len(items) > max_items:
            lines.append(f"\n*...and {len(items) - max_items} more*")

    return "\n".join(lines)


def _section_portfolio_alerts(results: dict) -> str:
    """Generate ## Portfolio Alerts section."""
    lines = ["## Portfolio Alerts\n"]
    kc = results.get("killcriteria", {})
    issues = kc.get("issues", [])
    no_thesis = kc.get("positions_without_thesis", [])

    if not issues and not no_thesis:
        lines.append("All clear.\n")
        return "\n".join(lines)

    # Group by type
    by_type: dict[str, list] = {}
    for issue in issues:
        t = issue.get("type", "other")
        by_type.setdefault(t, []).append(issue)

    if "P1_violation" in by_type:
        lines.append("### Kill Criteria Violations")
        for i in by_type["P1_violation"]:
            lines.append(f"- {i['detail']}")

    if "invalidation_breach" in by_type:
        lines.append("\n### Invalidation Breaches")
        for i in by_type["invalidation_breach"]:
            lines.append(f"- {i['detail']}")

    if "drawdown_alert" in by_type:
        lines.append("\n### Drawdown Alerts")
        for i in by_type["drawdown_alert"]:
            lines.append(f"- {i['detail']}")

    if "stale_kc" in by_type:
        lines.append("\n### Stale Theses")
        for i in by_type["stale_kc"][:10]:
            lines.append(f"- {i['detail']}")
        if len(by_type["stale_kc"]) > 10:
            lines.append(f"- *...and {len(by_type['stale_kc']) - 10} more*")

    if "concentration_alert" in by_type:
        lines.append("\n### Concentration Alerts")
        for i in by_type["concentration_alert"]:
            lines.append(f"- {i['detail']}")

    if "incomplete_thesis" in by_type:
        lines.append("\n### Incomplete Theses (Active Positions)")
        for i in by_type["incomplete_thesis"]:
            lines.append(f"- {i['detail']}")

    if no_thesis:
        lines.append(f"\n### Positions Without Thesis ({len(no_thesis)})")
        for sym in no_thesis[:15]:
            lines.append(f"- {sym}")
        if len(no_thesis) > 15:
            lines.append(f"- *...and {len(no_thesis) - 15} more*")

    return "\n".join(lines)


def _section_smart_money(results: dict) -> str:
    """Generate ## Smart Money Signals section."""
    lines = ["## Smart Money Signals\n"]
    tf = results.get("13f_delta", {})

    if tf.get("status") == "failed":
        lines.append(
            f"*13F analysis unavailable: {tf.get('errors', ['unknown'])[0]}*\n"
        )
        return "\n".join(lines)

    metrics = tf.get("metrics", {})
    latest_q = metrics.get("latest_quarter", "?")
    prev_q = metrics.get("previous_quarter", "?")
    lines.append(f"**{latest_q} vs {prev_q}**\n")

    overlaps = tf.get("overlap_tickers", [])
    if overlaps:
        lines.append(f"### Portfolio Overlaps: {', '.join(overlaps)}")
        # Show detail for overlapping tickers
        for item in tf.get("new_positions", []):
            if item.get("portfolio_overlap"):
                lines.append(
                    f"- **NEW** {item['manager_name']}: {item['ticker']} (${item['value_k']:,.0f}K)"
                )
        for item in tf.get("exits", []):
            if item.get("portfolio_overlap"):
                lines.append(f"- **EXIT** {item['manager_name']}: {item['ticker']}")
        for item in tf.get("size_changes", []):
            if item.get("portfolio_overlap"):
                direction = "+" if item["direction"] == "increase" else "-"
                lines.append(
                    f"- **{direction}{item['change_pct']:.0f}%** {item['manager_name']}: {item['ticker']}"
                )
        lines.append("")

    # Top non-overlap signals
    new_ct = metrics.get("new_positions", 0)
    exit_ct = metrics.get("exits", 0)
    change_ct = metrics.get("size_changes", 0)
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| New positions | {new_ct} |")
    lines.append(f"| Exits | {exit_ct} |")
    lines.append(f"| Significant size changes | {change_ct} |")
    lines.append(f"| Portfolio overlaps | {len(overlaps)} |")

    return "\n".join(lines)


def _section_research_updates(results: dict) -> str:
    """Generate ## Research Updates section."""
    lines = ["## Research Updates\n"]
    linker = results.get("linker", {})

    if linker.get("status") == "failed":
        lines.append(f"*Linker unavailable: {linker.get('errors', ['unknown'])[0]}*\n")
        return "\n".join(lines)

    metrics = linker.get("metrics", {})
    links_added = metrics.get("links_added", 0)
    narrative_changes = metrics.get("narrative_changes", 0)
    cross_refs = metrics.get("cross_references", 0)
    notes_scanned = metrics.get("notes_scanned", 0)

    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Notes scanned | {notes_scanned} |")
    lines.append(f"| Wikilinks added | {links_added} |")
    lines.append(f"| Cross-references | {cross_refs} |")
    lines.append(f"| Narrative changes | {narrative_changes} |")

    # Detail narrative changes
    for change in linker.get("narrative_changes_detail", []):
        lines.append(f"\n### {change.get('ticker', '?')} Narrative Change")
        lines.append(f"- {change.get('detail', 'No detail')}")

    return "\n".join(lines)


def _section_vault_health(results: dict) -> str:
    """Generate ## Vault Health section."""
    lines = ["## Vault Health\n"]
    hygiene = results.get("hygiene", {})
    kc = results.get("killcriteria", {})

    h_metrics = hygiene.get("metrics", {})
    score = _compute_health_score(hygiene, kc)

    # Score emoji based on range
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    else:
        grade = "D"

    lines.append(f"**Health Score: {score}/100 ({grade})**\n")
    lines.append("| Check | Count |")
    lines.append("|-------|-------|")
    lines.append(f"| Files scanned | {h_metrics.get('files_scanned', 0)} |")
    lines.append(f"| Issues found | {h_metrics.get('issues_found', 0)} |")
    lines.append(f"| Auto-fixed | {h_metrics.get('auto_fixed', 0)} |")
    lines.append(f"| Missing frontmatter | {h_metrics.get('missing_frontmatter', 0)} |")
    lines.append(f"| Missing date prefix | {h_metrics.get('missing_date_prefix', 0)} |")
    lines.append(f"| Empty files | {h_metrics.get('empty_files', 0)} |")
    lines.append(f"| Orphan notes | {h_metrics.get('orphan_notes', 0)} |")
    lines.append(f"| Backlink index size | {h_metrics.get('backlink_index_size', 0)} |")

    return "\n".join(lines)


def run(
    config: dict, dry_run: bool = False, agent_results: dict = None, **kwargs
) -> dict:
    """Run the daily briefing generator."""
    started = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    result = {
        "agent": "briefing",
        "status": "success",
        "started_at": started,
        "metrics": {},
        "issues": [],
        "actions_taken": [],
        "errors": [],
    }

    results = agent_results or {}
    b_cfg = config.get("briefing", {})
    output_folder = b_cfg.get("output_folder", "导航/Nightly-Intel")
    max_items = b_cfg.get("max_action_items", 10)
    vault_path = config["vault_path"]

    # Build briefing markdown
    sections = [
        _section_action_items(results, max_items),
        _section_portfolio_alerts(results),
        _section_smart_money(results),
        _section_research_updates(results),
        _section_vault_health(results),
    ]

    # Count P1 issues across all agents
    p1_count = 0
    for agent_name, agent_result in results.items():
        if isinstance(agent_result, dict):
            for issue in agent_result.get("issues", []):
                if issue.get("severity") == "P1":
                    p1_count += 1

    health_score = _compute_health_score(
        results.get("hygiene", {}),
        results.get("killcriteria", {}),
    )

    frontmatter = f"""---
date: {today}
type: vault-intel
tags: [daily-brief, vault-intel]
health_score: {health_score}
p1_count: {p1_count}
---"""

    header = f"# Vault Intelligence — {today}\n"

    body = "\n\n".join([frontmatter, header] + sections)

    # Write to vault
    output_dir = vault_path / output_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{today}-briefing.md"

    if not dry_run:
        try:
            safe_write(output_file, body)
            result["actions_taken"].append(
                {
                    "type": "briefing_created",
                    "path": str(output_file.relative_to(vault_path)),
                    "details": f"Daily briefing for {today}",
                }
            )
        except Exception as e:
            result["errors"].append(f"Failed to write briefing: {e}")
            result["status"] = "partial"
    else:
        result["actions_taken"].append(
            {
                "type": "briefing_preview",
                "path": str(output_file.relative_to(vault_path)),
                "details": f"[DRY RUN] Would create briefing at {output_file}",
            }
        )

    result["metrics"] = {
        "health_score": health_score,
        "p1_count": p1_count,
        "sections_generated": len(sections),
        "output_path": str(output_file.relative_to(vault_path)),
    }

    # Generate summary line for Telegram
    result["telegram_summary"] = (
        f"Vault Intel {today}: Score {health_score}/100, "
        f"P1={p1_count}, "
        f"Issues={results.get('hygiene', {}).get('metrics', {}).get('issues_found', 0)}"
    )

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily Briefing Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()

    # Load result files from data dir if running standalone
    agent_results = {}
    for name in ["hygiene", "killcriteria", "linker", "thirteenf"]:
        result_file = OUTPUT_DIR / f"{name}_result.json"
        if result_file.exists():
            with open(result_file, encoding="utf-8") as f:
                agent_results[name if name != "thirteenf" else "13f_delta"] = json.load(
                    f
                )

    result = run(cfg, dry_run=args.dry_run, agent_results=agent_results)

    out_path = OUTPUT_DIR / "briefing_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Status: {result['status']}")
    print(
        f"  Health: {result['metrics']['health_score']}/100, P1: {result['metrics']['p1_count']}"
    )
    print(f"  Output: {result['metrics']['output_path']}")
    if result["errors"]:
        print(f"  Errors: {result['errors']}")
