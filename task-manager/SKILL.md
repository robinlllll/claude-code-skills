---
name: task
description: Task Manager - Centralized task tracking, daily planning, calendar sync, and ingestion pipeline health dashboard
---

# /task - Task Manager

Centralized task management for the investment workflow. Tracks tasks with priorities, generates daily plans with time blocks, exports to iPhone calendar (.ics), and monitors the content ingestion pipeline health.

## Project Location

`~/.claude/skills/shared/task_manager.py`

## Database

`~/.claude/skills/shared/data/task_manager.db` (SQLite, WAL mode)

## Syntax

```
/task add "title" [options]
/task list [filters]
/task done ID
/task cancel ID
/task start ID
/task plan [--ics]
/task calendar [--recurring]
/task pipeline [--type TYPE] [--attention STAGE]
```

## Instructions for Claude

### `/task add "title"` — Create a task

**Options:**
- `--priority 1-4` (1=Critical, 2=High, 3=Medium, 4=Low; default: 2)
- `--ticker TICKER` (associate with a stock)
- `--due YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS` (deadline)
- `--category` (research|trade|thesis|review|ingestion|admin|meeting|general)
- `--est MINUTES` (estimated time; default: 30)
- `--recurrence` (daily|weekly|monthly|quarterly)

**Implementation:**
```bash
cd ~/.claude/skills && python shared/task_manager.py add "TITLE" -p PRIORITY -t TICKER -d DUE -c CATEGORY -e MINUTES
```

Or via Python import:
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.task_manager import add_task
task_id = add_task("Review PM thesis", priority=1, ticker="PM", category="thesis", due_at="2026-02-15", estimated_minutes=45)
```

**Output:** Confirm with task ID and summary line.

### `/task list` — List tasks

**Filters:**
- `--status pending|in_progress|done|cancelled`
- `--ticker TICKER`
- `--category CATEGORY`
- `--all` (include completed/cancelled)

Default: shows pending + in_progress tasks, sorted by priority-urgency score.

**Implementation:**
```bash
cd ~/.claude/skills && python shared/task_manager.py list [--status pending] [--ticker PM]
```

**Output:** Markdown table with columns: #, Priority, Category, Title, Ticker, Due, Estimated.

### `/task done ID` — Complete a task

Marks the task as done with a completion timestamp.

For **recurring tasks**: advances `due_at` to the next occurrence instead of marking done. Never backfills missed instances.

**Implementation:**
```bash
cd ~/.claude/skills && python shared/task_manager.py done ID
```

### `/task cancel ID` — Cancel a task

### `/task start ID` — Start working on a task

Sets status to `in_progress` and records `started_at` in metadata (for passive time tracking).

### `/task plan` — Daily plan with time blocks

Generates a prioritized daily plan fitting tasks into time blocks:
- Morning: 08:00-12:00
- Afternoon: 13:00-18:00
- 5-minute buffer between tasks
- Overflow tasks marked as "DEFERRED"

**Options:**
- `--date YYYY-MM-DD` (plan for a specific day; default: today)
- `--ics` (also export the plan to .ics calendar file)

**Implementation:**
```bash
cd ~/.claude/skills && python shared/task_manager.py plan [--date 2026-02-10] [--ics]
```

**Output format:**
```
## Daily Plan: 2026-02-10
Capacity: 285m / 480m (59%)

**Overdue:** 2 tasks

- [ ] 08:00-08:45 [P1 thesis] PM Review PM thesis
- [ ] 08:50-09:50 [P1 research] NVDA Process earnings
- [ ] 09:55-10:25 [P2 research] TSM Update supply chain
  12:00-13:00 — Lunch —
- [ ] 13:00-13:15 [P3 ingestion] Run /link on podcast folder
- [ ] [DEFERRED] [admin] Backfill framework tags
```

### `/task calendar` — Export to .ics

Exports all tasks with deadlines to an `.ics` file with VALARM reminders (15-min and 60-min warnings).

**Options:**
- `--recurring` — Export recurring tasks with RRULE

**Output:** `~/CALENDAR-CONVERTER/tasks_YYYY-MM-DD.ics` or `~/CALENDAR-CONVERTER/recurring_tasks.ics`

User can then open the .ics file to import into iPhone Calendar.

### `/task pipeline` — Ingestion pipeline health

Shows completion rates across the 5 pipeline stages for all ingestion sources.

**Stages (funnel):**
```
ingested → has_frontmatter → has_tickers → has_framework_tags → has_wikilinks → is_reviewed
```

**Options:**
- `--type podcast|substack|wechat|xueqiu|x-bookmark|chatgpt` — filter by source
- `--attention STAGE` — list items missing a specific stage (e.g., `--attention wikilinks`)
- `--days N` — time window (default: 30)
- `--backfill` — one-time import from existing ingestion_state.db

**Implementation:**
```bash
cd ~/.claude/skills && python shared/task_manager.py pipeline [--type podcast] [--attention wikilinks]
```

**Output format:**
```
| Source    | Total | FM | Tickers | Framework | Links | Reviewed |
|-----------|-------|----|---------|-----------|-------|----------|
| podcast   | 23    | 23 | 18      | 15        | 8     | 5        |
| substack  | 30    | 28 | 25      | 20        | 18    | 10       |
| **Rate**  | **53**| 96%| 81%     | 66%       | 49%   | 28%      |

Bottleneck: **Links** (49%)
Unreviewed: 38

Action: Run `/link 信息源/` to process unlinked items
```

## Priority System

| Level | Label | Use Case |
|-------|-------|----------|
| 1 | Critical | Must do today: earnings call, kill criteria triggered |
| 2 | High | Should do today: thesis update, active research |
| 3 | Medium | This week: process backlog, pipeline health |
| 4 | Low | Someday: backfill, optimization |

## Categories

| Category | Purpose |
|----------|---------|
| research | Research tasks (earnings, deep dives) |
| trade | Post-trade follow-ups |
| thesis | Thesis updates and reviews |
| review | Periodic reviews |
| ingestion | Content pipeline processing |
| admin | Administrative tasks |
| meeting | Meeting-related actions |
| general | Everything else |

## Auto-Task Generation

Other skills automatically create tasks via `auto_create_task()` with 7-day dedup:

| Source | Trigger | Task Created |
|--------|---------|--------------|
| `/trade BUY NVDA` | After trade logged | "Update thesis after BUY NVDA" (P2, due tomorrow) |
| `/review week` | After review generated | "Process review next actions (5)" (P3, meta-task with checklist) |
| `thesis_staleness_check.py` | Daily 08:30 | "Review stale thesis: PM (45 days)" (P2) |

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `/trade` | Auto-creates "update thesis" task post-trade |
| `/review` | Converts next actions to meta-task |
| `/thesis` | Staleness check creates tasks via scheduled script |
| `/link` | Updates pipeline stage `has_wikilinks` after linking |
| 6 ingestion skills | Record pipeline entries after ingestion |

## Examples

```
/task add "Review PM thesis" --priority 1 --ticker PM --due 2026-02-15 --est 45 --category thesis
/task add "Process earnings: NVDA Q4" -p 1 -t NVDA -c research -e 60
/task add "Weekly pipeline health check" -p 3 -c ingestion -r weekly
/task list --ticker PM
/task list --category research --status pending
/task done 3
/task plan --ics
/task pipeline --attention wikilinks
/task pipeline --type podcast
/task pipeline --backfill
```
