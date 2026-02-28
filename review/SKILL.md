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
    • Sector Concentration Analysis（见下方说明）
       ↓
[3.5] Sector Concentration Analysis
    • 将 key focus tickers 按 entity_dictionary.yaml[ticker].sector 分组
    • 计算各行业占研究活动的百分比
    • 输出示例：
      > **本周行业分布:**
      > - Semiconductors: 3 tickers (NVDA, TSM, MU) — 45% of research activity
      > - Consumer Staples: 2 tickers (PM, CELH) — 25%
      > - Financials: 1 ticker (HOOD) — 15%
      >
      > ⚠️ Research skew: 45% of activity in Semiconductors — check for sector confirmation bias.
    • 若单一行业占比 >60%，自动 flag：⚠️ Sector concentration risk: {sector} dominates this week's research
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
    • 统计 win/loss/neutral 分布（整体汇总）
    • 生成"待填 outcome"提醒表
    • Sector-Grouped Decision Quality（见下方说明）
       ↓
[5.6] Sector-Grouped Decision Quality
    • 将 investments.db 决策按 entity_dictionary.yaml[ticker].sector 分组
    • 输出各行业胜率和平均 P&L 表格：

      | Sector | Decisions | Win | Loss | Neutral | Win Rate | Avg P&L |
      |--------|-----------|-----|------|---------|----------|---------|
      | Semiconductors | 8 | 5 | 2 | 1 | 62% | +4.2% |
      | Consumer Staples | 4 | 3 | 1 | 0 | 75% | +2.8% |
      | Financials | 3 | 1 | 2 | 0 | 33% | -1.5% |

    • Sector resolution: JOIN investments.db decisions WITH entity_dictionary.yaml[ticker].sector
    • 行为模式 flag：若某行业 loss 占所有 loss 的 >50%，输出：
      "⚠️ {N} of {total} losses this quarter were in {sector} — consider whether valuation discipline differs by sector."
       ↓
[6] 保存到 Obsidian
    • 路径: ~/Documents/Obsidian Vault/写作/投资回顾/YYYY-MM-DD_{period}_review.md
    • 同时输出摘要到终端

[6.5] Monthly Sector Attribution (仅 /review month 和 /review quarter 触发)
    • 按行业拆解组合 P&L，回答以下问题：
      - 哪个行业对本月回报贡献最大？
      - 哪个行业是最大拖累（drag）？
      - 行业仓位分布是否与 thesis conviction 分数匹配？
        （高 conviction thesis = 高行业仓位？否则 flag 不一致）
    • 数据来源：investments.db decisions + entity_dictionary.yaml sectors + portfolio P&L
    • 若行业 P&L 与 conviction 不匹配，输出：
      "⚠️ {sector}: high conviction but underweight — or low conviction but overweight. Review sizing discipline."
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
