---
name: flashback
description: 投资时间线回溯 - 按时间轴还原某个 ticker 的全部研究轨迹，识别认知演变和关键转折点
---

# /flashback - 投资时间线回溯

为 ticker 生成按时间排序的完整研究轨迹：从第一次提及到最近动态，展示认知如何演变、关键转折点在哪里。用于持仓复盘、模式识别、投资决策审计。

## Important Rules

- MUST search ticker + company name + Chinese name (e.g., NVDA / NVIDIA / 英伟达) across all data sources — partial coverage is a reporting failure.
- MUST include all 14 data sources in the output, even if a source yields zero results — note "无记录" rather than omitting the section.
- NEVER copy large blocks of text from source notes — quote 1-2 sentences max per entry; time-line entries must be brief.
- 时间线中的引用要简短（1-2 句话），不要复制大段原文。
- IMPORTANT: 认知演变分析必须基于实际数据，不得凭空推测。
- IMPORTANT: If vector memory or NLM modules are unavailable, skip gracefully (non-blocking) — never abort the whole skill.
- NEVER fabricate trade prices, dates, or conviction scores — only record what exists in trades.json or the decisions DB.

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

13. **Vector Memory (Semantic)** — 语义相似度检索
    - 调用 vector memory 查询该 ticker 的所有历史嵌入：
      ```bash
      /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
      import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
      from shared.vector_memory import query_ticker, query_similar, format_memories_for_context
      # 1. Get all stored memories for this ticker
      memories = query_ticker('{TICKER}', top_k=20)
      for m in memories:
          print(f\"{m['date']} | {m['source_type']} | {m['section_id']} | {m['chunk_text'][:80]}...\")
      print('---')
      # 2. Semantic query for pattern matching
      results = query_similar('{TICKER} investment thesis narrative evolution', top_k=5, ticker='{TICKER}')
      print(format_memories_for_context(results))
      "
      ```
    - 与关键词搜索不同，这里检索的是**语义相似的历史模式**
    - 每条结果附带 cosine similarity score，>0.85 为高度相关
    - 结果分两类：earnings sections（综合评估、管理层叙事）和 meeting stances（周会讨论立场）
    - 如果 vector memory 为空或模块不可用，跳过此源（非阻塞）

14. **Decisions & Failures** — SQLite 决策记录 + JSONL 失误日志
    - 查询 SQLite 决策历史：
      ```bash
      /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
      import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills\shared')
      from db_utils import get_decisions_for_ticker
      rows = get_decisions_for_ticker('{TICKER}')
      for r in rows:
          outcome = r['outcome_result'] or 'pending'
          print(f\"{r['date']} | 📍{r['decision_type']} | conviction={r['conviction']} | {outcome} | {r['reasoning'][:80]}\")
      "
      ```
    - 查询 JSONL 失误记录：
      ```bash
      /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe -c "
      import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills\shared')
      from jsonl_utils import query_jsonl
      from pathlib import Path
      failures = query_jsonl(Path.home() / '.claude' / 'data' / 'failures.jsonl', ticker='{TICKER}')
      for f in failures:
          print(f\"{f.get('created_at','?')[:10]} | ⚠️{f.get('failure_type','?')} | {f.get('description','')[:80]}\")
      "
      ```
    - 时间线标记：📍决策（BUY/SELL/ADD/TRIM）、⚠️失误（追涨/忽视信号/过度交易等）
    - 决策带 outcome 状态（win/loss/neutral/pending）—— 用于模式识别
    - 如果 DB 或 JSONL 不存在/为空，跳过此源（非阻塞）

**时间线构建：**
- 所有条目按日期升序排列
- 每条标注来源类型和简要内容
- 识别关键转折点：首次交易、加仓/减仓、thesis 修改、重大信息、📍决策记录、⚠️失误记录

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
    • 标注条目类型（trade/research/earnings/meeting/news/📍decision/⚠️failure）
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

完整 Markdown 模板（含 NVDA 示例数据）见 [`references/output-format.md`](references/output-format.md)。

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
