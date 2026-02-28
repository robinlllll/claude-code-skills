---
name: telegram
description: "Telegram Bot - Unified mobile entry point for investment workflow. Smart routing for photos, URLs, PDFs, text. Ticker detection + Gemini analysis + Obsidian save. Use when user says 'start bot', 'telegram', 'run bot', or needs to manage the Telegram bot."
metadata:
  version: 1.0.0
---

# Telegram Bot — 统一移动入口

Unified mobile entry point: forward any content → auto-analyze + ticker detect + Obsidian save + next action suggestions.

## Project Location

`C:\Users\thisi\Screenshots`

## When to Use This Skill

- User wants to start/manage the Telegram bot
- User mentions saving content from Telegram
- User wants to configure mobile workflow

## Key Files

- `telegram_photo_bot.py` - Main bot script (~2500 lines)
- `run_bot.bat` - Run with visible window
- `run_bot_hidden.vbs` - Run silently in background
- `.env` - Bot token + Notion config

## Commands

### Start Bot
```bash
cd "C:\Users\thisi\Screenshots" && python telegram_photo_bot.py
```

### Start Bot (Background)
```bash
cd "C:\Users\thisi\Screenshots" && start run_bot_hidden.vbs
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/pos [TICKER]` | Portfolio positions |
| `/t TICKER` | Quick thesis view |
| `/13f TICKER` | Institutional holders |
| `/kc TICKER` | Kill criteria |
| `/size TICKER` | Position sizing |
| `/dj` | Decision journal |
| `/sync` | IBKR sync |

## Task Dispatch Tiers

| Tier | Commands | Mechanism |
|------|----------|-----------|
| Tier 1 | /task, /plan, /brief, /coverage, /rq | Direct import — runs immediately |
| Tier 2 | Push notifications | Via `shared/telegram_notify.py` |
| Tier 3 | /do (custom tasks) | Inline keyboard → SQLite queue for later processing |

## Content Routing

- **Photos** → Claude Vision + ticker detect + ChatGPT prompt
- **PDFs** → pdfplumber + Gemini analysis
- **URLs** → WeChat/Substack/Xueqiu/generic smart routing
- **Text** → ticker query / trade note / thought analysis / quick note

## Output

- Photos: `Screenshots/inbox/` + GitHub + Notion + Obsidian
- Articles: `Documents/Obsidian Vault/收件箱/`
- Substack: `Documents/Obsidian Vault/信息源/Substack/{author}/`
- Xueqiu: `Documents/Obsidian Vault/信息源/雪球/`

## Dependencies

shared/ticker_detector, shared/entity_resolver, shared/frontmatter_utils, shared/13f_query, Gemini 2.0 Flash, trafilatura, pdfplumber
