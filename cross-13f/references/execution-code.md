# Execution

## Setup (all modes)

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
```

## Mode 1: Full Pipeline (group name argument)

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
- `result["consensus_buys"][:5]` -- most-held tickers with active buying
- `result["new_names"][:3]` -- 2+ managers initiated same ticker
- `result["research_triggers"][:2]` -- divergent (buyers + sellers)

Rank by **signal strength** (GROUP-DEPENDENT):
- **Biotech:** Rank by Fresh signal count, EQUAL-WEIGHT (BT-4: Fresh-EW > all)
- **TMT:** Rank by Fresh signal, CREDIBILITY-WEIGHTED (BT-4: Fresh-CW > all)
- **Energy:** Rank by Deep signal (tenure + position size), CREDIBILITY-WEIGHTED (BT-4: Deep-CW > all)

Display the screen results as a table:

| # | Ticker | Signal Type | Fresh Count | Breadth | Classification | Insider | Direction |
|---|--------|-------------|-------------|---------|----------------|---------|-----------|

Classification = CONSENSUS (3+ top-Q holders) or VARIANT (1-2 top-Q holders) or MIXED.
Insider column = Biotech only (from Stage 1.5 below). Shows "CFO buy", "C-suite", or blank.

**Stage 1.5: Insider Overlay (Biotech only)**

For Biotech group, fetch Form 4 insider signals for all screened tickers and append as overlay column.

```python
if group == "Biotech":
    from insider_signals import InsiderSignalFetcher

    fetcher = InsiderSignalFetcher()
    screened_tickers = [t["ticker"] for t in consensus_buys + new_names + variants]
    insider_data = fetcher.fetch_signals(screened_tickers)

    for ticker_result in stage1_results:
        signal = insider_data.get(ticker_result["ticker"])
        if signal and signal.signal_strength != "none":
            ticker_result["insider_signal"] = signal.signal_strength
            ticker_result["insider_detail"] = (
                f"CFO buy" if signal.cfo_buys else
                f"{signal.csuite_buys} C-suite" if signal.csuite_buys else ""
            )
        else:
            ticker_result["insider_signal"] = ""
            ticker_result["insider_detail"] = ""
```

Insider data also gets injected into per-ticker Obsidian notes (Stage 2) via `fetcher.format_obsidian_section(signal)`.

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

**Biotech** (Consensus-first, Fresh-signal, purity-filtered -- BT-4/5):
- Section 1: **Consensus Opportunities** (purity-filtered specialists, Fresh-ranked, EW, HIGHEST PRIORITY)
- Section 2: **Variant Opportunities** (supplementary, idiosyncratic bets)
- Section 3: **Per-ticker Manager Intelligence** (Fresh list first, credibility as badge only, insider overlay for Biotech)
- Section 4: **Research Agenda** (Consensus meetings first, then Variant)

**TMT** (Consensus-first, Fresh-signal -- BT-4/5):
- Section 1: **Consensus Opportunities** (screened tickers, Fresh-ranked, CW-Hybrid, HIGHEST PRIORITY)
- Section 2: **Variant Opportunities** (lower priority, supplementary)
- Section 3: **Per-ticker Manager Intelligence** (Fresh list first, credibility used for weighting)
- Section 4: **Research Agenda** (Consensus meetings first, then Variant)

**Energy** (Variant-first, Deep-signal -- BT-4/5, 12Q backtest):
- Section 1: **Variant Opportunities** (top-Q idiosyncratic bets, HIGHEST PRIORITY, flag high vol 18.4%)
- Section 2: **Consensus Opportunities** (screened tickers, Deep-ranked, CW)
- Section 3: **Per-ticker Manager Intelligence** (**Deep list first**, then Fresh for context, credibility used for weighting)
- Section 4: **Research Agenda** (Variant meetings first; prioritize long-tenure Deep holders for questions)

**Other groups** (no backtest data yet): Default to TMT rules (EW, Fresh-first, Consensus-first) until group-specific backtests are run.

## Mode 2: Single Ticker (ticker argument)

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

## Mode 3: Credibility Leaderboard (`credibility` subcommand)

```python
from pm_credibility import ManagerCredibilityScorer

scorer = ManagerCredibilityScorer()
results = scorer.score_group("Biotech", "2025-Q3")
print(scorer.format_results(results, "Biotech", "2025-Q3"))
scorer.save_obsidian(results, "Biotech", "2025-Q3")
# -> 研究/13F/credibility/Biotech_2025-Q3_credibility.md
```

## Key Classes and Methods

| Class | Method | Returns |
|-------|--------|---------|
| `GroupAnalyzer` | `.analyze(group, quarter)` | dict with consensus_buys, new_names, research_triggers |
| `PMRecommender` | `.recommend(ticker, quarter)` | `RecommendResult` with fresh_list, deep_list, all_holders |
| `PMRecommender` | `.save_obsidian(result)` | Path to saved file |
| `IntelligentQuestionGenerator` | `.generate_questions(result, top_n)` | list of `LLMQuestions` |
| `ManagerCredibilityScorer` | `.score_group(group, quarter)` | list of `CredibilityResult` |
