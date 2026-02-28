# Valuation Methodologies Reference

Comprehensive reference for equity valuation. Adapted from Anthropic FSI equity-research plugin.

## 1. Discounted Cash Flow (DCF)

### Step 1: Unlevered Free Cash Flow (UFCF)
```
UFCF = EBIT × (1 - Tax Rate) + D&A - CapEx - ΔWorking Capital
```

Or equivalently:
```
UFCF = EBITDA × (1 - Tax Rate) + D&A × Tax Rate - CapEx - ΔWC
```

### Step 2: Weighted Average Cost of Capital (WACC)
```
WACC = E/(D+E) × Ke + D/(D+E) × Kd × (1 - Tax Rate)
```

Where:
- **Ke (Cost of Equity)** = Risk-Free Rate + Beta × Equity Risk Premium
  - Risk-Free Rate: 10-year Treasury yield
  - Beta: Levered beta from regression (2-5 year weekly returns vs. S&P 500)
  - ERP: Typically 5-6% for US equities (Damodaran, Duff & Phelps)
  - Size premium: Add 1-3% for small/mid cap (if applicable)
- **Kd (Cost of Debt)** = Weighted average interest rate on outstanding debt
- **E, D** = Market value of equity, book value of debt

### Step 3: Terminal Value

**Method A: Perpetuity Growth**
```
TV = UFCF_final × (1 + g) / (WACC - g)
```
Where g = long-term growth rate (typically 2-3%, ≤ nominal GDP growth)

**Method B: Exit Multiple**
```
TV = EBITDA_final × Exit Multiple
```
Where Exit Multiple = current trading multiple or peer median

**Sanity check:** Both methods should produce similar results. If >20% divergence, investigate assumptions.

### Step 4: Present Value & Equity Bridge
```
Enterprise Value = Σ [UFCF_t / (1 + WACC)^t] + TV / (1 + WACC)^n
Equity Value = Enterprise Value - Net Debt - Minority Interest - Preferred Stock + Associates
Per Share Value = Equity Value / Diluted Shares Outstanding
```

### Step 5: Sensitivity Table
Create a 2D matrix:
- **Rows:** WACC (±1% in 0.25% increments)
- **Columns:** Terminal growth rate (1.5% to 3.5% in 0.5% increments)
- Or: WACC vs. Exit Multiple

### DCF Pitfalls
- Terminal value shouldn't be >70% of total EV (if so, projection period is too short)
- Don't use a terminal growth rate > GDP growth
- Beta should be forward-looking; historical beta may be stale
- Working capital swings can dominate FCF for fast-growing companies

---

## 2. Comparable Company Analysis (Trading Comps)

### Peer Selection (5-10 companies)
Criteria for good comps:
1. Same industry / sub-sector
2. Similar business model (B2B vs. B2C, subscription vs. transactional)
3. Similar size (within 0.5x-3x revenue)
4. Similar growth profile (±10pp revenue growth)
5. Similar margin profile (±500bps EBITDA margin)

### Multiple Calculation
```
EV = Market Cap + Net Debt + Minority Interest + Preferred - Associates - Cash
```

Common multiples:
| Multiple | Formula | Best For |
|----------|---------|----------|
| EV/Revenue | EV / NTM Revenue | High-growth, pre-profit |
| EV/EBITDA | EV / NTM EBITDA | Mature, capital-light |
| EV/EBIT | EV / NTM EBIT | Capital-intensive |
| P/E | Price / NTM EPS | Profitable, stable |
| P/FCF | Price / NTM FCF per share | Cash-generative |
| EV/GP | EV / Gross Profit | Marketplace/platform |
| PEG | P/E / EPS Growth Rate | Growth at reasonable price |

### Statistical Summary (mandatory)
For each multiple, calculate:
| Stat | Value |
|------|-------|
| Maximum | |
| 75th percentile | |
| Median | |
| Mean | |
| 25th percentile | |
| Minimum | |
| Target company | |
| Premium/(Discount) to median | |

### Premium/Discount Justification
- **Justify >10% premium:** Superior growth, margins, market position, or TAM
- **Justify >10% discount:** Execution risk, concentration, governance, cyclicality
- Rule of thumb: Growth differential of 5pp ≈ 1x EV/EBITDA multiple turn

---

## 3. Precedent Transactions

### When to Use
- M&A scenario analysis
- Floor valuation (control premium provides downside protection)
- Strategic vs. financial buyer analysis

### Control Premium
```
Control Premium = (Offer Price / Unaffected Price) - 1
```
Typical ranges:
- Strategic buyer: 25-40% premium
- Financial buyer (PE): 15-30% premium
- Hostile takeover: 30-50%+ premium

### Transaction Multiple vs. Trading Multiple
```
Transaction Multiple = Trading Multiple + Control Premium Effect
```
Typically 2-4x EBITDA turns higher than trading comps.

### Relevance Decay
- Transactions >3 years old: use with caution
- Transactions >5 years old: generally exclude
- Adjust for market cycle (boom vs. recession multiples)

---

## 4. Valuation Reconciliation

### Football Field Chart
Present all three methods side-by-side:

```
Method              Low    Mid    High
─────────────────────────────────────
DCF                 $42    $55    $68
Trading Comps       $38    $48    $58
Precedent Tx        $52    $62    $72
─────────────────────────────────────
Blended Target      $44    $55    $66
Current Price       $50
Upside/(Downside)  -12%   +10%   +32%
```

### Weighting Guidelines
| Context | DCF | Comps | Precedent |
|---------|-----|-------|-----------|
| Stable, predictable cash flows | 50% | 35% | 15% |
| High-growth, no FCF yet | 20% | 60% | 20% |
| M&A target | 20% | 30% | 50% |
| Distressed / restructuring | 60% | 20% | 20% |

### Sanity Checks
1. Implied exit multiple from DCF should be within peer range
2. Implied growth rate from current multiple should be achievable
3. Terminal value < 70% of total DCF value
4. Implied FCF yield at target price should be reasonable (>3% for mature)
5. Cross-check: Does the stock screen well on the implied metrics?
