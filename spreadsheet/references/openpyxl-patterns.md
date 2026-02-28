# openpyxl Code Patterns

## Basic Workbook Creation

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment, numbers

wb = Workbook()
ws = wb.active
ws.title = "Sheet1"

# Write data
ws['A1'] = "Header"
ws['A1'].font = Font(bold=True)

# From DataFrame
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows

df = pd.read_csv("data.csv")
for r in dataframe_to_rows(df, index=False, header=True):
    ws.append(r)

wb.save("output.xlsx")
```

## Styles

### Fonts
```python
Font(name='Calibri', size=11, bold=True, color='000000')      # Black formula
Font(name='Calibri', size=11, bold=False, color='0000FF')      # Blue input
Font(name='Calibri', size=11, bold=False, color='008000')      # Green linked
Font(name='Calibri', size=11, bold=False, color='808080')      # Gray constant
Font(name='Calibri', size=11, bold=False, color='FF0000')      # Red error/negative
Font(name='Calibri', size=11, bold=False, color='FF8C00')      # Orange review
```

### Fills
```python
PatternFill(start_color='003366', end_color='003366', fill_type='solid')  # Section header (dark blue)
PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')  # Alternating row
PatternFill(start_color='DAEEF3', end_color='DAEEF3', fill_type='solid')  # Input cell highlight
```

### Borders
```python
thin = Side(style='thin')
medium = Side(style='medium')

Border(bottom=medium)          # Total line — medium bottom border
Border(bottom=thin)            # Subtotal — thin bottom border
Border(top=thin, bottom=thin)  # Section separator
```

### Alignment
```python
Alignment(horizontal='right', vertical='center')   # Numbers
Alignment(horizontal='left', vertical='center')     # Labels
Alignment(horizontal='center', vertical='center')   # Headers
Alignment(wrap_text=True)                            # Long text
```

## Number Formats

```python
# Currency
cell.number_format = '#,##0.00'          # 1,234.56
cell.number_format = '$#,##0.00'         # $1,234.56
cell.number_format = '#,##0.0'           # 1,234.6

# Percentage
cell.number_format = '0.0%'             # 12.3%
cell.number_format = '0.00%'            # 12.34%

# IB convention: negatives in red parentheses, zeros as dash
cell.number_format = '#,##0;[Red](#,##0);"-"'
cell.number_format = '#,##0.0;[Red](#,##0.0);"-"'
cell.number_format = '$#,##0;[Red]($#,##0);"-"'

# Dates
cell.number_format = 'YYYY-MM-DD'
cell.number_format = 'MMM-YY'           # Jan-26

# Large numbers (millions)
cell.number_format = '#,##0.0,,"mm"'    # Display in millions
```

## Formulas

```python
# SUM
ws['B10'] = '=SUM(B2:B9)'

# INDEX/MATCH (cross-sheet lookup)
ws['C2'] = '=INDEX(Data!B:B,MATCH(A2,Data!A:A,0))'

# IF/IFERROR
ws['D2'] = '=IFERROR(C2/B2, 0)'
ws['E2'] = '=IF(D2>0.1, "Above", "Below")'

# Growth rate
ws['F3'] = '=(F3-F2)/F2'

# Named ranges for assumptions
from openpyxl.workbook.defined_name import DefinedName
ref = f"Assumptions!$B$2"
dn = DefinedName("growth_rate", attr_text=ref)
wb.defined_names.add(dn)
```

## Conditional Formatting

```python
from openpyxl.formatting.rule import FormulaRule, CellIsRule, ColorScaleRule

# Red fill if negative
ws.conditional_formatting.add('B2:B100',
    CellIsRule(operator='lessThan', formula=['0'],
              fill=PatternFill(bgColor='FFC7CE')))

# Green fill if > 10%
ws.conditional_formatting.add('C2:C100',
    CellIsRule(operator='greaterThan', formula=['0.1'],
              fill=PatternFill(bgColor='C6EFCE')))

# Color scale (red → yellow → green)
ws.conditional_formatting.add('D2:D100',
    ColorScaleRule(start_type='min', start_color='F8696B',
                   mid_type='percentile', mid_value=50, mid_color='FFEB84',
                   end_type='max', end_color='63BE7B'))
```

## Charts

```python
from openpyxl.chart import BarChart, LineChart, Reference

# Bar chart
chart = BarChart()
chart.title = "Revenue by Quarter"
chart.y_axis.title = "Revenue ($mm)"
data = Reference(ws, min_col=2, min_row=1, max_row=5, max_col=4)
cats = Reference(ws, min_col=1, min_row=2, max_row=5)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.shape = 4
ws.add_chart(chart, "F2")

# Line chart
line = LineChart()
line.title = "Price History"
line.y_axis.title = "Price ($)"
line.style = 10
data = Reference(ws, min_col=2, min_row=1, max_row=100)
line.add_data(data, titles_from_data=True)
ws.add_chart(line, "F20")
```

## Column Width Auto-Fit

```python
from openpyxl.utils import get_column_letter

for col in ws.columns:
    max_length = 0
    col_letter = get_column_letter(col[0].column)
    for cell in col:
        if cell.value:
            max_length = max(max_length, len(str(cell.value)))
    ws.column_dimensions[col_letter].width = min(max_length + 2, 50)
```

## Freeze Panes

```python
ws.freeze_panes = 'B2'   # Freeze row 1 and column A
ws.freeze_panes = 'A2'   # Freeze row 1 only
```

## Print Setup

```python
ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
ws.page_setup.paperSize = ws.PAPERSIZE_A4
ws.page_setup.fitToPage = True
ws.print_title_rows = '1:1'  # Repeat row 1 on every page
```

## Multiple Sheets

```python
# Create sheets
assumptions = wb.create_sheet("Assumptions")
model = wb.create_sheet("Model")
output_sheet = wb.create_sheet("Output")

# Cross-sheet formula
model['B2'] = "=Assumptions!B2 * (1 + Assumptions!B3)"
```

## Reading Existing Files

```python
from openpyxl import load_workbook

wb = load_workbook("existing.xlsx", data_only=False)  # Preserve formulas
ws = wb.active

# Read cell
value = ws['A1'].value

# Iterate rows
for row in ws.iter_rows(min_row=2, values_only=True):
    print(row)
```
