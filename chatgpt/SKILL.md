---
name: chatgpt
description: ChatGPT browser automation - ask questions, select models, multi-turn conversations
version: 1.0.0
---

> ℹ️ **备用工具** — 日常多AI协同请用 `/write --team`（socratic-writer）。本工具仅在需要特定 GPT 模型（如 o3）或上传文件到 ChatGPT 网页版时使用。

# ChatGPT Browser Automation Skill

Reusable ChatGPT automation via Patchright (Playwright fork). Opens a visible Chrome browser, types questions, detects responses using dual stop-button + text-stability polling, and persists Q&A to JSON + Obsidian.

## When to Use

- Other skills need ChatGPT as a reasoning backend (e.g., `socratic-writer`)
- You need to query ChatGPT with model selection (o3, gpt-4o, etc.)
- You want Q&A history searchable in Obsidian

## When NOT to Use

- Claude can answer the question directly — no need for ChatGPT
- The task requires the ChatGPT API (use the OpenAI SDK instead)
- Headless automation — ChatGPT blocks headless browsers

## Quick Start

```bash
# First time: setup venv + install deps
python scripts/run.py setup_environment

# Authenticate (opens browser for manual login)
python scripts/run.py auth_manager setup

# Ask a question
python scripts/run.py ask_question --question "What is 2+2?"

# Ask with model selection
python scripts/run.py ask_question --question "Explain quantum entanglement" --model o3

# Multi-turn interactive session
python scripts/run.py conversation interactive --model gpt-4o
```

## Core Workflow

### One-Shot Q&A (`ask_question.py`)

The primary entry point. Each call opens a fresh browser session:

1. Auth check → launch persistent Chrome context (visible)
2. Navigate to chatgpt.com → wait for page load
3. Dismiss popups → select model (if specified)
4. Click-focus input → `page.keyboard.type()` (ProseMirror compatible)
5. Click send button (or fallback Enter)
6. **Dual response detection:**
   - Layer 1: Stop button visible → still generating (progress every 15s)
   - Layer 2: Text stability — 3 identical reads at 1.5s intervals
7. Save cookies → persist to history → return text

```python
# Programmatic usage from other skills
from ask_question import ask_chatgpt

answer = ask_chatgpt("What is 2+2?", model="o3")
```

### Multi-Turn Conversation (`conversation.py`)

Keeps browser open across questions:

```bash
# Interactive REPL
python scripts/run.py conversation interactive --model o3
# Type questions, get answers, empty line to end
```

## Script Reference

| Script | Purpose | CLI |
|--------|---------|-----|
| `ask_question.py` | One-shot Q&A | `--question "..." [--model o3] [--no-history]` |
| `conversation.py` | Multi-turn sessions | `interactive [--model o3]` |
| `auth_manager.py` | Login management | `setup\|status\|validate\|clear\|reauth` |
| `history_manager.py` | Q&A history | `search --query "..."\|list\|stats` |
| `debug_selectors.py` | Selector diagnostics | (no args — opens browser, reports) |
| `config.py` | All selectors + config | (imported, not run directly) |
| `browser_utils.py` | BrowserFactory + stealth | (imported, not run directly) |
| `run.py` | Venv wrapper | `<script_name> [args]` |
| `setup_environment.py` | First-time setup | `[--check]` |

## Model Selection

Available models (update `MODEL_MAPPINGS` in `config.py` when ChatGPT changes):

| Name | Key | Timeout |
|------|-----|---------|
| o3 | `o3` | 300s (thinking) |
| GPT-4o | `gpt-4o` | 120s |
| GPT-4 | `gpt-4` | 120s |
| GPT-4.5 | `gpt-4.5` | 120s |
| o4-mini | `o4-mini` | 120s |
| o4-mini-high | `o4-mini-high` | 300s (thinking) |
| Deep Research | `deep-research` | 300s (thinking) |

## Data & Persistence

| Data | Location |
|------|----------|
| Browser state | `data/browser_state/state.json` |
| Chrome profile | `data/browser_state/browser_profile/` |
| Auth metadata | `data/auth_info.json` |
| Q&A history | `data/history.json` |
| Obsidian logs | `~/Documents/Obsidian Vault/ChatGPT/ChatGPT_YYYY-MM-DD.md` |

## Troubleshooting

### "Not authenticated"
```bash
python scripts/run.py auth_manager setup
```

### Selectors broken (UI changed)
```bash
python scripts/run.py debug_selectors
```
This shows which selectors match and which are broken. Update `config.py` accordingly.

### Model not found in menu
The model picker UI changes frequently. Run `debug_selectors.py` to see current button labels, then update `MODEL_MAPPINGS` in `config.py`.

### Response timeout
- Thinking models (o3, deep-research) have 300s timeout — this is normal
- If standard models timeout, check that the stop button selector still works
- Run `debug_selectors.py` to verify `STOP_BUTTON_SELECTORS`

### ProseMirror typing issues
The skill uses `page.keyboard.type()` instead of `element.fill()` because ChatGPT's contenteditable div (ProseMirror) only processes real keyboard events. If typing fails, the input selector may have changed — check `INPUT_SELECTORS` in config.

## Integration with Other Skills

Other skills can import `ask_chatgpt` directly:

```python
import sys
sys.path.insert(0, str(Path.home() / ".claude/skills/chatgpt/scripts"))
from ask_question import ask_chatgpt

# Simple query
answer = ask_chatgpt("Analyze this argument: ...")

# With model selection
answer = ask_chatgpt("Deep analysis needed", model="o3")

# Skip history (for internal queries)
answer = ask_chatgpt("Quick check", no_history=True)
```

For multi-turn from code:

```python
from conversation import ChatGPTSession

session = ChatGPTSession()
session.start(model="gpt-4o")
answer1 = session.ask("First question")
answer2 = session.ask("Follow-up based on your answer")
session.end()  # Saves all Q&A to history
```

## Architecture Notes

- **Browser mode:** Always visible (`headless=False`) — ChatGPT actively blocks headless
- **Browser pattern:** `launch_persistent_context` — better fingerprint persistence than `new_context`
- **Input method:** `page.keyboard.type()` — ProseMirror rejects `fill()` on contenteditable
- **Response detection:** Dual algorithm (stop-button + text stability polling)
- **Auth expiry:** 3 days (ChatGPT sessions expire faster than Google)
- **Config centralization:** All selectors in `config.py` — single file to update on UI changes
