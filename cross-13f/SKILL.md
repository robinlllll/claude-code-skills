---
name: cross-13f
description: Cross-13F Opportunity Screen + Manager Intelligence — Screen tickers across PM groups, identify managers to talk to, generate meeting questions
---

# Cross-13F: Opportunity Screen + Manager Intelligence

3-stage pipeline: **Screen tickers** -> **Identify managers** -> **Generate questions**

Workflow: "I have a bunch of bio hedge funds -> generate 5-10 tickers that indicate opportunity -> identify which managers to talk to -> what questions to ask"

## Project Location

`C:\Users\thisi\13F-CLAUDE`

## When to Use This Skill

- User wants to find investment opportunities across a group of fund managers
- User asks "what are the top picks" or "what's the consensus" in a sector
- User wants to know who to talk to about a specific ticker
- User asks for manager intelligence, meeting prep, or question generation
- User mentions cross-13F, group analysis, consensus buys, new names

## Syntax

```
/cross-13f Biotech                              # Full pipeline: screen -> top tickers -> managers -> questions
/cross-13f Biotech --quarter 2025-Q2            # Specific quarter
/cross-13f Biotech --no-llm                     # Skip LLM question generation (faster)
/cross-13f ABIVAX                               # Single ticker deep-dive (skip screening)
/cross-13f ABIVAX --llm                         # Single ticker + LLM questions
/cross-13f credibility Biotech                  # Credibility leaderboard only
```

## Argument Detection

- **Group name:** Title-case word matching a known PM group (Biotech, Healthcare, TMT, etc.)
- **Ticker:** ALL-CAPS 1-5 character string (e.g., ABIVAX, MRNA, SGEN)
- **Subcommand:** `credibility` keyword before group name
- **Default quarter:** `2025-Q3` (override with `--quarter`)
- **Default LLM:** Enabled for full pipeline, disabled for single ticker (override with `--llm` / `--no-llm`)

## Backtest Integration Rules (MANDATORY — GROUP-SPECIFIC)

Rules differ by group. Always check the group before applying.

### Universal Rules (all groups)

| Rule | Source | What to Do |
|------|--------|------------|
| **Top-Q identification** | BT-1: ρ=0.83 cred vs Sharpe | Compute top-quartile managers (top 25% by credibility; top-third for groups < 12 managers). Use them for consensus/variant classification. |
| **Signal purity** | BT-3: Q1 TE 17% vs Q4 24% | Tag managers with low tracking error as "high signal purity" — their position changes are more meaningful. |
| **Keep default weights** | BT-6: p>0.25 | Do not adjust credibility component weights. |
| **CN geo-discount** | BT-7: CN hit 50% vs US 57% | Zero out portfolio_pct bonus for CN_PM managers. Keep action signals (new/add/sell). |

**Note:** Fresh vs Deep priority is GROUP-SPECIFIC (not universal). Check the group rules below.

### Quick Reference: Group Rules Matrix

| Rule | Biotech | TMT | Energy |
|------|---------|-----|--------|
| **Signal priority** | Fresh > Deep | Fresh > Deep | **Deep > Fresh** |
| **Weighting** | EW (no cred) | CW-Hybrid | **CW (cred-weighted)** |
| **Section order** | Variant-first | Consensus-first | **Variant-first** |
| **Benchmark** | XBI | XLK | XLE |

### Biotech-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh Sharpe 2.44 vs Deep 1.01 | Prioritize Fresh list as primary signal. Deep is supplementary context. |
| **EW > CW** | BT-4: Sharpe 2.44 vs 1.01 | Do NOT weight or rank by credibility. Equal-weight ranking. Credibility is display-only badge. |
| **Variant > Consensus** | BT-5: +9.76%/qtr excess | Variant positions are HIGHEST PRIORITY. Surface as first section in output. |

### TMT-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-CW Sharpe 1.48 vs Deep-EW 1.46 | Fresh signal wins, but gap is smaller than Biotech. |
| **CW-Hybrid > EW** | BT-4: Sharpe 0.79 vs 0.61 | USE credibility (hybrid) to weight ticker ranking. Higher-credibility managers' signals count more. |
| **Consensus > Variant** | BT-5: +4.98% vs +1.59%/qtr | Consensus positions are HIGHEST PRIORITY. Surface as first section. Variant is lower priority. |

### Energy-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Deep > Fresh** | BT-4: Deep-CW +104% cumulative vs Fresh-EW +49% (12Q) | **OPPOSITE of Biotech/TMT.** Prioritize Deep list (longest tenure, heaviest position) as PRIMARY signal. Fresh list is secondary. |
| **CW > EW** | BT-4: CW adds ~0.55%/qtr over EW | USE credibility to weight ticker ranking. Deep-CW is the optimal Energy strategy. |
| **Variant > Consensus** | BT-5: +7.63% vs +1.14% excess/qtr | Variant positions are HIGHEST PRIORITY, but with HIGH VOLATILITY (18.4%). Surface Variant first, flag volatility risk. |
| **Deep-list display** | BT-4 Energy result | Show **Deep list FIRST** in per-ticker output (not Fresh). Tag Deep managers as primary signal. |

### How to Apply in Practice

**Stage 0 (before screening): Get top-quartile managers**

```python
from pm_credibility import ManagerCredibilityScorer
scorer = ManagerCredibilityScorer()
cred_results = scorer.score_group(group, quarter)
scores_sorted = sorted([r.credibility_score for r in cred_results], reverse=True)
q1_threshold = scores_sorted[len(scores_sorted) // 4]
top_q_managers = [r for r in cred_results if r.credibility_score >= q1_threshold]
```

**Variant scan: Find high-conviction idiosyncratic bets from top-Q managers**

```python
# For each top-Q manager, load holdings, find positions >3% weight
# Group by ticker: if only 1-2 top-Q managers hold it → VARIANT
# Biotech/Energy: these are HIGHEST PRIORITY (BT-5 Variant alpha)
# TMT: these are LOWER PRIORITY (BT-5 Consensus wins)
```

**Ticker ranking: GROUP-DEPENDENT**

```python
# Biotech: Fresh-signal priority, EQUAL-WEIGHT
#   1. Count Fresh actions equally (do NOT multiply by credibility)
#   2. Surface Variant tickers first, then Consensus

# TMT: Fresh-signal priority, CREDIBILITY-WEIGHTED (hybrid)
#   1. Weight Fresh actions by manager's hybrid credibility score
#   2. Surface Consensus tickers first, then Variant

# Energy: Deep-signal priority, CREDIBILITY-WEIGHTED
#   1. Rank by Deep score (tenure*20 + pct*15), weighted by credibility
#   2. Surface Variant tickers first, then Consensus
#   3. Fresh list is SECONDARY — show after Deep list in per-ticker output
```

Tag each ticker as CONSENSUS (3+ top-Q holders) or VARIANT (1-2 top-Q holders)

## Execution

### Setup (all modes)

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
```

### Mode 1: Full Pipeline (group name argument)

**Stage 0: Credibility + Top-Quartile Identification**

```python
from pm_credibility import ManagerCredibilityScorer

scorer = ManagerCredibilityScorer()
cred_results = scorer.score_group("Biotech", "2025-Q3")
scores_sorted = sorted([r.credibility_score for r in cred_results], reverse=True)
q1_threshold = scores_sorted[len(scores_sorted) // 4]
top_q = [r for r in cred_results if r.credibility_score >= q1_threshold]
print(f"Top-Q threshold: {q1_threshold}, {len(top_q)} managers")
```

**Stage 1: Screen tickers** via `group_analyzer.py`

```python
from group_analyzer import GroupAnalyzer, save_obsidian_report

analyzer = GroupAnalyzer()
result = analyzer.analyze("Biotech", "2025-Q3")

# Save group report to Obsidian
save_obsidian_report(result)  # -> 研究/13F/groups/Biotech/2025-Q3_report.md
```

Extract top 5-10 tickers by combining and deduplicating:
- `result["consensus_buys"][:5]` — most-held tickers with active buying
- `result["new_names"][:3]` — 2+ managers initiated same ticker
- `result["research_triggers"][:2]` — divergent (buyers + sellers)

Rank by **signal strength** (GROUP-DEPENDENT):
- **Biotech:** Rank by Fresh signal count, EQUAL-WEIGHT (BT-4: Fresh-EW > all)
- **TMT:** Rank by Fresh signal, CREDIBILITY-WEIGHTED (BT-4: Fresh-CW > all)
- **Energy:** Rank by Deep signal (tenure + position size), CREDIBILITY-WEIGHTED (BT-4: Deep-CW > all)

Display the screen results as a table:

| # | Ticker | Signal Type | Fresh Count | Breadth | Classification | Direction |
|---|--------|-------------|-------------|---------|----------------|-----------|

Classification = CONSENSUS (3+ top-Q holders) or VARIANT (1-2 top-Q holders) or MIXED.

**Stage 1b: Variant Position Scan**

Separately scan all top-Q manager holdings for Variant positions not captured by the group screen:

```python
from pathlib import Path
import json
from security_master import SecurityMaster

sm = SecurityMaster()
holdings_dir = Path(r'C:\Users\thisi\13F-CLAUDE\output')

ticker_holders = {}
for r in top_q:
    manager_dir = holdings_dir / r.cik
    quarter_files = sorted(manager_dir.glob("*.json"), reverse=True)
    if not quarter_files:
        continue
    with open(quarter_files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)
    for h in data.get('holdings', []):
        pct = h.get('portfolio_pct', 0)
        if pct < 3.0:
            continue
        ticker = sm.cusip_to_ticker(h.get('cusip', '')) or h.get('issuer_name', '')
        if ticker not in ticker_holders:
            ticker_holders[ticker] = []
        ticker_holders[ticker].append((r.manager_name, pct, r.credibility_score))

# Variant = 1-2 top-Q holders
variants = [(t, h, max(x[1] for x in h)) for t, h in ticker_holders.items() if 1 <= len(h) <= 2]
variants.sort(key=lambda x: x[2], reverse=True)
```

Display top 10-15 Variant positions as a separate table.

**Stage 2: Per-ticker manager intelligence** via `pm_recommender.py`

Run for BOTH the screened consensus tickers AND the top variant tickers.

```python
from pm_recommender import PMRecommender

rec = PMRecommender()
for ticker in top_tickers:
    result = rec.recommend(ticker, "2025-Q3")
    print(rec.format_result(result))
    rec.save_obsidian(result)  # -> 研究/13F/recommender/{TICKER}_{QUARTER}.md
```

Display per-ticker (GROUP-DEPENDENT order):
- **Biotech/TMT:** **Fresh list first** (primary signal per BT-4), then Deep list for context.
- **Energy:** **Deep list first** (primary signal per BT-4 Energy), then Fresh list for context.
Tag top-Q managers with badge.

**Stage 3: Question generation** via LLM (unless `--no-llm`)

Only generate LLM questions for tickers where PM meeting is actionable (typically top 4-5 by Fresh signal strength).

```python
from pm_recommender import IntelligentQuestionGenerator

gen = IntelligentQuestionGenerator()
for ticker_result in top_results:
    llm_questions = gen.generate_questions(ticker_result, top_n=3)
    # Prints 3 tiers: must_ask, explore, calibrate per manager
    print(gen.format_llm_questions(ticker_result, llm_questions))

    # Inject LLM questions into existing Obsidian file
    if llm_questions:
        llm_section = gen.obsidian_llm_section(llm_questions)
        obsidian_path = rec.save_obsidian(ticker_result)
        content = obsidian_path.read_text(encoding='utf-8')
        content = content.replace("## All Holders", llm_section + "\n## All Holders")
        obsidian_path.write_text(content, encoding='utf-8')
```

**Final output: Cross-analysis summary to Obsidian**

After all stages, generate a unified summary note at:
`研究/13F/cross-analysis/{GROUP}_{QUARTER}_opportunities.md`

Structure (GROUP-DEPENDENT section ordering):

**Biotech** (Variant-first, Fresh-signal — BT-4/5):
- Section 1: **Variant Opportunities** (top-Q idiosyncratic bets, HIGHEST PRIORITY)
- Section 2: **Consensus Opportunities** (screened tickers, Fresh-ranked, EW)
- Section 3: **Per-ticker Manager Intelligence** (Fresh list first, credibility as badge only)
- Section 4: **Research Agenda** (Variant meetings first, then Consensus)

**TMT** (Consensus-first, Fresh-signal — BT-4/5):
- Section 1: **Consensus Opportunities** (screened tickers, Fresh-ranked, CW-Hybrid, HIGHEST PRIORITY)
- Section 2: **Variant Opportunities** (lower priority, supplementary)
- Section 3: **Per-ticker Manager Intelligence** (Fresh list first, credibility used for weighting)
- Section 4: **Research Agenda** (Consensus meetings first, then Variant)

**Energy** (Variant-first, Deep-signal — BT-4/5, 12Q backtest):
- Section 1: **Variant Opportunities** (top-Q idiosyncratic bets, HIGHEST PRIORITY, flag high vol 18.4%)
- Section 2: **Consensus Opportunities** (screened tickers, Deep-ranked, CW)
- Section 3: **Per-ticker Manager Intelligence** (**Deep list first**, then Fresh for context, credibility used for weighting)
- Section 4: **Research Agenda** (Variant meetings first; prioritize long-tenure Deep holders for questions)

**Other groups** (no backtest data yet): Default to Biotech rules (EW, Fresh-first, Variant-first) until group-specific backtests are run.

### Mode 2: Single Ticker (ticker argument)

Skip Stage 1. Go directly to Stage 2 + optionally Stage 3.

```python
from pm_recommender import PMRecommender

rec = PMRecommender()
result = rec.recommend("ABIVAX", "2025-Q3")
print(rec.format_result(result))
rec.save_obsidian(result)  # -> 研究/13F/recommender/ABIVAX_2025-Q3.md
```

If `--llm` flag is present:
```python
from pm_recommender import IntelligentQuestionGenerator
gen = IntelligentQuestionGenerator()
llm_questions = gen.generate_questions(result, top_n=3)
print(gen.format_llm_questions(result, llm_questions))
```

### Mode 3: Credibility Leaderboard (`credibility` subcommand)

```python
from pm_credibility import ManagerCredibilityScorer

scorer = ManagerCredibilityScorer()
results = scorer.score_group("Biotech", "2025-Q3")
print(scorer.format_results(results, "Biotech", "2025-Q3"))
scorer.save_obsidian(results, "Biotech", "2025-Q3")
# -> 研究/13F/credibility/Biotech_2025-Q3_credibility.md
```

## Output Locations

| Output | Path |
|--------|------|
| Group analysis report | `研究/13F/groups/{GROUP}/{QUARTER}_report.md` |
| Per-ticker recommender | `研究/13F/recommender/{TICKER}_{QUARTER}.md` |
| Cross-analysis summary | `研究/13F/cross-analysis/{GROUP}_{QUARTER}_opportunities.md` |
| Credibility leaderboard | `研究/13F/credibility/{GROUP}_{QUARTER}_credibility.md` |

## Performance Notes

- Group analysis: ~5-15s depending on group size
- Per-ticker recommender: ~2-5s per ticker (scans all manager folders)
- LLM question generation: ~5-10s per ticker (Gemini + GPT in parallel)
- Full pipeline for 8 tickers with LLM: ~2-3 minutes

## Key Classes and Methods

| Class | Method | Returns |
|-------|--------|---------|
| `GroupAnalyzer` | `.analyze(group, quarter)` | dict with consensus_buys, new_names, research_triggers |
| `PMRecommender` | `.recommend(ticker, quarter)` | `RecommendResult` with fresh_list, deep_list, all_holders |
| `PMRecommender` | `.save_obsidian(result)` | Path to saved file |
| `IntelligentQuestionGenerator` | `.generate_questions(result, top_n)` | list of `LLMQuestions` |
| `ManagerCredibilityScorer` | `.score_group(group, quarter)` | list of `CredibilityResult` |

## Language

All output notes use 中文 for section headers and analysis. Table column names in English. Code/technical terms in English.
