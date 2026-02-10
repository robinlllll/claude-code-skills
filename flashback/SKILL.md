---
name: flashback
description: 投资时间线回溯 - 按时间轴还原某个 ticker 的全部研究轨迹，识别认知演变和关键转折点
---

# /flashback - 投资时间线回溯

为 ticker 生成按时间排序的完整研究轨迹：从第一次提及到最近动态，展示认知如何演变、关键转折点在哪里。用于持仓复盘、模式识别、投资决策审计。

## Instructions for Claude

**自动创建目录：** 如果 `~/Documents/Obsidian Vault/Flashback/` 不存在，自动创建。

**数据收集（并行搜索所有来源）：**

1. **Trades** - `~/PORTFOLIO/portfolio_monitor/data/trades.json`
   - 提取该 ticker 的所有交易记录（日期、操作、金额）
   - 这是最关键的时间锚点

2. **Thesis** - `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/thesis.md`
   - 读取当前 thesis（含 Phase 4 attribution 字段: idea_source, nlm_citation, first_seen）
   - 检查 git history 或文件修改时间

3. **Research Notes** - `研究/研究笔记/{TICKER}_*.md`
   - 文件名含日期，直接提取

4. **Earnings Analysis** - `研究/财报分析/{TICKER}/*.md`
   - 从文件名提取日期和季度

5. **收件箱** - frontmatter `tickers` 包含该 ticker 的文件
   - 从 frontmatter `date` 提取日期

6. **Podcasts** - `信息源/播客/` 中正文提到该 ticker 的
   - 从 frontmatter `publish_date` 提取日期

7. **周会** - `周会/会议实录 *.md` 中提到该 ticker 的
   - 从文件名提取日期
   - 提取该 ticker 相关段落

8. **13F** - 机构持仓数据
   - 扫描 `~/Documents/Obsidian Vault/研究/13F 持仓/` 中提到该 ticker 的分析报告
   - 也搜索 `~/13F-CLAUDE/output/*/` 中的 CSV 文件（列: nameOfIssuer, ticker, shares, value）
   - 提取：哪些基金经理持有/增减持该 ticker，哪个季度，变动幅度
   - 这是 "smart money" 验证信号——机构动向可以验证或挑战你的 thesis

9. **Supply Chain Mentions**
   - 读取 `~/Documents/Obsidian Vault/研究/供应链/{TICKER}_mentions.md`
   - 也可查询 `~/.claude/skills/supply-chain/data/supply_chain.db`：
     `SELECT * FROM mentions WHERE mentioned_ticker = '{TICKER}' ORDER BY date`
   - 提取：哪些公司在财报中提到了该 ticker（如 TSM 提到 NVDA 的 CoWoS 需求）
   - 按日期排入时间线——供应链提及是前瞻性信号

10. **XUEQIU** - 雪球讨论

11. *(Knowledge Base removed — was empty)*

12. **ChatGPT Conversations**
    - 搜索 `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` 中提到该 ticker 的文件
    - 搜索策略：ticker + 公司名 + 中文名
    - 提取：日期、讨论主题、关键分析观点
11. **NotebookLM 周会讨论弧 (Phase 4 NLM Integration)** — 投资观点周报 notebook
    - 调用 NLM perception arc query:
      ```bash
      cd ~/.claude/skills && python -c "
      from shared.nlm_attribution import query_multi_notebook
      result = query_multi_notebook('{TICKER}', '{COMPANY_NAME}')
      for m in result['combined_mentions']:
          print(f\"{m.get('date','?')} | {m.get('notebook','?')} | {m['sentiment']} | {m['summary'][:100]}\")
      "
      ```
    - 返回跨多 notebook 的时间线（投资观点周报 + ticker 专题 notebook 如 PM Transcripts）
    - 每条包含: 日期, 情绪, 一句话摘要, 来源 notebook
    - **这是认知演变分析的最佳数据源** — NLM 的语义理解比关键词搜索更准
12. **Passed Record** - `research/companies/{TICKER}/passed.md`
    - 如果存在，纳入时间线（passed 日期、原因、价格）

**时间线构建：**
- 所有条目按日期升序排列
- 每条标注来源类型和简要内容
- 识别关键转折点：首次交易、加仓/减仓、thesis 修改、重大信息

**分析维度：**
- 初始 thesis 是什么？核心假设有哪些？
- 哪些假设被验证了？哪些被推翻了？
- 关键信息出现的时间点与交易时间点是否吻合？
- 是否存在信息已经改变但仓位没有调整的情况？（认知滞后）

## When to Use This Skill

- 用户使用 `/flashback TICKER`
- 用户说"回顾一下 XX 的投资历程"
- 持仓复盘、年度总结时
- 准备卖出/加仓前的决策审计

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

## Core Workflow

```
输入 TICKER
       ↓
[1] 并行搜索所有数据源
    • 搜索 ticker + 公司名 + 中文名
    • 收集所有相关条目 + 日期
       ↓
[2] 按时间排序
    • 构建完整时间线
    • 标注条目类型（trade/research/earnings/meeting/news）
       ↓
[3] 提取每条记录的关键信息
    • 交易: 日期、操作、金额
    • 研究: 核心观点/结论
    • 财报: 关键指标、超预期/miss
    • 周会: 讨论要点、多空观点
    • 文章: 关键信息
       ↓
[4] 分析认知演变
    • 初始 thesis → 当前状态
    • 识别假设验证/推翻的时间点
    • 标记关键转折点
       ↓
[5] 生成时间线报告
    • 可视化时间线
    • 分析总结
    • 经验教训
       ↓
[6] 保存到 Obsidian
    • ~/Documents/Obsidian Vault/Flashback/{TICKER}_flashback.md
```

## Quick Start

```
/flashback NVDA                     # NVDA 完整时间线
/flashback UBER                     # UBER 投资历程
/flashback UBER --since 2025-06     # 只看 2025-06 之后
/flashback list                     # 列出已生成的 flashback
```

## 输出格式

```markdown
---
created: YYYY-MM-DD
type: flashback
ticker: NVDA
company: NVIDIA Corporation
aliases: [英伟达]
first_mention: YYYY-MM-DD
total_events: 25
tags: [flashback, NVDA, review]
---

# NVDA — Investment Flashback

> 从 YYYY-MM-DD 到 YYYY-MM-DD 的完整投资轨迹，共 25 条记录。

## 📋 Summary

| 维度 | 状态 |
|------|------|
| **首次提及** | 2025-03-15 (周会讨论) |
| **首次交易** | 2025-04-02 (建仓) |
| **最近动态** | 2026-02-05 (研究笔记) |
| **交易次数** | 3 (1 建仓, 1 加仓, 1 减仓) |
| **研究笔记** | 2 篇 |
| **财报分析** | 0 篇 |
| **周会提及** | 5 次 |
| **文章/播客** | 8 条 |

## 🎯 Thesis Evolution

### 初始 Thesis (2025-04-02)
> AI 基础设施核心供应商，数据中心 GPU 需求远未见顶...

### 当前 Thesis (2026-02-05)
> 叠加 AI Agent 新叙事，but 估值已反映大部分预期...

### 关键假设追踪

| 假设 | 初始判断 | 当前状态 | 验证时间 |
|------|---------|----------|---------|
| 数据中心 GPU 需求持续增长 | ✅ 看多 | ✅ 已验证 | Q3 2025 财报 |
| 竞争对手（AMD/Intel）短期难追赶 | ✅ 看多 | ⚠️ AMD MI300 进展超预期 | 2025-08 |
| 估值合理 (<35x forward PE) | ✅ 合理 | ❌ 当前 42x | 2025-12 |

## 📅 Timeline

### 2025

#### 2025-03-15 — 🗓️ 周会首次讨论
> [[会议实录 2025-03-15]] — "AI 硬件链看好，NVDA 为核心..."
> **立场：** 偏多

#### 2025-04-02 — 💰 首次建仓
> Trade: BUY NVDA @ $850, 3% position
> **触发因素：** 数据中心收入连续超预期

#### 2025-06-15 — 📝 首篇研究笔记
> [[NVDA_2025-06-15]] — 深度覆盖报告
> **核心观点：** ...

#### 2025-08-20 — 📈 Q2 财报后加仓
> Trade: BUY NVDA @ $920, position → 5%
> [[NVDA Q2 2025 Earnings Analysis]] — 数据中心收入 +150% YoY

#### 2025-10-11 — 🗓️ 周会讨论
> [[会议实录 2025-10-11]] — "AMD MI300 进展值得关注..."
> **立场：** 中性偏多（竞争风险上升）

#### 2025-12-20 — ⚠️ 减仓
> Trade: SELL partial NVDA @ $1100, position → 3%
> **触发因素：** 估值偏高，锁定部分利润

### 2026

#### 2026-01-03 — 🗓️ 周会讨论
> [[会议实录 2026-01-03]] — "AI硬件偏多，存储股弹性更大..."
> **立场：** 相对偏好存储/封装 over NVDA

#### 2026-02-05 — 📝 研究更新
> [[NVDA_2026-02-05]] — 深度研究更新
> **核心变化：** 新增 AI Agent 叙事

## 💬 Weekly Discussion Arc (NLM)

> NotebookLM 投资观点周报中关于 NVDA 的讨论演变（语义检索，非关键词匹配）

| 日期 | Notebook | 情绪 | 摘要 |
|------|----------|------|------|
| 2025-03-15 | 投资观点周报 2025 | 偏多 | AI 硬件链条看好，NVDA 为核心供应商 |
| 2025-08-22 | 投资观点周报 2025 | 看多 | Q2 超预期，数据中心收入加速 |
| 2025-10-11 | 投资观点周报 2025 | 中性 | AMD MI300 竞争风险上升，关注份额变化 |
| 2025-12-20 | 投资观点周报 2025 | 偏空 | 估值偏高，建议减仓锁利 |
| 2026-01-03 | 投资观点周报 2025 | 中性 | 相对偏好存储/封装 over NVDA |

**认知转折点:** 2025-10-11 — 从纯看多转向关注竞争风险（AMD MI300）
**情绪弧:** 偏多 → 看多 → 中性 → 偏空 → 中性

*数据来源: NotebookLM semantic query via `shared.nlm_attribution.query_multi_notebook()`*

## 🔍 认知演变分析

### What Went Right ✅
- 数据中心需求判断正确，Q2/Q3 持续超预期
- 首次建仓时机合理（$850），后续收益显著

### What Could Be Better ⚠️
- 减仓决策可能过早（$1100 → 后续涨至 $1300）
- 周会 2025-10-11 提到 AMD 竞争风险，但未深入研究

### Blind Spots 🔴
- 未追踪 NVDA 在中国市场的合规风险变化
- 信息源/播客 中有 3 篇相关播客未处理

### Pattern Recognition 🧠
- 从建仓到首次减仓耗时 8 个月，期间加仓 1 次
- 信息更新（周会/文章）频率约 2 周/次
- 财报是最强的仓位变动触发器

## 📎 Related Notes Index

所有相关笔记的完整索引（按来源分组）：

### 交易记录
- 2025-04-02: BUY @ $850 (3%)
- 2025-08-20: BUY @ $920 (→5%)
- 2025-12-20: SELL partial @ $1100 (→3%)

### 研究笔记
- [[NVDA_2025-06-15]]
- [[NVDA_2026-02-05]]

### 周会
- [[会议实录 2025-03-15]]
- [[会议实录 2025-10-11]]
- [[会议实录 2026-01-03]]

### 播客/文章
- [[The Hidden Economics Powering AI]] — 2026-01-26
- ...

---
*Generated by /flashback on YYYY-MM-DD*
```

## Commands Reference

```bash
/flashback {TICKER}                   # 完整时间线
/flashback {TICKER} --since YYYY-MM   # 指定起始时间
/flashback {TICKER} --trades-only     # 只看交易记录
/flashback list                       # 列出已生成的 flashback
/flashback {TICKER} --refresh         # 重新生成
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/moc` | flashback 是 MOC 的时间维度版本 |
| `/review` | review 按时间段聚合，flashback 按 ticker 聚合 |
| `/thesis` | flashback 追踪 thesis 的演变 |
| `/trade` | flashback 包含所有交易记录 |
| `/research` | flashback 索引所有研究笔记 |

## 注意事项

- 交易数据从 trades.json 读取，格式需先确认
- 搜索要覆盖 ticker + 公司名 + 中文名（如 NVDA/NVIDIA/英伟达）
- 周会搜索重点看前 10 行摘要和"提到公司"字段
- 时间线中的引用要简短（1-2 句话），不要复制大段原文
- 认知演变分析是最有价值的部分，要基于实际数据而非推测
- 第一次运行时如果数据源较少，时间线可能很短——这也是有价值的信息（说明研究深度不够）
