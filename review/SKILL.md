---
name: review
description: 定期投资回顾 - 聚合 Portfolio、Research、周会、Inbox 活动，生成周/月回顾报告，输出到 Obsidian
---

# /review - 定期投资回顾

聚合一段时间内的投资活动：交易、研究、周会讨论、收件箱处理，生成结构化回顾报告。

## Instructions for Claude

**自动创建目录：** 如果 `~/Documents/Obsidian Vault/写作/投资回顾/` 不存在，自动创建。

**时间范围计算：**
- `week` = 过去 7 天（从上周一到本周日）
- `month` = 过去 30 天（上月同日到今天）
- `YYYY-MM-DD to YYYY-MM-DD` = 自定义范围

**数据源扫描（全部并行）：**

1. **Portfolio / Trades**
   - 读取 `~/PORTFOLIO/portfolio_monitor/data/trades.json`
   - 或查询 `portfolio.db`（SQLite，用 Python）
   - 提取：新建仓、加仓、减仓、清仓

2. **Research Notes**
   - 扫描 `研究/研究笔记/` 中日期在范围内的文件
   - 格式: `{TICKER}_YYYY-MM-DD.md`

3. **Earnings Analysis**
   - 扫描 `研究/财报分析/` 中日期在范围内的文件
   - 看文件名中的日期

4. **Thesis Updates**
   - 检查 `~/PORTFOLIO/portfolio_monitor/research/companies/*/thesis.md`
   - 按文件修改时间过滤

5. **周会 (Weekly Meetings)**
   - 扫描 `周会/会议实录 YYYY-MM-DD.md` 日期在范围内的
   - 读取前 10 行（含会议摘要和提到公司）

6. **收件箱**
   - 统计范围内新增的 inbox 条目
   - 统计 `processed: true` vs `processed: false`
   - 提取高频 tickers

7. **Podcast**
   - 扫描 `信息源/播客/` 中 `publish_date` 在范围内的
   - 统计已处理 vs 未处理

8. **13F Institutional Holdings** (季度回顾时重点展示)
   - 扫描 `~/Documents/Obsidian Vault/研究/13F 持仓/` 中的分析报告
   - 也检查 `~/13F-CLAUDE/output/*/` 中的 CSV 数据
   - 按持仓 ticker 过滤：哪些机构增持/减持了你持有的股票
   - 格式化为 "Smart Money Activity" 表格

9. **Supply Chain Mentions**
   - 扫描 `~/Documents/Obsidian Vault/研究/供应链/` 中的提及报告
   - 也可查询 `~/.claude/skills/supply-chain/data/supply_chain.db`：
     `SELECT * FROM mentions WHERE date >= '{start_date}' ORDER BY date`
   - 总结：本期新增的供应链提及（谁在财报中提到了什么公司）

10. **ChatGPT Investment Conversations**
    - 扫描 `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` 中日期在范围内的文件
    - 提取 ticker 相关的分析讨论

11. **NotebookLM Q&A Activity**
    - 读取 `~/.claude/skills/notebooklm/data/history.json`
    - 统计范围内的查询次数和涉及的 ticker
    - 总结关键问答（问了什么、得到了什么答案）

12. **Source Attribution (Research ROI)**
    - 调用 `shared/attribution_report.py` 生成归因报告
    - 提取 Source Efficiency Ranking + Conviction Calibration + Coverage vs Returns
    - 展示"哪个信息源赚钱最多""高 conviction 是否真的赚更多""研究越深回报越好吗"

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
    • 识别重点关注的公司（多个数据源都提到的）
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

## 📊 Portfolio Activity

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

## 📝 研究活动

### 新增研究笔记 (2)
- [[NVDA_2026-02-05]] - 深度研究
- [[UBER_2026-02-04]] - 财报后更新

### 财报分析 (3)
- [[UBER Q4 2025 vs Q3 2025 Claude Analysis]] - UBER 超预期
- [[AAON-US Q4 2025 vs Q3 2025 Analysis]] - 毛利改善
- [[WOSG-GB Q3 2026 vs Q2 2026 Analysis]] - 销售回暖

### Thesis 更新
- `NVDA/thesis.md` - 更新于 2026-02-05（新增 AI agent 叙事）

## 🗓️ 周会要点

### 会议实录 2026-01-03
> AI硬件链条偏多，存储股两周涨40%，美债利率回到高位需警惕
- 关键 tickers: TSM, MU, BIDU, GOOGL, MSFT
- 行动: 跟踪存储/封装链价格验证

## 📬 收件箱统计

| 指标 | 数量 |
|------|------|
| 本期新增 | 12 |
| 已处理 | 5 |
| 未处理 | 7 |
| 高频 Tickers | NVDA(3), TSLA(2) |

## 🎙️ Podcast 活动
- 新增: 5 篇
- 已处理: 2 篇
- 待处理: 3 篇

## 🏦 13F Smart Money Activity (季度回顾)

| Ticker | 机构动向 | 来源 |
|--------|---------|------|
| PM | Einhorn 增持 15% (Q3 '25) | 13F |
| NVDA | 3 家新建仓 | 13F |

## 🔗 Supply Chain Signals

本期新增的供应链提及：
- TSM Q4 财报提到 NVDA CoWoS 产能扩张
- AVGO 提到 AI networking 需求加速

## 💬 ChatGPT & NotebookLM Activity

- ChatGPT 投资对话: 5 篇 (涉及: NVDA, PM, TSM)
- NotebookLM 查询: 8 次 (主要: PM ZYN thesis, NVDA competition)

## 🔑 重点关注公司

多个数据源同时提到的公司：

| Ticker | 出现次数 | 来源 |
|--------|---------|------|
| NVDA | 12 | Research, 周会, Inbox, Podcast, 13F, Supply Chain, ChatGPT |
| UBER | 5 | Earnings, Research, Trade |

## ✅ Next Actions

- [ ] 处理 7 个未读收件箱条目
- [ ] 更新 UBER thesis（Q4 财报后）
- [ ] 处理 3 个未读播客笔记
- [ ] 跟进周会中提到的存储/封装链
```

## Agent Teams Mode (Experimental)

当数据源多、时间范围长（月度/季度）时，可用 Agent Teams 并行化数据采集 + 交叉验证。

### 启用条件
- 环境变量 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 已设置
- 用户使用 `--team` 参数，或 Claude 判断任务复杂度适合（月度/季度回顾自动建议）

### 团队结构

```
Lead Agent (Opus) — 协调者：分配任务、去重合并、生成最终报告
  │
  ├── Teammate A: "Portfolio Analyst" (Sonnet)
  │   → 数据源: trades.json, portfolio.db, thesis updates
  │   → 职责: 交易汇总、持仓变化、thesis 更新检测
  │   → 输出: 交易记录表 + 持仓变化列表 + 更新的 thesis 清单
  │
  ├── Teammate B: "Research Scanner" (Sonnet)
  │   → 数据源: 研究笔记, 财报分析, Podcast, 收件箱
  │   → 职责: 研究活动统计、内容摘要、未处理项清单
  │   → 输出: 新增笔记列表 + 财报分析摘要 + Inbox/Podcast 统计
  │
  ├── Teammate C: "External Intelligence" (Sonnet)
  │   → 数据源: 13F holdings, Supply Chain DB, ChatGPT, NotebookLM history
  │   → 职责: 机构动向、供应链信号、AI 对话活动统计
  │   → 输出: Smart Money 表格 + 供应链信号 + ChatGPT/NLM 活动
  │
  └── Teammate D: "Meeting Analyst" (Sonnet)
      → 数据源: 周会/会议实录, 行动项历史
      → 职责: 会议要点提取、行动项跟进状态
      → 输出: 会议摘要 + 未完成行动项
```

### 交叉验证（Agent Teams 独有价值）

Teammates 之间直接通信，实现单 agent 模式做不到的交叉验证：

| 发现方 | 验证方 | 交叉验证内容 |
|--------|--------|-------------|
| A (Portfolio) | C (External) | A 发现加仓某 ticker → C 检查 13F 是否有机构同步增持/减持 |
| C (External) | A (Portfolio) | C 发现 13F manager 大幅减持 → A 检查对应 thesis 的 kill criteria |
| B (Research) | D (Meeting) | B 发现新 earnings analysis → D 检查周会是否讨论过同一公司 |
| D (Meeting) | B (Research) | D 提取周会行动项 → B 检查是否有对应 research note 跟进 |
| C (External) | B (Research) | C 发现供应链新信号 → B 检查是否有相关 podcast 或研究笔记 |

### Lead Agent 额外职责（仅 Team 模式）

1. **去重** — 多个 teammate 可能报告同一 ticker，Lead 合并为单条
2. **冲突标记** — 如 Portfolio 显示加仓但 13F 显示机构减持，Lead 标记为 "⚠️ 关注信号"
3. **重点公司识别** — 跨 teammate 出现 ≥3 次的 ticker 自动升级为"重点关注"
4. **提前终止** — 如果某 teammate 数据源为空（如本周无周会），Lead 提前终止该 teammate 节省 token

### 成本对比

| 模式 | 适用场景 | 预计 Token |
|------|---------|-----------|
| 单 Agent（默认） | 周回顾、数据源少 | ~30K |
| Agent Teams (`--team`) | 月度/季度、全数据源 | ~100-150K |

**建议：** Teammates 用 Sonnet（数据拉取），Lead 用 Opus（综合分析）。

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

## Phase 4: Attribution & Passed Review

### `/review attribution`

Generates a source attribution report showing which information channels produce the best investment ideas.

**Workflow:**
1. Run the attribution report generator:
   ```bash
   cd ~/.claude/skills && python -c "
   from shared.attribution_report import generate_attribution_report
   report = generate_attribution_report(save=True)
   print(report)
   "
   ```
2. Report shows: Source → Ideas → Positions → Pass Rate → Avg Return → Win Rate
3. Includes "Weekly Meeting" as a source channel (from NLM attribution)
4. Lists unattributed tickers that need `idea_source` tagging
5. Saved to `Documents/Obsidian Vault/写作/投资回顾/YYYY-MM-DD_attribution_report.md`

### `/review passed`

Monthly check on all passed companies + NLM-based discovery of new candidates.

**Workflow:**
1. Run the passed tracker:
   ```bash
   cd ~/.claude/skills && python -c "
   from shared.passed_tracker import generate_full_report
   report = generate_full_report(save=True)
   print(report)
   "
   ```
2. Part 1: Price tracking — compares price_at_pass vs. current price for all passed records
3. Part 2: NLM discovery — queries 投资观点周报 for tickers discussed but not in portfolio/passed
4. Shows decision accuracy: what % of your passes were "correct" (stock <5% up since pass)
5. Saved to `Documents/Obsidian Vault/写作/投资回顾/YYYY-MM-DD_passed_review.md`

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/portfolio` | 读取持仓和交易数据 |
| `/research` | 统计研究笔记产出 |
| `/thesis` | 检查 thesis 更新 + idea_source attribution |
| `/moc` | 回顾中的 ticker 可生成 MOC |
| `/inbox` | 统计 inbox 处理进度 |
| `/podcast` | 统计播客处理进度 |
| `/13f` | 读取机构持仓变动（季度回顾重点） |
| `/supply-chain` | 读取供应链提及数据 |
| `/chatgpt-organizer` | 统计投资相关 ChatGPT 对话 |
| `/notebooklm` | 统计 Q&A 查询活动 |
| `/flashback` | 回顾中的 ticker 可深入生成 flashback |
| NotebookLM | `/review attribution` + `/review passed` 使用 NLM 查询 |

## Auto-Task from Next Actions

回顾报告生成后，如果 Next Actions 有 ≥1 条，自动创建 **一个** meta-task（不是每条一个 task，减少噪音）：
```python
try:
    import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
    from shared.task_manager import auto_create_task
    from datetime import date
    checklist = "\n".join(f"- [ ] {item}" for item in next_actions)
    auto_create_task(
        f"Process review next actions ({len(next_actions)})",
        source="post-review", category="review", priority=3,
        estimated_minutes=len(next_actions) * 10,
        description=checklist,
        dedup_key=f"review-actions-{period}-{date.today().isoformat()}"
    )
except ImportError:
    pass
```
只在终端简短提示: `[Auto-task: Process review next actions (5)]`

## 注意事项

- trades.json 格式需要先读取确认结构
- portfolio.db 是 SQLite，可用 Python 查询
- 周会文件前几行包含结构化摘要，是最重要的提取目标
- 日期过滤要兼容不同格式（YYYY-MM-DD, created frontmatter, 文件名中的日期）
- 回顾报告应该以数据驱动，避免主观判断
- 输出同时到文件和终端（终端版更简洁）
