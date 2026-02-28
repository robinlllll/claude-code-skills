---
name: calendar
description: "投资催化剂日历管理 — 自动聚合、手动添加、结果归档、.ics导出。Use when user says 'calendar', 'catalyst', '日历', '催化剂', '.ics', 'add to calendar', 'upcoming events', or asks about upcoming catalysts."
metadata:
  version: 2.0.0
---

# Catalyst Calendar Manager

管理投资催化剂日历：自动从持仓聚合、手动添加非标事件、事件后归档结果、导出 .ics 到手机日历。

## Project Location

`C:\Users\thisi\CALENDAR-CONVERTER`

## Syntax

```bash
/calendar                     # 显示未来 2 周催化剂
/calendar next month          # 显示未来 1 个月催化剂
/calendar add TICKER "event"  # 手动添加催化剂
/calendar archive             # 归档已过期催化剂，记录结果
/calendar export              # 导出 .ics 文件
/calendar export next 30 days # 导出指定时间范围
```

## Catalyst Taxonomy

| 类型 | 示例 | 影响级别 | 颜色 |
|------|------|---------|------|
| Earnings | 季度财报、业绩指引 | 🔴 高 | Red |
| Corporate | M&A、管理层变动、回购 | 🟡 中 | Yellow |
| Regulatory | FDA 决定、反垄断、政策 | 🔴 高 | Red |
| Macro | Fed 会议、CPI、就业数据 | 🟡 中 | Yellow |
| Conference | 投资者日、行业会议 | 🟢 低 | Green |
| Custom | 用户自定义催化剂 | 用户指定 | — |

## Workflow

### Step 1: Auto-Populate from Portfolio

扫描所有 `PORTFOLIO/research/companies/*/thesis.yaml` 文件：

```python
import os, yaml
from datetime import datetime, timedelta

companies_dir = r'C:\Users\thisi\PORTFOLIO\research\companies'
catalysts = []

for ticker in os.listdir(companies_dir):
    yaml_path = os.path.join(companies_dir, ticker, 'thesis.yaml')
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        # Extract kill criteria with expected_by dates
        for kc in (data.get('kill_criteria') or []):
            if kc.get('expected_by'):
                catalysts.append({
                    'ticker': ticker,
                    'date': kc['expected_by'],
                    'event': kc['condition'],
                    'type': 'Earnings' if 'earning' in kc['condition'].lower() else 'Custom',
                    'impact': '🔴 高'
                })
```

同时用 yfinance 拉取 portfolio tickers 的 earnings dates：
```python
import yfinance as yf
for ticker in portfolio_tickers:
    t = yf.Ticker(ticker)
    cal = t.calendar
    if cal is not None and 'Earnings Date' in cal:
        # Add earnings dates to catalysts
```

### Step 2: Display Catalyst Calendar

按时间排序，分组显示：

```
📅 催化剂日历 (2026-02-27 → 2026-03-13)

本周 (Feb 27 - Mar 1):
🔴 Feb 28  CELH   Earnings    Q4 2025 财报发布 (BMO)
🟢 Feb 28  PM     Conference  Consumer Analyst Group (CAGNY)

下周 (Mar 2 - Mar 8):
🔴 Mar 5   NVDA   Earnings    Q4 FY2026 财报发布 (AMC)
🟡 Mar 7   —      Macro       非农就业数据

再下周 (Mar 9 - Mar 15):
🟡 Mar 12  —      Macro       CPI 数据发布
🟢 Mar 13  AAPL   Conference  Apple Spring Event (rumored)
```

### Step 3: Manual Add

`/calendar add TICKER "event description"`

交互流程：
1. 解析 ticker 和事件描述
2. 用 AskUserQuestion 询问：
   - **日期:** 具体日期 (YYYY-MM-DD)
   - **类型:** Earnings / Corporate / Regulatory / Macro / Conference / Custom
   - **影响级别:** 🔴 高 / 🟡 中 / 🟢 低
   - **备注:** 预期影响、关注点 (可选)
3. 写入 `CALENDAR-CONVERTER/catalysts.yaml`:

```yaml
catalysts:
  - ticker: CELH
    date: 2026-02-28
    event: "Q4 2025 Earnings"
    type: Earnings
    impact: high
    notes: "关注 velocity 数据"
    added: 2026-02-27
    status: pending    # pending / completed / archived
```

### Step 4: Outcome Archiving

`/calendar archive`

扫描已过期催化剂（date < today），逐个询问结果：

```
📋 归档已过期催化剂

1. CELH Q4 Earnings (Feb 28)
   预期: Beat consensus, velocity improvement
   实际结果? [用户输入]
   Thesis 影响? Strengthens ↑ / Neutral ↔ / Weakens ↓

   → 已归档。建议运行 /thesis CELH update "Q4 results: ..."
```

归档记录追加到 `CALENDAR-CONVERTER/catalyst_archive.yaml`:

```yaml
archive:
  - ticker: CELH
    date: 2026-02-28
    event: "Q4 2025 Earnings"
    expected: "Beat consensus"
    actual: "Revenue beat 3%, EPS miss, guided down"
    thesis_impact: weakens
    archived_at: 2026-03-01
```

同时输出归档摘要到 Obsidian: `Documents/Obsidian Vault/收件箱/{date} - 催化剂归档.md`

### Step 5: Export to .ics

`/calendar export [timeframe]`

生成 .ics 文件，兼容 iPhone/Outlook：
- 默认导出未来 30 天
- 每个催化剂一个日历事件
- 事件标题: `[影响] TICKER: Event`
- 事件描述: notes + thesis context
- 颜色标记 (通过 calendar category)

```python
from icalendar import Calendar, Event
from datetime import datetime

cal = Calendar()
cal.add('prodid', '-//Robin Catalyst Calendar//EN')
cal.add('version', '2.0')

for catalyst in catalysts:
    event = Event()
    event.add('summary', f"[{catalyst['impact']}] {catalyst['ticker']}: {catalyst['event']}")
    event.add('dtstart', catalyst['date'])
    event.add('description', catalyst.get('notes', ''))
    cal.add_component(event)

with open('catalysts.ics', 'wb') as f:
    f.write(cal.to_ical())
```

输出: `CALENDAR-CONVERTER/catalysts.ics`

## Data Files

| File | Purpose |
|------|---------|
| `CALENDAR-CONVERTER/catalysts.yaml` | 当前催化剂列表 (手动 + 自动) |
| `CALENDAR-CONVERTER/catalyst_archive.yaml` | 已归档催化剂 + 实际结果 |
| `CALENDAR-CONVERTER/catalysts.ics` | 导出的日历文件 |
| `PORTFOLIO/research/companies/*/thesis.yaml` | 自动聚合来源 |

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/thesis` | 从 thesis.yaml 自动聚合催化剂；归档结果建议更新 thesis |
| `/today` | 晨间简报引用近期催化剂 |
| `/trade` | 催化剂触发交易时自动关联 |
| `/consensus-dashboard` | Earnings 催化剂关联 consensus 数据 |
| `/review` | 月度回顾分析催化剂预测准确率 |

## Calibration Tracking

Over time, the archive builds an "expected vs. actual" track record:

```
📊 催化剂预测校准 (最近 20 个)

预期方向正确率: 65% (13/20)
Earnings 准确率: 70% (7/10)
Macro 准确率: 50% (3/6)
Corporate 准确率: 75% (3/4)

最大意外: NVDA Q3 — 预期 beat, 实际 guide down → thesis weakened
```

运行 `/calendar calibration` 可查看校准统计。
