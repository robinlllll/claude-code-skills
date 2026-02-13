---
name: 13f
description: 13F Fund Manager Downloader - Download institutional investor holdings data from SEC EDGAR
---

# 13F Fund Manager Downloader

Download institutional investor holdings data from SEC EDGAR (same source as WhaleWisdom). Exports to CSV and JSON. AI analysis via 3-step pipeline: Gemini 2-stage → Grok 2-stage → Grok Synthesis.

## Project Location

`C:\Users\thisi\13F-CLAUDE`

## When to Use This Skill

- User wants to download 13F filings
- User mentions institutional holdings, hedge fund positions, SEC EDGAR
- User wants to track fund manager portfolios
- User mentions WhaleWisdom alternative
- User wants to analyze holdings with AI (Gemini, Grok, Synthesis)

## Key Files

- `downloader.py` - Main script with watchlist
- `sec_client.py` - SEC EDGAR API client
- `webapp.py` - Web interface (localhost:8013)
- `ai_analyzer.py` - AI analysis prompt generator (2-stage)
- `history_builder.py` - Cross-quarter position history
- `position_chart.py` - Position weight charts
- `price_context.py` - Price attribution data
- `watchlist.json` - Fund managers to track

## 3-Step Analysis Pipeline (Default)

One command runs the full pipeline: Gemini 2-stage → Grok 2-stage → Grok Synthesis.

| Step | Engine | Content | Purpose |
|------|--------|---------|---------|
| 1 | Gemini | Stage 1 (描述) + Stage 2 (推理) | 量化叙事、配对交易逻辑 |
| 2 | Grok | Stage 1 (描述) + Stage 2 (推理) | 逆向思维、市场结构分析 |
| 3 | Grok | Synthesis of Gemini + Grok | 综合最终报告，解决分歧，PM行动建议 |

### Stage breakdown (per model)

| Stage | Content | Purpose |
|-------|---------|---------|
| Stage 1 | SUMMARY, PORTFOLIO DNA, CAPITAL FLOW, KEY CHANGES + ATTRIBUTION, THEMES, BOTTOM LINE | "发生了什么" — 描述型 |
| Stage 2 | LONG-TERM HOLDS, SHORT INFERENCE, CONVICTION SCORECARD, SCENARIO, RESEARCH, BLIND SPOTS | "意味着什么" — 推理型 |

## AI Analysis Workflow

### One-command (recommended)
```bash
python ai_analyzer.py MANAGER_FOLDER 2025-Q3 --model all --obsidian
# Output: gemini vN.md, grok vN.md, synthesis vN.md → all in Obsidian
```

### Programmatic (from Python / Claude Code)
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
from ai_analyzer import (
    load_manager_data, get_available_managers,
    run_two_stage_analysis, find_latest_obsidian_analysis,
    run_synthesis, save_to_obsidian,
)

data = load_manager_data('MANAGER_FOLDER', '2025-Q3')

# Step 1-2: Run Gemini + Grok 2-stage
run_two_stage_analysis(data, model='gemini', obsidian=True, folder_name='MANAGER_FOLDER')
run_two_stage_analysis(data, model='grok', obsidian=True, folder_name='MANAGER_FOLDER')

# Step 3: Synthesis (reads latest Obsidian outputs)
manager_name = data.get('name', 'MANAGER_FOLDER')
gp = find_latest_obsidian_analysis(manager_name, '2025-Q3', 'gemini')
kp = find_latest_obsidian_analysis(manager_name, '2025-Q3', 'grok')
run_synthesis(gp.read_text(encoding='utf-8'), kp.read_text(encoding='utf-8'), manager_name, '2025-Q3')
```

### Generate dashboard chart (optional)
```python
from position_chart import generate_dashboard
generate_dashboard('MANAGER_FOLDER')
# Saves dashboard.png to manager's Obsidian folder
```

## CLI Commands

```bash
# Full 3-step pipeline (recommended): Gemini + Grok + Synthesis → Obsidian
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all --obsidian

# Single model only (no synthesis)
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model gemini --obsidian
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model grok --obsidian

# Legacy single-stage mode
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model gemini --single-stage

# List available managers
python ai_analyzer.py --list 2025-Q3

# Cross-holdings analysis (stocks held by 3+ managers)
python ai_analyzer.py --cross 2025-Q3 --model all

# Build history for all managers (run before analysis)
python history_builder.py --all

# Generate charts for a manager
python position_chart.py MANAGER_FOLDER
```

## AI Analysis Engines

| Engine | Role | API Key |
|--------|------|---------|
| Gemini | 量化叙事、配对逻辑 | GEMINI_API_KEY in .env |
| Grok | 逆向思维、市场结构 + Synthesis | XAI_API_KEY in .env |

**Note:** Claude and ChatGPT models are deprecated for 13F analysis. Use `--model all` (Gemini + Grok + Synthesis).

## Output Locations

- **13F Data**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}_{CIK}/`
- **AI Prompts**: `C:\Users\thisi\13F-CLAUDE\output\_prompts/`
- **AI Analysis**: `C:\Users\thisi\13F-CLAUDE\output\_analysis/`
- **Charts**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}/_charts/`
- **Obsidian Notes**: `C:\Users\thisi\Documents\Obsidian Vault\13F\`
