# Report Template & Output Format

## 输出格式

```markdown
---
created: YYYY-MM-DD
type: review
period: week
start_date: YYYY-MM-DD
end_date: YYYY-MM-DD
tags: [review, weekly]
---

# 投资回顾：YYYY-MM-DD ~ YYYY-MM-DD

> 周度/月度投资活动汇总

## Portfolio Activity

### 交易记录
| 日期 | 操作 | Ticker | 方向 | 备注 |
|------|------|--------|------|------|
| 2026-02-03 | 新建仓 | NVDA | Long | AI 基础设施 |
| 2026-02-05 | 加仓 | UBER | Long | Q4 超预期 |

### 持仓变化
- **新增：** NVDA
- **加仓：** UBER (+2%)
- **减仓：** 无
- **清仓：** 无

## 研究活动

### 新增研究笔记 (2)
- [[NVDA_2026-02-05]] - 深度研究
- [[UBER_2026-02-04]] - 财报后更新

### 财报分析 (3)
- [[UBER Q4 2025 vs Q3 2025 Claude Analysis]] - UBER 超预期
- [[AAON-US Q4 2025 vs Q3 2025 Analysis]] - 毛利改善
- [[WOSG-GB Q3 2026 vs Q2 2026 Analysis]] - 销售回暖

### Thesis 更新
- `NVDA/thesis.md` - 更新于 2026-02-05（新增 AI agent 叙事）

## 周会要点

### 会议实录 2026-01-03
> AI硬件链条偏多，存储股两周涨40%，美债利率回到高位需警惕
- 关键 tickers: TSM, MU, BIDU, GOOGL, MSFT
- 行动: 跟踪存储/封装链价格验证

## 收件箱统计

| 指标 | 数量 |
|------|------|
| 本期新增 | 12 |
| 已处理 | 5 |
| 未处理 | 7 |
| 高频 Tickers | NVDA(3), TSLA(2) |

## Podcast 活动
- 新增: 5 篇
- 已处理: 2 篇
- 待处理: 3 篇

## 13F Smart Money Activity (季度回顾)

| Ticker | 机构动向 | 来源 |
|--------|---------|------|
| PM | Einhorn 增持 15% (Q3 '25) | 13F |
| NVDA | 3 家新建仓 | 13F |

## Supply Chain Signals

本期新增的供应链提及：
- TSM Q4 财报提到 NVDA CoWoS 产能扩张
- AVGO 提到 AI networking 需求加速

## ChatGPT & NotebookLM Activity

- ChatGPT 投资对话: 5 篇 (涉及: NVDA, PM, TSM)
- NotebookLM 查询: 8 次 (主要: PM ZYN thesis, NVDA competition)

## 重点关注公司

多个数据源同时提到的公司：

| Ticker | 出现次数 | 来源 |
|--------|---------|------|
| NVDA | 12 | Research, 周会, Inbox, Podcast, 13F, Supply Chain, ChatGPT |
| UBER | 5 | Earnings, Research, Trade |

## Next Actions

- [ ] 处理 7 个未读收件箱条目
- [ ] 更新 UBER thesis（Q4 财报后）
- [ ] 处理 3 个未读播客笔记
- [ ] 跟进周会中提到的存储/封装链
```

## Agent Teams Mode (Experimental)

When data sources are many and time range is long (monthly/quarterly), use Agent Teams for parallel data collection + cross-validation.

### 启用条件
- Environment variable `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set
- User uses `--team` parameter, or Claude judges task complexity is suitable (auto-suggest for monthly/quarterly reviews)

### 团队结构

```
Lead Agent (Opus) — Coordinator: assign tasks, deduplicate & merge, generate final report
  │
  ├── Teammate A: "Portfolio Analyst" (Sonnet)
  │   → Data sources: trades.json, portfolio.db, thesis updates
  │   → Responsibilities: trade summary, position changes, thesis update detection
  │   → Output: trade record table + position change list + updated thesis list
  │
  ├── Teammate B: "Research Scanner" (Sonnet)
  │   → Data sources: 研究笔记, 财报分析, Podcast, 收件箱
  │   → Responsibilities: research activity stats, content summaries, unprocessed item list
  │   → Output: new note list + earnings analysis summary + Inbox/Podcast stats
  │
  ├── Teammate C: "External Intelligence" (Sonnet)
  │   → Data sources: 13F holdings, Supply Chain DB, ChatGPT, NotebookLM history
  │   → Responsibilities: institutional activity, supply chain signals, AI conversation stats
  │   → Output: Smart Money table + supply chain signals + ChatGPT/NLM activity
  │
  └── Teammate D: "Meeting Analyst" (Sonnet)
      → Data sources: 周会/会议实录, action item history
      → Responsibilities: meeting highlights extraction, action item follow-up status
      → Output: meeting summary + incomplete action items
```

### 交叉验证（Agent Teams 独有价值）

Teammates communicate directly for cross-validation impossible in single agent mode:

| 发现方 | 验证方 | 交叉验证内容 |
|--------|--------|-------------|
| A (Portfolio) | C (External) | A discovers position increase → C checks if 13F institutions increased/decreased in parallel |
| C (External) | A (Portfolio) | C discovers 13F manager large reduction → A checks corresponding thesis kill criteria |
| B (Research) | D (Meeting) | B discovers new earnings analysis → D checks if weekly meeting discussed the same company |
| D (Meeting) | B (Research) | D extracts meeting action items → B checks if corresponding research notes followed up |
| C (External) | B (Research) | C discovers new supply chain signal → B checks if related podcast or research notes exist |

### Lead Agent 额外职责（仅 Team 模式）

1. **Dedup** — Multiple teammates may report the same ticker, Lead merges into single entry
2. **Conflict flagging** — If Portfolio shows position increase but 13F shows institutional decrease, Lead flags as "Warning Signal"
3. **Key company identification** — Tickers appearing across >=3 teammates auto-upgrade to "Key Focus"
4. **Early termination** — If a teammate's data source is empty (e.g., no meetings this week), Lead terminates early to save tokens

### 成本对比

| Mode | Use Case | Estimated Tokens |
|------|---------|-----------|
| Single Agent (default) | Weekly review, few data sources | ~30K |
| Agent Teams (`--team`) | Monthly/quarterly, all data sources | ~100-150K |

**Recommendation:** Teammates use Sonnet (data collection), Lead uses Opus (synthesis & analysis).
