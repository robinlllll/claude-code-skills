---
name: pdf
description: "Use when tasks involve creating PDF reports, reading/extracting content from PDFs, or generating formatted documents. NOT for earnings transcripts (use /transcript-analyzer). Triggers on: PDF, report generation, read PDF, extract PDF, create document."
---

# PDF Skill (Read, Create, Analyze)

## When to Use

- Generate investment research reports as PDF
- Read and extract content from any PDF (tables, text, images)
- Create formatted documents (memos, briefs, summaries)
- Annotate or combine PDFs

**Boundary:** Earnings transcript PDFs → use `/transcript-analyzer`. This skill handles everything else.

## Workflow

### Reading PDFs
1. **Try text extraction first** — `pdfplumber` for digital PDFs
2. **If text extraction fails** (scanned/image PDF) — use Claude's vision to read the file directly
3. **For tables** — `pdfplumber.extract_tables()` → DataFrame
4. Extract what's needed, present to user

### Creating PDFs
1. **Confirm structure** — sections, content, layout requirements
2. **Build with reportlab** — see `references/reportlab-patterns.md`
3. **Handle Chinese text** — register font first (see references)
4. **Open for review** — `start output.pdf` (Windows auto-opens PDF viewer)
5. **Iterate** — adjust layout based on feedback

## Primary Tooling

| Tool | Use For |
|------|---------|
| `pdfplumber` | Text/table extraction from digital PDFs |
| `reportlab` | PDF generation with full layout control |
| `pypdf` | Merge, split, rotate existing PDFs |
| Claude Vision | Read scanned/image PDFs directly |

## Reading Patterns

```python
import pdfplumber

# Extract all text
with pdfplumber.open("input.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()

# Extract tables
with pdfplumber.open("input.pdf") as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            df = pd.DataFrame(table[1:], columns=table[0])
```

## Chinese Text Support

Chinese font registration is REQUIRED before any Chinese text output.
See `references/reportlab-patterns.md` for the complete font registration code with Windows font path.

## Quality Requirements

- Consistent typography, spacing, margins
- No clipped text, overlapping elements, or broken tables
- Charts and images: sharp, aligned, clearly labeled
- Headers/footers with page numbering
- Section hierarchy visually clear

## Output Convention

- Generate file → run `start output.pdf` to open
- Filenames: `{topic}_report_{date}.pdf`, `{ticker}_research_{date}.pdf`

## Dependencies

```
pip install reportlab pdfplumber pypdf
```

## References

- reportlab code patterns + font setup: `references/reportlab-patterns.md`
- Investment report template: `references/investment-report-template.md`
