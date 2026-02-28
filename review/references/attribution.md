# Attribution, Skill Integration & Notes

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
2. Report shows: Source -> Ideas -> Positions -> Pass Rate -> Avg Return -> Win Rate
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
2. Part 1: Price tracking -- compares price_at_pass vs. current price for all passed records
3. Part 2: NLM discovery -- queries 投资观点周报 for tickers discussed but not in portfolio/passed
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

回顾报告生成后，如果 Next Actions 有 >=1 条，自动创建 **一个** meta-task（不是每条一个 task，减少噪音）：
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
