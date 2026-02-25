"""SKILL.md Lost-in-Middle Audit Script.

Scans all SKILL.md files in the skills directory and flags those
that may suffer from lost-in-middle issues: critical instructions
buried deep in the file where LLMs are less likely to attend.

Usage:
    python audit_skills.py              # audit all skills
    python audit_skills.py --json       # JSON output
    python audit_skills.py --verbose    # show per-check details
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent
MIN_LINES = 200  # only audit files longer than this

# Keywords that indicate guardrails / constraints
GUARDRAIL_KEYWORDS = re.compile(
    r"\b(MUST|NEVER|IMPORTANT|CRITICAL|REQUIRED|MANDATORY|DO NOT|ALWAYS|禁止|必须|不可)\b",
    re.IGNORECASE,
)

# Keywords that indicate execution steps
EXECUTION_KEYWORDS = re.compile(
    r"(## (Execution Steps|Core Workflow|Workflow|Instructions|Quick Start)|"
    r"### \d+\.|Step \d+|阶段|步骤)",
    re.IGNORECASE,
)

# Patterns that indicate template/example content (code blocks, sample output)
TEMPLATE_PATTERNS = re.compile(
    r"^(```|---\n|> |#{1,3} 20\d{2}|#### 20\d{2}|^\| )", re.MULTILINE
)


def audit_skill(skill_dir: Path) -> dict | None:
    """Audit a single SKILL.md file. Returns None if < MIN_LINES."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")
    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines < MIN_LINES:
        return None

    skill_name = skill_dir.name
    issues = []

    # --- Check 1: Execution steps in first 50 lines ---
    first_50 = "\n".join(lines[:50])
    has_exec_early = bool(EXECUTION_KEYWORDS.search(first_50))
    if not has_exec_early:
        issues.append(
            {
                "check": "execution_steps_early",
                "detail": "No execution steps / workflow header found in first 50 lines",
                "severity": "high",
            }
        )

    # --- Check 2: Guardrails in first 100 lines ---
    first_100 = "\n".join(lines[:100])
    guardrail_matches = GUARDRAIL_KEYWORDS.findall(first_100)
    if len(guardrail_matches) < 2:
        issues.append(
            {
                "check": "guardrails_early",
                "detail": f"Only {len(guardrail_matches)} guardrail keywords in first 100 lines (need >=2)",
                "severity": "medium",
            }
        )

    # --- Check 3: Template/example ratio ---
    in_code_block = False
    template_lines = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            template_lines += 1
            continue
        if in_code_block:
            template_lines += 1
        elif stripped.startswith("> ") or stripped.startswith("| "):
            template_lines += 1

    template_ratio = template_lines / total_lines if total_lines > 0 else 0
    if template_ratio > 0.50:
        issues.append(
            {
                "check": "template_ratio",
                "detail": f"Template/example content is {template_ratio:.0%} of file ({template_lines}/{total_lines} lines)",
                "severity": "medium",
            }
        )

    # --- Check 4: Large movable reference sections ---
    refs_dir = skill_dir / "references"
    has_refs_dir = refs_dir.exists()

    # Find sections that look like references/templates after line 100
    large_sections = []
    current_section = None
    section_start = 0
    for i, line in enumerate(lines):
        if line.startswith("## "):
            if current_section and i - section_start > 50 and section_start > 100:
                section_lower = current_section.lower()
                if any(
                    kw in section_lower
                    for kw in [
                        "template",
                        "example",
                        "output",
                        "format",
                        "reference",
                        "输出格式",
                        "模板",
                    ]
                ):
                    large_sections.append(
                        {
                            "section": current_section,
                            "start_line": section_start + 1,
                            "length": i - section_start,
                        }
                    )
            current_section = line.strip("# ").strip()
            section_start = i
    # Check last section
    if current_section and total_lines - section_start > 50 and section_start > 100:
        section_lower = current_section.lower()
        if any(
            kw in section_lower
            for kw in [
                "template",
                "example",
                "output",
                "format",
                "reference",
                "输出格式",
                "模板",
            ]
        ):
            large_sections.append(
                {
                    "section": current_section,
                    "start_line": section_start + 1,
                    "length": total_lines - section_start,
                }
            )

    if large_sections:
        for sec in large_sections:
            issues.append(
                {
                    "check": "movable_section",
                    "detail": f"Section '{sec['section']}' ({sec['length']} lines from L{sec['start_line']}) could move to references/",
                    "severity": "low",
                }
            )

    # --- Verdict ---
    high_count = sum(1 for i in issues if i["severity"] == "high")
    medium_count = sum(1 for i in issues if i["severity"] == "medium")

    if high_count > 0 or medium_count >= 2:
        verdict = "RESTRUCTURE"
    elif medium_count == 1 or len(issues) >= 2:
        verdict = "REVIEW"
    else:
        verdict = "OK"

    return {
        "skill": skill_name,
        "lines": total_lines,
        "verdict": verdict,
        "has_references_dir": has_refs_dir,
        "template_ratio": round(template_ratio, 2),
        "guardrails_in_100": len(guardrail_matches),
        "exec_in_50": has_exec_early,
        "issues": issues,
    }


def main():
    json_output = "--json" in sys.argv
    verbose = "--verbose" in sys.argv

    results = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith((".", "_", "shared")):
            continue
        result = audit_skill(skill_dir)
        if result:
            results.append(result)

    if json_output:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Summary table
    restructure = [r for r in results if r["verdict"] == "RESTRUCTURE"]
    review = [r for r in results if r["verdict"] == "REVIEW"]
    ok = [r for r in results if r["verdict"] == "OK"]

    print(f"SKILL.md Audit — {len(results)} files >={MIN_LINES} lines")
    print(f"  RESTRUCTURE: {len(restructure)}")
    print(f"  REVIEW:      {len(review)}")
    print(f"  OK:          {len(ok)}")
    print()

    for r in sorted(
        results,
        key=lambda x: ("OK", "REVIEW", "RESTRUCTURE").index(x["verdict"]),
        reverse=True,
    ):
        icon = {"RESTRUCTURE": "🔴", "REVIEW": "🟡", "OK": "🟢"}[r["verdict"]]
        refs = "📁" if r["has_references_dir"] else "  "
        print(
            f"  {icon} {r['verdict']:13s} {r['skill']:25s} "
            f"{r['lines']:4d}L  tpl={r['template_ratio']:.0%}  "
            f"guard={r['guardrails_in_100']}  exec50={'Y' if r['exec_in_50'] else 'N'}  {refs}"
        )
        if verbose and r["issues"]:
            for issue in r["issues"]:
                sev = {"high": "‼️", "medium": "⚠️", "low": "ℹ️"}[issue["severity"]]
                print(f"      {sev} {issue['detail']}")

    if restructure:
        print(f"\n--- RESTRUCTURE candidates ({len(restructure)}) ---")
        for r in restructure:
            print(f"\n  🔴 {r['skill']} ({r['lines']}L)")
            for issue in r["issues"]:
                sev = {"high": "‼️", "medium": "⚠️", "low": "ℹ️"}[issue["severity"]]
                print(f"     {sev} {issue['detail']}")


if __name__ == "__main__":
    main()
