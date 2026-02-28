---
name: 13f
description: "13F Fund Manager Downloader - Download institutional investor holdings data from SEC EDGAR. Use when user says '13F', 'institutional holdings', 'fund manager', 'SEC filing', or asks about hedge fund positions."
metadata:
  version: 2.0.0
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

For CLI commands, programmatic API, email delivery, and engine details, see `references/cli-and-api.md`.

## Output Locations

- **13F Data**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}_{CIK}/`
- **AI Prompts**: `C:\Users\thisi\13F-CLAUDE\output\_prompts/`
- **AI Analysis**: `C:\Users\thisi\13F-CLAUDE\output\_analysis/`
- **Charts**: `C:\Users\thisi\13F-CLAUDE\output\{MANAGER}/_charts/`
- **Obsidian Notes**: `C:\Users\thisi\Documents\Obsidian Vault\13F\`
