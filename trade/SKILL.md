---
name: trade
description: "Trade Logger - Log trades with execution details, thesis links, and risk management. Use when user says 'log trade', 'BUY', 'SELL', 'SHORT', 'COVER', '记录交易', or mentions executing a trade."
allowed-tools: "Bash Read Write Edit Glob Grep"
metadata:
  version: 1.0.0
---

# Trade Logger

Quick trade logging during market hours with minimal friction. Logs trades as markdown files with automatic position context.

## Project Location

`C:\Users\thisi\PORTFOLIO`

## Syntax

```
/trade {ACTION} {TICKER} {QTY} @ {PRICE} "{REASON}"
```

**Actions:** BUY, SELL, SHORT, COVER, ADD, TRIM

**Examples:**
- `/trade BUY AAPL 100 @ 185.50 "AI services growth thesis"`
- `/trade SELL NVDA 50 @ 140 "Taking profits after run"`
- `/trade ADD TSM 200 @ 330 "Buying the dip"`
- `/trade TRIM NVDA 100 @ 145 "Reducing position size"`

## Quick Mode Workflow

This is a **quick mode** skill - minimal questions, maximum speed.

### 1. Parse Trade Details

Extract from command:
- ACTION: BUY/SELL/SHORT/COVER/ADD/TRIM
- TICKER: Stock symbol
- QTY: Number of shares
- PRICE: Execution price
- REASON: Why this trade (the quoted text)

### 2. Fetch Current Position

```bash
curl -s http://localhost:8000/api/portfolio
```

From the response, find the ticker and extract:
- Current shares held
- Average cost basis
- Market value
- Total portfolio NAV

Calculate:
- Trade total value: `qty * price`
- % of NAV: `(trade_total / nav) * 100`
- New position size after trade

### 3. Check for Existing Thesis

Look for: `C:\Users\thisi\PORTFOLIO\research\companies\{TICKER}\thesis.md`

- If thesis exists: Link to it in the trade log
- If NO thesis for BUY/SHORT: Add a warning note (but still log the trade)

### 4. Create Trade Log

**File:** `C:\Users\thisi\PORTFOLIO\decisions\trades\{YYYY-MM-DD}_{ACTION}_{TICKER}.md`

If a file with that name already exists (multiple trades same day), append a sequence number:
- `2026-01-27_BUY_TSM.md` (first trade)
- `2026-01-27_BUY_TSM_2.md` (second trade same day)

### 5. Update Thesis Position History (if exists)

If thesis file exists, append an entry to the Position History table.

### 5.5. Record Decision to SQLite

After logging the trade file and updating thesis, record the decision in the investments database:

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\.claude\skills\shared')
from schemas import DecisionRecord
from db_utils import init_db, insert_decision

init_db()  # ensures table exists

record = DecisionRecord(
    date="{YYYY-MM-DD}",          # today's date
    ticker="{TICKER}",
    decision_type="{action}",      # map: BUY→buy, SELL→sell, ADD→add, TRIM→trim, SHORT→buy, COVER→sell
    reasoning="{REASON}",          # the quoted reason from user's command
    conviction=conviction,         # from thesis.yaml conviction field, default 5 if not found
    thesis_link="PORTFOLIO/research/companies/{TICKER}/thesis.md",
    trigger="{trigger}",           # infer from context: "earnings" if post-earnings, "thesis" if thesis-driven, "other" default
)
decision_id = insert_decision(record)
```

- Add `decision_id: {UUID}` to the trade .md file's frontmatter
- Display in confirmation: `Decision ID: {first 8 chars}`
- If db write fails: log warning but do NOT block the trade log (trade file is the primary record)

### 6. Thesis Status Auto-Transition

After logging the trade and updating thesis.md, check thesis.yaml for status transitions:

1. Read `thesis.yaml` for the ticker (if it exists, skip silently if not)
2. Get current `thesis_status` (default: none → skip)

**If ACTION is BUY, LONG, or ADD:**
- If `thesis_status` is `watching` or `past` → update to `active`
- Set `status_changed_at` to today, `status_reason` to "Auto: Position opened via /trade"
- Log: "Thesis status: {old} → active (auto-transition)"

**If ACTION is SELL or COVER:**
- Check if full exit: remaining shares == 0 OR user explicitly says "全部", "full exit", "清仓"
- If full exit AND `thesis_status` is `active` → update to `past`
- Set `status_changed_at` to today, `status_reason` to "Auto: Full position exit"
- Log: "Thesis status: active → past (auto-transition)"
- If PARTIAL exit (TRIM or shares remaining > 0) → do NOT change status

Write changes to thesis.yaml using `yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)`.

### 7. Confirm to User

Display a brief confirmation:
```
✓ Logged: BUY 100 TSM @ $332.71 ($33,271)
  Position after: 8,900 shares (15.55% of NAV)
  Thesis: Linked ✓
  Status: watching → active (auto)
```

See `references/trade-template.md` for template and calculation formulas.

See `references/post-trade-checks.md` for auto-checks, decision journal, and reflection questions.

## If No Position Data Available

If the portfolio API is unavailable or ticker not found:
- Still create the trade log
- Leave position fields as "N/A"
- Note: "Position data unavailable - update manually"

## For Exit Trades (SELL/COVER/TRIM)

When logging exits, the trade log should note:
- Shares sold
- Remaining position (if any)
- Calculate realized P&L if average cost is known

## Output Files

- `decisions/trades/{YYYY-MM-DD}_{ACTION}_{TICKER}.md` - Trade log
- Updates `research/companies/{TICKER}/thesis.md` - Position history (if exists)

## Important Notes

- **No questions asked** - just parse and log
- **Speed is priority** - market hours, need quick logging
- Risk fields (stop/target) left blank for manual fill later
- Thesis creation is separate - use `/thesis {TICKER}` command
- Decision Journal is separate - handled by Telegram Nightly Check (10 PM)
