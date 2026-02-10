---
name: meeting-transcript
description: Two-stage meeting transcript pipeline — ASR cleaning + analytical briefing via Gemini
---

# Meeting Transcript Pipeline

Two-stage pipeline for weekly investment meeting transcripts:
- **Stage 1 (ASR Clean)**: Chunks + corrects raw transcripts → verbatim cleaned record
- **Stage 2 (Briefing)**: Full-context analytical summary → per-company investment briefings with action hints

## When to Use This Skill

- User says `/meeting-transcript` or asks to clean/process meeting transcripts
- User has raw transcript files (txt, docx, pdf) that need ASR error correction
- User wants to batch process multiple meeting recordings into readable notes

## Key Features

**Stage 1 (ASR Clean):**
- **Dialect auto-detection**: Sichuan dialect vs Mandarin — adjusts prompt automatically
- **Smart chunking**: Splits long files at speaker boundaries (~15K chars) to avoid Gemini output truncation
- **Iterating dictionary**: Accumulates correction patterns across runs
- **Skip-if-exists**: Safely re-runnable — skips already processed files (>10KB)
- **Multi-format**: Reads .txt, .docx, .pdf source files
- **Retry mode**: Auto-deletes and reprocesses files below retention threshold

**Stage 2 (Briefing):**
- **Full-context analysis**: Sends entire cleaned transcript in one Gemini call (no chunking)
- **Per-company structure**: 4 anchors per company — 核心观点摘要、正文复述、潜在行动提示、关键跟踪点
- **Summary table**: One-line IC-ready table for all companies discussed
- **Obsidian backlink**: Frontmatter links briefing back to cleaned transcript via `[[wikilink]]`

## Key Files

- `scripts/batch_process.py` — Main processing script (both stages)
- `prompts/cleaning_prompt.md` — Stage 1: ASR cleaning prompt (editable)
- `prompts/briefing_prompt.md` — Stage 2: Analytical briefing prompt (editable)
- `data/dictionary.json` — Accumulated correction dictionary

## Dependencies

```bash
pip install google-genai python-dotenv pdfplumber python-docx
```

Requires `GEMINI_API_KEY` in `~/13F-CLAUDE/.env`.

## Commands

### Process all transcripts (default directories)
```bash
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py
```
Source: `~/Downloads/周会转写/原文转写/`
Output: `~/Documents/会议实录/`

### Process with custom directories
```bash
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py \
  --source "~/Downloads/my-transcripts/" \
  --output "~/Documents/Obsidian Vault/Meeting Notes/"
```

### Process a subset (by index range)
```bash
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --start 10 --end 20
```

### Retry files below threshold
```bash
# Delete and reprocess any file below 65% retention
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --retry --threshold 65
```

### Use a different Gemini model
```bash
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --model gemini-3-pro-preview
```

### Stage 2: Generate analytical briefings
```bash
# Generate briefings for all cleaned transcripts
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --briefing

# Generate briefing for a specific file (by index)
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --briefing --start 49 --end 50

# Force regeneration (overwrite existing)
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --briefing --force

# Use a different model for briefing
python ~/.claude/skills/meeting-transcript/scripts/batch_process.py --briefing --briefing-model gemini-3-pro-preview
```

## Output

**Stage 1:**
- **Location**: `~/Documents/会议实录/` (default)
- **Naming**: `YYYY-MM-DD-会议实录.md`
- **Format**: Cleaned markdown with speaker labels, company names bolded, metadata header

**Stage 2:**
- **Location**: `~/Documents/会议实录/` (same directory)
- **Naming**: `YYYY-MM-DD-周会分析.md`
- **Format**: Per-company investment briefing with 4 anchors + IC summary table
- **Frontmatter**: YAML with tickers, source backlink to cleaned transcript

## Workflow

```
Stage 1: ASR Clean
Source files (txt/docx/pdf)
  → Extract text (pdfplumber/python-docx)
  → Detect dialect (Sichuan markers count)
  → Split into ~15K char chunks at speaker boundaries
  → Send each chunk to Gemini with cleaning prompt + dictionary
  → Concatenate chunks
  → Save as YYYY-MM-DD-会议实录.md
  → Report retention ratio (target ≥80%)

Stage 2: Analytical Briefing
Cleaned transcript (YYYY-MM-DD-会议实录.md)
  → Strip frontmatter
  → Send FULL text to Gemini 2.5 Pro (no chunking)
  → Per-company analysis with 4 anchors
  → Detect tickers, generate frontmatter with source backlink
  → Save as YYYY-MM-DD-周会分析.md
```

## Known Issues

- **Gemini chunk shrinkage**: ~20-30% of chunks randomly return ~4K output from ~15K input (API-side issue). Retry usually fixes it.
- **Scanned PDFs**: pdfplumber can't extract text from image-only PDFs. These will be skipped.
- **Rate limiting**: 3s between chunks, 5s between files to avoid Gemini 429/500 errors.

## Customization

### Editing the cleaning prompt
The prompt at `prompts/cleaning_prompt.md` contains:
- Role definition (TMT/consumer analyst + dialect expert)
- Company name correction dictionary (core mappings)
- Formatting rules (metadata header, speaker labels, filler cleanup)
- Output requirements (≥80% retention, completeness priority)

Edit freely to add new company names, change formatting rules, or adjust the role.

## Post-Processing

After Stage 1 completes, suggest: "Processed N transcripts. Run `--briefing` to generate analytical summaries?"

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link 周会/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。

## Pipeline Tracking

**自动执行:** 每个 transcript 处理后，记录到 ingestion pipeline（如果 task_manager 可用）：
```python
try:
    from shared.task_manager import record_pipeline_entry
    record_pipeline_entry(
        canonical_key=canonical_key,  # from record_ingestion()
        item_type="meeting", item_title=transcript_filename,
        source_platform="meeting-transcript", obsidian_path=str(output_path),
        has_frontmatter=True, has_tickers=bool(tickers),
        has_framework_tags=bool(framework_sections),
        tickers_found=tickers, framework_sections=framework_sections,
    )
except ImportError:
    pass
```

### Growing the dictionary
The `data/dictionary.json` file accumulates corrections across runs. Add entries manually:
```json
{
  "corrections": [
    {"from": "错误词", "to": "正确词", "reason": "context note"}
  ]
}
```
