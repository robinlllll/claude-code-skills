---
name: review
description: "定期投资回顾 - 聚合 Portfolio、Research、周会、Inbox 活动，生成周/月回顾报告，输出到 Obsidian。Use when user says 'review', '回顾', 'weekly review', 'monthly review', or asks for investment performance summary."
metadata:
  version: 1.0.0
---

# /review - 定期投资回顾

聚合一段时间内的投资活动：交易、研究、周会讨论、收件箱处理，生成结构化回顾报告。

## Instructions for Claude

**自动创建目录：** 如果 `~/Documents/Obsidian Vault/写作/投资回顾/` 不存在，自动创建。

**时间范围计算：**
- `week` = 过去 7 天（从上周一到本周日）
- `month` = 过去 30 天（上月同日到今天）
- `YYYY-MM-DD to YYYY-MM-DD` = 自定义范围

**数据源扫描：** 并行扫描 12 个数据源（Portfolio, Research Notes, Earnings, Thesis, 周会, 收件箱, Podcast, 13F, Supply Chain, ChatGPT, NotebookLM, Attribution）。详见 `references/data-sources.md`。

## When to Use This Skill

- 用户使用 `/review week`、`/review month` 等
- 用户说"回顾一下这周/这个月的情况"
- 每周五下午或月末适合运行

## 配置

- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

## Core Workflow

```
输入时间范围
       ↓
[1] 计算日期范围
    • week/month/custom → start_date, end_date
       ↓
[2] 并行扫描所有数据源
    • Trades, Research, Earnings, Thesis, 周会, 收件箱, Podcast
    • 13F, 供应链, ChatGPT, NotebookLM Q&A
       ↓
[3] 汇总统计
    • 按类别计数
    • 按 ticker 聚合
    • 识别重点关注的公司（3+ sources 提及 = key focus）
       ↓
[4] 生成回顾报告
    • 结构化 Markdown
    • 包含 [[wikilinks]] 到相关笔记
       ↓
[5] 生成行动项
    • 未处理的 inbox 项
    • 需要更新的 thesis
    • 需要跟进的周会决策
       ↓
[5.5] 决策回顾 (Decision Review)
    • 查询 investments.db 待回顾决策
    • 统计 win/loss/neutral 分布
    • 生成"待填 outcome"提醒表
       ↓
[6] 保存到 Obsidian
    • 路径: ~/Documents/Obsidian Vault/写作/投资回顾/YYYY-MM-DD_{period}_review.md
    • 同时输出摘要到终端
```

## Quick Start

```
/review week                         # 过去一周回顾
/review month                        # 过去一个月回顾
/review 2026-01-01 to 2026-01-31     # 自定义日期范围
/review quarter                      # 过去一个季度
/review attribution                  # Source attribution report (Phase 4)
/review passed                       # Monthly passed ticker price check (Phase 4)
```

## Commands Reference

```bash
# 单 Agent 模式（默认）
/review week                          # 周回顾
/review month                         # 月回顾
/review quarter                       # 季回顾
/review YYYY-MM-DD to YYYY-MM-DD      # 自定义范围
/review week --focus TICKER           # 聚焦某个 ticker 的周回顾

# Agent Teams 模式
/review week --team                   # Agent Teams 周回顾
/review month --team                  # Agent Teams 月回顾（推荐）
/review quarter --team                # Agent Teams 季回顾（强烈推荐）

# Phase 4 专项
/review attribution                   # Source attribution report
/review passed                        # Monthly passed ticker review
```

## References

Detailed reference material -- read as needed:
- Data sources (12 sources with scan instructions): `references/data-sources.md`
- Report template and output format: `references/report-template.md`
- Attribution, skill integration, auto-task: `references/attribution.md`
