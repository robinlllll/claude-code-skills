# reportlab Code Patterns

## Chinese Font Registration (MUST DO FIRST)

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Windows font path — Microsoft YaHei
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
pdfmetrics.registerFont(TTFont('MSYH', FONT_PATH, subfontIndex=0))
pdfmetrics.registerFont(TTFont('MSYH-Bold', FONT_PATH, subfontIndex=1))

# Usage in styles
from reportlab.lib.styles import ParagraphStyle
chinese_style = ParagraphStyle('Chinese', fontName='MSYH', fontSize=10)
```

**If font not found:** Try `msyh.ttf` or `C:/Windows/Fonts/msyhbd.ttc` (bold variant).

## Basic Document Creation

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib import colors

doc = SimpleDocTemplate(
    "output.pdf",
    pagesize=A4,
    rightMargin=2*cm,
    leftMargin=2*cm,
    topMargin=2.5*cm,
    bottomMargin=2.5*cm
)

styles = getSampleStyleSheet()
story = []

# Title
story.append(Paragraph("Report Title", styles['Title']))
story.append(Spacer(1, 12))

# Body text
story.append(Paragraph("Content here...", styles['Normal']))

doc.build(story)
```

## Custom Styles

```python
# Title style
title_style = ParagraphStyle(
    'CustomTitle',
    fontName='MSYH-Bold',
    fontSize=18,
    leading=22,
    alignment=TA_CENTER,
    spaceAfter=20
)

# Section header
h1_style = ParagraphStyle(
    'H1',
    fontName='MSYH-Bold',
    fontSize=14,
    leading=18,
    spaceBefore=16,
    spaceAfter=8,
    textColor=colors.HexColor('#003366')
)

# Normal with Chinese support
body_style = ParagraphStyle(
    'Body',
    fontName='MSYH',
    fontSize=10,
    leading=14,
    spaceBefore=4,
    spaceAfter=4
)

# Small footnote
footnote_style = ParagraphStyle(
    'Footnote',
    fontName='MSYH',
    fontSize=8,
    leading=10,
    textColor=colors.grey
)
```

## Tables

```python
# Basic table
data = [
    ['Ticker', 'Name', 'Price', 'Change'],
    ['AAPL', 'Apple Inc.', '$185.50', '+2.3%'],
    ['MSFT', 'Microsoft', '$410.20', '-0.5%'],
]

table = Table(data, colWidths=[60, 120, 80, 80])
table.setStyle(TableStyle([
    # Header row
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 10),
    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

    # Data rows
    ('FONTNAME', (0, 1), (-1, -1), 'MSYH'),
    ('FONTSIZE', (0, 1), (-1, -1), 9),
    ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),  # Numbers right-aligned

    # Alternating row colors
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),

    # Grid
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#003366')),

    # Padding
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
]))

story.append(table)
```

## Charts (matplotlib → reportlab)

```python
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.platypus import Image

# Create chart
fig, ax = plt.subplots(figsize=(6, 3))
ax.bar(['Q1', 'Q2', 'Q3', 'Q4'], [100, 120, 115, 140])
ax.set_title("Quarterly Revenue")
ax.set_ylabel("$mm")

# Save to buffer
buf = BytesIO()
fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
plt.close(fig)
buf.seek(0)

# Add to PDF
img = Image(buf, width=14*cm, height=7*cm)
story.append(img)
```

## Headers and Footers

```python
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate

def header_footer(canvas, doc):
    canvas.saveState()

    # Header
    canvas.setFont('MSYH', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2*cm, A4[1] - 1.5*cm, "Investment Research Report")
    canvas.drawRightString(A4[0] - 2*cm, A4[1] - 1.5*cm, "CONFIDENTIAL")
    canvas.line(2*cm, A4[1] - 1.7*cm, A4[0] - 2*cm, A4[1] - 1.7*cm)

    # Footer
    canvas.drawString(2*cm, 1*cm, f"Generated: {datetime.now().strftime('%Y-%m-%d')}")
    canvas.drawRightString(A4[0] - 2*cm, 1*cm, f"Page {doc.page}")

    canvas.restoreState()

doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
```

## Table of Contents

```python
from reportlab.platypus import TableOfContents

toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle('TOC1', fontName='MSYH-Bold', fontSize=11, leftIndent=20, spaceBefore=5),
    ParagraphStyle('TOC2', fontName='MSYH', fontSize=10, leftIndent=40, spaceBefore=3),
]
story.append(toc)
story.append(PageBreak())

# Use heading styles that notify TOC
h1_toc = ParagraphStyle('H1TOC', fontName='MSYH-Bold', fontSize=14)
# In doc.build, use MultiBuildDocument for TOC to work
```

## Page Breaks

```python
from reportlab.platypus import PageBreak, KeepTogether

# Force page break
story.append(PageBreak())

# Keep elements together (don't split across pages)
story.append(KeepTogether([
    Paragraph("Section Title", h1_style),
    table,
    Paragraph("Caption", body_style),
]))
```

## Multi-Column Layout

```python
from reportlab.platypus import Frame, PageTemplate

frame1 = Frame(2*cm, 2*cm, 8*cm, 25*cm, id='col1')
frame2 = Frame(11*cm, 2*cm, 8*cm, 25*cm, id='col2')

template = PageTemplate(id='TwoColumn', frames=[frame1, frame2])
doc.addPageTemplates([template])
```

## PDF Merge/Split (pypdf)

```python
from pypdf import PdfReader, PdfWriter

# Merge
writer = PdfWriter()
for pdf_path in ["file1.pdf", "file2.pdf"]:
    reader = PdfReader(pdf_path)
    for page in reader.pages:
        writer.add_page(page)
writer.write("merged.pdf")

# Split (extract pages 1-5)
reader = PdfReader("input.pdf")
writer = PdfWriter()
for i in range(min(5, len(reader.pages))):
    writer.add_page(reader.pages[i])
writer.write("first_5_pages.pdf")
```
