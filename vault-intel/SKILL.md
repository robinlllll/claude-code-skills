---
name: vault-intel
description: "Nightly vault maintenance — hygiene, linking, kill criteria monitoring, 13F deltas, daily briefing. Use when user says 'vault intel', 'nightly', 'vault maintenance', 'run vault-intel', or asks for vault automation. NOT for one-off health checks (use /vault-health)."
---

# vault-intel — Nightly Vault Maintenance & Intelligence

Consolidates vault hygiene, research linking, kill criteria monitoring, 13F delta analysis, and daily briefing into a single coordinated pipeline.

## When to Use

- User says "run vault intel", "nightly check", "vault maintenance"
- Scheduled nightly at 21:00 via Task Scheduler
- User asks about vault health, orphan notes, thesis staleness, or 13F changes

## Architecture

**3-Stage Pipeline (eliminates race conditions):**
1. **Hygiene** (sequential) — scans vault, fixes frontmatter, builds backlink index
2. **Intelligence** (parallel) — linker + kill criteria + 13F delta run simultaneously
3. **Briefing** (sequential) — consumes all results, writes daily intelligence note

**5 Agents:**
| Agent | Purpose | Writes to Vault? |
|-------|---------|-----------------|
| `agent_hygiene.py` | Frontmatter fixes, orphan detection, backlink index | Yes (frontmatter only) |
| `agent_linker.py` | Cross-reference wikilinks, narrative changes | Yes (## Related section) |
| `agent_killcriteria.py` | KC violations, position health, task creation | No (tasks via task_manager) |
| `agent_13f_delta.py` | Quarter-over-quarter 13F holding changes | No (read-only) |
| `agent_vector_memory.py` | Incremental vector memory backfill (new embeddings) | No (writes to SQLite DB) |
| `agent_briefing.py` | Daily intelligence note in 导航/Nightly-Intel/ | Yes (new file only) |

## Execution

```bash
# Full pipeline (dry run)
python .claude/skills/vault-intel/scripts/coordinator.py --dry-run

# Full pipeline (live)
python .claude/skills/vault-intel/scripts/coordinator.py

# Single agent
python .claude/skills/vault-intel/scripts/coordinator.py --agent hygiene --dry-run
python .claude/skills/vault-intel/scripts/coordinator.py --agent killcriteria
python .claude/skills/vault-intel/scripts/coordinator.py --agent 13f_delta
python .claude/skills/vault-intel/scripts/coordinator.py --agent linker
python .claude/skills/vault-intel/scripts/coordinator.py --agent briefing
```

## Claude Instructions

When the user invokes this skill:

1. **Check lessons** via `read_lessons("vault-intel")`
2. **Ask mode**: Full pipeline or specific agent?
3. **Default to `--dry-run`** on first run of the day, then offer to run live
4. **Execute**: Run coordinator.py with appropriate flags
5. **Report**: Show the summary table from the output
6. **Flag P1 items**: If any P1 issues found, highlight them prominently

### For scheduled runs (nightly mode):
- Run `coordinator.py nightly` (no dry-run)
- Telegram notification sent automatically
- Briefing note appears in `导航/Nightly-Intel/`

## Reference

For configuration options, safety rules, health scoring, output paths, and dependencies, see [references/config-and-scoring.md](references/config-and-scoring.md).
