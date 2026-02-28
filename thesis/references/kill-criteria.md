## Sector-Specific KC Templates

When creating or checking kill criteria, reference `shared/references/sector_metrics.yaml` for sector-canonical KC suggestions. Each sector has 3 pre-built KC templates with:
- `condition`: What would invalidate the thesis
- `type`: quantitative or qualitative
- `threshold`: Specific measurable trigger
- `data_source`: Where to find evidence

**Example — Semiconductors:**
1. Book-to-bill < 1.0 for 2 consecutive quarters (SEMI Association)
2. Inventory days > 150 with revenue growth decelerating (Balance sheet)
3. Data center/AI segment growth < 20% QoQ (Earnings supplement)

**Example — Consumer Staples:**
1. Volume decline > 3% for 2 consecutive quarters (Earnings call)
2. Market share loss > 200bps YoY (Nielsen/IRI scanner data)
3. Gross margin contracts > 200bps for 2Q without one-time explanation (Income statement)

Use these as starting points; always customize thresholds to the specific company's context.

---

### 6. Check Subcommand

**Syntax:** `/thesis TICKER check`

Review each kill criteria against the latest available information and update check_result + check_note in thesis.yaml.

**Workflow:**

1. Read `research/companies/{TICKER}/thesis.yaml` — extract kill_criteria list
2. For each criterion:
   - **Quantitative:** Search for latest data (web search, earnings analysis in Obsidian, NotebookLM history). Present the data and propose pass/warning/fail.
   - **Qualitative:** Present the condition and last check_note. Ask user for their current assessment (pass/warning/fail) and a brief note.
3. Update thesis.yaml with new `check_result`, `check_note`, and `last_checked` date
   - **Trend Assessment:** Compare current check_result + check_note with previous entry in `trend_history`.
     Ask: "Is this KC improving ↑, stable ↔, or deteriorating ↓ vs. last check?"
     Update `trend` field and append "{check_result}:{trend}" to `trend_history`.
     If trend == "deteriorating" for 2+ consecutive checks → flag: "⚠️ Sustained deterioration — consider upgrading to WARNING"
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
   Result: Pass (unchanged) | Trend: Stable ↔

2. FDA lowers PMTA barriers
   Last note: "PMTA process remains rigorous"
   Your assessment? [pass/warning/fail + note]

   ...

Summary: 5 checked | 4 pass | 1 warning | 0 fail | Trends: 3 stable, 1 improving, 1 deteriorating
Updated thesis.yaml
```

**Example:**
```
User: /thesis PM check
Claude: Checking 5 kill criteria for PM...

        1/5: ZYN US share <50% OR category <10% OR competitor +5pp [QT]
        Latest: ZYN share ~64% (Q4 2025), category +30% YoY
        -> Pass (no change) | Trend: Stable ↔

        2/5: FDA lowers PMTA barriers [QL]
        Last check (2026-02-07): "PMTA process remains rigorous"
        Any update? [pass]
        -> Pass | Trend: Stable ↔

        ...

        Summary: 5/5 pass, 0 warnings, 0 fails | Trends: 4 stable, 1 improving, 0 deteriorating
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
