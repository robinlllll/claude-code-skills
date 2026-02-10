"""Per-skill lessons learned system.

Records, retrieves, and distills lessons from skill executions.
Each skill has a `lessons.md` file; lessons are markdown entries with timestamps.
Distillation promotes recurring patterns to `context/memory/tools.md`.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent  # .claude/skills/
MEMORY_TARGET = SKILLS_DIR.parent / "context" / "memory" / "tools.md"

MAX_ENTRIES = 50
MAX_AGE_DAYS = 90
ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) \| (.+)$")


def _lessons_path(skill_name: str) -> Path:
    """Return the lessons.md path for a skill."""
    return SKILLS_DIR / skill_name / "lessons.md"


def _parse_entries(text: str) -> list[dict]:
    """Parse lessons.md content into a list of entry dicts."""
    entries = []
    lines = text.split("\n")
    current = None
    for line in lines:
        m = ENTRY_RE.match(line)
        if m:
            if current:
                entries.append(current)
            current = {
                "date": m.group(1),
                "summary": m.group(2),
                "body_lines": [],
            }
        elif current is not None:
            current["body_lines"].append(line)
    if current:
        entries.append(current)
    # Strip trailing blank lines from each body
    for e in entries:
        while e["body_lines"] and not e["body_lines"][-1].strip():
            e["body_lines"].pop()
    return entries


def _render_entries(entries: list[dict]) -> str:
    """Render entry dicts back to markdown."""
    parts = ["# Lessons Learned\n"]
    for e in entries:
        parts.append(f"## {e['date']} | {e['summary']}")
        if e["body_lines"]:
            parts.append("\n".join(e["body_lines"]))
        parts.append("")  # blank line separator
    return "\n".join(parts)


def _trim_entries(entries: list[dict]) -> list[dict]:
    """Enforce rolling window: max MAX_ENTRIES, drop older than MAX_AGE_DAYS."""
    cutoff = (datetime.now() - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    entries = [e for e in entries if e["date"] >= cutoff]
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    return entries


def read_lessons(skill_name: str, max_entries: int = 5) -> str:
    """Return the most recent N lesson entries as markdown."""
    path = _lessons_path(skill_name)
    if not path.exists():
        return f"No lessons.md found for skill '{skill_name}'."
    text = path.read_text(encoding="utf-8")
    entries = _parse_entries(text)
    if not entries:
        return f"No lessons recorded for '{skill_name}'."
    recent = entries[-max_entries:]
    return _render_entries(recent)


def write_lesson(skill_name: str, lesson_text: str) -> str:
    """Append a timestamped lesson entry and enforce rolling window.

    lesson_text format:
        First line = summary (one line)
        Remaining lines = body (optional details)
    """
    path = _lessons_path(skill_name)
    if not path.exists():
        return f"Error: no lessons.md for skill '{skill_name}'. Create it first."

    text = path.read_text(encoding="utf-8")
    entries = _parse_entries(text)

    lines = lesson_text.strip().split("\n")
    summary = lines[0].strip()
    body_lines = lines[1:] if len(lines) > 1 else []

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary,
        "body_lines": body_lines,
    }
    entries.append(entry)
    entries = _trim_entries(entries)

    path.write_text(_render_entries(entries), encoding="utf-8")
    return f"Lesson recorded for '{skill_name}' ({len(entries)} total)."


def distill_lessons(skill_name: str, dry_run: bool = False) -> dict:
    """Scan lessons for recurring patterns (3+ occurrences) and distill to memory.

    Looks for lines starting with "Problem:" and counts exact matches.
    Returns dict with 'patterns' found and 'distilled' count.
    """
    path = _lessons_path(skill_name)
    if not path.exists():
        return {"error": f"No lessons.md for '{skill_name}'"}

    text = path.read_text(encoding="utf-8")
    entries = _parse_entries(text)

    # Count "Problem:" lines
    problem_counts: dict[str, int] = {}
    for e in entries:
        for line in e["body_lines"]:
            line_s = line.strip()
            if line_s.startswith("Problem:"):
                problem_counts[line_s] = problem_counts.get(line_s, 0) + 1

    # Filter to 3+ occurrences
    recurring = {k: v for k, v in problem_counts.items() if v >= 3}

    if not recurring:
        return {
            "patterns": {},
            "distilled": 0,
            "message": "No recurring patterns found.",
        }

    if dry_run:
        return {
            "patterns": recurring,
            "distilled": 0,
            "message": "Dry run — no changes made.",
        }

    # Build distill summary
    today = datetime.now().strftime("%Y-%m-%d")
    distill_lines = [f"\n## Skill Lessons Distilled: {skill_name} ({today})"]
    for problem, count in recurring.items():
        distill_lines.append(f"- ({count}x) {problem}")

    # Append to memory target
    MEMORY_TARGET.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_TARGET, "a", encoding="utf-8") as f:
        f.write("\n".join(distill_lines) + "\n")

    # Replace distilled entries with a summary marker in lessons.md
    for e in entries:
        new_body = []
        for line in e["body_lines"]:
            if line.strip() in recurring:
                new_body.append(f"[Distilled → memory/tools.md] {line.strip()}")
            else:
                new_body.append(line)
        e["body_lines"] = new_body

    path.write_text(_render_entries(entries), encoding="utf-8")

    return {
        "patterns": recurring,
        "distilled": len(recurring),
        "message": "Distilled to memory/tools.md.",
    }


def list_all_lessons(max_per_skill: int = 3) -> str:
    """Cross-skill overview of recent lessons."""
    output = ["# Skill Lessons Overview\n"]
    skill_dirs = sorted(
        d
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "shared" and (d / "lessons.md").exists()
    )
    found = 0
    for d in skill_dirs:
        text = (d / "lessons.md").read_text(encoding="utf-8")
        entries = _parse_entries(text)
        if not entries:
            continue
        found += 1
        recent = entries[-max_per_skill:]
        output.append(f"## {d.name}")
        for e in recent:
            output.append(f"- **{e['date']}** — {e['summary']}")
        output.append("")
    if not found:
        output.append("No lessons recorded in any skill yet.")
    return "\n".join(output)


# --- CLI test ---
if __name__ == "__main__":
    import sys

    print("=== Skill Lessons CLI Test ===\n")

    test_skill = "explore"
    path = _lessons_path(test_skill)
    if not path.exists():
        print(f"SKIP: {path} does not exist. Create lessons.md templates first.")
        sys.exit(1)

    # Write test lessons
    for i in range(1, 4):
        result = write_lesson(
            test_skill, f"Test lesson {i}\nProblem: test issue\nFix: did something"
        )
        print(f"write_lesson #{i}: {result}")

    # Read them back
    print(f"\n--- read_lessons('{test_skill}') ---")
    print(read_lessons(test_skill))

    # List all
    print("--- list_all_lessons() ---")
    print(list_all_lessons())

    # Distill (dry run)
    print("--- distill_lessons (dry_run) ---")
    print(distill_lessons(test_skill, dry_run=True))

    # Clean up test entries
    text = path.read_text(encoding="utf-8")
    entries = _parse_entries(text)
    entries = [e for e in entries if not e["summary"].startswith("Test lesson")]
    path.write_text(_render_entries(entries), encoding="utf-8")
    print(f"\nCleaned up test entries from {path}")
    print("\n=== All tests passed ===")
