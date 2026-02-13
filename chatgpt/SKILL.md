---
name: chatgpt
description: ChatGPT API — ask questions, select models, multi-turn conversations
version: 2.0.0
---

# ChatGPT API Skill

Query OpenAI models via API. Supports one-shot questions, multi-turn conversations, and Q&A history persistence to JSON + Obsidian.

## When to Use

- Other skills need GPT as a reasoning backend (e.g., `socratic-writer`)
- You need to query a specific OpenAI model (gpt-5.2, o3, o4-mini, etc.)
- You want Q&A history searchable in Obsidian

## When NOT to Use

- Claude can answer the question directly
- You need web browsing / file upload (use ChatGPT web manually)

## Setup

```bash
# API key — set env var OR save to config
export OPENAI_API_KEY="sk-..."

# Or save to skill config
python scripts/chatgpt_api.py config set openai_api_key sk-...
```

Requires: `pip install openai` (already installed).

## Quick Start

```bash
# Ask a question (default model: gpt-5.2-chat-latest)
python scripts/chatgpt_api.py ask "What is 2+2?"

# Ask with model selection
python scripts/chatgpt_api.py ask "Explain quantum entanglement" --model o3

# Multi-turn conversation
python scripts/chatgpt_api.py conversation --model gpt-4o

# Skip history
python scripts/chatgpt_api.py ask "Quick check" --no-history

# Search history
python scripts/chatgpt_api.py history search --query "quantum"

# Show stats
python scripts/chatgpt_api.py history stats
```

## Programmatic Usage (from other skills)

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude/skills/chatgpt/scripts"))
from chatgpt_api import ask_chatgpt, ChatGPTSession

# One-shot
answer = ask_chatgpt("What is 2+2?")
answer = ask_chatgpt("Deep analysis needed", model="o3")
answer = ask_chatgpt("Quick check", no_history=True)

# Multi-turn
session = ChatGPTSession(model="gpt-4o")
a1 = session.ask("First question")
a2 = session.ask("Follow-up based on your answer")
session.end()  # Saves all Q&A to history
```

## Available Models

| Name | Key | Notes |
|------|-----|-------|
| GPT-5.2 | `gpt-5.2-chat-latest` | Default |
| o3 | `o3` | Reasoning |
| o4-mini | `o4-mini` | Fast reasoning |
| GPT-4o | `gpt-4o` | Multimodal |

## Data & Persistence

| Data | Location |
|------|----------|
| Config | `data/config.json` |
| Q&A history | `data/history.json` |
| Obsidian logs | `~/Documents/Obsidian Vault/ChatGPT/ChatGPT_YYYY-MM-DD.md` |

## Script Reference

| Script | Purpose |
|--------|---------|
| `chatgpt_api.py` | Core API wrapper + CLI |
| `history_manager.py` | Q&A persistence (JSON + Obsidian) |
