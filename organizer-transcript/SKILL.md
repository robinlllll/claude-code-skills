---
name: organizer-transcript
description: Earnings Transcript Organizer - Organize FactSet/Callstreet transcript PDFs from Downloads into company folders
---

# Earnings Transcript Organizer

Organizes earnings call transcript PDFs from Downloads into structured company folders. Includes a web browser for viewing transcripts, generating analysis prompts, and running AI analysis with Obsidian integration.

## Project Location

`C:\Users\thisi\.claude\skills\organizer-transcript`

## When to Use This Skill

- User wants to organize transcript files
- User mentions earnings transcripts or call transcripts
- User wants to clean up downloaded PDFs
- User says "organize transcripts" or "transcript organizer"
- User wants to browse transcripts or generate analysis prompts
- User wants to analyze earnings with Claude or Gemini
- User says "analyze [TICKER]" or "transcript analysis"

## What It Does

### 1. Organizer
- Scans Downloads folder for transcript PDFs
- Extracts company name and ticker from filename
- Creates company folders: `{Company Name} ({TICKER})`
- Moves PDFs into appropriate folders
- Updates job registry with run stats
- **Auto-refreshes browser** when new transcripts are organized

### 2. Browser (http://localhost:8008)
- Browse all 600+ companies with transcripts
- Search by ticker or company name
- **Recently added transcripts appear first** with "NEW" badge
- Select quarters and generate analysis prompts
- **Direct AI Analysis** - Analyze with Gemini 2.5 Pro (button in browser)
- **Obsidian Integration** - Analyses saved to `Obsidian Vault/研究/财报分析/`
- Save company-specific notes and follow-up questions
- Track analysis history with AI responses and comments

### 3. Claude Analysis (Direct in Claude Code)
For Claude Opus 4.5 analysis, use this skill directly:
```
/organizer-transcript analyze TICKER Q1 2025 Q4 2024
```
Claude Code will read the PDFs and provide analysis - no API key needed!

## Key Files

| File | Purpose |
|------|---------|
| `organize_transcripts.py` | Main organizer script |
| `browser/app.py` | FastAPI browser backend (port 8008) |
| `browser/indexer.py` | Transcript indexer |
| `browser/obsidian.py` | Obsidian vault writer |
| `browser/ai_provider.py` | AI provider abstraction |
| `browser/data/` | Notes, history, recent additions |
| `browser/.env` | API keys (Gemini configured) |

## Commands

### Organize Transcripts
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/organizer-transcript/organize_transcripts.py"
```

### Start Browser
```bash
cd "C:/Users/thisi/.claude/skills/organizer-transcript/browser" && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe app.py
```
Then open http://localhost:8008

### Direct Claude Analysis
When user asks to analyze a company:
1. Read the transcript PDFs from `Downloads/Earnings Transcripts/{Company} ({TICKER})/`
2. Apply the analysis prompt template
3. Provide structured analysis directly in conversation

## Workflow Options

### Option A: Web Browser (Gemini)
1. Start browser at http://localhost:8008
2. Select company and quarters
3. Click "Analyze with Gemini 2.5 Pro"
4. Add comments → Save to Obsidian

### Option B: Claude Code (Claude Opus 4.5)
1. User: "analyze WOSG Q2 2026 vs Q4 2025"
2. Claude Code reads PDFs directly
3. Returns structured analysis
4. User can save to Obsidian via browser

## Browser Features

| Feature | Description |
|---------|-------------|
| Company Search | Search by ticker or name |
| Recently Added | New transcripts appear first with green badge |
| Company Notes | Save background notes per company |
| Follow-up Questions | Track questions for next quarter's analysis |
| Analysis History | Store AI responses and your comments |
| Quick Select | "Latest 2 Quarters" or "All Earnings" buttons |
| Direct AI Analysis | Gemini 2.5 Pro button (1-2 min) |
| Obsidian Save | Auto-saves to `研究/财报分析/{TICKER}/` |
| Open in Obsidian | Click to open analysis in Obsidian app |

## Obsidian Integration

Analyses are saved to:
```
C:\Users\thisi\Documents\Obsidian Vault\研究\财报分析\
└── {TICKER}/
    ├── 2026-02-04 1630 TICKER Q2 2026 vs Q4 2025 Analysis.md
    └── _TICKER Notes.md
```

Each analysis file includes:
- YAML frontmatter with tags
- AI analysis content
- User comments
- Follow-up questions (auto-extracted)
- Source transcript references

## API Configuration

API keys in `browser/.env`:
```
GOOGLE_API_KEY=...  # For Gemini (configured)
ANTHROPIC_API_KEY=... # For Claude API (optional)
```

**Note:** Claude analysis via Claude Code doesn't need an API key!

## Input

Transcript PDFs in Downloads matching patterns:
- `CORRECTED TRANSCRIPT_*.pdf`
- `TRANSCRIPT_*.pdf`
- `CALLSTREET REPORT_*.pdf`
- `*earnings call*.pdf`

## Output

- Organized folders at `C:\Users\thisi\Downloads\Earnings Transcripts\{Company} ({Ticker})\`
- Analysis files in `C:\Users\thisi\Documents\Obsidian Vault\研究\财报分析\`
