---
name: initiate
description: "Coverage Initiation Engine — Multi-AI, multi-phase equity research report for first coverage of a company. Use when user says 'initiate', 'initiate coverage', 'first coverage', 'coverage initiation', or wants a comprehensive 9-section CFA-level research report on a new ticker."
metadata:
  version: 0.1.0
---

# /initiate — Coverage Initiation Engine

Multi-phase, multi-AI coverage initiation pipeline. Produces a rigorous 9-section CFA-level equity research report.

## Usage

```
/initiate TICKER                    # Full coverage initiation
/initiate TICKER --fast             # Skip cross-validation
/initiate TICKER --refresh          # Force re-fetch data (ignore cache)
/initiate TICKER --review           # Pause after analysis for review
/initiate TICKER --no-email         # Skip email notification
/initiate rq TICKER                 # Answer [?] research questions (dual-AI)
/initiate rq TICKER --dry-run       # Preview prompt without sending
/initiate rq TICKER --gpt-only      # Skip Grok, GPT only
```

## Execution

### Full Pipeline

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  ~/.claude/skills/initiate/scripts/coverage_pipeline.py \
  TICKER [flags]
```

The script handles all phases: preflight → data collection → analysis → synthesis → output.

### Research Questions (Post-Report)

After reading a report, mark questions with `- [?] Your question here` anywhere in the file, then run:

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  ~/.claude/skills/initiate/scripts/research_questions.py \
  TICKER [--dry-run] [--file PATH] [--model MODEL] [--gpt-only]
```

- Sends all `[?]` questions to GPT o3 + Grok in parallel (~30s)
- Writes answers to file top (after frontmatter, before first heading)
- Marks answered questions `[?]` → `[x]`
- Supports multiple rounds: add new `[?]` questions and re-run
- Accepts informal markers (`? question`, `？question`) — auto-normalizes

## Architecture

### Phase 1: Data Collection (16 Perplexity queries + SEC + yfinance)
- **Industry** (4 queries): TAM per segment, growth decomposition, lifecycle/cyclicality, downturn/cycle
- **Competitive** (5 queries): Market share + HHI, share trends, pricing/ASPs, Porter's Five Forces, value chain
- **Moat** (3 queries): Unique assets/patents/brand, switching costs/network effects, economies of scale
- **Management** (1 query) + **Risks** (1 query) + **Catalysts** (2 queries): recent developments + upcoming events
- All 6 topic groups run in parallel via `asyncio.gather`
- SEC EDGAR (10-K annual + 10-Q quarterly XBRL, 8-K filings) + yfinance (price, financials, info)
- 7-day TTL cache in `runs/_cache/`

#### Sector-Aware Query Enhancement

After resolving the ticker's sector from `entity_dictionary.yaml` → `sector_metrics.yaml`:
1. Load `research_queries` from `sector_metrics.yaml[sector]` (4 sector-specific queries)
2. Add these as queries 17-20 in the data collection batch
3. These target the sector's canonical KPIs that generic queries may miss

**Example — Semiconductors:**
- Q17: "{TICKER} revenue by end market data center AI automotive industrial"
- Q18: "{TICKER} inventory levels days and channel inventory trends"
- Q19: "SEMI book to bill and wafer fab equipment spending"
- Q20: "{TICKER} competitive positioning process node technology roadmap"

### Phase 2A: Sections S1-S3 dual-model + S4-S7 single (10 parallel calls)
- S1-S3 → **BOTH Gemini AND GPT** in parallel (6 calls), then Claude merges best-of-both
- S4-S7 → Single provider: GPT (S4,S5,S7) / Gemini (S6)
- S1-S3 are **Knowledge-led** — model training knowledge is primary, data pack is supplementary
- S4-S7 are **Data-led** — SEC EDGAR + yfinance are primary sources

**S4 Sector Injection:**
When generating S4, prepend to the section prompt:
> "This is a {sector} company. In addition to standard financial analysis, specifically address these sector-canonical KPIs: {sector_kpis_list}. For each, provide: current value, trend, peer comparison, and forward outlook. Use the `beat_miss_guide` from sector_metrics.yaml as quality benchmarks."

### Phase 2A2: Claude Merge (3 parallel calls)
- For each of S1-S3, Claude synthesizes Gemini + GPT outputs into a unified section
- Resolves conflicts, picks stronger analysis per subsection, flags disagreements

### Phase 2B: Red Team (Grok)
- Adversarial review of all 7 merged sections, tags claims [DATA PACK]/[MODEL KNOWLEDGE]/[CONFLICT]

**Sector-Specific Red Team Checks:**
Include in the adversarial prompt:
> "Cross-check the following sector-specific claims against available data:
> - For Semiconductors: Are inventory and book-to-bill claims consistent with SEMI Association data?
> - For Consumer Staples: Are volume vs. pricing claims consistent with category scanner data?
> - For Financials: Are credit quality trends consistent with Fed/FDIC aggregate data?
> - For Healthcare: Are pipeline success probability assumptions realistic vs. industry base rates?"

### Phase 2C: Synthesis S8-S9 (Claude)
- Incorporates red team findings into final investment conclusion and research gaps

**Sector-Appropriate Valuation (S8):**
Use `sector_metrics.yaml[sector].valuation_methods` to determine:
- `primary`: Main valuation methodology for the target price
- `secondary`: Cross-check methodologies
- `peer_multiples`: Which multiples to include in the comps table

Example: For a SaaS company, primary = EV/NTM Revenue, with EV/ARR and P/FCF cross-checks.
For a bank, primary = P/TBV (ROTCE-adjusted), with P/E cross-check.

## Output

- Report: `研究/Coverage Initiation/{TICKER}/{YYYY-MM-DD HHMM} {TICKER} Coverage Initiation.md`
- Workspace: `~/.claude/skills/initiate/runs/{TICKER}_{TIMESTAMP}/`
