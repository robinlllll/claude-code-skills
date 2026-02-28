---
name: transcript-analyzer
description: "Earnings Transcript Analyzer - Claude earnings call analysis with 7-section structured output. Also handles peer comparison (同业对比). Use when user says 'analyze earnings', '分析财报', 'transcript', 'peer comparison', '同业对比', or shares an earnings PDF. For single-ticker only. 2+ tickers → /earnings-pipeline. Non-earnings PDFs → /pdf."
---

# Earnings Transcript Analyzer

## Quick Reference

| Item | Path / Value |
|------|-------------|
| Downloads (new) | `C:\Users\thisi\Downloads` (scan here first for today's PDFs) |
| Transcripts (organized) | `~/Downloads/Earnings Transcripts/{Company Name} ({TICKER})/` |
| Prompt template | `prompts/prompt_claude.py` → read for 7-section structure and rules |
| Insight Ledger | `~/Documents/Obsidian Vault/研究/财报分析/{TICKER}/_{TICKER} Insight Ledger.md` |
| Save path | `~/Documents/Obsidian Vault/研究/财报分析/{TICKER}/` |
| Email module | `shared/email_notify.py` → `send_analysis_email()` |
| Sample output | `samples/HOOD-US_Q4_2025_vs_Q3_2025.md` |
| Organizer script | `organize_transcripts.py` |
| Python | `/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe` |

## Main Workflow: Analyze Ticker

When user says "analyze TICKER", "分析 XX 财报", or similar — follow steps 1–8 exactly.

### Step 1: Parse Input

Extract from user message:
- **Ticker** (e.g., DASH → DASH-US)
- **Current quarter** (curr) and **previous quarter** (prev)
- If quarters not specified, auto-detect from the 2 most recent transcripts in the folder

### Step 1b: Query Vector Memory (Non-blocking)

Before analyzing, check if there's prior context for this ticker in vector memory. This runs in a try/except — failure does NOT block the analysis.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.vector_memory import query_similar, format_memories_for_context
results = query_similar('earnings analysis investment thesis', top_k=3, ticker='{TICKER}')
if results:
    print(format_memories_for_context(results, max_chars=2000))
else:
    print('No prior vector memories for {TICKER}')
"
```

If results are returned, inject them as a `## Prior Context` block when constructing the analysis prompt. This gives Claude historical awareness of how management narratives have evolved.

### Step 1c: Sector Resolution

Resolve the company's sector for sector-aware analysis:
1. Check `shared/entity_dictionary.yaml[TICKER].sector`
2. Map to framework sector using `shared/references/sector_metrics.yaml`
3. For broad sectors (Technology, Consumer Staples), refine using `key_products` and thesis context
4. Load `canonical_kpis` list for the resolved sector
5. Pass `{sector}` and `{sector_kpis}` variables to the prompt template

**Sub-sector mapping:**
- Technology → SaaS/Cloud | E-commerce | Ad Tech | Technology (General)
- Consumer Staples → Tobacco/Nicotine (PM, MO, BTI, SWMA) | Consumer Staples

### Step 2: Find Transcript PDFs

**Default search: `C:\Users\thisi\Downloads` (the Downloads root).** New transcripts land here, not in subfolders.

Search order:
1. **`C:\Users\thisi\Downloads\*.pdf`** — scan for today's transcript PDFs matching the ticker
2. **`C:\Users\thisi\Downloads\Earnings Transcripts\*({TICKER})\*.pdf`** — fallback for older/organized transcripts

Filter by filename containing `TRANSCRIPT` or `CALLSTREET`. Sort by date. Prefer CORRECTED over RAW for the same event.

When user says "find new transcripts" or "find today's transcripts": scan `C:\Users\thisi\Downloads\` for PDFs modified today whose filenames contain `TRANSCRIPT` or `CALLSTREET`. List all matches — do not look in `Earnings Transcripts/` subfolders for this.

If no PDFs found in either location, ask user to provide transcript files.

### Step 3: Read PDFs with Read Tool

**MUST use the Read tool** — it supports PDF natively. Do NOT use pdfplumber, PyPDF2, or any Python library.

```
Read(file_path="path/to/Q4_transcript.pdf")
Read(file_path="path/to/Q3_transcript.pdf")
```

For PDFs >20 pages, use the `pages` parameter: `Read(file_path="...", pages="1-20")` then `Read(file_path="...", pages="21-40")`.

### Step 4: Load Prior Insights

Check if Insight Ledger exists:
```
~/Documents/Obsidian Vault/研究/财报分析/{TICKER}/_{TICKER} Insight Ledger.md
```

If it exists, read it with the Read tool. Look for active insights (⏳ or 🔄 status) — these must be verified in Section 7 of the analysis. Also note resolved insights (✅ or ❌) for background context.

If no ledger exists, skip — Section 7 becomes conditional (omit it).

### Step 5: Read Prompt Template

Read `prompts/prompt_claude.py` in this skill directory. This file defines the exact analysis structure and rules. Follow it as your output framework.

**The 7 required sections:**
1. **综合评估与投资启示** — Synthesis, scenarios table, catalyst board
2. **业绩概览** — Performance table + guidance table (with classification tags)
3. **核心业绩驱动** — Segments, KPIs (with reliability tags), geography
4. **管理层叙事演变** — Narrative shift table
5. **Q&A透视** — Every question listed, scored, grouped by theme
6. **季度间主题演变** — Theme frequency comparison, modelability scoring
7. **前次 Insight 验证追踪** — Only if Step 4 found active insights

**Critical rules from the template:**
- Page citations: `({curr} transcript p.X)` format, ≥5 distinct locations
- **List every Q&A question** — never summarize or omit any
- Guidance items tagged: `NEW` / `REITERATED` / `RAISED` / `LOWERED` / `NARROWED` / `SOFTENED` / `WITHDRAWN`
- KPI data tagged: `[H]` Hard / `[D]` Derived / `[I]` Inferred
- Flag Prepared Remarks vs Q&A number inconsistencies
- Inline 3–5 `[?]` research questions scattered through the analysis body
- Style: 投行研究报告, not 新闻摘要

### Step 5b: Data Freshness Verification

Before beginning analysis, verify all data sources are current:

1. **Transcript date check:** Confirm the transcript PDF date matches the expected quarter. If the file is >90 days old relative to the analysis date, flag: "⚠️ This transcript is from {N} days ago. Confirm this is the correct quarter."
2. **Consensus estimate date:** If using cached consensus data, verify it is <7 days old. Stale consensus = misleading beat/miss analysis.
3. **Stock price reference:** Use today's price for valuation context, not a cached value. Pull fresh via yfinance.
4. **Prior quarter comparison:** If referencing prior quarter analysis, verify it exists in the vault. If not, note: "Prior quarter analysis not found — comparisons are vs. reported figures only."

**3-Month Rule:** Any external data point >90 days old must be flagged with ⚠️ and the date it was last verified.

### Step 6: Validate Output

Before saving, verify all 4 gates:
1. ✅ All 7 sections present (or 6 if no prior insights)
2. ✅ Page citations `(p.X)` in ≥5 distinct locations
3. ✅ Quarter labels match the requested curr/prev quarters
4. ✅ Each section has >100 characters of content

If any gate fails, fix inline before proceeding.

### Step 7: Save to Obsidian

Write to: `~/Documents/Obsidian Vault/研究/财报分析/{TICKER}/{YYYY-MM-DD} {HHMM} {TICKER} {curr} vs {prev} Analysis.md`

YAML frontmatter format:
```yaml
---
ticker: {TICKER}
company: {Company Name}
current_quarter: {curr}
previous_quarter: {prev}
quarters: [{curr}, {prev}]
date: {YYYY-MM-DD}
ai_provider: claude
tags: [earnings, transcript-analysis, {TICKER}]
---
```

After frontmatter, include hint line:
```
> [?] 提问语法: `- [?] 问题` | 运行 `/rq {TICKER}` 发送至 ChatGPT
```

Then `# {TICKER} {curr} vs {prev} Analysis` followed by `## AI Analysis` and the full analysis content.

### Step 7b: Store in Vector Memory (Non-blocking)

After saving to Obsidian, embed the analysis into vector memory for future semantic retrieval. This runs in a try/except — failure does NOT block email or any other step.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.vector_memory import upsert_from_file
result = upsert_from_file(r'{obsidian_path}')
print(f\"Vector memory: {result['inserted']} chunks stored\")
"
```

This extracts Section 1 (综合评估) and Section 4 (管理层叙事) and stores their embeddings. Future runs of `/transcript-analyzer` for the same ticker will retrieve these via Step 1b.

### Step 8: Send Email (Default — Do Not Ask)

After save, automatically send email. Run via Bash:
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.email_notify import send_analysis_email
content = open(r'{obsidian_path}', encoding='utf-8').read()
send_analysis_email('Earnings', '{TICKER} {curr} vs {prev}', content, obsidian_path=r'{obsidian_path}')
print('Email sent')
"
```

---

## Secondary Workflows

### Organize Transcripts
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/transcript-analyzer/organize_transcripts.py"
```

### Peer Comparison
When user says "比较 TICKER1 TICKER2" or "peer comparison":
1. Read `references/peer-comparison.md` for the full workflow
2. Use `prompts/prompt_peer.py` for the peer prompt template
3. Max 4 companies per comparison (context limit)
4. Save to `~/Documents/Obsidian Vault/研究/财报分析/_Peer Comparisons/`

---

## Citation & Source Attribution Standards

Every analysis output MUST include source attribution with links:

### Required Sources (include in every analysis)
- Earnings transcript: `[[{date} - {TICKER} Q{N} Transcript]]` (Obsidian wikilink)
- SEC filing: `[10-Q](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={TICKER}&type=10-Q&dateb=&owner=include&count=5)` (EDGAR search link)
- Earnings release: `[Press Release](investor.{company}.com)` if available
- Consensus estimates: Source + date (e.g., "FactSet consensus as of 2026-02-25")
- Prior guidance: Reference to previous quarter's analysis `[[{prev_date} - {TICKER} Q{N-1} Analysis]]`

### Citation Format in Analysis
When referencing specific data points, always include source:

**Good:** "Revenue of $352M beat consensus of $340M (FactSet, Feb 25) by 3.5%, per the Q4 earnings release"
**Bad:** "Revenue beat estimates"

### Source Block (append to every analysis file)
Append this block at the very end of every saved analysis file:

```
---
## Sources
- Transcript: [[{YYYY-MM-DD} - {TICKER} Q{N} {YYYY} Transcript]]
- SEC Filing: [10-Q on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={TICKER}&type=10-Q)
- Consensus: FactSet/Yahoo Finance as of {date}
- Prior Quarter: [[{prev analysis wikilink}]]
```

---

## Beat/Miss Quantification Format

ALL beat/miss comparisons MUST include both absolute and percentage:

**Mandatory format:** "{Metric} {beat/missed} by ${absolute} or {percentage}%"

Examples:
- "Revenue beat by $12M or 3.5%"
- "EPS missed by $0.03 or 4.2%"
- "Gross margin beat by 120bps (48.2% vs. 47.0% est.)"

For guidance comparisons:
- "FY26 revenue guided to $1.4B-$1.45B vs. consensus $1.42B (midpoint +1.1%)"

**Never write:** "Revenue beat estimates" or "EPS came in above consensus" without quantification.

---

## Key Files

| File | Purpose |
|------|---------|
| `prompts/prompt_claude.py` | **Claude analysis prompt template (MUST READ in Step 5)** |
| `prompts/prompt_peer.py` | Peer comparison prompt template |
| `organize_transcripts.py` | PDF organizer script |
| `samples/HOOD-US_Q4_2025_vs_Q3_2025.md` | **Reference output — match this format** |
| `references/peer-comparison.md` | Peer comparison workflow details |
