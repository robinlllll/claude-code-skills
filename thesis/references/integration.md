## Open Questions 展示

在 `/thesis TICKER view` 输出末尾，自动查询 `task_manager.py questions TICKER`，展示该 ticker 的未解决研究问题：

```markdown
## 待解决的研究问题
来源: open_questions DB
1. [HIGH] 问题描述... (since 2026-02-09)
→ 建议: /research TICKER "具体问题"
```

如果没有 open questions，跳过此部分。

实现：
```bash
cd ~/.claude/skills && python shared/task_manager.py questions TICKER
```

---

## 反思检查站（自动追加）

在 `/thesis TICKER view` 和 `/thesis TICKER challenge` 输出末尾，自动追加 `shared/reflection_questions.yaml` 中的 7 个反思问题（R1-R7）。

Challenge 模式已有灵魂拷问机制，反思问题作为补充框架，确保覆盖 recency bias 和 position-induced bias。

---

## Key Files

- `research/companies/{TICKER}/thesis.md` - Active thesis document (markdown, detailed)
- `research/companies/{TICKER}/thesis.yaml` - Structured data (kill criteria, peers, conviction, sizing)
- `research/companies/{TICKER}/passed.md` - Why I Passed record
- `research/companies/{TICKER}/notes/` - Additional research notes
- `decisions/trades/*_{TICKER}.md` - Related trade logs

## thesis.yaml Schema

```yaml
ticker: TICKER

# --- Lifecycle Status ---
thesis_status: active          # active / watching / past
status_changed_at: 'YYYY-MM-DD'
status_reason: "Migration: In current portfolio"

invalidation_price: 0         # Price-based stop (read by BiasEngine)
invalidation_window_days: 2
bear_case_1: "..."
bear_case_2: "..."
bull_case: "..."
horizon_days: 365
conviction: 4                  # 1-5 scale
target_weight_pct: 8
created_date: YYYY-MM-DD

# --- Phase 4: Idea Attribution (NLM-assisted) ---
idea_source: weekly-meeting    # substack/x/podcast/13f/supply-chain/weekly-meeting/chatgpt/self-research/other
source_detail: "投资观点周报 2025, 2025-12-15"
source_link: "[[2025-12-15 - 投资观点周报]]"
nlm_citation: "首次在 Week 50 讨论，初始情绪看多..."  # NLM verbatim citation
first_seen: 2025-12-15         # Date idea first appeared
first_position: 2026-02-01     # Date first trade was made (auto-filled by /trade)

kill_criteria:
  - condition: "Description of what would invalidate thesis"
    type: quantitative         # or qualitative
    threshold: "<50%"          # quantitative only
    status: active             # active / triggered / retired
    last_checked: YYYY-MM-DD
    check_result: pass         # pass / warning / fail / unchecked
    check_note: "Brief rationale for the assessment"
    data_source: "10-Q filing"       # where to find evidence
    expected_by: "Q2 2026 earnings"  # when to expect evidence
    trend: stable              # improving / stable / deteriorating
    trend_history: []          # list of "check_result:trend" strings, e.g. ["pass:stable", "pass:improving"]

peers:
  - ticker: "BATS"
    relationship: "Global competitor"

supply_chain:
  - "Key regulatory/supply dependency"

quality_grade: "B"             # A/B/C based on KC clarity + data availability

sector_framework: "Semiconductors"  # Resolved from entity_dictionary + sector_metrics.yaml
sector_canonical_kpis: ["Revenue by End Market", "GM%", "Inventory Days"]  # Primary KPIs for quick reference
```

## Framework Coverage Integration

### In Thesis Template

Add a `## Framework Coverage` section at the end of the thesis template, after Thesis Log:

```markdown
## Framework Coverage

| # | Section | Level | Key Source |
|---|---------|-------|-----------|
| S1 | Market & Growth | ✅ | earnings Q4, CAGNY |
| S2 | Competitive Landscape | ✅ | supply chain, earnings |
| ... | ... | ... | ... |

Score: 83% (7/9 covered) | Last scan: YYYY-MM-DD
Gaps: S5 管理层
```

### In thesis.yaml Schema

Add `framework_coverage` field:

```yaml
framework_coverage:
  score: 83
  last_scanned: 2026-02-07
  gaps: [S5]
  covered: [S1, S2, S3, S4, S6, S7, S8]
```

### Auto-Scan on Create

After creating a new thesis (step 4B), automatically run:
```bash
cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER --brief
```
Show the coverage result as a gap alert:
> "Framework coverage: 45% — S3 护城河, S5 管理层, S6 估值, S7 风险 需要更多研究。
> 运行 `/research TICKER --deep` 可针对性填补盲区。"

### In `/thesis TICKER check`

Add framework coverage check after kill criteria check (step 4 in check workflow):
```bash
cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER --format json
```
If any section has degraded since last scan → flag it.
If `framework_coverage.last_scanned` is >30 days ago → suggest re-scan.

## Auto-Task Integration

### Staleness Alerts → Tasks
`scripts/thesis_staleness_check.py` (daily 08:30) automatically creates tasks for stale theses with new mentions:
```python
auto_create_task(
    f"Review stale thesis: {TICKER} ({days_stale} days)",
    source="thesis-stale", category="thesis", ticker=TICKER,
    priority=2, dedup_key=f"thesis-stale-{TICKER}-{today}"
)
```
These tasks appear in `/task list` and the daily brief.

### Post-Trade → Thesis Update Task
When `/trade` creates a task "Update thesis after BUY NVDA", `/thesis TICKER` is the natural follow-up.

## Integration with /trade

When a trade is logged via `/trade`, the thesis position history should be updated automatically if the thesis exists.
