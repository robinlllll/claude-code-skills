---
name: today
description: "晨间综合简报，一键获取每日所需信息。Use when user says 'today', '早报', 'morning brief', '今天', '简报', or starts the day asking for updates."
allowed-tools: "Bash Read Write Edit Glob Grep WebSearch"
metadata:
  version: 1.0.0
---

# /today — 晨间综合简报

每日一键获取"今天我需要知道的一切"。

## 使用方式

```bash
/today                  # 完整晨间简报（含市场数据）
/today --quick          # 快速模式（跳过市场数据拉取）
```

## 执行步骤

1. 运行晨间简报脚本：
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/morning_brief.py
   ```
   或快速模式：
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/morning_brief.py --quick
   ```

2. 脚本自动聚合：
   - 📊 持仓价格变动（yfinance）
   - 🌙 隔夜动态（盘后/盘前异动 >2%，含一行新闻标题）
   - 📊 昨日财报反应表（持仓中昨日发布财报的公司）
   - ✅ 今日任务计划（task_manager）
   - 📌 未解决研究问题（open_questions）
   - 📥 收件箱新笔记
   - ⚠️ 过期 thesis 提醒（>30天未更新）
   - 📚 知识库昨日新增
   - 📅 13F 截止日提醒
   - 💡 交易建议摘要（催化剂驱动）

3. 展示在终端 + 保存到 `收件箱/{date} - 晨间简报.md`

4. 对异动 ticker（>3%），建议 WebSearch 查新闻

## 输出路径

`收件箱/YYYY-MM-DD - 晨间简报.md`

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/task` | 读取今日任务计划 |
| `/research` | 异动 ticker 建议深入研究 |
| `/thesis` | 检测过期 thesis |
| `/kb-add` | 显示知识库新增统计 |

## 数据来源

- `shared/market_snapshot.py` / yfinance — 市场数据
- `shared/task_manager.py` — 任务 + open questions
- `PORTFOLIO/research/companies/` — thesis 文件
- `收件箱/` — Obsidian inbox
- `shared/task_manager.py` knowledge_index — KB 统计

## 隔夜动态模块

在持仓价格变动模块之前，先展示隔夜/盘前异动：

1. 用 yfinance 拉取 portfolio tickers 的 pre-market / after-hours 价格
2. 与昨日收盘价比较，标记 >2% 变动
3. 对异动 ticker 用 `yf.Ticker(t).news` 拉取最新标题

输出格式：
```
🌙 隔夜动态

CELH: +4.2% (盘后) — "Celsius Holdings Q4 Revenue Beats Estimates"
NVDA: -2.8% (盘前) — "Export Controls Tightened on AI Chips"
```

**Sector Context for Movers:**
When displaying tickers with >2% moves, include sector context:
> "📊 {TICKER} ({sector}): {price_change}% — {one-line news}"
> "→ Sector check: monitor {primary_sector_kpi} at next earnings"
>
> Example: "📊 MU (Semiconductors): +4.2% — DRAM spot prices up 3% w/w"
> "→ Sector check: monitor Inventory Days, Book-to-Bill"

Resolution: `entity_dictionary.yaml[TICKER].sector` → `sector_metrics.yaml[sector].canonical_kpis[0:2]`

## 财报反应模块

如果持仓中有公司在昨日/昨晚发布了财报，自动生成速览表：

检测方法：用 `yf.Ticker(t).calendar` 检查 earnings date 是否为昨日。

输出格式：
```
📊 昨日财报反应

| 公司 | EPS 预期 | EPS 实际 | 收入预期 | 收入实际 | 盘后反应 |
|------|---------|---------|---------|---------|---------|
| CELH | $0.12 | $0.15 | $340M | $352M | +4.2% |
```

数据来源：yfinance (EPS/Revenue estimates vs actuals) + consensus-dashboard 缓存

**Sector KPI in Earnings Reaction Table:**
Add a column for the primary sector-canonical KPI:

| Ticker | EPS | Rev | Sector KPI | Reaction |
|--------|-----|-----|------------|----------|
| NVDA | +12% beat | +8% beat | DC Rev +78% QoQ | +5.2% |
| PM | +3% beat | In-line | ZYN Vol +35% | +2.1% |

The "Sector KPI" value is sourced from the most recent `/transcript-analyzer` output in the vault.

## 交易建议模块

在简报末尾自动生成交易建议块，数据来源：

1. **近期催化剂（5日内）：** 扫描所有 `thesis.yaml` 的 `kill_criteria.expected_by` 和 earnings dates
2. **Conviction 变动：** 扫描 thesis.md 最近 7 天的 Thesis Log，标记 conviction 变化的 ticker
3. **Revisit 标记：** 扫描 passed.md 文件，检查 `revisit_trigger` 是否已触发（价格跌幅达标等）

输出格式：
```
💡 交易建议

| Ticker | 方向 | 触发事件 | 时间 | 当前价 | 建议 |
|--------|------|---------|------|--------|------|
| CELH | 关注 | Q4 Earnings | Feb 28 | $32.5 | 观察 velocity 数据 |
| PM | 持有 | Conviction ↑ (3→4) | Feb 25 | $168 | 近期 thesis update 利好 |
| TSLA | 回顾 | Price -22% since pass | — | $267 | 已触发 revisit trigger |
```
