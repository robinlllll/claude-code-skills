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

## Configuration

Edit `config.yaml` to adjust:
- `hygiene.auto_fix_frontmatter`: Toggle auto-fix (default: true)
- `hygiene.auto_fix_date_prefix`: Toggle date renaming (default: false — breaks wikilinks)
- `linker.lookback_days`: How far back to scan for new notes (default: 7)
- `kill_criteria.stale_check_days`: Staleness threshold (default: 14)
- `thirteenf.min_position_change_pct`: Delta threshold (default: 20%)
- `safety.max_renames_per_run`: Hard cap on file renames (default: 0)

## Safety

- **Lock file** prevents double execution (2h timeout)
- **Atomic writes** via tmp+replace for all vault modifications
- **Date prefix renaming disabled** by default (breaks wikilinks)
- **Rename cap** at 0 per run (override requires config change)
- **Conservative linking**: exact ticker matches only, blocklist for common words (ALL, IT, NOW, etc.)
- **Links only in `## Related`**: never mid-paragraph insertion

## Output

- **JSON results**: `data/{YYYYMMDD-HHMMSS}/{agent}_result.json`
- **Daily briefing**: `导航/Nightly-Intel/{YYYY-MM-DD}-briefing.md`
- **Telegram**: Summary line pushed via telegram_notify

## Health Score

Each category can deduct up to its max penalty (scales linearly to threshold):

| Category | Max Penalty | Threshold |
|----------|-------------|-----------|
| Missing frontmatter | 15 | 50 |
| Missing date prefix | 10 | 100 |
| Orphan notes | 10 | 200 |
| Empty files | 5 | 50 |
| P1 violations | 30 | 1 |
| Stale kill criteria | 15 | 3 |
| Incomplete theses | 15 | 5 |

Grades: A (90+), B (75-89), C (60-74), D (<60)

## Dependencies

- `shared/obsidian_utils.py` — vault operations
- `shared/task_manager.py` — auto-create P1/P2 tasks
- `shared/entity_dictionary.yaml` — ticker → aliases
- `shared/telegram_notify.py` — push notifications
- `shared/skill_lessons.py` — lessons tracking
- PyYAML (standard dependency)
