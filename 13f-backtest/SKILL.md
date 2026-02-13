---
name: 13f-backtest
description: 13F Backtest Suite — Run BT-1 through BT-6 backtests for PM credibility, Fresh vs Deep signals, consensus vs variant, and weight optimization
---

# 13F Backtest Suite

Run and manage 6 backtests that validate the PM Group Intelligence system.

## Project Location

`C:\Users\thisi\13F-CLAUDE`

## When to Use This Skill

- User wants to run backtests on 13F manager data
- User mentions BT-1, BT-2, ..., BT-6
- User asks about credibility validation, signal testing, or weight optimization
- User wants to check if backtest data is ready
- User wants to see latest backtest results

## Syntax

```
/13f-backtest run all                           # Run BT-1 through BT-6
/13f-backtest run bt3                           # Single backtest
/13f-backtest run bt4 --quarter 2025-Q2         # Specific quarter
/13f-backtest check                             # Verify data prerequisites
/13f-backtest status                            # Show latest results from Obsidian
/13f-backtest synthesis                         # Regenerate synthesis report
```

## Backtest Inventory

| Test | Name | What It Tests | Module | Runtime |
|------|------|---------------|--------|---------|
| BT-1 | Credibility vs NAV | Correlation between credibility score and fund NAV performance | `bt1_credibility_nav.py` (standalone) | ~30s |
| BT-2 | NAV Bonus Sensitivity | Impact of NAV bonus parameter on credibility accuracy | `bt2_nav_bonus_sensitivity.py` (standalone) | ~30s |
| BT-3 | Implied vs NAV Returns | 13F implied portfolio vs actual fund NAV tracking error | `pm_backtest.py: BT3ImpliedVsNAV` | ~40s |
| BT-4 | Fresh vs Deep Signals | Forward returns of Fresh-scored vs Deep-scored portfolios | `pm_backtest.py: BT4FreshVsDeep` | ~60s |
| BT-5 | Consensus vs Variant | Returns of widely-held vs idiosyncratic high-conviction positions | `pm_backtest.py: BT5ConsensusVsVariant` | ~30s |
| BT-6 | Weight Optimization | Grid search over credibility component weights | `pm_backtest.py: BT6WeightOptimization` | ~180s |

## Execution

### Setup (all modes)

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
```

### `run` subcommand

**Single backtest (BT-3 through BT-6):**

```python
from pm_backtest import (
    BT3ImpliedVsNAV, BT4FreshVsDeep, BT5ConsensusVsVariant,
    BT6WeightOptimization, check_data_ready,
    save_obsidian_bt3, save_obsidian_bt4, save_obsidian_bt5, save_obsidian_bt6,
)

# Example: BT-4
bt4 = BT4FreshVsDeep()
results = bt4.run("2025-Q3")
print(bt4.format_results(results))
save_obsidian_bt4(results)  # -> 研究/13F/backtest/BT4_fresh_vs_deep.md
```

**BT-1 and BT-2 (standalone scripts):**

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/13F-CLAUDE/bt1_credibility_nav.py
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/13F-CLAUDE/bt2_nav_bonus_sensitivity.py
```

**`run all`:**

For maximum efficiency, launch parallel subagents:
1. **Subagent 1:** Run BT-1 + BT-2 (bash commands, sequential)
2. **Subagent 2:** Run BT-3 (Python)
3. **Subagent 3:** Run BT-4 (Python, longest running)
4. **Subagent 4:** Run BT-5 (Python)
5. **Main context:** Run BT-6 last (depends on price data being loaded; longest)

Each subagent should:
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
# ... run the specific backtest, print results, save to Obsidian
```

After all complete, generate synthesis report.

### `check` subcommand

```python
from pm_backtest import check_data_ready
ready = check_data_ready()
# Prints diagnostics: price data, manager count, quarters available, NAV data
```

### `status` subcommand

Read the latest Obsidian backtest files and display a summary table.

Files to check:
- `研究/13F/backtest/BT3_implied_vs_nav.md`
- `研究/13F/backtest/BT4_fresh_vs_deep.md`
- `研究/13F/backtest/BT5_consensus_vs_variant.md`
- `研究/13F/backtest/BT6_weight_optimization.md`

For each file that exists:
1. Read frontmatter (type, test, generated date, observations)
2. Extract key metrics from content
3. Display summary table:

| Test | Last Run | Key Metric | Decision |
|------|----------|------------|----------|

### `synthesis` subcommand

Read all BT results from Obsidian and generate a unified synthesis report at:
`研究/13F/backtest/backtest_synthesis_biotech.md`

Structure:
1. **Executive Summary** — One-paragraph findings
2. **Results Table** — All 6 tests, key metrics, pass/fail
3. **Credibility Validation** — Does credibility predict performance? (BT-1, BT-3)
4. **Signal Comparison** — Fresh vs Deep, EW vs CW (BT-4)
5. **Position Sizing** — Consensus vs Variant (BT-5)
6. **Weight Recommendation** — Optimal weights vs default (BT-6)
7. **Limitations & Blindspots** — 13F-only coverage, survivorship bias, short history

## Key Classes and Methods

| Class | Method | Returns |
|-------|--------|---------|
| `BT3ImpliedVsNAV` | `.run(quarter)` | list of `BT3Result` |
| `BT4FreshVsDeep` | `.run(quarter)` | list of `BT4PortfolioResult` |
| `BT5ConsensusVsVariant` | `.run(quarter)` | list of `BT5Result` |
| `BT6WeightOptimization` | `.run(quarter)` | list of `BT6WeightVector` |
| (module-level) | `check_data_ready()` | bool |
| (module-level) | `save_obsidian_bt3/4/5/6(results)` | Path |

## Output Locations

| Output | Path |
|--------|------|
| BT-3 results | `研究/13F/backtest/BT3_implied_vs_nav.md` |
| BT-4 results | `研究/13F/backtest/BT4_fresh_vs_deep.md` |
| BT-5 results | `研究/13F/backtest/BT5_consensus_vs_variant.md` |
| BT-6 results | `研究/13F/backtest/BT6_weight_optimization.md` |
| Synthesis | `研究/13F/backtest/backtest_synthesis_biotech.md` |

## Data Prerequisites

Run `check` first. Requirements:
- `output/_price_data.csv` — Historical stock prices (from `bt0_data_acquisition.py`)
- `output/_cusip_ticker_map.json` — CUSIP to ticker mapping
- At least 2 quarters of 13F data for Biotech group members
- `biotech_nav_summary.json` — NAV data for BT-1/BT-3 (optional but recommended)

If data is missing, run Phase 0:
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/13F-CLAUDE/bt0_data_acquisition.py
```

## Performance Notes

- Price data load: ~3s (2.3M rows, pre-indexed by ticker)
- BT-3: ~40s, BT-4: ~60s, BT-5: ~30s, BT-6: ~180s
- `run all` with parallel subagents: ~4 minutes total
- BT-1/BT-2 are fast standalone scripts (~30s each)

## Language

All Obsidian output in English (backtests are technical/quantitative). Analysis summaries may include 中文 annotations where relevant.
