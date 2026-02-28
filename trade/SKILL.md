---
name: trade
description: "Trade Logger - Log trades with execution details, thesis links, and risk management. Use when user says 'log trade', 'BUY', 'SELL', 'SHORT', 'COVER', '记录交易', or mentions executing a trade."
allowed-tools: "Bash Read Write Edit Glob Grep"
metadata:
  version: 2.0.0
---

# Trade Logger (Script-Driven)

Quick trade logging during market hours with minimal friction. Deterministic Python script handles all logic.

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

## Workflow (3 Steps)

### Step 1: Parse Input

Extract from user command:
- **ACTION:** BUY / SELL / SHORT / COVER / ADD / TRIM
- **TICKER:** Stock symbol (uppercase)
- **QTY:** Number of shares (numeric)
- **PRICE:** Execution price (numeric)
- **REASON:** Quoted reason text (may be empty)

### Step 2: Execute Script

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  "C:\Users\thisi\.claude\skills\trade\scripts\trade_logger.py" \
  {ACTION} {TICKER} {QTY} {PRICE} --reason "{REASON}"
```

The script handles everything deterministically:
1. Fetches portfolio data (graceful fallback if API unavailable)
2. Calculates trade total, % of NAV, new position
3. Creates trade .md file in `PORTFOLIO/decisions/trades/`
4. Updates thesis.md Position History (if exists)
5. Auto-transitions thesis.yaml status (BUY/ADD → active, full SELL/COVER → past)
6. Records to SQLite (`~/.claude/data/investments.db`)
   - Includes sector metadata: `entity_dictionary[ticker].get('sector', 'Unknown')` stored in DecisionRecord for downstream `/review` sector-grouped analysis
7. Creates follow-up task via task_manager
8. Prints JSON confirmation to stdout

### Step 3: Present Results

Parse the JSON stdout from the script. Display confirmation:

```
✓ Logged: {ACTION} {QTY} {TICKER} @ ${PRICE} (${TOTAL})
  Position after: {SHARES} shares ({PCT}% of NAV)
  Thesis: {status} | Conviction: {N}/10
  Decision ID: {first 8 chars}
```

If `thesis.status_changed` is true:
```
  Status: {old} → {new} (auto)
```

If there are warnings, display them.

Then append reflection questions (T1-T3 from `shared/reflection_questions.yaml`):

> **T1:** 这笔交易的 thesis 和我上次更新 thesis 时相比，有新信息吗？还是纯粹情绪驱动？
> **T2:** 如果这笔交易亏损 20%，我的反应会是加仓还是止损？现在就想清楚。
> **T3:** 谁在卖出？为什么他们认为是卖出的好时机？我是那个 'sucker at the table' 吗？

**T4 (Sector-Specific, optional):**
Based on the resolved sector, add one targeted reflection question:

| Sector | T4 Question |
|--------|-------------|
| Semiconductors | "What stage of the inventory cycle are we in? Am I buying into a downcycle?" |
| SaaS / Cloud | "What is the NRR trend — expanding or compressing? Does this entry assume re-acceleration?" |
| Consumer Staples | "Is volume growth positive? Am I relying on pricing that may face elasticity limits?" |
| Financials | "Where are we in the credit cycle? Is NIM expanding or compressing?" |
| Healthcare | "What is the next binary catalyst (trial readout, FDA date)? Is the risk/reward asymmetric?" |
| Tobacco / Nicotine | "Is the RRP transition thesis intact? Volume decline rate accelerating or stable?" |
| Industrials | "Is book-to-bill > 1.0? Am I entering with backlog visibility or hoping for orders?" |
| Energy | "Am I making a commodity price bet or a company-specific bet? What's the breakeven?" |

Display after T1-T3. User can skip. T4 is logged but not required.

**Sector Context (display only, non-blocking):**
After trade confirmation, append a one-line sector context:
> "📊 Sector: {sector} — Primary KPIs to monitor: {top 2-3 sector KPIs from sector_metrics.yaml}"
>
> Example: "📊 Sector: Semiconductors — Monitor: GM%, Inventory Days, Data Center Revenue %"

Resolution: `entity_dictionary.yaml[TICKER].sector` → `sector_metrics.yaml[sector].canonical_kpis` (top 3 by importance).

For exit trades (SELL/COVER/TRIM), also suggest:
```
考虑更新 thesis: `/thesis {TICKER} update "Exited — {REASON}"`
```

## Important Notes

- **No questions asked** — just parse and log
- **Speed is priority** — market hours, need quick logging
- Risk fields (stop/target) left blank for manual fill later
- Decision Journal is separate — handled by Telegram Nightly Check (10 PM)
- If script fails, check stderr and report the error

## References

- `references/trade-template.md` — template format and calculation formulas
- `references/post-trade-checks.md` — post-trade logic and auto-checks
