---
name: 13f
description: 13F Fund Manager Downloader - Download institutional investor holdings data from SEC EDGAR
---

# 13F Fund Manager Downloader

Download institutional investor holdings data from SEC EDGAR (same source as WhaleWisdom). Exports to CSV and JSON.

## Project Location

`C:\Users\thisi\13F-CLAUDE`

## When to Use This Skill

- User wants to download 13F filings
- User mentions institutional holdings, hedge fund positions, SEC EDGAR
- User wants to track fund manager portfolios
- User mentions WhaleWisdom alternative
- User wants to analyze holdings with AI (Claude, Gemini, ChatGPT)

## Key Files

- `downloader.py` - Main script with watchlist
- `sec_client.py` - SEC EDGAR API client
- `webapp.py` - Web interface (localhost:8013)
- `ai_analyzer.py` - AI analysis prompt generator
- `watchlist.json` - Fund managers to track

## Commands

### Download 13F Filings
```bash
cd "C:\Users\thisi\13F-CLAUDE" && python downloader.py
```

### Start Web Interface
```bash
cd "C:\Users\thisi\13F-CLAUDE" && python webapp.py
```

### AI Analysis

```bash
# List available managers
python ai_analyzer.py --list 2025-Q3

# Generate prompts for all 3 AIs (Claude, Gemini, ChatGPT)
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all

# Specific AI
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model gemini

# Cross-holdings analysis (stocks held by 3+ managers)
python ai_analyzer.py --cross 2025-Q3 --model all

# Focus options: general, changes, sectors, new_positions
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --focus changes
```

### Install Dependencies
```bash
cd "C:\Users\thisi\13F-CLAUDE" && pip install -r requirements.txt
```

## AI Analysis Modes

| Model | Delivery |
|-------|----------|
| Claude | Prompt saved to file, paste into Claude Code |
| Gemini | Direct API call (requires GEMINI_API_KEY in .env) |
| ChatGPT | Copied to clipboard, paste into ChatGPT |

## Output Locations

- **13F Data**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}_{CIK}/`
- **AI Prompts**: `C:\Users\thisi\13F-CLAUDE\output\_prompts/`
- **AI Analysis**: `C:\Users\thisi\13F-CLAUDE\output\_analysis/`
- **Obsidian Notes**: `C:\Users\thisi\Documents\Obsidian Vault\13F\`
