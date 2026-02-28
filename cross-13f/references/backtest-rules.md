# Backtest Integration Rules (MANDATORY -- GROUP-SPECIFIC)

Rules differ by group. Always check the group before applying.
All 9 groups now have full Phase 3 backtest data (updated 2026-02-18).

## Universal Rules (all groups)

| Rule | Source | What to Do |
|------|--------|------------|
| **Top-Q identification** | BT-1: p=0.83 cred vs Sharpe | Compute top-quartile managers (top 25% by credibility; top-third for groups < 12 managers). Use them for consensus/variant classification. |
| **Signal purity** | BT-3: Q1 TE 17% vs Q4 24% | Tag managers with low tracking error as "high signal purity" -- their position changes are more meaningful. |
| **Keep default weights** | BT-6: p>0.25 | Do not adjust credibility component weights. |
| **CN geo-discount** | BT-7: CN hit 50% vs US 57% | Zero out portfolio_pct bonus for CN_PM managers. Keep action signals (new/add/sell). |

**Note:** Fresh vs Deep priority is GROUP-SPECIFIC (not universal). Check the group rules below.

## Quick Reference: All 9 Groups

| Group | Signal | Weighting | BT-5 Basket | Section Order | Benchmark | Sharpe | Confidence |
|-------|--------|-----------|-------------|---------------|-----------|--------|------------|
| **Biotech** | Fresh | EW | **Consensus** (purity-filtered) | Consensus-first | XBI | 1.09 (raw), 1.64 (trimmed) | High |
| **CN_PM** | Fresh | EW | Variant | Variant-first | SPY | 3.14 | High |
| **TMT** | Fresh | EW | Consensus | Consensus-first | XLK | 1.52 | High |
| **Healthcare** | Fresh | **CW** | Consensus | Consensus-first | XLV | 1.45 | Medium |
| **Financials** | **Deep** | EW | Variant | Variant-first | XLF | 2.44 | Medium |
| **Energy** | **Deep** | **CW** | Variant | Variant-first | XLE | 1.47 | Medium |
| **Generalist** | Fresh | EW | Consensus | Consensus-first | SPY | 1.75 | Medium |
| **Consumer** | Fresh | **CW** | Consensus | Consensus-first | XLY | 1.69 | High |
| **Real Estate** | **Deep** | EW | Consensus | Consensus-first | XLRE | 0.58 | Low |

### Pattern Summary
- **Fresh signal wins:** Biotech, CN_PM, TMT, Healthcare, Generalist, Consumer (6/9)
- **Deep signal wins:** Financials, Energy, Real Estate (3/9 — all specialists)
- **EW wins:** Biotech, CN_PM, TMT, Generalist (large groups >15)
- **CW wins:** Healthcare, Energy, Consumer (small groups <15 with quality dispersion)
- **Variant wins:** CN_PM, Financials, Energy (3/9 — dominant stock-pickers)
- **Consensus wins:** Biotech (purity-filtered), TMT, Healthcare, Generalist, Consumer, Real Estate (6/9 — convergent smart money)

## Biotech-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh Sharpe 2.44 vs Deep 1.01 | Prioritize Fresh list as primary signal. Deep is supplementary context. |
| **EW > CW** | BT-4: Sharpe 2.44 vs 1.01 | Do NOT weight or rank by credibility. Equal-weight ranking. Credibility is display-only badge. |
| **Consensus > Variant** (purity-filtered) | BT-5 + Verdad purity filter: Con +12.84% vs Var +1.73% excess, Sharpe 1.09 vs 0.31 | **FLIPPED from raw BT-5.** With `--purity 0.5` (specialist >50% biotech allocation), Consensus positions are HIGHEST PRIORITY. Robust across trimming (Trim-2: +6.62% vs +1.61%, Sharpe 1.64 vs 0.45). Win rate 75%. |
| **Purity filter default** | BT-5 purity comparison (2026-02-25) | Always run BT-5 with `purity_threshold=0.5` for Biotech. Without filter, raw Variant edge is a mean-driven illusion (median and win rate favor Consensus even unfiltered). |
| **Insider overlay** | Verdad: CFO > C-suite > Board > CEO=noise | Append Form 4 insider column to Stage 1 screening table for Biotech. CFO open-market buys are the strongest signal. Use `insider_signals.py`. |

## CN_PM-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-EW Sharpe 3.14, +7.43%/qtr | Strongest Fresh signal of all groups. Prioritize Fresh list. |
| **EW > CW** | BT-4: EW beats CW by 0.68% | Do NOT weight by credibility. Equal-weight. |
| **Variant > Consensus** | BT-5: +9.13% vs +5.57%/qtr excess (Phase 3) | Top China PMs (FengHe, CloudAlpha, Keywise) generate alpha from idiosyncratic picks. Surface Variant first. |
| **CN geo-discount** | BT-7 | Zero out portfolio_pct bonus. Keep action signals only. |

## TMT-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-EW Sharpe 1.52 | Fresh signal wins. |
| **EW > CW** | BT-4: EW beats CW by 0.28% | Minimal difference, but EW slightly better for large group (50 members). |
| **Consensus > Variant** | BT-5: +2.82% vs +2.30%/qtr | Consensus positions are HIGHEST PRIORITY. Surface Consensus first. Variant supplementary. |

## Healthcare-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-CW +108.95% cumulative | Fresh signal wins. |
| **CW > EW** | BT-4: CW beats EW by +3.66% | Small group (13) with wide quality spread. USE credibility to weight rankings. |
| **Consensus > Variant** | BT-5: +7.54% vs +5.14%/qtr excess (Phase 3) | Consensus positions are HIGHEST PRIORITY. Surface Consensus first. |

## Financials-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Deep > Fresh** | BT-4: Deep-EW +124.06% cumulative, Sharpe 2.44 | **OPPOSITE of most groups.** Prioritize Deep list (tenure + position size) as PRIMARY signal. |
| **EW > CW** | BT-4: EW is better for this tiny group (5 members) | Do NOT weight by credibility. Equal-weight. |
| **Variant > Consensus** | BT-5: +2.77% vs +1.90%/qtr | Variant positions are higher priority. Surface Variant first. |
| **Small group caveat** | Only 5 members | Very concentrated. Results may be sample-dependent. |

## Energy-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Deep > Fresh** | BT-4: Deep-CW +120.18% cumulative (12Q) | Prioritize Deep list (longest tenure, heaviest position) as PRIMARY signal. Fresh is secondary. |
| **CW > EW** | BT-4: CW adds ~0.67%/qtr over EW | USE credibility to weight ticker ranking. Deep-CW is the optimal Energy strategy. |
| **Variant > Consensus** | BT-5: +4.76% vs +1.36% excess/qtr (Phase 3) | Variant positions are HIGHEST PRIORITY, but with HIGH VOLATILITY (19.10%). Surface Variant first, flag volatility risk. |
| **Deep-list display** | BT-4 Energy result | Show **Deep list FIRST** in per-ticker output (not Fresh). Tag Deep managers as primary signal. |
| **Goodlander concentration** | BT-5 investigation | Goodlander (CIK 2018973, #1 credibility) runs 11-position concentrated portfolio. Their variant picks can dominate single-quarter returns (e.g., BE +253% in Q3 2025). Flag Goodlander-only positions. |

## Generalist-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-EW +83.49% cumulative | Fresh signal wins. |
| **EW > CW** | BT-4: negligible difference (-0.05%) | Equal-weight. Large group (27 members). |
| **Consensus > Variant** | BT-5: +5.70% vs +3.88%/qtr (Phase 3 flipped) | Consensus positions are HIGHEST PRIORITY. Top generalists (Maverick, Viking) converge on winners. |

## Consumer-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Fresh > Deep** | BT-4: Fresh-CW +107.80% cumulative | Fresh signal wins. |
| **CW > EW** | BT-4: CW beats EW by +0.68% | Small group (12) with quality dispersion. USE credibility to weight rankings. |
| **Consensus > Variant** | BT-5: +1.92% vs +0.74%/qtr (Phase 3) | Consensus positions are HIGHEST PRIORITY. Surface Consensus first. |
| **TMT overlap caveat** | Risk analysis | AMZN, GOOGL appear across most Consumer portfolios — overlap with TMT mega-caps. Deduplicate when running alongside TMT screen. |

## Real Estate-Specific Rules

| Rule | Source | What to Do |
|------|--------|------------|
| **Deep > Fresh** | BT-4: Deep-EW +24.44% cumulative | Deep signal wins, but weakest alpha of all groups. |
| **EW > CW** | BT-4: EW beats CW marginally (-0.16%) | Equal-weight. |
| **Consensus > Variant** | BT-5: +2.54% vs +1.26%/qtr (Phase 3 flipped) | Consensus is higher priority. Top RE managers (LDR Capital, Long Pond) converge on quality REITs. |
| **Weak alpha caveat** | BT-4: Sharpe 0.58 | Marginal signal quality. Consider whether this group justifies active tracking vs just buying XLRE. |

## How to Apply in Practice

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
# Group by ticker: if only 1-2 top-Q managers hold it -> VARIANT
# Variant-first groups (Biotech, CN_PM, Financials, Energy): HIGHEST PRIORITY
# Consensus-first groups (TMT, Healthcare, Generalist, Consumer, Real Estate): LOWER PRIORITY
```

**Ticker ranking: GROUP-DEPENDENT**

```python
# Fresh-EW groups (Biotech, CN_PM, TMT, Generalist):
#   Count Fresh actions equally (do NOT multiply by credibility)

# Fresh-CW groups (Healthcare, Consumer):
#   Weight Fresh actions by manager's hybrid credibility score

# Deep-EW groups (Financials, Real Estate):
#   Rank by Deep score (tenure*20 + pct*15), equal-weight

# Deep-CW groups (Energy):
#   Rank by Deep score, weighted by credibility
```

Tag each ticker as CONSENSUS (3+ top-Q holders) or VARIANT (1-2 top-Q holders)
