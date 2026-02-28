---
name: schedule
description: Interactive Week Planner — calendar + tasks + research, Python auto-scheduling
---

# /schedule - Interactive Week Planner

Interactive weekly planning: gather context (tasks, calendar, thesis, pipeline) → discuss priorities → Python auto-schedules → user adjusts → save to Obsidian + .ics.

## Project Location

- `~/.claude/skills/shared/week_planner.py` — data gathering + scheduling
- `~/.claude/skills/shared/task_manager.py` — `scheduled_date` column + 7 week functions
- `~/.claude/skills/shared/gcal.py` — Google Calendar API integration

## Google Calendar Setup (one-time)

```bash
# 1. Authenticate (opens browser for OAuth)
cd ~/.claude/skills && python shared/gcal.py auth

# 2. Test connectivity
cd ~/.claude/skills && python shared/gcal.py test
```

Requires `shared/data/credentials.json` from Google Cloud Console (Calendar API enabled, OAuth Desktop app).
Token auto-refreshes after first auth. If not authenticated, falls back to `.ics` files only.

## Syntax

```
/schedule plan              Full interactive planning session
/schedule dashboard         Generate unified visual dashboard (replaces dashboard.html)
/schedule today             Today's scheduled tasks + calendar events
/schedule status            Current week progress (done vs remaining)
/schedule reschedule        Mid-week interactive replanning
/schedule review            End-of-week completion stats
```

## Instructions for Claude

### `/schedule dashboard` — Generate Visual Dashboard

Generates a unified scheduling dashboard HTML file with week/day/month views, task sidebar, and auto-scheduling.

Calendar events are loaded from Google Calendar API (if authenticated) + local `.ics` files in `~/CALENDAR-CONVERTER/`.

#### Step 1: Run the dashboard generator (single command)

```bash
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/dashboard_generator.py generate \
    --week-start YYYY-MM-DD \
    --output C:\Users\thisi\dashboard.html
```

Use Monday of the current week for `--week-start`.

The generator will:
- Auto-detect `.ics` files in `~/CALENDAR-CONVERTER/` and parse events for the target week
- Load tasks from `task_manager.db`
- Auto-schedule tasks into free calendar slots
- Inject everything into the HTML template

**Optional overrides:**
- `--ics-dir PATH` — Use a different directory for `.ics` files
- `--calendar-json 'JSON'` — Pass calendar events as JSON directly (bypasses .ics parsing)

#### Step 2: Confirm to user

> "Dashboard generated at dashboard.html with N calendar events + M scheduled tasks. Open it from your file browser."

---

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

#### Step 3b: Earnings Week Protocol

When context shows portfolio tickers reporting this week, run the earnings protocol **during Step 3 discussion**:

**1. Extract earnings times from calendar context:**
The `week_planner.py context` output includes `raw.calendar_events` with per-day events. Filter for portfolio tickers to get exact release and call times:
```python
# From context JSON
cal = context['raw']['calendar_events']
portfolio_tickers = set(context['raw']['portfolio_tickers'])
for date in sorted(cal.keys()):
    for evt in cal[date]:
        ticker = evt.get('ticker', '')
        if ticker in portfolio_tickers:
            # evt has: time, summary, category (e.g. "Earnings Release", "Earnings Call"), ticker
            # Use these to build .ics reminders + analysis blocks
```
Key categories: `Earnings Release` (release time), `Earnings Call` (call time + duration ~1h).
Time values: `"06:00"`, `"16:00"`, `"09:00"` (TIME TBD = placeholder, usually before/after market).

**2. Check portfolio weights:**
```python
import json
with open(r'C:\Users\thisi\PORTFOLIO\portfolio_monitor\data\portfolio_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
positions = data['positions']
total_mv = sum(abs(float(p.get('market_value_native', 0)) * float(p.get('fx_rate', 1))) for p in positions)
# Calculate % for each earnings ticker
```

**2. Apply the >3% call listening rule:**
- Positions >3% of NAV → block 1h for listening to earnings call
- Positions <3% → no call listening by default
- User can override and choose to listen to any call regardless of weight

**3. Handle call time conflicts:**
When two calls overlap (same timeslot):
- Ask user which to listen **live** vs follow via **live transcript**
- Live call: block 1h with 5min-before alarm
- Live transcript: add a **15min-after-start** reminder (not a full block)

**4. Build .ics calendar events for each portfolio earnings ticker:**

| Event Type | Timing | Duration | Alarm |
|------------|--------|----------|-------|
| Release reminder | Release time | 5min | **5min before** |
| Call listen block | Call time (if listening) | 60min | 5min before |
| Live transcript reminder | Call start + 15min | 5min | at event time |
| Analysis block | Call end + 2h | **30min** | 5min before |

- After-market calls (17:00): analysis blocks land at 19:00 same evening (user can shift to next morning)
- Before-market calls: analysis blocks land same day mid-morning
- No call scheduled: analysis block = release time + 4h

**5. Create prep tasks:**
For each portfolio ticker reporting this week:
- P1 task if position has thesis or is major holding
- P2 task for smaller positions
- Schedule prep task on the **day before** earnings (via `--earnings` flag)
- Estimated time: 30-45min for P1 (45m for top holdings like NVDA), 20min for P2

**6. Trim stale rollover tasks:**
If prior weeks left P3 peer/upstream/downstream earnings tasks:
- Keep only tasks where the **reviewed ticker itself** is in the current portfolio
- Delete tasks where the ticker is NOT in portfolio (just a peer of a holding)
- Check portfolio membership against `portfolio_data.json` positions list

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

3. **Generate .ics** — Two options:

   **a) If no earnings this week** (simple):
   ```python
   from shared.week_planner import generate_week_ics
   generate_week_ics(week_start, schedule_result['schedule'], context['raw']['calendar_events'])
   ```

   **b) If earnings week** (enhanced — build ICS directly with earnings events):
   Generate a full .ics file with VALARM reminders using Python's string building:
   - Release reminders: 5min-before alarm for each portfolio earnings release
   - Call listen blocks: 1h events for calls user chose to listen to
   - Live transcript reminders: events at call_start + 15min for conflicting calls
   - Analysis blocks: 30min events at call_end + 2h with 5min alarm
   - Use `TZID=America/New_York` and proper VTIMEZONE block
   - Save to `CALENDAR-CONVERTER/schedule_plan_YYYY-MM-DD.ics`

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
