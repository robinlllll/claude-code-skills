---
name: thesis
description: Investment Thesis Manager - Create, view, and update investment thesis documents for portfolio positions
---

# Investment Thesis Manager

Manage investment thesis documents for portfolio positions. Structure matches the Trading Journal web app for conceptual consistency.

## Project Location

`C:\Users\thisi\PORTFOLIO`

## Syntax

```
/thesis {TICKER}
/thesis {TICKER} update "{note}"
/thesis {TICKER} check
/thesis {TICKER} passed
/thesis {TICKER} passed update
```

**Examples:**
- `/thesis AAPL` - View or create thesis for AAPL
- `/thesis TSM update "Q4 beat, raising target"` - Add thesis log entry
- `/thesis PM check` - Check all kill criteria against latest data
- `/thesis NVDA passed` - Record why you passed on NVDA (creates passed.md)
- `/thesis NVDA passed update` - Update an existing passed record

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

## Classification Fields (Match Web App)

### Industry (13 options)
| Code | Industry |
|------|----------|
| BMAT | Basic Materials |
| CCYC | Consumer Cyclicals |
| CNCY | Consumer Non-Cyclicals |
| EDUC | Education |
| ENRG | Energy |
| FINA | Financials |
| HLTH | Healthcare |
| INDU | Industrial |
| REAL | Real Estate |
| TECH | Technology |
| TELE | Telecomm |
| UNCL | Unclassified |
| UTIL | Utilities |

### Strategy (5 options)
| Strategy | Description |
|----------|-------------|
| Value | Undervalued by market |
| Growth | High growth potential |
| GARP | Growth at reasonable price |
| Event-Driven | Catalyst-based |
| Momentum | Trend following |

### Driver (7 options)
| Driver | Description |
|--------|-------------|
| Valuation | Price vs intrinsic value |
| Growth | Revenue/earnings growth |
| Momentum | Price momentum |
| Event | Specific catalyst |
| Macro | Economic factors |
| Technical | Chart patterns |
| Catalyst | Upcoming event |

### Info Source (9 options)
| Source | Description |
|--------|-------------|
| Self-Research | Own analysis |
| Sell-Side | Analyst reports |
| Social Media | Twitter/X, etc |
| News | News articles |
| Podcast | Investment podcasts |
| 13F | Institutional filings |
| Friend | Personal network |
| Earnings | Earnings call/report |
| Other | Other source |

### Planned Hold Period
| Period | Days |
|--------|------|
| 30 days | Short-term trade |
| 60 days | Near-term |
| 90 days | Quarter |
| 180 days | Half year |
| 365 days | Long-term |

## Workflow

### 1. Parse Arguments
Extract ticker from command (e.g., `/thesis AAPL` -> AAPL)
Check if "update" subcommand with note

### 2. Fetch Current Position
```bash
curl -s http://localhost:8000/api/portfolio
```

Extract for this ticker:
- Current shares
- Average cost
- Market value
- Unrealized P&L
- % of portfolio

### 3. Check if Thesis Exists

**File location:** `C:\Users\thisi\PORTFOLIO\research\companies\{TICKER}\thesis.md`

### 4A. If Thesis EXISTS: Display It

1. Read and display the thesis file (thesis.md if exists, otherwise summarize thesis.yaml)
2. **Idea Source Backfill Check:** Read thesis.yaml — if `idea_source` is missing or empty:
   ```
   ⚠️ 归因缺失：此 thesis 无 idea_source。请现在设置。
   | # | Source | Description |
   |---|--------|-------------|
   | 1 | self-research | 自主研究 |
   | 2 | weekly-meeting | 周会讨论 |
   | 3 | earnings | 财报/Earnings call |
   | 4 | 13f | 机构持仓 13F |
   | 5 | podcast | 播客 |
   | 6 | substack | Substack 文章 |
   | 7 | x | X/Twitter |
   | 8 | supply-chain | 供应链线索 |
   | 9 | chatgpt | ChatGPT 对话 |
   | 10 | friend | 朋友推荐 |
   | 11 | other | 其他 |
   ```
   Use AskUserQuestion to let user pick. After selection → write `idea_source` and `first_seen: {today}` to thesis.yaml.
   If thesis.yaml already has `idea_source` → skip silently.
3. Show current position status from portfolio API
4. **Show Kill Criteria status table** (from thesis.yaml `kill_criteria` field):
   ```
   Kill Criteria (5 active)
   | # | Condition                                              | Type | Result  | Checked    |
   |---|--------------------------------------------------------|------|---------|------------|
   | 1 | ZYN US share <50% OR category <10% OR competitor +5pp  | QT   | Pass    | 2026-02-07 |
   | 2 | FDA lowers PMTA barriers                               | QL   | Pass    | 2026-02-07 |
   | 3 | Global SFP category growth <5% for 2Q                  | QT   | Pass    | 2026-02-07 |
   | 4 | IQOS Japan HTU share <65%                              | QT   | Pass    | 2026-02-07 |
   | 5 | 3+ markets impose punitive SFP taxes/bans              | QL   | Pass    | 2026-02-07 |
   ```
   - If no kill_criteria in YAML: show "No kill criteria defined. Use /thesis TICKER to add."
   - Flag any criteria with check_result = "warning" or "fail"
   - Flag any criteria where last_checked is >14 days ago (qualitative) or >30 days ago (quantitative)
5. **Discipline Violation Check:** For each KC with `fail_detected_at`:
   - Calculate hours since fail: `hours = (now - fail_detected_at).total_hours`
   - If hours > 48 AND thesis.yaml `updated_date` < `fail_detected_at`:
     ```
     🔴 **纪律违规：** "{condition}" 在 {hours} 小时前触发，无任何行动。
     48 小时内必须：更新 thesis / 减仓 / 明确 override。
     ```
   - Append to thesis.yaml `discipline_violations[]`:
     ```yaml
     discipline_violations:
       - condition: "the failed KC condition"
         fail_detected_at: 2026-02-07T10:30:00
         violation_flagged_at: 2026-02-09T14:00:00
         hours_unresolved: 51.5
     ```
6. Show peers if defined in thesis.yaml
7. **Show 13F Institutional Activity** (auto, from shared/13f_query.py):
   ```bash
   cd ~/.claude/skills && python shared/13f_query.py {TICKER} --summary
   ```
   - Display one-line summary: "{TICKER} (Q3): 12 holders (2 new, 3 up, 1 down). Top: Scion Asset (4.2%)"
   - If user wants details: run `python shared/13f_query.py {TICKER}` for full markdown table
   - If no 13F data available: silently skip (don't show empty section)
   - For Python import: use `importlib.import_module('shared.13f_query')`
8. **Show Position Sizing** (from thesis.yaml sizing fields):
   ```
   📐 Sizing: conviction(4/High) × quality(B/1.0) = 5% × 1.5 × 1.0 = 7.5%
   当前实际仓位: 8.2% → ⚠️ 略超建议 (0.7% over)
   ```
   - Formula: `target = base_size_pct × conviction_multiplier × quality_multiplier`
   - Conviction: 1=0.5x, 2=0.75x, 3=1.0x, 4=1.5x, 5=2.0x
   - Quality: A=1.2x, B=1.0x, C=0.7x
   - Hard cap: min(result, 10%)
   - If no sizing fields: show "No sizing data. conviction={N}, quality={grade}"
   - Get actual position weight from `curl -s http://localhost:8000/api/portfolio` and compare
9. Offer options:
   - Add thesis log entry
   - Update catalysts
   - Update bull/bear case
   - Update position history
   - **Check kill criteria** (`/thesis TICKER check`)

### 4B. If Thesis DOES NOT EXIST: Create New (NLM-Assisted)

1. Create directory: `C:\Users\thisi\PORTFOLIO\research\companies\{TICKER}\`
2. **NLM Attribution Query (auto, before asking user):**
   - Run NLM first-mention query against 投资观点周报 notebook:
     ```bash
     cd ~/.claude/skills && python -c "
     from shared.nlm_attribution import query_first_mention
     result = query_first_mention('{TICKER}', '{COMPANY_NAME}')
     print(result)
     "
     ```
   - If NLM returns a result, present to user:
     > "根据周会纪要，{TICKER} 最早在 {date} 讨论过：'{citation}'
     > 初始情绪: {bullish/bearish/neutral}
     > 确认这是想法来源？还是来自其他渠道？"
   - User confirms → auto-fill `idea_source: weekly-meeting`, `source_detail`, `nlm_citation`, `first_seen`
   - User overrides → use their selection from Info Source options
   - **Fallback:** If NLM fails or returns no result → proceed directly to manual Info Source selection
3. Ask user for:
   - Industry (show options)
   - Strategy (show options)
   - Driver (show options)
   - Info Source (**pre-filled if NLM succeeded**, show options if not)
   - Core thesis (1-2 sentences)
   - Bull case with target price
   - Bear case with stop price
   - Key catalysts with dates
   - Planned hold period
4. **Kill Criteria step (MANDATORY — after bear case):**
   - **最少 3 条 kill criteria（2 quantitative + 1 qualitative）。不可跳过。**
   - Ask: "What are the core moats, growth drivers, and key threats?"
   - For each dimension the user provides, generate a specific kill criteria condition
   - User reviews and approves/edits the conditions
   - Aim for 4-7 kill criteria total, mix of quantitative and qualitative
   - **Enforcement rules:**
     - If user attempts to skip or provides fewer than 3 KC → refuse to save thesis:
       *"没有退出条件的不是投资，是赌注。请至少提供 3 条 kill criteria（2 quantitative + 1 qualitative）。"*
     - If kill_criteria list is empty after user input → loop back to this step
     - Count types: must have ≥2 with `type: quantitative` AND ≥1 with `type: qualitative`
     - If type mix requirement not met → prompt user to add the missing type
   - Also ask for 2-3 key peers (ticker + relationship)
5. Create thesis.md from template (include NLM attribution fields in frontmatter)
6. **Create thesis.yaml** with kill_criteria, peers, supply_chain, quality_grade, idea_source
7. Pre-fill with portfolio data if position exists

### 5. Update Subcommand

If `/thesis {TICKER} update "{note}"`:
- Add entry to Thesis Log table with today's date
- Confirm update

## Thesis Template

```markdown
# Investment Thesis: {TICKER}

**Company:** {Full company name}
**Last Updated:** {YYYY-MM-DD}

---

## Classification

| Field | Value |
|-------|-------|
| Industry | {Industry} |
| Strategy | {Value/Growth/GARP/Event-Driven/Momentum} |
| Driver | {Valuation/Growth/Momentum/Event/Macro/Technical/Catalyst} |
| Info Source | {Self-Research/Sell-Side/Social Media/News/Podcast/13F/Friend/Earnings/Weekly Meeting/Other} |
| Idea Source | {substack/x/podcast/13f/supply-chain/weekly-meeting/chatgpt/self-research/other} |
| Source Detail | {e.g. "投资观点周报 2025, 2025-12-15 — 首次讨论 ZYN growth"} |
| Position | {LONG/SHORT/NONE} |
| Planned Hold | {30/60/90/180/365} days |

---

## Core Thesis

{2-3 sentences on why you own this}

---

## Bull Case

**Target:** ${TARGET} (+{PCT}% from entry)

1. {Reason 1}
2. {Reason 2}
3. {Reason 3}

## Bear Case

**Stop:** ${STOP} (-{PCT}% from entry)

1. {Risk 1}
2. {Risk 2}
3. {Risk 3}

---

## Key Catalysts

| Catalyst | Expected Date | Status |
|----------|---------------|--------|
| {Event 1} | {YYYY-MM-DD} | Pending |
| {Event 2} | {YYYY-MM-DD} | Pending |
| {Event 3} | {YYYY-MM-DD} | Pending |

---

## Position History

| Date | Action | Qty | Price | Notes |
|------|--------|-----|-------|-------|
| {YYYY-MM-DD} | {BUY/SELL} | {Qty} | ${Price} | {Notes} |

**Current Position:** {X} shares @ ${avg_cost} avg ({pct}% of NAV)

---

## Thesis Log

| Date | Update |
|------|--------|
| {YYYY-MM-DD} | Thesis created |

---

## Next Review

**Date:** {30 days from now}
**Trigger:** Next earnings / Key catalyst date
```

## Example Usage

**Create new thesis:**
```
User: /thesis TSM
Claude: No thesis found for TSM. Let me create one.
        Current position: 8,800 shares @ $348.18 avg (15.3% of NAV)

        I'll need a few details:
        1. Industry? [Technology]
        2. Strategy? [Growth/GARP/Value/Event-Driven/Momentum]
        3. Primary driver? [Growth/Valuation/Catalyst/...]
        4. Info source? [Self-Research/Sell-Side/...]
        5. Core thesis?
        6. Bull case + target?
        7. Bear case + stop?
        8. Key catalysts?
        9. Planned hold period?
```

**View existing thesis:**
```
User: /thesis NVDA
Claude: [Displays thesis.md content]

        📊 Current Position Status:
        • Shares: 3,800
        • Avg Cost: $187.97
        • Current: $186.47 (-0.80%)
        • Unrealized: -$5,683
        • % of NAV: 3.2%

        Would you like to update the thesis?
```

**Quick update:**
```
User: /thesis NVDA update "Blackwell shipping ahead of schedule"
Claude: ✓ Added to NVDA thesis log:
        2026-01-27 | Blackwell shipping ahead of schedule
```

### 6. Check Subcommand

**Syntax:** `/thesis TICKER check`

Review each kill criteria against the latest available information and update check_result + check_note in thesis.yaml.

**Workflow:**

1. Read `research/companies/{TICKER}/thesis.yaml` — extract kill_criteria list
2. For each criterion:
   - **Quantitative:** Search for latest data (web search, earnings analysis in Obsidian, NotebookLM history). Present the data and propose pass/warning/fail.
   - **Qualitative:** Present the condition and last check_note. Ask user for their current assessment (pass/warning/fail) and a brief note.
3. Update thesis.yaml with new `check_result`, `check_note`, and `last_checked` date
4. **If any KC has `check_result: fail`:**
   - Write `fail_detected_at: {ISO 8601 timestamp}` to that KC entry in thesis.yaml (if not already set)
   - Create a P1 urgent task via `auto_create_task()`:
     ```python
     import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
     from shared.task_manager import auto_create_task
     auto_create_task(
         f"KC FAIL: {TICKER} — {condition[:60]}",
         source="thesis-kc-fail", category="thesis", ticker=TICKER,
         priority=1, estimated_minutes=60,
         description=f"48h deadline. Must: update thesis / reduce position / explicit override.\nCondition: {condition}\nCheck note: {check_note}",
         dedup_key=f"kc-fail-{TICKER}-{condition_hash}"
     )
     ```
   - Display: `"🔴 FAIL 已检测。48 小时内必须：更新 thesis / 减仓 / 明确 override"`
5. Display summary table with any changes highlighted

**Output format:**
```
Kill Criteria Check: PM (2026-02-07)

1. ZYN US share <50% OR category <10% OR competitor +5pp
   Data: Share ~64% (Q4), category +30%, no single competitor threat
   Result: Pass (unchanged)

2. FDA lowers PMTA barriers
   Last note: "PMTA process remains rigorous"
   Your assessment? [pass/warning/fail + note]

   ...

Summary: 5 checked | 4 pass | 1 warning | 0 fail
Updated thesis.yaml
```

**Example:**
```
User: /thesis PM check
Claude: Checking 5 kill criteria for PM...

        1/5: ZYN US share <50% OR category <10% OR competitor +5pp [QT]
        Latest: ZYN share ~64% (Q4 2025), category +30% YoY
        -> Pass (no change)

        2/5: FDA lowers PMTA barriers [QL]
        Last check (2026-02-07): "PMTA process remains rigorous"
        Any update? [pass]

        ...

        Summary: 5/5 pass, 0 warnings, 0 fails
        thesis.yaml updated with new last_checked dates.
```

---

### 7. Challenge Subcommand

**Syntax:** `/thesis TICKER challenge`

Stress-test your thesis by surfacing contradicting evidence from NotebookLM history and the Obsidian vault — searching cached Q&A first before making live API calls.

**Workflow:**

1. Read existing thesis from `research/companies/{TICKER}/thesis.md` — extract core thesis, bull/bear cases
2. Search NLM answer history (free, no daily limit cost):
   ```bash
   cd ~/.claude/skills/notebooklm && python scripts/run.py history_manager.py search --query "{TICKER}"
   ```
   Also search company name and common aliases (e.g., NVDA → NVIDIA → 英伟达)
3. Grep Obsidian vault `导航/NotebookLM/` folder for ticker mentions:
   ```
   Grep ~/Documents/Obsidian Vault/导航/NotebookLM/ for TICKER, company name, aliases
   ```
4. Search 13F institutional holdings for smart money signals:
   ```bash
   cd ~/.claude/skills && python shared/13f_query.py {TICKER}
   ```
   - Flag any top holders that significantly reduced positions (>20% decrease)
   - Flag if a well-known contrarian fund took a new position
5. Present "Devil's Advocate" findings: contradicting evidence, risks not in bear case, outdated assumptions
5. Offer optional **deep challenge** via NotebookLM:
   ```bash
   cd ~/.claude/skills/notebooklm && python scripts/thesis_challenger.py {TICKER}
   ```
   This uploads the thesis to NLM and asks 3 devil's advocate questions with citations.
   Output saved to `Obsidian Vault/导航/NotebookLM/{date}_{TICKER}_challenge.md`
6. Optionally append challenge summary to thesis log via `/thesis TICKER update "..."`
7. Suggest updating kill criteria if new risks were discovered

**Output format:**

```markdown
## Thesis Challenge: {TICKER}

### Your Current Thesis
> {core thesis from thesis.md}

### Contradicting Evidence from NotebookLM History
| Source | Date | Finding |
|--------|------|---------|
| {notebook_name} | {date} | {relevant excerpt} |

### Risks Not in Current Bear Case
1. {risk from NLM answers not captured in bear case}

### Recommendation
{Keep / Update bear case / Flag for full review}
```

**Example:**
```
User: /thesis NVDA challenge
Claude: Reading NVDA thesis... Core thesis: "AI compute demand sustains pricing power"

        Searching NotebookLM history for NVDA, NVIDIA, 英伟达...
        Found 3 relevant Q&A pairs across 2 notebooks.

        ## Thesis Challenge: NVDA

        ### Your Current Thesis
        > AI compute demand sustains pricing power through 2027

        ### Contradicting Evidence from NotebookLM History
        | Source | Date | Finding |
        |--------|------|---------|
        | AI Infrastructure Economics | 2026-01-25 | Custom ASIC adoption at hyperscalers accelerating |
        | Semiconductor Supply Chain | 2026-02-01 | TSMC capacity expansion may reduce GPU scarcity premium |

        ### Risks Not in Current Bear Case
        1. Google TPU v6 performance parity mentioned in NLM source analysis

        ### Recommendation
        Update bear case — add custom silicon competitive risk

        💡 Want me to query NotebookLM live for deeper analysis?
```

---

## "Why I Passed" Workflow

### Purpose

Track companies you researched but decided NOT to invest in. This is critical for:
- Auditing your filtering intuition (did passed companies underperform?)
- Identifying systematic missed opportunities (are you too conservative on a category?)
- Attribution analysis in `/review` (what % of researched ideas become positions?)

### 6. Passed Subcommand

**Syntax:** `/thesis {TICKER} passed`

**Goal: ≤2 minutes to complete.** Low friction is more important than completeness.

**Workflow:**

1. Create directory if needed: `C:\Users\thisi\PORTFOLIO\research\companies\{TICKER}\`
2. Check if `passed.md` already exists
3. If NEW: Ask 3 quick questions using AskUserQuestion tool:
   - **Q1: "Where did you first see this idea?"**
     Options: Self-Research / Sell-Side / Social Media / Podcast / 13F / Earnings / Friend / Other
   - **Q2: "Why are you passing? (1-3 sentences)"**
     Free text — this is the most important field
   - **Q3: "Under what conditions would you revisit?"**
     Free text — e.g. "Stock drops >20%" or "New product launch"
4. Auto-fetch current stock price via Yahoo Finance:
   ```python
   import yfinance as yf
   price = yf.Ticker(TICKER).info.get('regularMarketPrice', 'N/A')
   ```
5. Create `passed.md` from template below
6. Confirm creation with price recorded

If UPDATE (`/thesis TICKER passed update`): append a new entry to the Passed Log table.

### Passed Template

```markdown
---
status: passed
ticker: {TICKER}
first_seen: {YYYY-MM-DD}
source: {info_source from Q1}
price_at_pass: {current_price}
tags: [passed, {sector}]
---

# Passed: {TICKER}

**Company:** {Full company name — look up via yfinance}
**Date:** {YYYY-MM-DD}
**Price at Pass:** ${price_at_pass}

---

## Source

| Field | Value |
|-------|-------|
| Info Source | {Q1 answer} |
| Source Detail | {optional detail from Q1} |

---

## Why I Passed

{Q2 answer — 1-3 sentences}

---

## Revisit Trigger

{Q3 answer — conditions under which to reconsider}

---

## Passed Log

| Date | Price | Note |
|------|-------|------|
| {YYYY-MM-DD} | ${price} | Initial pass — {brief reason} |

---

## Price Check (auto-updated by /review)

_This section will be populated by the monthly passed review._
```

### Example: Passed

```
User: /thesis TSLA passed

Claude: Recording a pass on TSLA.

        Q1: Where did you first see this idea?
        > [Social Media]

        Q2: Why are you passing?
        > Valuation too stretched at 80x forward. FSD revenue model
        > still unproven. Elon distraction risk from other ventures.

        Q3: Under what conditions would you revisit?
        > Stock drops >30% or FSD achieves Level 4 regulatory approval.

        Current price: $342.50

        Created: PORTFOLIO/research/companies/TSLA/passed.md
        Price recorded: $342.50 on 2026-02-07
```

### Example: Passed Update

```
User: /thesis TSLA passed update

Claude: Updating TSLA passed record.
        Current price: $285.00 (was $342.50 at initial pass, -16.8%)

        What's the update?
        > Dropped significantly but FSD still no Level 4. Watching.

        Added to Passed Log:
        2026-04-15 | $285.00 | Dropped 16.8% but FSD still no Level 4. Watching.
```

---

## 📌 Open Questions 展示

在 `/thesis TICKER view` 输出末尾，自动查询 `task_manager.py questions TICKER`，展示该 ticker 的未解决研究问题：

```markdown
## 📌 待解决的研究问题
来源: open_questions DB
1. [HIGH] 问题描述... (since 2026-02-09)
→ 建议: /research TICKER "具体问题"
```

如果没有 open questions，跳过此部分。

实现：
```bash
cd ~/.claude/skills && python shared/task_manager.py questions TICKER
```

---

## 🪞 反思检查站（自动追加）

在 `/thesis TICKER view` 和 `/thesis TICKER challenge` 输出末尾，自动追加 `shared/reflection_questions.yaml` 中的 7 个反思问题（R1-R7）。

Challenge 模式已有灵魂拷问机制，反思问题作为补充框架，确保覆盖 recency bias 和 position-induced bias。

---

## Key Files

- `research/companies/{TICKER}/thesis.md` - Active thesis document (markdown, detailed)
- `research/companies/{TICKER}/thesis.yaml` - Structured data (kill criteria, peers, conviction, sizing)
- `research/companies/{TICKER}/passed.md` - Why I Passed record
- `research/companies/{TICKER}/notes/` - Additional research notes
- `decisions/trades/*_{TICKER}.md` - Related trade logs

## thesis.yaml Schema

```yaml
ticker: TICKER
invalidation_price: 0         # Price-based stop (read by BiasEngine)
invalidation_window_days: 2
bear_case_1: "..."
bear_case_2: "..."
bull_case: "..."
horizon_days: 365
conviction: 4                  # 1-5 scale
target_weight_pct: 8
created_date: YYYY-MM-DD

# --- Phase 4: Idea Attribution (NLM-assisted) ---
idea_source: weekly-meeting    # substack/x/podcast/13f/supply-chain/weekly-meeting/chatgpt/self-research/other
source_detail: "投资观点周报 2025, 2025-12-15"
source_link: "[[2025-12-15 - 投资观点周报]]"
nlm_citation: "首次在 Week 50 讨论，初始情绪看多..."  # NLM verbatim citation
first_seen: 2025-12-15         # Date idea first appeared
first_position: 2026-02-01     # Date first trade was made (auto-filled by /trade)

kill_criteria:
  - condition: "Description of what would invalidate thesis"
    type: quantitative         # or qualitative
    threshold: "<50%"          # quantitative only
    status: active             # active / triggered / retired
    last_checked: YYYY-MM-DD
    check_result: pass         # pass / warning / fail / unchecked
    check_note: "Brief rationale for the assessment"

peers:
  - ticker: "BATS"
    relationship: "Global competitor"

supply_chain:
  - "Key regulatory/supply dependency"

quality_grade: "B"             # A/B/C based on KC clarity + data availability
```

## Framework Coverage Integration

### In Thesis Template

Add a `## Framework Coverage` section at the end of the thesis template, after Thesis Log:

```markdown
## 📐 Framework Coverage

| # | Section | Level | Key Source |
|---|---------|-------|-----------|
| S1 | 📈 Market & Growth | ✅ | earnings Q4, CAGNY |
| S2 | 🏟️ Competitive Landscape | ✅ | supply chain, earnings |
| ... | ... | ... | ... |

Score: 83% (7/9 covered) | Last scan: YYYY-MM-DD
Gaps: S5 管理层
```

### In thesis.yaml Schema

Add `framework_coverage` field:

```yaml
framework_coverage:
  score: 83
  last_scanned: 2026-02-07
  gaps: [S5]
  covered: [S1, S2, S3, S4, S6, S7, S8]
```

### Auto-Scan on Create

After creating a new thesis (step 4B), automatically run:
```bash
cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER --brief
```
Show the coverage result as a gap alert:
> "📐 Framework coverage: 45% — S3 护城河, S5 管理层, S6 估值, S7 风险 需要更多研究。
> 运行 `/research TICKER --deep` 可针对性填补盲区。"

### In `/thesis TICKER check`

Add framework coverage check after kill criteria check (step 4 in check workflow):
```bash
cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER --format json
```
If any section has degraded since last scan → flag it.
If `framework_coverage.last_scanned` is >30 days ago → suggest re-scan.

## Auto-Task Integration

### Staleness Alerts → Tasks
`scripts/thesis_staleness_check.py` (daily 08:30) automatically creates tasks for stale theses with new mentions:
```python
auto_create_task(
    f"Review stale thesis: {TICKER} ({days_stale} days)",
    source="thesis-stale", category="thesis", ticker=TICKER,
    priority=2, dedup_key=f"thesis-stale-{TICKER}-{today}"
)
```
These tasks appear in `/task list` and the daily brief.

### Post-Trade → Thesis Update Task
When `/trade` creates a task "Update thesis after BUY NVDA", `/thesis TICKER` is the natural follow-up.

## Integration with /trade

When a trade is logged via `/trade`, the thesis position history should be updated automatically if the thesis exists.
