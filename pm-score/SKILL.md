---
name: pm-score
description: PM Performance Scoring Pipeline — Run implied returns, stock-level skill, performance scoring, and hybrid credibility for any industry group
---

# PM Performance Scoring Pipeline

Full pipeline: **Implied Returns** -> **Stock-Level Skill** -> **Performance Scorer** -> **Hybrid Credibility**

Scores fund managers on sector-relative implied performance (vs XBI/XLK/SPY) and blends with behavioral credibility scores using conditional alpha weighting.

## Project Location

`C:\Users\thisi\13F-CLAUDE`

## When to Use This Skill

- User wants to score/rank managers in any group (Biotech, TMT, Healthcare, etc.)
- User asks about manager performance, implied returns, stock picking skill
- User wants to refresh or generate performance scores for a group
- User mentions "score managers", "pm score", "performance pipeline", "hybrid credibility"
- User adds new managers to a group and wants to generate scores

## Syntax

```
/pm-score Biotech                    # Full pipeline for Biotech (all quarters)
/pm-score TMT                        # Full pipeline for TMT
/pm-score Healthcare                  # Full pipeline for Healthcare
/pm-score Biotech --step implied      # Only run implied returns
/pm-score Biotech --step skill        # Only run stock-level skill
/pm-score Biotech --step perf         # Only run performance scorer
/pm-score Biotech --step credibility  # Only run hybrid credibility
/pm-score status                      # Show which groups have scores
/pm-score Biotech --quarters 2024-Q1,2024-Q2,2024-Q3  # Specific quarters
```

## Available Groups

| Group | Managers | Benchmark | Status |
|-------|----------|-----------|--------|
| Biotech | 26 | XBI | Active (13 quarters scored) |
| TMT | 50 | XLK | Active (9 quarters scored) |
| Healthcare | 13 | XBI | Ready (needs pipeline run) |
| Generalist | 27 | SPY | Ready (needs pipeline run) |
| Financials | 5 | XLF | Ready (needs pipeline run) |
| Energy | 6 | XLE | Ready (needs pipeline run) |
| CN_PM | 17 | SPY | Ready (needs pipeline run) |

## Argument Detection

- **Group name:** Title-case word matching a PM group (Biotech, TMT, Healthcare, Generalist, Financials, Energy, CN_PM)
- **`--step`:** Run only one pipeline step (implied, skill, perf, credibility)
- **`--quarters`:** Comma-separated quarter list (default: `--all-quarters`)
- **`status`:** Show which groups have output files

## Prerequisites Check

Before running the pipeline, verify data exists:

```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
from pm_group_manager import PMGroupManager
from pm_backtest import _get_available_quarters_for_group

gm = PMGroupManager()
members = gm.get_all_members("<GROUP>")
quarters = _get_available_quarters_for_group(gm, "<GROUP>")
print(f"Members: {len(members)}, Quarters on disk: {len(quarters)}")
```

If managers have < 4 quarters on disk, run Phase 1 first:
```bash
cd C:\Users\thisi\13F-CLAUDE
python batch_historical_download.py
```

If price data is missing for benchmark ETFs, run Phase 2:
```bash
python expand_price_data.py
```

## Full Pipeline Execution

Python path: `/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe`
Working directory: `C:\Users\thisi\13F-CLAUDE`

### Step 1: Implied Returns (Phase 3)

Computes sector-relative portfolio returns per manager per quarter.

```bash
python implied_returns.py --group <GROUP> --all-quarters
```

- Input: Holdings data (`output/{MANAGER}/{QUARTER}/full_data_*.json`) + price data (`output/_price_data.csv`)
- Output: `output/_implied_returns_{group}.json`
- Metrics: EW/MW portfolio return, sector alpha (vs benchmark), SPY return
- Runtime: ~30-60s per group

### Step 2: Stock-Level Skill (Phase 3b)

Measures whether a manager's fresh picks (new positions, large adds >50%) outperform the sector benchmark.

```bash
python stock_level_skill.py --group <GROUP> --all-quarters --save
```

- Input: Same as Step 1
- Output: `output/_stock_level_skill_{group}.json`
- Metrics: Stock hit rate, average alpha per pick, pick count
- **IMPORTANT:** Must use `--save` flag to write JSON output
- Runtime: ~30-60s per group

### Step 3: Performance Scorer (Phase 4)

Combines 3 metrics with Empirical Bayes shrinkage into a single performance score (0-100).

```bash
python performance_scorer.py --group <GROUP>
```

- Input: `output/_implied_returns_{group}.json` + `output/_stock_level_skill_{group}.json`
- Output: Console display + used by credibility scorer
- Metrics: Information Ratio, Hit Rate, Stock Hit Rate
- Shrinkage: `w = N_quarters / (N_quarters + 8)` toward group mean (50.0)
- Runtime: <5s

### Step 4: Hybrid Credibility (Phase 5)

Blends behavioral credibility (5 metrics) with performance score using conditional alpha.

```bash
python pm_credibility.py --group <GROUP> --quarter <LATEST_QUARTER> --obsidian
```

- Formula: `Final = α × Behavioral + (1-α) × Performance`
- Alpha: `α = max(0, 1 - (N_quarters - 3) / 12)`
  - N < 3: pure behavioral (α = 1.0)
  - N = 9: 50/50 blend (α = 0.5)
  - N ≥ 15: pure performance (α = 0.0)
- **Veto Gate:** If performance_score < 30, cap final score at 50
- Output: `研究/13F/credibility/{GROUP}_{QUARTER}_credibility.md`

## Running the Full Pipeline (Recommended)

For a full pipeline run, execute steps 1-4 sequentially. Use subagents for steps 1+2 in parallel since they're independent:

```python
import sys, subprocess
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')

PYTHON = r'/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe'
GROUP = "<GROUP>"

# Step 1 + 2 can run in parallel (both read from holdings + prices)
# Step 1: Implied Returns
subprocess.run([PYTHON, 'implied_returns.py', '--group', GROUP, '--all-quarters'], cwd=r'C:\Users\thisi\13F-CLAUDE')

# Step 2: Stock-Level Skill
subprocess.run([PYTHON, 'stock_level_skill.py', '--group', GROUP, '--all-quarters', '--save'], cwd=r'C:\Users\thisi\13F-CLAUDE')

# Step 3: Performance Scorer (reads output from steps 1+2)
subprocess.run([PYTHON, 'performance_scorer.py', '--group', GROUP], cwd=r'C:\Users\thisi\13F-CLAUDE')

# Step 4: Hybrid Credibility + Obsidian
subprocess.run([PYTHON, 'pm_credibility.py', '--group', GROUP, '--quarter', '2025-Q3', '--obsidian'], cwd=r'C:\Users\thisi\13F-CLAUDE')
```

**When using subagents:** Launch Step 1 and Step 2 as parallel subagents. Wait for both to complete. Then run Step 3 and Step 4 sequentially.

## `status` Subcommand

Check which groups have scored data:

```python
import sys
from pathlib import Path
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')

output = Path(r'C:\Users\thisi\13F-CLAUDE\output')
for group in ['biotech', 'tmt', 'healthcare', 'generalist', 'financials', 'energy', 'cn_pm']:
    ir = output / f'_implied_returns_{group}.json'
    sl = output / f'_stock_level_skill_{group}.json'
    status = []
    if ir.exists():
        import json
        with open(ir, encoding='utf-8') as f:
            data = json.load(f)
        n_mgrs = len(data.get('managers', {}))
        n_qtrs = len(data.get('quarters', []))
        status.append(f"IR: {n_mgrs} mgrs × {n_qtrs} qtrs")
    if sl.exists():
        status.append("StockSkill: yes")
    if not status:
        status.append("not scored")
    print(f"{group.upper():15s} {' | '.join(status)}")
```

## Output Files

| File | Content |
|------|---------|
| `output/_implied_returns_{group}.json` | Per-manager per-quarter EW/MW returns + sector alpha |
| `output/_stock_level_skill_{group}.json` | Per-manager stock picking accuracy (hit rate, alpha) |
| `output/_performance_scores.json` | Aggregated performance scores (if --save used) |
| `研究/13F/credibility/{GROUP}_{QUARTER}_credibility.md` | Obsidian report with hybrid leaderboard |

## Benchmark Mapping

Benchmarks are defined in `implied_returns.py` and `stock_level_skill.py`:

```python
GROUP_BENCHMARKS = {
    "Biotech": "XBI",
    "Healthcare": "XBI",
    "TMT": "XLK",
    "Financials": "XLF",
    "Energy": "XLE",
    "Real_Estate": "XLRE",
    "Consumer": "XLY",
}
DEFAULT_BENCHMARK = "SPY"  # fallback for Generalist, CN_PM, etc.
```

To add a new benchmark: update both `GROUP_BENCHMARKS` dicts in `implied_returns.py` and `SECTOR_BENCHMARKS` in `stock_level_skill.py`, then ensure the ETF ticker exists in `output/_price_data.csv` (run `expand_price_data.py` if needed).

## Key Metrics Explained

| Metric | Description | Minimum Data |
|--------|-------------|-------------|
| **Information Ratio** | mean(alpha) / std(alpha) — consistency of outperformance | 6 quarters |
| **Hit Rate** | % of quarters with positive sector alpha | 4 quarters |
| **Stock Hit Rate** | % of fresh picks (new/large adds) that beat sector benchmark | 10 picks |
| **Shrinkage** | Pulls extreme scores toward group mean for managers with less data | κ=8 |
| **Veto Gate** | Performance < 30 → cap hybrid score at 50 | Always applies |

## Adding a New Group

1. Add CIKs to `pm_groups.yaml` under the appropriate group key
2. Download historical 13F data: `python batch_historical_download.py`
3. Expand price data if needed: `python expand_price_data.py`
4. Run `/pm-score <NewGroup>` — executes the full 4-step pipeline
5. Results appear in Obsidian under `研究/13F/credibility/`

## Troubleshooting

### "No data found for group"
- Check `pm_groups.yaml` — are CIKs listed under the group?
- Run `python downloader.py` to download latest filings

### "No price data for XYZ"
- Run `python expand_price_data.py` to fetch missing tickers
- Check `output/_price_download_failures.json` for delisted tickers

### Low coverage warnings
- Coverage < 70% means many CUSIPs couldn't be resolved to tickers
- Check `output/_cusip_unresolved.json` for unresolved CUSIPs
- Run `python cusip_resolver.py` to resolve via OpenFIGI

### Performance scorer returns all 50.0
- Check that group-specific files exist: `_implied_returns_{group}.json`
- Files from different groups overwrite each other if using old generic names
