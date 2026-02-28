---
name: spreadsheet
description: "Use when tasks involve creating, editing, analyzing, or formatting spreadsheets (.xlsx, .csv, .tsv). Covers simple data exports AND complex financial models. Triggers on: Excel, spreadsheet, .xlsx, CSV, financial model, DCF, valuation, data export."
---

# Spreadsheet Skill (Create, Edit, Analyze)

## When to Use

- Create new workbooks with formulas, formatting, structured layouts
- Read or analyze tabular data (filter, aggregate, pivot, compute metrics)
- Modify existing workbooks without breaking formulas or references
- Export DataFrames to clean Excel files
- Build financial models (DCF, LBO, valuation, P&L tracker)

## Mode Selection (Required First Step)

**Always determine the mode before starting:**

### Data Mode (Default)
Simple DataFrame → Excel conversion. Minimal formatting.
- CSV/TSV → Excel conversion
- Query results → spreadsheet
- Data dumps, exports, simple tables
- Use when user does NOT mention: model, 估值, DCF, IB格式, financial model

### Model Mode
Full investment banking formatting conventions.
- Trigger: user mentions "模型", "model", "估值", "DCF", "IB格式", "financial model", "valuation"
- Color conventions, formula-driven, named ranges, assumption blocks
- See `references/financial-templates.md` for templates

**When unsure, default to Data Mode.** Simple is better than over-engineered.

**Auto-Sector Detection for Financial Models:**
When user requests a model for a specific ticker:
1. Resolve sector: `entity_dictionary.yaml[TICKER].sector` → `sector_metrics.yaml`
2. Auto-load the sector's model template from `references/financial-modeling.md` Quick-Start section
3. Use `sector_metrics.yaml[sector].valuation_methods` to determine:
   - Which valuation tab to prioritize (DCF vs. comps vs. sum-of-parts)
   - Which `peer_multiples` to include in the comps tab
4. Pre-populate Tab 1 (Revenue Model) structure based on sector:
   - SaaS: ARR/subscription breakdown, NRR-driven expansion, new logo adds
   - Consumer Staples: Volume × Price × Mix by product category and geography
   - Semiconductor: End market breakdown × ASP × utilization
   - Financials: NII + Fee Income, NIM × earning assets, provision modeling
   - (Full list in `shared/references/sector_metrics.yaml`)

No user interaction needed — auto-detect and apply.

## Workflow

1. **Determine mode** — Data Mode or Model Mode
2. **Confirm goals** — file type, data source, output structure
3. **Select tooling** — `openpyxl` for .xlsx formatting, `pandas` for analysis/CSV
4. **Generate** — write the workbook
5. **Open for review** — `start output.xlsx` (Windows auto-opens Excel)
6. **Iterate** — adjust based on user feedback

## Primary Tooling

- **`openpyxl`** — create/edit .xlsx, preserve formatting, formulas, charts
- **`pandas`** — analysis, CSV/TSV workflows, DataFrame operations
- **`openpyxl.chart`** — native Excel charts (prefer over matplotlib for Excel output)

See `references/openpyxl-patterns.md` for code patterns.

## Formula Rules (Model Mode)

- Use formulas for derived values — never hardcode computed results
- Keep formulas legible; use helper cells for complex logic
- Avoid volatile functions (INDIRECT, OFFSET) unless required
- Prefer cell references over magic numbers (`=H6*(1+$B$3)` not `=H6*1.04`)
- Guard against #REF!, #DIV/0!, #VALUE!, #N/A with IFERROR
- openpyxl does NOT evaluate formulas — leave formulas intact, they calculate when opened in Excel

## Formatting Rules

### Data Mode
- Clean headers, auto-width columns, consistent number formats
- Dates as dates, currency with symbols, percentages with precision
- No excessive borders — use whitespace and selective borders

### Model Mode (IB Conventions)
- **Colors:** Blue=user input, Black=formulas, Green=linked values, Gray=constants, Orange=review, Red=error
- **Zeros:** Display as "-"
- **Negatives:** Red text in parentheses `(1,234)`
- **Units:** Always in headers — "Revenue ($mm)", "Margin (%)"
- **Layout:** Section headers = merged cells with dark fill + white text
- **Totals:** Sum range directly above; horizontal border above totals
- **Alignment:** Column labels right-aligned, row labels left-aligned
- **Sources:** Cite inputs in cell comments

See `references/financial-templates.md` for IB model layouts.

## Output Convention

- Generate file → run `start output.xlsx` to open in Excel
- No PNG preview needed on Windows
- Keep filenames descriptive: `{ticker}_dcf_model.xlsx`, `portfolio_pnl.xlsx`

## Dependencies

```
pip install openpyxl pandas
```

Optional for chart-heavy workflows:
```
pip install matplotlib
```

## References

- Code patterns and examples: `references/openpyxl-patterns.md`
- Financial model templates: `references/financial-templates.md`
- Financial Modeling: `references/financial-modeling.md` — 6-tab Excel model specification with color coding, data extraction, and sector-specific templates
