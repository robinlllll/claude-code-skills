# Financial Templates for Spreadsheet Skill

## Template 1: Portfolio P&L Tracker

**Use case:** Generate from IBKR data or portfolio_monitor SQLite

```
Sheet: "Holdings"
Layout:
  Row 1: Title "Portfolio P&L — {date}" (merged, dark fill)
  Row 2: Headers
  Row 3+: Data rows

Columns:
  A: Ticker (left-aligned)
  B: Name (left-aligned)
  C: Sector (left-aligned)
  D: Shares (right, #,##0)
  E: Avg Cost ($#,##0.00)
  F: Current Price ($#,##0.00)
  G: Market Value ($#,##0) = D*F
  H: Cost Basis ($#,##0) = D*E
  I: P&L ($#,##0;[Red]($#,##0);"-") = G-H
  J: P&L % (0.0%;[Red](0.0%);"-") = I/H
  K: Weight (0.0%) = G/total_mv

Footer row:
  A: "TOTAL" (bold)
  G: =SUM(G3:Gn)
  H: =SUM(H3:Hn)
  I: =SUM(I3:In)
  J: =I_total/H_total
  K: =SUM(K3:Kn)  → should = 100%

Color rules:
  - J column: green if >0, red if <0
  - K column: orange if >5% (concentration warning)
```

## Template 2: DCF Model Skeleton

```
Sheet "Assumptions":
  B2: Revenue Growth Rate (blue input)
  B3: EBITDA Margin (blue input)
  B4: CapEx % Revenue (blue input)
  B5: Tax Rate (blue input)
  B6: WACC (blue input)
  B7: Terminal Growth (blue input)

Sheet "Model":
  Row 1: Title
  Row 2: Year headers (Year 1 ... Year 5, Terminal)

  Section "Revenue Build":
    Revenue (=prior*(1+growth))
    YoY Growth (formula)

  Section "Profitability":
    EBITDA (=Revenue*margin)
    D&A (assumption or % revenue)
    EBIT (=EBITDA-D&A)
    Tax (=EBIT*tax_rate)
    NOPAT (=EBIT-Tax)

  Section "Free Cash Flow":
    NOPAT
    + D&A
    - CapEx (=Revenue*capex_pct)
    - Change in NWC
    = Unlevered FCF

  Section "Valuation":
    PV of FCF (=FCF/(1+WACC)^year)
    Terminal Value (=FCF_terminal*(1+g)/(WACC-g))
    PV of Terminal
    Enterprise Value (=sum PV)
    - Net Debt
    Equity Value
    Shares Outstanding (blue input)
    Implied Price/Share

Sheet "Sensitivity":
  WACC vs Terminal Growth matrix
  =DATA_TABLE function or manual grid
```

## Template 3: 13F Holdings Comparison

```
Sheet: "13F Comparison — {manager}"
Layout:
  Row 1: Title (merged)
  Row 2: "Current Filing: {date}" | "Prior Filing: {date}"
  Row 3: Headers

Columns:
  A: Ticker
  B: Company Name
  C: Current Shares (#,##0)
  D: Current Value ($#,##0)
  E: Current Weight (0.0%)
  F: Prior Shares (#,##0)
  G: Prior Value ($#,##0)
  H: Prior Weight (0.0%)
  I: Share Change (#,##0;[Red](#,##0);"-") = C-F
  J: Weight Change (0.0%;[Red](0.0%);"-") = E-H
  K: Action (=IF(F=0,"NEW",IF(C=0,"EXIT",IF(I>0,"ADD","TRIM"))))

Color rules:
  K column: Green="NEW"/"ADD", Red="EXIT"/"TRIM"
  Sort by: abs(J) descending (biggest weight changes first)
```

## Template 4: Quarterly Review Dashboard

```
Sheet: "Q{n} Review"

Section 1: Performance Summary (Row 1-8)
  Portfolio Return vs Benchmark
  Attribution (top 5 contributors, bottom 5)

Section 2: Position Changes (Row 10-25)
  New positions added
  Positions exited
  Significant size changes

Section 3: Thesis Scorecard (Row 27-45)
  Active theses status
  Kill criteria breaches
  Conviction changes

Charts:
  - Bar chart: Monthly returns (portfolio vs benchmark)
  - Pie chart: Sector allocation
  - Waterfall: P&L attribution
```

## Common Patterns

### IB Section Header
```python
def write_section_header(ws, row, text, max_col=11):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(bold=True, color='FFFFFF', size=12)
    cell.fill = PatternFill(start_color='003366', end_color='003366', fill_type='solid')
    cell.alignment = Alignment(horizontal='left', vertical='center')
```

### IB Total Row
```python
def write_total_row(ws, row, sum_cols, data_start, data_end):
    ws.cell(row=row, column=1, value="Total").font = Font(bold=True)
    for col in sum_cols:
        cell = ws.cell(row=row, column=col)
        col_letter = get_column_letter(col)
        cell.value = f'=SUM({col_letter}{data_start}:{col_letter}{data_end})'
        cell.font = Font(bold=True)
        cell.border = Border(top=Side(style='medium'))
        cell.number_format = '#,##0;[Red](#,##0);"-"'
```

### Auto-Width with Padding
```python
def auto_width(ws, min_width=8, max_width=40, padding=3):
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        lengths = [len(str(c.value or '')) for c in col]
        width = min(max(max(lengths) + padding, min_width), max_width)
        ws.column_dimensions[letter].width = width
```
