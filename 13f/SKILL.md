---
name: 13f
description: 13F Fund Manager Downloader - Download institutional investor holdings data from SEC EDGAR
---

# 13F Fund Manager Downloader

Download institutional investor holdings data from SEC EDGAR (same source as WhaleWisdom). Exports to CSV and JSON. AI analysis via 2-stage prompts (Claude, Gemini, ChatGPT).

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
- `ai_analyzer.py` - AI analysis prompt generator (2-stage)
- `history_builder.py` - Cross-quarter position history
- `position_chart.py` - Position weight charts
- `price_context.py` - Price attribution data
- `watchlist.json` - Fund managers to track

## 2-Stage Analysis Architecture (Default)

Analysis is split into 2 stages for deeper output:

| Stage | Content | Purpose |
|-------|---------|---------|
| Stage 1 | SUMMARY, PORTFOLIO DNA, CAPITAL FLOW, KEY CHANGES + ATTRIBUTION, THEMES, BOTTOM LINE | "发生了什么" — 描述型 |
| Stage 2 | LONG-TERM HOLDS, SHORT INFERENCE, CONVICTION SCORECARD, SCENARIO, RESEARCH, BLIND SPOTS | "意味着什么" — 推理型 |

Stage 2 receives Stage 1 output as context for cross-referencing.

## AI Analysis Workflow

When user asks to analyze a manager's 13F:

### Step 1: Identify the manager and quarter
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
from ai_analyzer import (
    load_manager_data, get_available_managers,
    run_two_stage_analysis, build_single_manager_prompt,
    build_stage2_prompt, save_to_obsidian,
)
```

### Step 2: For Gemini and ChatGPT — use `run_two_stage_analysis()`
```python
data = load_manager_data('MANAGER_FOLDER', '2025-Q3')
# Runs both stages via API, merges, saves to Obsidian
result = run_two_stage_analysis(data, model='gemini', obsidian=True, folder_name='MANAGER_FOLDER')
result = run_two_stage_analysis(data, model='chatgpt', obsidian=True, folder_name='MANAGER_FOLDER')
```

### Step 3: For Claude — self-analysis (2 stages)
```python
data = load_manager_data('MANAGER_FOLDER', '2025-Q3')

# Stage 1: Build prompt, then YOU (Claude) analyze it
s1_prompt = build_single_manager_prompt(data, 'claude', 'general')
s1_prompt += "\n\n**语言要求：请用中文回答全部分析内容。表格列名保留英文，但分析、叙述、研究问题全部用中文。**"
# Read the prompt and produce Stage 1 analysis yourself

# Stage 2: Build prompt with your Stage 1 output, then analyze
s2_prompt = build_stage2_prompt(data, 'claude', stage1_output)
# Read the prompt and produce Stage 2 analysis yourself

# Merge and save
final = stage1_output + "\n\n---\n\n# 深度分析 (Stage 2)\n\n" + stage2_output
save_to_obsidian(final, 'MANAGER NAME', '2025-Q3', 'claude')
```

### Step 4: Generate dashboard chart
```python
from position_chart import generate_dashboard
generate_dashboard('MANAGER_FOLDER')
# Saves dashboard.png to manager's Obsidian folder
```

### Running all 3 models in parallel
For efficiency, launch Gemini and ChatGPT as background Task subagents while Claude self-analyzes in the main context. Each subagent calls `run_two_stage_analysis()`.

## CLI Commands

```bash
# 2-stage analysis (default) — Gemini/ChatGPT call API, Claude saves prompts
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all --obsidian

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

## AI Analysis Modes

| Model | Delivery | 2-Stage Support |
|-------|----------|-----------------|
| Claude | Self-analysis in Claude Code | Yes (2 sequential self-analyses) |
| Gemini | API call (GEMINI_API_KEY in .env) | Yes (2 API calls, auto-merged) |
| ChatGPT | API call (OPENAI_API_KEY in .env) | Yes (2 API calls, auto-merged) |

## GPT-5.2 API Quirks
- Use `max_completion_tokens` (NOT `max_tokens`)
- Do NOT set `temperature` (only default 1 supported)

## Output Locations

- **13F Data**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}_{CIK}/`
- **AI Prompts**: `C:\Users\thisi\13F-CLAUDE\output\_prompts/`
- **AI Analysis**: `C:\Users\thisi\13F-CLAUDE\output\_analysis/`
- **Charts**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}/_charts/`
- **Obsidian Notes**: `C:\Users\thisi\Documents\Obsidian Vault\13F\`
