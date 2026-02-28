---
name: cross-13f
description: "Cross-13F Opportunity Screen + Manager Intelligence — Screen tickers across PM groups, identify managers to talk to, generate meeting questions. Use when user says 'cross-13f', 'screen tickers', 'PM meeting prep', or wants to compare fund manager holdings."
metadata:
  version: 1.0.0
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

**Biotech-specific flags:**
- `--purity 0.5` is the **default** for Biotech BT-5 (specialist >50% biotech allocation). Purity-filtered Consensus is highest priority.
- **Insider overlay** (Stage 1.5): Form 4 insider signals auto-appended for Biotech screens. CFO open-market buys are the strongest signal (Verdad hierarchy).

## Argument Detection

- **Group name:** Title-case word matching a known PM group (Biotech, Healthcare, TMT, etc.)
- **Ticker:** ALL-CAPS 1-5 character string (e.g., ABIVAX, MRNA, SGEN)
- **Subcommand:** `credibility` keyword before group name
- **Default quarter:** `2025-Q3` (override with `--quarter`)
- **Default LLM:** Enabled for full pipeline, disabled for single ticker (override with `--llm` / `--no-llm`)

## Backtest Rules (GROUP-SPECIFIC)

Rules differ by group -- **always check before applying.**

Quick summary: Biotech=EW+Consensus(purity)+Fresh, TMT=EW+Consensus+Fresh, Energy=CW+Variant+Deep.

Full rules and code: see `references/backtest-rules.md`

## Execution

For full execution code (3 modes), Python API, and class reference, see `references/execution-code.md`

## Output Locations

| Output | Path |
|--------|------|
| Group analysis report | `研究/13F/groups/{GROUP}/{QUARTER}_report.md` |
| Per-ticker recommender | `研究/13F/recommender/{TICKER}_{QUARTER}.md` |
| Cross-analysis summary | `研究/13F/cross-analysis/{GROUP}_{QUARTER}_opportunities.md` |
| Credibility leaderboard | `研究/13F/credibility/{GROUP}_{QUARTER}_credibility.md` |

## 13F Price Coverage Check

After running implied returns / cross-13f / pm-score, if any manager's price coverage <90%, proactively warn the user and ask whether to supplement. Common cause: foreign-registered companies (G/N/Y/H/M/B prefix CUSIP) listed on US exchanges but missing price data. Fix: yfinance supplement + security_master.json CUSIP mapping.

## Performance Notes

- Group analysis: ~5-15s depending on group size
- Per-ticker recommender: ~2-5s per ticker (scans all manager folders)
- LLM question generation: ~5-10s per ticker (Gemini + GPT in parallel)
- Full pipeline for 8 tickers with LLM: ~2-3 minutes

## Language

All output notes use 中文 for section headers and analysis. Table column names in English. Code/technical terms in English.
