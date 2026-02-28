---
name: thesis
description: "Investment Thesis Manager - Create, view, and update investment thesis documents for portfolio positions. Use when user says 'thesis', 'kill criteria', '论文', or wants to create/view/update an investment thesis."
metadata:
  version: 1.0.0
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
/thesis {TICKER} set-status active|watching|past
```

**Examples:**
- `/thesis AAPL` - View or create thesis for AAPL
- `/thesis TSM update "Q4 beat, raising target"` - Add thesis log entry
- `/thesis PM check` - Check all kill criteria against latest data
- `/thesis NVDA passed` - Record why you passed on NVDA (creates passed.md)
- `/thesis NVDA passed update` - Update an existing passed record
- `/thesis CELH set-status past` - Change lifecycle status (active/watching/past)

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

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

**Status-Aware Display:** Read `thesis_status` from thesis.yaml (default: `watching`).

- **If `active`:** Run FULL workflow (all sub-steps below)
- **If `watching`:** SKIP sub-steps 3 (position fetch), 8 (sizing). Show note: "Status: WATCHING — not yet in portfolio"
- **If `past`:** SKIP sub-steps 3, 5 (48h violations), 6 (peers), 7 (13F), 8 (sizing). Show only KC summary (counts) and note: "Status: PAST — monitoring only. Changed: {status_changed_at}. Reason: {status_reason}"

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
   Sizing: conviction(4/High) × quality(B/1.0) = 5% × 1.5 × 1.0 = 7.5%
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
1.5. **Historical Failure Query (auto, before asking user):**
   - 查询该 ticker 的历史失误：
     ```bash
     /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
     import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills\shared')
     from jsonl_utils import query_jsonl
     from pathlib import Path
     failures = query_jsonl(Path.home() / '.claude' / 'data' / 'failures.jsonl', ticker='{TICKER}')
     for f in failures:
         print(f\"{f.get('created_at','?')[:10]} | {f.get('failure_type','?')} | {f.get('description','')[:100]}\")
     "
     ```
   - 也查询同类型失误（跨所有 ticker）以识别行为模式：
     ```bash
     /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
     import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills\shared')
     from jsonl_utils import read_jsonl
     from pathlib import Path
     from collections import Counter
     all_failures = read_jsonl(Path.home() / '.claude' / 'data' / 'failures.jsonl')
     types = Counter(f.get('failure_type','unknown') for f in all_failures)
     for t, c in types.most_common(5):
         print(f'{t}: {c}x')
     "
     ```
   - If ticker has prior failures → display warning:
     ```
     ⚠️ 历史教训: {TICKER} 有 {N} 条失误记录：
     | 日期 | 类型 | 描述 |
     |------|------|------|
     | 2025-08-01 | 追涨 | ... |
     ```
   - If common failure pattern found (e.g., "追涨" 3x across portfolio) → display:
     ```
     🔴 行为模式警告: 你有 {N} 次 "{failure_type}" 记录，建议在 kill criteria 中针对此模式设防。
     ```
   - If no failures found → skip silently (non-blocking)
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

### Step 4a: Sector-Aware KC Suggestions

Before prompting user for kill criteria, load sector templates:
1. Resolve sector: `entity_dictionary.yaml[TICKER].sector` → `sector_metrics.yaml` sector
2. Load `suggested_kill_criteria` from `shared/references/sector_metrics.yaml[sector]`
3. Present sector-suggested KCs as starting templates:

> **Suggested Kill Criteria for {sector}:**
> Based on sector framework (`shared/references/sector_metrics.yaml`):
> 1. {KC1 condition} — threshold: {threshold}, source: {data_source}
> 2. {KC2 condition} — threshold: {threshold}, source: {data_source}
> 3. {KC3 condition} — threshold: {threshold}, source: {data_source}
>
> Adopt, modify, or add custom KCs. At minimum 2 KCs required.

4. Pre-populate `data_source` and `expected_by` fields from the sector template
5. User can accept, modify, or reject any suggested KC

4.5. **Falsifiability Validation (auto)**
   For each kill criterion just defined, verify:
   - Can you name a **specific data source** where evidence would appear? (e.g., "10-Q filing", "monthly channel check", "earnings call")
   - Can you name a **specific timeframe** when you'd expect to see it? (e.g., "next quarterly earnings", "within 6 months")
   If either is missing, prompt: "This KC may be unfalsifiable. Consider: what data, from where, by when, would prove this wrong?"
   Record `data_source` and `expected_by` fields in thesis.yaml for each KC.

   When validating falsifiability, use sector_metrics.yaml `data_source` hints:
   - For each KC, verify the `data_source` is specific and available
   - Cross-check against sector_metrics.yaml suggested sources
   - Example: A Semiconductor KC about "inventory days" should cite "Balance sheet, earnings call" not just "quarterly filing"
5. Create thesis.md from template (include NLM attribution fields in frontmatter)
6. **Create thesis.yaml** with kill_criteria, peers, supply_chain, quality_grade, idea_source
7. Pre-fill with portfolio data if position exists

### 5. Update Subcommand

**Syntax:** `/thesis TICKER update "note"`

When updating a thesis with new information:

1. Read existing thesis.md and thesis.yaml
2. Ask structured questions (use AskUserQuestion):
   - **Data point:** What happened? (free text — the note from command)
   - **Thesis impact:** Which pillar does this affect? Options: [list pillars from thesis.yaml] + "None / General"
   - **Impact direction:** Strengthens ↑ / Neutral ↔ / Weakens ↓
   - **Action taken:** No change / Increase position / Trim / Exit / Add to watchlist
   - **Updated conviction:** 1-5 (show current conviction from thesis.yaml)
3. Append structured entry to thesis.md Thesis Log table:

| Date | Data Point | Pillar Affected | Impact | Action | Conviction |
|------|-----------|-----------------|--------|--------|------------|
| 2026-02-27 | Q4 beat, 22% growth | Revenue growth | ↑ Strengthens | No change | 4→4 |

4. Update thesis.yaml: `conviction`, `updated_date`
5. If impact direction is "Weakens" → suggest running `/thesis TICKER check` to verify kill criteria

### 6. Set-Status Subcommand

If `/thesis {TICKER} set-status STATUS`:

1. Validate STATUS is one of: `active`, `watching`, `past`
2. Read `thesis.yaml` → get current `thesis_status`
3. Update `thesis.yaml`:
   - `thesis_status: STATUS`
   - `status_changed_at: {today}`
   - `status_reason: "Manual override"`
4. Invalidate cache: `curl -s -X PUT http://localhost:8000/api/theses/{TICKER}/status -H "Content-Type: application/json" -d '{"status": "STATUS", "reason": "Manual override via /thesis"}'`
5. Confirm: "{TICKER} status: {old} → {new}"

## References

Detailed reference material — read as needed:
- Classification fields (Industry, Strategy, Driver, Info Source): `references/classification-fields.md`
- Thesis templates and example usage: `references/templates.md`
- Kill criteria, thesis challenge, passed workflow: `references/kill-criteria.md`
- Integration (files, schema, framework, auto-task, /trade): `references/integration.md`
