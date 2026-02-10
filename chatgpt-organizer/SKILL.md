# ChatGPT History

Parse, categorize, search, and export ChatGPT conversation history to Obsidian.

## Trigger

User says `/chatgpt-organizer` or asks to organize/search/analyze ChatGPT exports.

## What This Skill Does

Processes ChatGPT data exports (ZIP files) into an organized, searchable knowledge base:
- **Parse** conversations using iterative back-trace (no RecursionError on deep trees)
- **Index** in SQLite with FTS5 full-text search
- **Categorize** via rule-based keywords + Gemini Flash for ambiguous cases
- **Summarize** conversations using Gemini Flash
- **Export** to Obsidian Vault as organized Markdown with YAML frontmatter
- **Incremental** — re-importing the same export skips unchanged conversations and markdown files

## Instructions for Claude

**All commands use the standalone CLI at `~/chatgpt-history/`.**

```bash
PYTHON="/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe"
CLI="$HOME/chatgpt-history/chatgpt_history.py"
```

### Import from ZIP/JSON

**Large file guard (>100MB):** Print the command for the user to run in a separate terminal — Bun will crash from memory pressure on long-running tasks. For files ≤100MB, run normally.

```bash
# Basic import (DB only)
$PYTHON $CLI import <ZIP_OR_JSON_PATH>

# Import + categorize + write Obsidian markdown
$PYTHON $CLI import <ZIP_OR_JSON_PATH> --categorize --markdown

# Import + everything (categorize + summarize + markdown)
$PYTHON $CLI import <ZIP_OR_JSON_PATH> --categorize --summarize --markdown
```

Incremental behavior:
- Conversations already in DB with same `update_time` → skipped
- Markdown files already on disk with newer mtime than `update_time` → skipped
- Output shows: `X new, Y updated, Z skipped`

### Search

```bash
$PYTHON $CLI search "keyword"
$PYTHON $CLI search "portfolio" --category investment-research
$PYTHON $CLI search --ticker AAPL
$PYTHON $CLI search "code" --model gpt-4 --limit 10
$PYTHON $CLI search "valuation" --json          # machine-readable output
$PYTHON $CLI search "PM" --preview              # show content preview
```

### Statistics

```bash
$PYTHON $CLI stats
$PYTHON $CLI stats --json
```

### Categorization

```bash
# Rule-based only (free, instant)
$PYTHON $CLI categorize

# Rule-based + Gemini for ambiguous
$PYTHON $CLI categorize --gemini

# Re-categorize all conversations
$PYTHON $CLI categorize --recategorize --gemini
```

### AI Summaries (requires GEMINI_API_KEY)

```bash
$PYTHON $CLI summarize
$PYTHON $CLI summarize --category investment-research
$PYTHON $CLI summarize --limit 50
$PYTHON $CLI summarize --force                  # re-summarize all
```

### Maintenance

```bash
$PYTHON $CLI rebuild-fts                        # rebuild FTS search index
```

## Categories

| ID | Label | Focus |
|----|-------|-------|
| investment-research | Investment Research | 投资, 估值, earnings, thesis |
| meeting-notes | Meeting Notes | 会议, 纪要, transcript |
| technical-coding | Technical / Coding | python, API, code, bug |
| personal-tax | Personal / Tax | tax, IRS, 报税, insurance |
| learning | Learning | explain, what is, 概念 |
| writing | Writing | write, draft, 文章, 润色 |
| data-analysis | Data Analysis | analyze, data, chart, CSV |
| other | Other | (fallback) |

## Output

- **Obsidian:** `Documents/Obsidian Vault/ChatGPT/{Category}/YYYY-MM-DD - title.md`
- **Database:** `~/chatgpt-history/data/chatgpt.db`
- **Config:** `~/chatgpt-history/config.json`

## Post-Import

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link ChatGPT/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。

## Dependencies

```
orjson, google-generativeai, python-dotenv, pathvalidate
```

Install: `$PYTHON -m pip install -r ~/chatgpt-history/requirements.txt`
