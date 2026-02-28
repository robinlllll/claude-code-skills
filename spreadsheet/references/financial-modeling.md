# Financial Modeling Reference

Institutional-grade 6-tab Excel financial model specification. Adapted from Anthropic FSI equity-research plugin.

## Model Structure

### Tab 1: Revenue Model
- **Rows:** 15-25 product/segment rows + 10-15 geography rows
- **Columns:** 3 years historical + 3 years projected (quarterly breakdown for current + next FY)
- **Key formulas:** Growth rates (YoY, QoQ), segment mix %, geographic mix %
- **Bottom:** Total revenue roll-up with cross-check against reported figures

### Tab 2: Income Statement
- **Rows:** 35-45 line items from Revenue → Net Income
- **Structure:**
  - Revenue (linked from Tab 1)
  - COGS → Gross Profit → Gross Margin %
  - R&D, SG&A, Other OpEx → Operating Income → Operating Margin %
  - Interest, Tax, Other → Net Income → EPS
  - Share count (basic + diluted, with buyback assumptions)
- **Key formulas:** Margin expansion/compression bridge, OpEx as % of revenue
- **Actuals vs. Estimates:** Clearly separate A (actual) from E (estimate) columns

### Tab 3: Cash Flow Statement
- **Rows:** 25-30 line items
- **Structure:**
  - Net Income (linked from Tab 2)
  - D&A, SBC, Working Capital changes → CFO
  - CapEx, Acquisitions → CFI
  - Debt, Buybacks, Dividends → CFF
  - → Free Cash Flow = CFO - CapEx
  - → FCF Yield = FCF / Market Cap
- **Key formulas:** FCF conversion (FCF/Net Income), CapEx intensity (CapEx/Revenue)

### Tab 4: Balance Sheet
- **Rows:** 30-40 line items
- **Structure:** Assets / Liabilities / Equity with quarterly snapshots
- **CRITICAL:** Balance check formula: `=Assets - Liabilities - Equity` must equal 0
  - Highlight in RED if non-zero
- **Key ratios:** Net Debt/EBITDA, Current Ratio, DSO/DIO/DPO

### Tab 5: Scenarios
- **Structure:**
  - Assumption table (10-15 key assumptions)
  - Three columns: Bull / Base / Bear
  - Each assumption has a specific value per scenario
  - Toggle cell at top to switch between scenarios
  - Output: Revenue, EBITDA, EPS, FCF, Target Price per scenario
- **Assumptions to include:**
  - Revenue growth rate
  - Gross margin
  - OpEx growth
  - CapEx intensity
  - Tax rate
  - Share count (buyback pace)
  - Terminal multiple

### Tab 6: DCF Inputs
- **Structure:**
  - WACC calculation (CAPM: Rf + Beta × ERP)
  - Projection period FCFs (linked from Tab 3)
  - Terminal value (perpetuity growth method + exit multiple method)
  - PV of FCFs + PV of Terminal Value → Enterprise Value
  - Less: Net Debt → Equity Value → Per Share Value
  - Sensitivity table: WACC vs. Terminal Growth Rate (or Exit Multiple)
- **Key inputs:**
  - Risk-free rate (10Y Treasury)
  - Equity risk premium
  - Beta (levered)
  - Terminal growth rate
  - Exit EV/EBITDA multiple

## Color Coding Standard

| Color | Meaning | Usage |
|-------|---------|-------|
| Blue (font) | Hard-coded input | User assumptions, manually entered data |
| Black (font) | Formula | Calculated cells |
| Green (font) | Cross-sheet link | References to other tabs |
| Light yellow (fill) | Input cell | Highlights editable assumptions |
| Light gray (fill) | Historical data | Actuals from filings |
| Red (font/fill) | Error/Warning | Balance check ≠ 0, negative values where unexpected |

## Data Extraction from SEC Filings

When building a model from scratch:

1. **10-K (Annual):** Revenue breakdown, full P&L, balance sheet, cash flow, segment data
   - EDGAR link: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={TICKER}&type=10-K`
2. **10-Q (Quarterly):** Latest quarterly data for projection base
3. **Earnings Release:** Often has cleaner segment breakdowns than the 10-Q/K
4. **Investor Presentation:** May include KPIs not in filings (ARR, NRR, unit economics)

## Formula Best Practices

- **Never hardcode** a number that can be derived from another cell
- **Label every assumption** with a comment or adjacent text cell
- **Use named ranges** for key inputs (WACC, tax_rate, terminal_growth)
- **Include error checks:**
  - Balance sheet balances (=0)
  - Revenue roll-up matches consolidated
  - FCF reconciliation (CFO - CapEx = FCF)
  - EPS × Shares = Net Income (within rounding)
- **Version control:** Include a "Model Log" row at top with last-updated date and change notes

## Quick-Start for Common Sectors

### Consumer Staples (e.g., PM, CELH)
- Tab 1: Revenue by product category + geography
- Key metrics: Volume, Price/Mix, Market Share
- Tab 5 scenarios: Volume growth ± pricing power

### Tech / SaaS
- Tab 1: Revenue by ARR/subscription vs. services
- Key metrics: NRR, Logo adds, ARPU, Rule of 40
- Tab 5 scenarios: NRR range, customer retention

### Semiconductor
- Tab 1: Revenue by end market (DC, Mobile, Auto, etc.)
- Key metrics: ASP trends, utilization, inventory
- Tab 5 scenarios: Cycle timing, pricing pressure

### Quick-Start: Financials (Banks/Brokers)
- **Tab 1 driver:** NII (NIM × avg earning assets) + Non-interest income by line
- **Key assumptions:** Rate sensitivity, deposit beta, loan growth, credit cost
- **Scenario drivers:** Fed rate path, credit cycle, capital markets activity
- **Primary valuation:** P/TBV (ROTCE-adjusted), P/E

### Quick-Start: Healthcare / Pharma
- **Tab 1 driver:** Revenue by drug/product (TRx × net price), pipeline probability-weighted
- **Key assumptions:** Script growth rates, gross-to-net, patent cliff timing, pipeline Phase success
- **Scenario drivers:** Clinical trial outcomes, FDA decisions, formulary access
- **Primary valuation:** P/E for large pharma, rNPV for biotech/pipeline

### Quick-Start: Industrials
- **Tab 1 driver:** Revenue by segment (OE + aftermarket), organic growth + backlog conversion
- **Key assumptions:** Book-to-bill, backlog duration, price escalation, margin bridge
- **Scenario drivers:** Capex cycle, defense budget, aftermarket mix shift
- **Primary valuation:** P/E, EV/EBITDA

### Quick-Start: Energy (E&P / Integrated)
- **Tab 1 driver:** Production volume (BOE/d) × realized price by commodity
- **Key assumptions:** Production growth, realized vs. benchmark pricing, lifting cost/BOE
- **Scenario drivers:** Oil/gas strip curve, production ramp, capital discipline
- **Primary valuation:** EV/EBITDA at strip, P/FCF, EV/BOE

### Quick-Start: Tobacco / Nicotine
- **Tab 1 driver:** Combustible volume × pricing + RRP units × ASP by category
- **Key assumptions:** Volume decline rate, pricing power, RRP adoption curve, mix shift
- **Scenario drivers:** Regulation, excise tax, competitor RRP launches
- **Primary valuation:** P/E, dividend yield, sum-of-parts (combustible + RRP)

### Quick-Start: E-commerce / Marketplace
- **Tab 1 driver:** GMV × take rate, broken down by 1P vs 3P, by geography
- **Key assumptions:** Active buyer growth, frequency, AOV, take rate expansion
- **Scenario drivers:** Consumer spending, competitive intensity, regulatory
- **Primary valuation:** EV/Revenue, EV/GMV, P/E for profitable names
