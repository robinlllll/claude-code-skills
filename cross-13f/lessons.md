# Lessons Learned

## 2026-02-12 | 2026-02-12: Q4 early filer analysis
- GroupAnalyzer returns EMPTY consensus_buys/sells when coverage < ~30% (breadth thresholds don't trigger). For thin coverage, do manual aggregate analysis directly from full_data JSON files.
- full_data JSON structure: 'latest_holdings' (not 'holdings'), 'sold_positions' at top level. Holdings have 'portfolio_pct', 'share_change_pct' (can be None), 'is_new', 'issuer_name', 'cusip'.
- CredibilityResult uses 'name' not 'manager_name'.
- DigitalBridge (CIK 1679688) has 165 holdings with many sub-entity duplicates (same stock 3-4x). Need to aggregate.
- Proem Advisors Q4 filing has ALL positions marked NEW — likely first-time 13F filer. Treat with caution.
- Candlestick Capital Q4: 0 holdings (liquidated 49 positions). Exclude from sell signals.
- Summit Partners: PE holdings (Klaviyo 58%). Not actionable for HF signals. Exclude from screening.
- CN_PM geo-discount: behavioral scoring works without implied_returns (warning only, not error).
- Encoding: use io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') for Windows Python output with unicode.

## 2026-02-17 | 2026-02-17: Q4 full pipeline run. GroupAnalyzer returns dicts (not dataclasses) for consensus_buys/new_names/research_triggers. new_names uses initiators (int) and actions (list of dicts). research_triggers uses buyers/sellers as lists (not int counts). Recommendation dataclass: holding.portfolio_pct (not .portfolio_pct), .template (not .question_type), holding.first_quarter_owned for tenure. 23/26 Biotech managers filed Q4 (missing: Great Point, Orbimed, Janus Henderson). Checkpoint Capital only 7 holdings (ultra-concentrated). ABVX is the only Consensus High-Conviction name (4 top-Q holders >3% each).

## 2026-02-18 | 2026-02-18: Full 9-group pipeline run with Phase 3 backtest rules
- All 9 groups now have group-specific backtest rules in references/backtest-rules.md (was only 3: Biotech/TMT/Energy)
- Updated rules matrix: Fresh-EW (Biotech, CN_PM, TMT, Generalist), Fresh-CW (Healthcare, Consumer), Deep-EW (Financials, Real_Estate), Deep-CW (Energy)
- BT-5 Consensus/Variant: 5 Consensus (TMT, Healthcare, Generalist, Consumer, Real_Estate), 4 Variant (Biotech, CN_PM, Financials, Energy)
- Phase 3 flipped 3 groups vs behavioral-only: CN_PM to Variant, Generalist to Consensus, Real_Estate to Consensus
- Full pipeline (Stage 0+1+2 for 9 groups) best run as 3 parallel subagents of 3 groups each. Total time ~10min.
- GroupAnalyzer returns dicts not dataclasses. consensus_buys/new_names/research_triggers are lists of dicts.
- PMRecommender.recommend() and .save_obsidian() work per-ticker. Run top 8 tickers per group for Stage 2.
- Output: 9 individual opportunity reports at cross-analysis/{GROUP}_2025-Q3_opportunities.md + unified ALL_GROUPS report + ~72 per-ticker recommender notes
- Financials (5 members) and Real_Estate (10 members, Sharpe 0.58) have weakest signals. Flag caveats prominently.
- Energy Goodlander concentration: 11-position portfolio, single-manager variant picks can dominate (BE +253%, WULF +161% in Q3 2025).

## 2026-02-25 | Verdad purity filter + insider overlay implementation
- **BT-5 purity filter flips Biotech from Variant→Consensus.** With `--purity 0.5` (specialist >50% biotech allocation), Consensus excess +12.84%/qtr vs Variant +1.73%. Robust across trimming (Trim-2 Sharpe 1.64 vs 0.45, win rate 75%).
- **Even without purity filter**, Variant's mean edge is a "mean-driven illusion" — median (+3.37% vs +0.62%) and win rate (67%) favor Consensus. Extreme quarters (2023-Q1 +37%, 2025-Q2 +44%) inflate Variant's average.
- **Expanded group (Healthcare crossovers) provides <1% marginal improvement.** Not worth the complexity. Default: purity only, no expanded.
- **Biotech universe construction via SIC codes:** SEC EDGAR SIC codes 2833-2836 are the anchor. data.sec.gov DNS can fail — code needs graceful fallback to cached universe.
- **Lazy imports required:** Project linter strips unused top-level imports. Use `import yaml` / `from sec_client import SECClient` inside method bodies.
- **insider_signals.py:** Form 4 XML parsing works but SEC rate limits aggressively. 0.15s sleep between requests. Cache with 7-day TTL at `output/_insider_cache.json`.
- **Verdad insider hierarchy:** CFO open-market buys (+40 score) > C-suite (+20 each, max +60) > Board (ignored) > CEO (=noise). Filter out 10b5-1 planned trades via footnote detection.
- **Form 4 XML fetch bug (fixed):** `primary_document` field is often `xslF345X05/form4.xml` (XSLT-rendered HTML), not the raw XML. Fix: strip prefix and fetch bare filename `form4.xml` at the accession root. Without this fix, all XML fetches silently fail (no `<ownershipDocument>` in HTML response) → every ticker scores 0.
- **Title normalization gap (fixed):** Original regex only matched specific C-suite titles (COO, CTO, CMO, CSO, CCO). Missed "Chief Strategy Officer", "Chief Legal Officer", "Chief People Officer", etc. Fix: use `chief\s+\w+` pattern instead. Order matters — CFO and CEO regexes are checked first so they still match before the generic `chief` pattern.
- **Live test results:** Large-cap biotechs (MRNA, IONS, ALNY) are almost exclusively insider selling (options exercise). CFO buying is genuinely rare — SAVA was the only hit in 8 tickers tested (CSUITE buy, score=20). This confirms Verdad's thesis that CFO purchase is an anomaly signal.
