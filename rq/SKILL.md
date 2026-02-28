---
name: rq
description: 财报分析研究问题路由器 - 从分析文件读取 [?] 问题，双AI（GPT+Grok）并行回答，集中写入文件顶部
---

# Research Questions Router (`/rq`)

从 Obsidian 财报分析文件中读取 `[?]` 标记的研究问题，自动组装上下文（全局分析摘要 + 每题局部段落上下文 + 投资论点），并行发送至 GPT-5.2 和 Grok，双 AI 回答集中写入文件顶部。

## Syntax

```
/rq TICKER              # 双AI回答，写入顶部（默认）
/rq TICKER --followup   # 追问模式：携带上轮问答上下文，答案追加到已有section
/rq TICKER --dry-run    # 预览 prompt，不发送
/rq TICKER --file PATH  # 指定分析文件
/rq TICKER --model o3   # 指定 GPT 模型（默认 gpt-5.2）
/rq TICKER --gpt-only   # 仅 GPT，不发 Grok
/rq TICKER --inline     # 旧模式：逐题回答写在问题下方
```

## Workflow

1. **Read** `SKILL.md` instructions (you are here)
2. **Run** the script:
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/research_questions.py TICKER [OPTIONS]
   ```
3. **Report** results to user (questions answered, any failures)

## Question Format (in Obsidian)

Users add questions **anywhere in the analysis file** (inline, next to the relevant paragraph). Supports multiple formats:

```markdown
...管理层声称利润率将改善但未给出路径 (p.12)...

- [?] 行业数据是否支持利润率改善？竞争对手同期利润率趋势如何？
？这个跟历史比较怎么样
- ? 能不能解释一下这个概念
```

**Accepted markers:** `- [?]`, `- ?`, `- ？`, `？` at line start, `N. ？`
All are auto-converted to `- [?]` format before processing.

## Answer Quality Design

**Key improvement over v1:** The prompt tells AI models to provide **incremental value** — not to restate what's already in the analysis, but to add:
- Industry cross-comparisons (competitor data)
- Historical trend analysis
- External data validation
- Independent reasoning and judgment

Each question is sent with its **local context** (the paragraph it sits next to), so AI models understand what specific section the question relates to.

## Answer Format (After `/rq` runs)

Answers appear as a concentrated section at the top of the file:

```markdown
## Research Questions — AI Answers

> 10 questions | 2026-02-13 00:25

### GPT-5.2

Q1. 原题全文
回答内容...

Q2. 原题全文
回答内容...

### Grok

Q1. 原题全文
回答内容...

---
```

Inline questions are marked as answered: `- [?]` → `- [x]`

## Context Assembly

The script automatically reads:
- **Section 1 综合评估** from the analysis (~6k chars) — global context
- **Section 2 业绩概览** performance data (~2k chars) — financial data
- **Per-question local context** (~500 chars each) — the paragraph surrounding each [?]
- **Thesis** bull/bear case from `PORTFOLIO/research/companies/{TICKER}/thesis.md` (~2k chars)
- Falls back to first 8k chars of AI Analysis if Section 1 not found

## Available Models

| Name | Flag | Notes |
|------|------|-------|
| o3 | (default) | Reasoning model, best for analytical questions |
| GPT-5.2 | `--model gpt-5.2-chat-latest` | Broad knowledge, creative |
| o4-mini | `--model o4-mini` | Fast reasoning |
| GPT-4o | `--model gpt-4o` | Multimodal |
| Grok | (always included) | Contrarian/market structure angle |

## Follow-up Mode

`--followup` enables multi-round Q&A on the same analysis file:

1. **Round 1:** Run `/rq TICKER` — first batch of questions answered, marked `[x]`
2. **Read answers**, add new `[?]` follow-up questions in the file
3. **Round 2:** Run `/rq TICKER --followup` — prior answers injected as context, AI builds on them
4. Repeat as needed — each followup appends to the same answer section

**How it works:**
- Extracts existing `## Research Questions — AI Answers` section (~6k chars cap)
- Injects as "上一轮研究问答" in the prompt, telling AI to not repeat prior content
- New answers appended with `── Follow-up | N questions | timestamp ──` divider
- If no prior answers exist, falls back to normal mode automatically

## Examples

```bash
# Default: dual-AI (GPT + Grok), answers at top
/rq SHOP-CA

# Follow-up: add new [?] questions, then run with prior context
/rq SHOP-CA --followup

# Preview followup prompt without sending
/rq SHOP-CA --followup --dry-run

# GPT only, skip Grok
/rq APP-US --gpt-only

# Use reasoning model
/rq HOOD-US --model o3

# Legacy inline mode (answers below each question)
/rq SHOP-CA --inline
```

## Dependencies

- `shared/research_questions.py` — Core script
- OpenAI API key in `chatgpt/data/config.json`
- Grok API key in `socratic-writer/data/config.json`
- `openai` Python package
