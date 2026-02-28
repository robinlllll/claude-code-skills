---
name: earnings-preview
description: "Pre-earnings preview note — consensus, key metrics, scenarios, catalyst checklist. Use when user says 'earnings preview', 'pre-earnings', '财报预览', 'earnings prep', 'preview TICKER', or before an earnings call."
metadata:
  version: 1.1.0
---

# Earnings Preview Generator

生成财报发布前的预览笔记：共识预期、关键指标、三种情景、催化剂清单。

## Syntax

```bash
/earnings-preview TICKER          # 标准预览
/earnings-preview TICKER --deep   # 深度预览（含历史 beat/miss 模式）
```

## Workflow

### Step 1: Gather Context

1. **Read thesis:** `PORTFOLIO/research/companies/{TICKER}/thesis.yaml` — extract core thesis, kill criteria, conviction, peers
2. **Read prior analysis:** Search `Documents/Obsidian Vault/研究/财报分析/` for most recent `{TICKER}` analysis
3. **Pull consensus estimates:**
   - Check consensus-dashboard cache: `PORTFOLIO/data/consensus/`
   - If stale (>3 days), pull fresh via Yahoo Finance:
   ```python
   import yfinance as yf
   t = yf.Ticker(TICKER)
   # t.earnings_estimate, t.revenue_estimate, t.earnings_history
   ```
4. **Get earnings date + timing:**
   ```python
   cal = yf.Ticker(TICKER).calendar
   # BMO (Before Market Open) vs AMC (After Market Close)
   ```

### Step 2: Key Metrics Framework

Apply sector-specific key metrics. Resolve the company's sector:

1. **Sector lookup:** Check `entity_dictionary.yaml[TICKER].sector` → map to `shared/references/sector_metrics.yaml` framework sector
2. **Sub-sector refinement:** For broad sectors (Technology, Consumer Staples), check `key_products` and thesis context:
   - Technology → "SaaS / Cloud" (subscription), "E-commerce" (marketplace), "Ad Tech" (advertising), default "Technology (General)"
   - Consumer Staples → "Tobacco / Nicotine" (PM, MO, BTI, SWMA), default "Consumer Staples"
3. **Load canonical KPIs:** Read `shared/references/sector_metrics.yaml[sector].canonical_kpis`
4. **Build metrics table:** For each `importance: primary` KPI, show: last quarter actual, consensus estimate (if available), beat/miss criteria from `beat_miss_guide`

**Reference:** See `shared/references/sector_metrics.yaml` for full framework (11 sectors × 6 KPIs × KC templates × valuation methods).

### Step 3: Scenario Analysis

Build a 3-scenario table with stock reaction estimates:

```markdown
## 情景分析

| 情景 | 概率 | 收入 | EPS | 关键假设 | 预期股价反应 |
|------|------|------|-----|---------|-------------|
| 🐂 Bull | 25% | >$360M | >$0.18 | Velocity 改善 + 新渠道扩张 | +8-12% |
| ⚖️ Base | 50% | $340-360M | $0.12-0.18 | 符合 consensus, 稳定增长 | -2% to +3% |
| 🐻 Bear | 25% | <$340M | <$0.12 | 竞争加剧, 渠道去库存 | -10-15% |
```

Scenario probabilities should be informed by:
- Historical beat/miss pattern (if `--deep` mode)
- Management guidance trend (accelerating/decelerating)
- Sector conditions
- Options-implied move (see Step 4)

### Step 4: Options-Implied Move

If available, calculate the expected move from options pricing:

```python
import yfinance as yf
t = yf.Ticker(TICKER)
# Get nearest expiry options chain
# Straddle price at ATM strike / stock price = implied move %
```

```markdown
## 期权隐含波动

期权隐含波动: ±8.5% (基于最近到期的 ATM straddle)
历史实际波动 (近4季): ±6.2% 平均
→ 市场定价偏高 / 偏低 / 合理
```

### Step 5: Catalyst Checklist

Generate 3-5 key items to listen for on the earnings call:

```markdown
## 电话会议关注清单

1. [ ] **Velocity 数据** — 每店每周销量是否改善？与 Monster/Red Bull 对比
2. [ ] **Alani Nu 整合进展** — 便利店铺货 +100% 后动销如何？
3. [ ] **渠道库存** — 分销商库存天数是否正常化？
4. [ ] **国际扩张时间表** — 欧洲/亚洲进入计划
5. [ ] **全年指引** — 是否提供 FY2026 guidance
```

Checklist items sourced from:
- Kill criteria in thesis.yaml (what data would change your view)
- Prior quarter's open questions
- Consensus debate points (what analysts are divided on)
- Management's previous commitments/promises

### Step 6: Output

Save to Obsidian: `Documents/Obsidian Vault/研究/财报分析/{date} - {TICKER} Q{N} Earnings Preview.md`

Complete output template:

```markdown
---
ticker: {TICKER}
type: earnings-preview
quarter: Q{N} {YEAR}
earnings_date: {YYYY-MM-DD}
timing: {BMO/AMC}
created: {YYYY-MM-DD}
tags: [earnings-preview, {TICKER}, {sector}]
---

# {TICKER} Q{N} {YEAR} Earnings Preview

**财报日期:** {date} ({BMO/AMC})
**当前价格:** ${price} | **市值:** ${market_cap}
**Thesis:** {one-line from thesis.yaml}
**Conviction:** {conviction}/5

---

## 共识预期

| 指标 | Q{N-1} 实际 | Q{N} 预期 | YoY | 备注 |
|------|------------|----------|-----|------|
| Revenue | | | | |
| EPS | | | | |
| Gross Margin | | | | |
| {sector metrics} | | | | |

## 关键指标关注

{Step 2 output — sector-specific metrics}

## 情景分析

{Step 3 output — Bull/Base/Bear table}

## 期权隐含波动

{Step 4 output}

## 电话会议关注清单

{Step 5 output — numbered checklist}

## Kill Criteria 关联

| KC | 当前状态 | 本季应关注 |
|----|---------|-----------|
| {from thesis.yaml} | {check_result} | {what to watch} |

---

## Sources
- Consensus: Yahoo Finance / FactSet as of {date}
- Prior quarter: [[{prev analysis wikilink}]]
- Thesis: [[{TICKER} thesis]]
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/transcript-analyzer` | 财报后分析，与 preview 形成"预期-实际"闭环 |
| `/consensus-dashboard` | 共识数据来源 |
| `/thesis` | Kill criteria 和 conviction 来源 |
| `/calendar` | 自动触发：财报日期前 2 天提醒生成 preview |
| `/today` | 晨间简报引用即将发布的 preview |

## Deep Mode (--deep)

额外分析：
1. **历史 Beat/Miss 模式:** 最近 4-8 个季度的 beat/miss 记录
2. **Estimate 修正趋势:** 过去 90 天 consensus 上调/下调幅度
3. **管理层 guidance 可信度:** 历史 guidance vs. actual 对比
4. **季节性模式:** 该季度历史上是否有特定模式

输出追加到标准 preview 文件中。
