---
name: rq
description: 财报分析研究问题路由器 - 从分析文件读取 [?] 问题，组装上下文，发送 ChatGPT，回答写回原文件
---

# Research Questions Router (`/rq`)

从 Obsidian 财报分析文件中读取 `[?]` 标记的研究问题，自动组装上下文（分析核心发现 + 业绩数据 + 投资论点），发送至 ChatGPT API，回答以 blockquote 格式写回原文件。

## Syntax

```
/rq TICKER              # 处理最新分析文件的所有 [?] 问题
/rq TICKER --dry-run    # 预览 prompt，不发送
/rq TICKER --file PATH  # 指定分析文件
/rq TICKER --model o3   # 指定模型（默认 gpt-5.2）
```

## Workflow

1. **Read** `SKILL.md` instructions (you are here)
2. **Run** the script:
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/research_questions.py TICKER [--dry-run] [--file PATH] [--model MODEL]
   ```
3. **Report** results to user (questions answered, any failures)

## Question Format (in Obsidian)

Users add questions in the `## Research Questions` section of analysis files:

```markdown
## Research Questions

- [?] SHOP Merchant Solutions 毛利率连续3季下滑的结构性原因是什么？
- [?] UCP vs ACP 技术架构对比？
```

After `/rq` runs, answered questions become:

```markdown
- [x] SHOP Merchant Solutions 毛利率连续3季下滑的结构性原因是什么？
  > **GPT-5.2 | 2026-02-11 14:30**
  >
  > Merchant Solutions 毛利率下滑主要由支付渗透率提升驱动...
```

## Context Assembly

The script automatically reads:
- **Section 1 综合评估** from the analysis (~4k chars)
- **Section 2 业绩概览** performance data (~2k chars)
- **Thesis** bull/bear case from `PORTFOLIO/research/companies/{TICKER}/thesis.md` (~2k chars)
- Falls back to first 8k chars of AI Analysis if Section 1 not found

## Available Models

| Name | Flag | Notes |
|------|------|-------|
| GPT-5.2 | (default) | Best for deep analysis |
| o3 | `--model o3` | Reasoning model |
| o4-mini | `--model o4-mini` | Fast reasoning |
| GPT-4o | `--model gpt-4o` | Multimodal |

## Examples

```bash
# Basic: process all [?] questions for SHOP-CA
/rq SHOP-CA

# Preview prompts without sending
/rq SHOP-CA --dry-run

# Use reasoning model for complex questions
/rq HOOD-US --model o3

# Specific file
/rq SHOP-CA --file "~/Documents/Obsidian Vault/研究/财报分析/SHOP-CA/2026-02-11 SHOP-CA Q4 2025 vs Q3 2025 Analysis.md"
```

## Dependencies

- `shared/research_questions.py` — Core script
- `chatgpt/scripts/chatgpt_api.py` — `ask_chatgpt()` function
- OpenAI API key configured (env var or chatgpt skill config)
