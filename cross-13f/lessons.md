# cross-13f lessons

## 2026-02-10: Canonical tickers vs market tickers
- GroupAnalyzer returns canonical names from SecurityMaster (e.g., BRIDGEBIO, IMMUNOVANT, NEKTAR, UNIQURE)
- These are NOT the standard market tickers (BBIO, IMVT, NKTR, QURE)
- PMRecommender resolves canonical names correctly — pass them directly, don't convert to market tickers
- Only exception: ABIVAX works as both canonical and market ticker

## 2026-02-10: Performance
- Full pipeline (21 managers, 8 tickers, 4 with LLM): ~5 minutes total
- Stage 1 (GroupAnalyzer): ~5s
- Stage 2 (8x PMRecommender): ~30s sequential, could parallelize
- Stage 3 (4x LLM dual-model): ~3 minutes (Gemini + GPT in parallel per ticker)
- LLM is the bottleneck; use --no-llm for quick screens

## 2026-02-10: BT-7 CN Manager Geo-Discount
- CN_PM managers' portfolio_pct in 13F reflects only US equity sleeve, not total AUM
- BT-7 tested discount factors 0.0→1.0 on forward returns (Oct-Dec 2025, 3,114 signals)
- CN fresh hit rate 50.0% vs US 56.7% — direction signals weaker
- CW portfolio return monotonically decreases with CN weight (d=0.0: +10.54%, d=1.0: +9.75%)
- **Conclusion: GEO_DISCOUNT_FACTOR = 0.0** — zero out position-size bonus, keep action signals (new/add/sell)
- Applied in both pm_recommender.py and group_analyzer.py
- CN_PM group defined in pm_groups.yaml (17 members)
- Aspex (HK) and MayTech are Asia-based but NOT in CN_PM — monitor separately

## 2026-02-10: MUST apply backtest findings (GROUP-SPECIFIC)
- The pipeline must ALWAYS incorporate backtest findings — but rules differ by group!
- BT-1: Top-quartile threshold = top 25% by credibility score
- Fresh vs Deep is GROUP-SPECIFIC (NOT universal): Biotech/TMT = Fresh first, Energy = Deep first

### Biotech-specific rules:
- BT-4: EW > CW (Sharpe 2.44 vs 1.01) → do NOT weight by credibility. Credibility is display-only badge
- BT-5: Variant > Consensus (+3.2%/qtr alpha) → scan variant positions separately, surface as highest-priority section
- Variant positions are NOT captured by GroupAnalyzer screen — must do a separate holdings scan
- Caligan Partners has the most differentiated portfolio (6 variant names in top-10)
- ABIVAX is the only ticker that qualifies as CONSENSUS among top-Q managers

### TMT-specific rules (2026-02-11 backtest):
- BT-4: CW-Hybrid > EW (Sharpe 0.79 vs 0.61) → USE credibility weighting for TMT ticker ranking
- BT-4 Fresh vs Deep: Fresh-CW Sharpe 1.48 > Deep-EW 1.46 > Deep-CW 1.42 > Fresh-EW 1.40
  - Fresh > Deep confirmed for TMT (excess +4.69% vs +3.73%), but gap smaller than Biotech
  - Fresh-CW is the optimal TMT strategy (CW weighting + Fresh signal selection)
  - Fresh wins 5/8 quarters; Deep wins in down-markets (2024-Q3 drawdown)
- BT-5: Consensus > Variant (+4.98% vs +1.59%/qtr) → prioritize consensus screen, variant is lower priority
- Top-Q overlap (behavioral vs hybrid): only 65% — hybrid scoring materially changes TMT rankings
- Hybrid scoring adds more value for TMT because more performance data is available (longer track records)

## 2026-02-11: TMT cross-13f execution
- TMT has 50 managers (vs 26 Biotech) — GroupAnalyzer and variant scan both produce much more data
- TMT top-Q threshold: 60.6 (13 managers), lower spread than Biotech due to hybrid scoring compressing range
- GroupAnalyzer `new_names` has different structure than `consensus_buys`: `actions` is a list not dict, count field is `initiators`
- For TMT, pass ticker symbols directly to PMRecommender (MDB, SNPS, etc.) — they're already market tickers unlike Biotech canonical names
- Exception: Alphabet must be passed as "Alphabet Inc" (canonical name) — GOOGL resolves but saves as "ALPHABET INC"
- Light Street Capital appears across 6/10 screened tickers — highest cross-coverage manager for TMT meetings
- Strategy Capital has extremely concentrated positions (AXON 20.5%, SHOP 17.9%, NET 16.5%) — outlier conviction
- Appaloosa LP (David Tepper) has 15.6% BABA held 12Q — deep macro conviction on China TMT not in typical TMT group
- Running 10 PMRecommender calls in 2 parallel batches (5 each) takes ~40s vs ~100s sequential
- Hybrid credibility badges now show in all recommender output — score_dict() auto-loads all group perf data

### Energy-specific rules (2026-02-11 backtest):
- BT-4: **Deep >> Fresh** — OPPOSITE of Biotech/TMT!
  - Deep-CW cumulative +104.1% vs Fresh-EW +49.1% (12 quarters)
  - Deep-CW avg +6.49%/qtr, excess +5.11% vs XLE
  - CW adds ~0.55%/qtr over EW for both signal types
  - Explanation: Energy is asset-heavy, relationship-driven — deep knowledge of assets persists longer
- BT-5: **Variant >> Consensus** (similar to Biotech)
  - Variant avg excess +7.63%/qtr vs Consensus +1.14%/qtr
  - BUT Variant volatility 18.37% vs Consensus 4.25% — much lumpier returns
  - Top-third threshold used (not top-quartile) for small groups < 12 managers
  - pm_backtest.py patched: _get_top_quartile_ciks ensures min 3 CIKs for small groups
- Energy meeting priority: rank by ExpVal (stock picking quality), not credibility
  - Goodlander (+22.11% ExpVal) > Hill City (+12.54%) > Merewether (+1.17%)
  - Credibility ≠ stock picking skill in Energy group
- pm_backtest.py parameterized: BT4/BT5 now accept group= arg (default "Biotech")
  - BENCHMARK_MAP: Biotech→XBI, TMT→XLK, Energy→XLE, Healthcare→XLV, Financials→XLF
  - save_obsidian_bt4/bt5 also accept group= for correct file naming

## 2026-02-11: Energy cross-13f execution
- Energy has 7 managers (6 active, Oceanic inactive since Q3 2018)
- Top-Q threshold: 61.1 (2 managers: Merewether 61.5, Yaupon 61.1)
- Goodlander and Hill City have best stock-level skill but lower credibility — meeting priority should follow ExpVal not credibility
- Variant scan: zero overlap between Merewether and Yaupon at >3% weight — every position is variant
- FSLR is the strongest consensus signal: 5/6 PMs hold, all fresh
- Merewether utility rotation (ETR, SRE, NVT, XEL, NI) is the strongest thematic signal
- VST highest divergence: Goodlander 22% vs Merewether selling from 7.3%
