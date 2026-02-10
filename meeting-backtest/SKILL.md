---
name: meeting-backtest
description: 周会选股回测 - 测算周会讨论股票的前瞻收益，比较"有持仓"vs"仅讨论"的表现差异
---

# /meeting-backtest - 周会选股回测

解析 42 场周会记录，提取每只股票的看法（多/空/中性），匹配实际持仓与交易记录，测算讨论后 7/30/90 天的前瞻收益。用于投资决策质量审计。

## Usage

```
/meeting-backtest              # 完整回测，使用缓存价格
/meeting-backtest --no-cache   # 强制重新拉取价格数据
/meeting-backtest --verbose    # 显示每条记录详情
```

## Instructions for Claude

**运行脚本：**

```bash
python ~/.claude/skills/shared/meeting_backtest.py [--no-cache] [--verbose]
```

**脚本位置：** `~/.claude/skills/shared/meeting_backtest.py`

**报告输出：** `~/Documents/Obsidian Vault/写作/投资回顾/YYYY-MM-DD_meeting_backtest.md`

**运行时间：** 首次约 2-3 分钟（拉取 200+ 只股票价格），后续使用缓存约 30 秒。

## Pipeline

```
42 场周会 .md → 提取 (ticker, sentiment) 对
                      ↓
匹配 trades.json → 重建持仓时间线 → 标记 ACTED_ON / DISCUSSED_ONLY
                      ↓
yfinance 批量拉取 → 计算 7d/30d/90d 前瞻收益
                      ↓
聚合为 5 组 → 生成 Obsidian 报告
```

## 5 Groups

| Group | Definition |
|-------|-----------|
| Bullish + Acted On | 看多 + 持仓或窗口内交易 |
| Bullish + Discussed Only | 看多但无持仓 |
| Bearish + Acted On | 看空 + 持仓或窗口内交易 |
| Bearish + Discussed Only | 看空且无持仓 |
| Neutral / Unknown | 中性或无法判断 |

## Data Sources

| Source | Path | Usage |
|--------|------|-------|
| 周会记录 | `周会/会议实录 *.md` | frontmatter `tickers` + `### 潜在行动提示` 情绪提取 |
| 交易记录 | `PORTFOLIO/portfolio_monitor/data/trades.json` | 持仓重建 + 窗口交易匹配 |
| 价格数据 | yfinance + `PORTFOLIO/data/price_cache/` | 前瞻收益计算 |
| 实体字典 | `shared/entity_dictionary.yaml` | 公司名 → ticker 解析 |

## Sentiment Extraction

按优先级从 `### 潜在行动提示（强化版）` 提取：

- **复合模式优先：** 中性偏多 → BULLISH，中性偏谨慎/中性偏空 → BEARISH
- **多头信号：** 偏多、加仓、建仓、买入、逢低、布局
- **空头信号：** 偏空、减仓、回避、卖出、降低暴露
- **中性信号：** 中性、观察、维持、观望
- **兜底：** `### 核心观点摘要` → 会议摘要 header → 一句话汇报摘要表

## Position Matching

"Acted On" = 会议日期当天有持仓（从 trades.json 重建累计仓位）OR 窗口 [-3d, +7d] 内有交易。

报告中区分显示：
- **持仓** = 会议时已持有
- **交易** = 窗口内新交易
- **✗** = 无持仓

## Report Sections

1. **汇总表** — 5 组 × 3 窗口期的均值/中位数/胜率
2. **核心发现** — 自动生成 5 条洞察（选股正确性、空头准确率、胜率对比等）
3. **Top/Bottom 10** — 30 天收益最高/最低
4. **错过的机会** — 看多但未持仓，涨幅最高
5. **正确回避** — 看空且未持仓，跌幅最大
6. **频次分析** — 讨论次数 Top 20 股票
7. **缺失数据** — 无法获取价格的 ticker
8. **完整数据表** — 全部 ~675 条记录

## Price Cache

缓存文件：`~/.claude/skills/shared/data/meeting_backtest_cache.json`

用 `--no-cache` 清除缓存并重新拉取。
