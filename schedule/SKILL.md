---
name: schedule
description: Interactive Week Planner — calendar + tasks + research, Python auto-scheduling
---

# /schedule - Interactive Week Planner

Interactive weekly planning: gather context (tasks, calendar, thesis, pipeline) → discuss priorities → Python auto-schedules → user adjusts → save to Obsidian + .ics.

## Project Location

- `~/.claude/skills/shared/week_planner.py` — data gathering + scheduling
- `~/.claude/skills/shared/task_manager.py` — `scheduled_date` column + 7 week functions

## Syntax

```
/schedule plan              Full interactive planning session
/schedule today             Today's scheduled tasks + calendar events
/schedule status            Current week progress (done vs remaining)
/schedule reschedule        Mid-week interactive replanning
/schedule review            End-of-week completion stats
```

## Instructions for Claude

### `/schedule plan` — Full Interactive Planning

**This is a 6-step interactive workflow. Do NOT skip steps or combine them.**

#### Step 1: Gather context (no user input needed)

```bash
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/week_planner.py context --week-start YYYY-MM-DD
```

Use Monday of the current week unless user specifies otherwise.

#### Step 2: Present TIERED overview

**Tier 1 — Executive summary (always show, keep to ~10 lines):**

```
## 本周 Feb 10-14 (W07)

任务: 12 pending (3 overdue) | 日历: 8 events | 论文: PM stale (45d)
关键: 13F deadline Feb 14 | AMAT earnings Thu | Pipeline bottleneck: wikilinks (49%)

Top tasks by urgency:
#8  [P1] Update PM thesis (45m, overdue)
#12 [P1] Process NVDA Q4 earnings (60m, due Wed)
#15 [P2] Run /13f download (15m, due Fri — DEADLINE)
... (top 5-8 tasks only)
```

**Tier 2 — Offer details on demand:**
> "Want to see full task list / calendar / pipeline details?"

Only expand if user asks.

#### Step 3: Priority discussion (interactive)

Ask the user:
> "What are your top priorities this week? Any blocked times or constraints?"
> (e.g., "Wednesday PM is blocked", "focus on AMAT", "keep Friday light")

Wait for user response. Do NOT proceed without input.

#### Step 4: Python generates schedule

Translate user constraints into CLI args and run:

```bash
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/week_planner.py schedule \
    --week-start YYYY-MM-DD \
    --task-ids 8,12,15,3,7,14 \
    --blocked "Wed:afternoon" \
    --fixed "15:2026-02-14" \
    --float "7,14" \
    --earnings "AMAT:2026-02-12"
```

**Constraint mapping:**
- "Wednesday PM is blocked" → `--blocked "Wed:afternoon"`
- "Friday half day" → `--capacity "Fri:240"`
- "Task #15 must be Friday" → `--fixed "15:2026-02-14"`
- "Do #7 and #14 any day" → `--float "7,14"`
- "AMAT reports Thursday" → `--earnings "AMAT:2026-02-12"`

Render the JSON result as a formatted schedule table.

#### Step 5: User adjusts (interactive iteration)

Show task IDs and available commands:

```
Adjust:
  move #42 → Wed       reschedule to specific day
  move #42 → float     make floating
  add "Research ABNB"   create + schedule new task
  remove #81            unschedule task
  swap Mon Tue          swap all tasks between days
  block Thu:morning     add blocked slot, re-run scheduler
  approve               commit plan
```

**On each adjustment:** Re-run `week_planner.py schedule` with updated constraints. Always re-render the FULL schedule from canonical data. Never do incremental edits.

**If user says "approve" or "looks good" → proceed to Step 6.**

#### Step 6: Commit

Execute in sequence:

1. **batch_schedule()** — set `scheduled_date` on all tasks:
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.task_manager import batch_schedule
assignments = [(8, '2026-02-10'), (12, '2026-02-11'), ...]  # from schedule result
batch_schedule(assignments)
```

2. **Write Obsidian markdown:**
```python
from shared.week_planner import generate_week_markdown
generate_week_markdown(week_start, context, schedule_result, focus_note="user's priorities")
```

3. **Generate merged .ics:**
```python
from shared.week_planner import generate_week_ics
generate_week_ics(week_start, schedule_result['schedule'], context['raw']['calendar_events'])
```

4. Report what was saved:
   - `写作/周计划/YYYY-MM-DD_week_plan.md`
   - `CALENDAR-CONVERTER/schedule_plan_YYYY-MM-DD.ics`
   - Number of tasks scheduled

---

### `/schedule today` — Quick Daily View

1. Get today's date and this week's Monday
2. Run `week_planner.py context --week-start MONDAY`
3. Show only today's scheduled tasks (including rollovers) + calendar events
4. Show week progress bar: `[===---] 3/12 done (25%)`

Format:
```
## 今天 Feb 11 (Tue)

### 已排程
- [ ] 08:00-09:00 [P1 thesis] PM Update PM thesis (#8)
- [ ] 09:05-10:05 [P1 research] NVDA Process earnings (#12)

### Rollover (昨日未完成)
- [ ] **#5** Process podcast backlog (45m)

### 日历
- 14:00 [Earnings Call] KO-US
- 16:00 [Conference] UBS Financial Services

### 周进度
[====------] 4/12 done (33%) | Floating: 2 | Buffer: 5h remaining
```

---

### `/schedule status` — Current Week Progress

```bash
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/week_planner.py status --week-start MONDAY
```

Show:
- Completion rate (scheduled vs done)
- Per-day breakdown (done, remaining, rollover)
- Floating tasks status
- Pipeline items processed this week

---

### `/schedule reschedule` — Mid-Week Replanning

1. Run `week_planner.py status` → show completed / remaining / rollovers
2. Ask what changed:
   > "What changed? Any new constraints or priority shifts?"
   > "For partially-completed tasks, how much is left?"
3. Re-run scheduler excluding past days, including rollovers
4. User approves → update `scheduled_date` via `batch_schedule()`
5. Append "## Revision N" to existing Obsidian file
6. Regenerate .ics

---

### `/schedule review` — End-of-Week Stats

Show:
- Scheduled vs completed (% rate)
- Per-category completion: research X/Y, thesis X/Y, etc.
- Rolled-over tasks → suggest: reschedule to next week or deprioritize?
- Pipeline items processed
- Time estimation accuracy (if started_at metadata exists)

End with:
> "Carry over N tasks to next week? Run `/schedule plan` for next week?"

---

## Data Flow

```
week_planner.py context  →  JSON (tasks, calendar, thesis, pipeline, signals)
        ↓
Claude presents tiered summary
        ↓
User provides priorities + constraints
        ↓
week_planner.py schedule  →  JSON (per-day blocks, deferred, floating)
        ↓
Claude renders + user adjusts (re-run schedule each time)
        ↓
batch_schedule() + generate_week_markdown() + generate_week_ics()
```

## Constraint Syntax

| User says | CLI arg |
|-----------|---------|
| "Wed PM blocked" | `--blocked "Wed:afternoon"` |
| "Wed morning blocked" | `--blocked "Wed:morning"` |
| "Friday half day" | `--capacity "Fri:240"` |
| "Task #15 must be Friday" | `--fixed "15:2026-02-14"` |
| "Do #7 any day" | `--float "7"` |
| "AMAT reports Thu" | `--earnings "AMAT:2026-02-12"` |

## Output Files

| File | Location |
|------|----------|
| Week plan (Obsidian) | `写作/周计划/YYYY-MM-DD_week_plan.md` |
| Week plan (ICS) | `CALENDAR-CONVERTER/schedule_plan_YYYY-MM-DD.ics` |
| Task DB updates | `shared/data/task_manager.db` (scheduled_date column) |

## Scheduling Algorithm

Python-based deterministic bin-packing (NOT LLM):

1. Place fixed assignments first
2. Place earnings-related tasks (prep day-before)
3. Place P1 + overdue tasks on earliest day
4. Place remaining by priority-urgency score
5. Deep work (research/thesis) → morning blocks
6. Admin/ingestion → afternoon blocks
7. 60m buffer per day reserved for unplanned work
8. Weekday capacity: 480m, Weekend: 240m
9. Tasks that overflow → deferred list

## Examples

```
/schedule plan                          Start interactive planning for current week
/schedule plan next                     Plan for next week (user says "next week")
/schedule today                         Quick view of today's schedule
/schedule status                        Check progress mid-week
/schedule reschedule                    Replanning after things changed
/schedule review                        End-of-week stats
```
