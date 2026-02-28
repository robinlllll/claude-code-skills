# Podcast Output Format Reference

## Tier 1 输出（Scan/Batch — 浅层）

在 frontmatter 之后、原始 Summary 之前插入：

```markdown
## 🎯 Investment Insights (Auto-Generated)

**Tickers Mentioned:** [[NVDA]], [[MSFT]], [[GOOGL]]
**Topics:** AI Infrastructure, Data Center Economics, GPU Compute
**Portfolio Relevance:** 🔴 High（提到持仓 NVDA 的竞争格局变化）

### 关键投资论点
1. **AI 成本下降 99%** - frontier model 访问成本每 7 个月减半，利好应用层 [来源: Summary]
2. **硬件→能源瓶颈转移** - 算力不再是瓶颈，冷却和电力成为关键 [来源: Takeaway #6]

### 值得记录的引用
> "AI companies are achieving scale and distribution at an unprecedented rate..."

### 数据点
- 成本下降：99% cost reduction in frontier model access
- 能力翻倍周期：every 7 months

---
```

## Tier 2 输出（Deep Analysis — 7 sections）

```markdown
## 🎯 Investment Deep Analysis

### 1. 综合评估与投资启示
**核心结论：**
* **增长叙事**：[结构化拆解] [来源: Summary]
* **竞争格局变化**：[delta 分析] [来源: Takeaway #3]
* **风险信号**：[具体风险] [来源: Q&A]

**投资启示（决策导向）：** [偏多信号 + 风险升级]
**Devil's Advocate：** [量化风险，引用来源]

| 情景 | 概率 | 关键假设 | 影响方向 | 验证指标 |
|:---|:---|:---|:---|:---|
| Bull | X% | ... | 正面 | ... |
| Base | Y% | ... | 中性 | |
| Bear | Z% | ... | 负面 | |

### 2. Ticker 深度分析
**NVDA** — Thesis: ALIGNED
- 播客论点: ... [来源: Takeaway #3]
- 当前 thesis: ... [来源: thesis.yaml]
- 13F 信号: "42 holders (3 new, 12 up)"
- [?] 行业数据是否支持这个增长率假设？

### 3. 竞争格局
| 受益方 | 受损方 | 核心逻辑 | 来源 |
|:---|:---|:---|:---|
| ... | ... | ... | [来源标注] |

### 4. 嘉宾叙事与可信度
### 5. 关键引用与数据点
### 6. 催化剂与时间窗
| 时间窗 | 事件 | 方向 | 验证指标 | 来源 |
|:---|:---|:---|:---|:---|

### 7. Portfolio Action Flags
- 🟢 NVDA: thesis reinforced — [reason]
- 🟡 NEW: AMD — [why worth researching]
- 🔴 WARNING: TSM — [conflicts with bear case]

---
```

## Frontmatter 模板

**Tier 1:**
```yaml
---
title: "{Episode Title}"
podcast: "{Podcast Name}"
link: "{Podwise URL}"
publish_date: YYYY-MM-DD
status: "已处理"
enriched: true
enriched_date: YYYY-MM-DD
tickers: [NVDA, MSFT, GOOGL]
topics: [AI Infrastructure, Data Center, GPU]
portfolio_relevance: high
tags: [podcast, podwise, enriched]
---
```

**Tier 2 额外字段：**
```yaml
enriched_tier: 2
thesis_alignment:
  NVDA: ALIGNED
  MSFT: NEW INFO
action_flags: [NVDA-reinforced, AMD-research]
```
