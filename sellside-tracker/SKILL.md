---
name: sellside
description: 卖方报告结构化跟踪 — PDF/PPTX → AI提取 → YAML存储 → QoQ对比 → Obsidian笔记
---

# Sellside Report Tracker

将卖方季度跟踪报告（PDF/PPTX）自动提取为结构化数据，生成 QoQ 对比和 Obsidian 研究笔记。

## Project Location

`C:\Users\thisi\.claude\skills\sellside-tracker`

## When to Use This Skill

- User provides a sellside report file (PDF or PPTX)
- User says "卖方跟踪", "sellside", "卖方报告"
- User wants to extract KPIs from an analyst report
- User wants quarter-over-quarter comparison of a company's metrics
- User says "/sellside" with a file path

## Syntax

```
/sellside <file_path> [--ticker GOOG] [--quarter Q4-2025]
/sellside <file_path> --dry-run
/sellside <file_path> --no-obsidian
/sellside --history TICKER
```

**Examples:**
- `/sellside "C:/Users/thisi/Downloads/Google 25Q4.pdf"` — 自动检测 ticker 和 quarter，完整流程
- `/sellside report.pptx --ticker META --quarter Q3-2025` — 手动指定 ticker/quarter
- `/sellside report.pdf --dry-run` — 仅提取，不保存
- `/sellside report.pdf --ticker AMZN` — 通用模式（无 CSV 模板时自动触发）
- `/sellside --history AMZN` — 查看 AMZN 的历史券商观点变化表

## What It Does

The script has two operating modes, auto-detected based on whether a CSV template exists for the ticker.

### Mode 1: Template Mode (CSV exists — deep KPI tracking)

1. **文件提取** — PDF (pymupdf) 或 PPTX (python-pptx) 全文提取，带页码标记
2. **KPI 提取 (Pass 1)** — Gemini 按 CSV 模板结构化提取指标 → YAML（含 value, source_page, confidence, note）
3. **全文摘要 (Pass 2)** — Gemini 生成 8 section 叙事摘要，带页码引用
4. **校验** — 必填字段检查 + 异常值检测 + 与上季数据一致性校验
5. **QoQ 对比** — 自动与上季数据对比，生成变化表（含信号标注）
6. **保存** — YAML 时序数据库 + Obsidian Vault 笔记

### Mode 2: Generic Mode (no CSV template — auto-detected)

When no CSV template is found for a ticker, the script falls back to generic extraction:

1. **文件提取** — 同上
2. **通用 JSON 提取** — Gemini 提取标准化字段：firm, analyst, rating, prior_rating, target_price, prior_target, currency, key_thesis, catalysts, risks, estimates
3. **SQLite 存储** — 观点保存到 `data/sellside_views.db`（UNIQUE 约束 ticker+date+firm，支持 INSERT OR REPLACE）
4. **叙事摘要** — Gemini 生成中文投资笔记
5. **Obsidian 笔记** — 单报告笔记 + 汇总观点笔记（`{TICKER} 券商观点汇总.md`）
6. **Vector memory** — 自动 upsert 到向量记忆层

### History Display

```bash
python extract.py --history TICKER
```

Shows a table of all recorded analyst views for a ticker: date, firm, rating changes (Prior → Current), target price changes. Also shows consensus distribution (Buy/Hold/Sell counts) and average target price.

### Obsidian 输出结构 (3 层 — Template Mode)

1. **叙事摘要** — 核心观点 + 8 个业务 section（Search、Cloud、YouTube、AI、财务、估值等）
2. **QoQ 对比表** — 关键指标季度变化，含加速/减速信号
3. **KPI 明细附录** — 可折叠，按 segment 分组的完整指标表

### CSV 模板系统

每家公司一个 CSV 模板，定义该公司需要跟踪的指标：

```
segment,key,label,type,required,notes
financials,revenue_yoy,总收入 YoY,percent,yes,
search,search_rev_yoy,Search 收入 YoY,percent,yes,
cloud,cloud_rev_yoy,Cloud 收入 YoY,percent,yes,
```

扩展新公司只需新建 CSV，零代码。无 CSV 时自动使用通用模式。

## Workflow

### 1. Parse Arguments

从用户输入中提取：
- `file_path` — PDF 或 PPTX 路径
- `--ticker` — 可选，自动从文件名检测（支持 TICKER_ALIASES：google→GOOG）
- `--quarter` — 可选，自动从文件名检测（Q4-2025 格式）
- `--dry-run` — 仅提取，不保存到 YAML 和 Obsidian
- `--no-obsidian` — 保存 YAML 但跳过 Obsidian

### 2. Run Extract

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/sellside-tracker/extract.py" "<file_path>" [--ticker TICKER] [--quarter Q4-2025] [--dry-run] [--no-obsidian]
```

### 3. Review Output

脚本会输出：
- 提取进度和指标填充率（如 24/31）
- 校验警告
- 指标摘要表
- QoQ 对比表
- Obsidian 保存确认

## Key Files

| File | Purpose |
|------|---------|
| `extract.py` | 主脚本：提取 → AI → 校验 → 存储 → 对比 → Obsidian |
| `templates/*.csv` | 公司指标模板（每公司一个，无则自动通用模式） |
| `data/{ticker}_quarterly.yaml` | 季度时序数据库（Template Mode） |
| `data/sellside_views.db` | SQLite 券商观点数据库（Generic Mode，UNIQUE: ticker+date+firm） |

## Available Templates

| Template | Ticker | Indicators |
|----------|--------|------------|
| `goog.csv` | GOOG | 31 indicators (financials, search, cloud, youtube, ai, other, qualitative) |

### Adding a New Company

**Generic mode (instant, no setup):**
- Just run `/sellside report.pdf --ticker TICKER` — works for any ticker with no CSV template
- Saves to SQLite + Obsidian automatically

**Template mode (deep KPI tracking):**
1. Create `templates/{ticker}.csv` with columns: `segment,key,label,type,required,notes`
2. Run `/sellside report.pdf --ticker TICKER`
3. Done — YAML + Obsidian auto-generated with full QoQ comparison

## Data Storage

### YAML (`data/{ticker}_quarterly.yaml`)

```yaml
Q4-2025:
  ticker: GOOG
  quarter: Q4-2025
  report_date: 2026-02
  source: 方岚
  metrics:
    revenue_yoy:
      value: 14%
      source_page: 6
      confidence: high
      note: null
```

### Obsidian (`研究/卖方跟踪/{TICKER}/`)

```
研究/卖方跟踪/
├── GOOG/
│   ├── 2026-02-11 GOOG Q4-2025 卖方跟踪.md
│   └── 2025-10-xx GOOG Q3-2025 卖方跟踪.md
└── META/
    └── ...
```

## Dependencies

- `pymupdf` — PDF text extraction
- `python-pptx` — PPTX text extraction
- `google-genai` — Gemini API (key from `skills/prompt-optimizer/data/config.json`)
- `pyyaml` — YAML serialization
- `shared.obsidian_utils` — Vault note creation
- `shared.dashboard_updater` — Dashboard integration

## Input

Sellside analyst reports in PDF or PPTX format. Tested with:
- 方岚 quarterly tracking reports (Chinese, ~28 pages)
- Quarterly update presentations (PPTX)

## Output

- Structured YAML with all KPIs + source pages + confidence levels
- Rich Obsidian note with narrative summary + QoQ comparison + KPI appendix
- Console summary with extraction stats and warnings
