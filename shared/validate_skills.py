#!/usr/bin/env python3
"""
validate_skills.py — Validate all Claude Code skills for structural integrity.

Checks:
  1. SKILL.md exists with YAML frontmatter (name + description)
  2. lessons.md exists
  3. scripts/*.py have valid syntax (if scripts/ exists)
  4. Referenced files in SKILL.md actually exist (references/, samples/)
  5. SKILL.md line count warning (>400 lines = should split)

Usage:
  python validate_skills.py              # Validate all skills
  python validate_skills.py spreadsheet  # Validate one skill
  python validate_skills.py --verbose    # Show details for all checks

Output: Terminal table with pass/warn/fail per skill.
"""

import os
import sys
import re
import ast
import yaml

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_DIRS = {"shared", "__pycache__", ".git", "node_modules"}
MAX_SKILL_LINES = 400


def parse_frontmatter(content):
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    try:
        return yaml.safe_load(content[3:end])
    except yaml.YAMLError:
        return None


def find_referenced_files(content, skill_dir):
    """Find files referenced in SKILL.md (references/, samples/, scripts/)."""
    missing = []
    # Match patterns like: `references/xxx.md`, `samples/xxx`, `scripts/xxx.py`
    pattern = r"`((?:references|samples|scripts)/[^`]+)`"
    matches = re.findall(pattern, content)
    for ref in matches:
        ref_path = os.path.join(skill_dir, ref)
        if not os.path.exists(ref_path):
            missing.append(ref)
    return missing


def check_python_syntax(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def validate_skill(skill_name, skill_dir, verbose=False):
    """Validate a single skill. Returns (status, issues) where status is PASS/WARN/FAIL."""
    issues = []
    warnings = []

    # 1. Check SKILL.md exists
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        issues.append("SKILL.md missing")
        return "FAIL", issues, warnings

    # 2. Check YAML frontmatter
    with open(skill_md, "r", encoding="utf-8") as f:
        content = f.read()

    fm = parse_frontmatter(content)
    if fm is None:
        issues.append("No YAML frontmatter")
    else:
        if not fm.get("name"):
            issues.append("frontmatter: 'name' missing")
        if not fm.get("description"):
            issues.append("frontmatter: 'description' missing")

    # 3. Check line count
    line_count = content.count("\n") + 1
    if line_count > MAX_SKILL_LINES:
        warnings.append(
            f"SKILL.md is {line_count} lines (>{MAX_SKILL_LINES}) — consider splitting to references/"
        )

    # 4. Check lessons.md
    lessons_md = os.path.join(skill_dir, "lessons.md")
    if not os.path.exists(lessons_md):
        warnings.append("lessons.md missing")

    # 5. Check referenced files exist
    missing_refs = find_referenced_files(content, skill_dir)
    for ref in missing_refs:
        issues.append(f"Referenced file missing: {ref}")

    # 6. Check scripts/ syntax
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.isdir(scripts_dir):
        for fname in os.listdir(scripts_dir):
            if fname.endswith(".py"):
                fpath = os.path.join(scripts_dir, fname)
                ok, err = check_python_syntax(fpath)
                if not ok:
                    issues.append(f"scripts/{fname} syntax error: {err}")

    # Determine status
    if issues:
        return "FAIL", issues, warnings
    elif warnings:
        return "WARN", issues, warnings
    else:
        return "PASS", issues, warnings


def main():
    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    # Collect skills to validate
    if args:
        skill_names = args
    else:
        skill_names = sorted(
            [
                d
                for d in os.listdir(SKILLS_DIR)
                if os.path.isdir(os.path.join(SKILLS_DIR, d))
                and d not in SKIP_DIRS
                and not d.startswith(".")
            ]
        )

    results = []
    for name in skill_names:
        skill_dir = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(skill_dir):
            results.append((name, "SKIP", ["Directory not found"], []))
            continue
        status, issues, warnings = validate_skill(name, skill_dir, verbose)
        results.append((name, status, issues, warnings))

    # Print results
    print()
    print(f"  {'Skill':<30} {'Status':<8} {'Details'}")
    print(f"  {'─' * 30} {'─' * 8} {'─' * 50}")

    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for name, status, issues, warnings in results:
        counts[status] = counts.get(status, 0) + 1
        icon = {"PASS": "+", "WARN": "!", "FAIL": "X", "SKIP": "-"}[status]
        details = ""
        if issues:
            details = issues[0]
        elif warnings:
            details = warnings[0]

        print(f"  [{icon}] {name:<28} {status:<8} {details}")

        if verbose and (len(issues) > 1 or len(warnings) > 1):
            for issue in issues[1:]:
                print(f"      {'':28} {'':8} {issue}")
            for warn in warnings[1:]:
                print(f"      {'':28} {'':8} {warn}")

    # Summary
    print()
    total = len(results)
    print(
        f"  Summary: {counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail, {counts.get('SKIP', 0)} skip / {total} total"
    )
    print()

    return 1 if counts["FAIL"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
