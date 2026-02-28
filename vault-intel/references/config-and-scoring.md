# vault-intel — Configuration, Safety, Scoring & Dependencies

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
