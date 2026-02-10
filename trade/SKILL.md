---
name: trade
description: Trade Logger - Log trades with execution details, thesis links, and risk management
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

### 6. Confirm to User

Display a brief confirmation:
```
✓ Logged: BUY 100 TSM @ $332.71 ($33,271)
  Position after: 8,900 shares (15.55% of NAV)
  Thesis: Linked ✓
```

## Trade Log Template

```markdown
# Trade: {ACTION} {TICKER}

| Field | Value |
|-------|-------|
| Date | {YYYY-MM-DD HH:MM} |
| Action | {ACTION} |
| Ticker | {TICKER} |
| Qty | {QTY} |
| Price | ${PRICE} |
| Total | ${TOTAL} |
| % of NAV | {PCT}% |

## Position After Trade
- Shares: {NEW_SHARES}
- Avg Cost: ${AVG_COST}
- % of NAV: {POSITION_PCT}%

## Rationale
{REASON from command}

## Thesis Link
[{TICKER} Thesis](../../research/companies/{TICKER}/thesis.md)

## Risk (fill manually)
- Stop: $___
- Target: $___

---
*Logged via /trade command*
```

### 7. Post-Trade 自动检查

交易记录完成后，Claude **自动执行**以下检查（不需要用户要求）：

#### 1. Thesis 自动检查
- 读取 `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/thesis.md`
- **如果 thesis 存在:**
  - 读取 Position History 表
  - 如果当前交易与 thesis 记录一致 → 自动添加新行到 Position History，输出 1 行摘要
  - 如果数据不一致（如 thesis 记录的方向/仓位与交易矛盾）→ 提示用户确认，不静默覆盖
  - 输出: "[Thesis: conviction High, last updated 15 days ago]"
- **如果 thesis 不存在:**
  - "{TICKER} 没有投资论文，建议 `/thesis {TICKER}` 创建"

#### 2. Passed Record 自动检查
- 检查 `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/passed.md`
- **如果 passed.md 存在:**
  - "你曾在 {date} pass 了 {TICKER}，当时理由: {reason}。确定要交易？"
- **如果不存在:** 静默通过

#### 3. Flashback 建议（不自动执行）
- 输出: "如需查看完整研究轨迹: `/flashback {TICKER}`"
- 不自动执行（扫描 12 个数据源，token 消耗大）

After exit trades (SELL/COVER), also prompt: "考虑更新 thesis: `/thesis {TICKER} update \"Exited — {REASON}\"`"

#### 4. Auto-Task Creation (via task_manager)
交易记录完成后，自动创建跟进任务（7 天去重，不会重复创建）：
```python
try:
    import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
    from shared.task_manager import auto_create_task
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    auto_create_task(
        f"Update thesis after {ACTION} {TICKER}",
        source="post-trade", category="thesis", ticker=TICKER,
        priority=2, due_at=tomorrow, estimated_minutes=20,
        dedup_key=f"post-trade-thesis-{TICKER}-{date.today().isoformat()}"
    )
except ImportError:
    pass
```
只在终端简短提示: `[Auto-task: Update thesis after BUY NVDA — due tomorrow]`

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

## Key Calculations

**Trade Total:**
```
total = qty * price
```

**Position % of NAV:**
```
pct_nav = (total_shares * current_price) / nav * 100
```

**New Average Cost (for ADD/BUY):**
```
new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
```

## Output Files

- `decisions/trades/{YYYY-MM-DD}_{ACTION}_{TICKER}.md` - Trade log
- Updates `research/companies/{TICKER}/thesis.md` - Position history (if exists)

## Decision Journal

Trade logging and decision journaling are **separate concerns**:
- `/trade` = execution record (speed, minimal friction, market hours)
- Decision Journal = thought process + emotions (captured via **Nightly Journal Check at 10 PM** through Telegram)

**Do NOT ask DJ questions during `/trade`.** The Telegram bot will automatically push each unrecorded trade at 10 PM and walk through the DJ flow (emotion → confidence → why now → what if wrong → alternatives).

If the user wants to record DJ immediately, tell them to use `/dj TICKER ACTION` in Telegram.

## 🪞 交易反思（自动追加）

交易记录完成后，自动追加 `shared/reflection_questions.yaml` 中的 post_trade 问题（T1-T3）。

## Important Notes

- **No questions asked** - just parse and log
- **Speed is priority** - market hours, need quick logging
- Risk fields (stop/target) left blank for manual fill later
- Thesis creation is separate - use `/thesis {TICKER}` command
- Decision Journal is separate - handled by Telegram Nightly Check (10 PM)
