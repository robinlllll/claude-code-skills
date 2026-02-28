# Post-Trade Checks

## 7. Post-Trade 自动检查

交易记录完成后，Claude **自动执行**以下检查（不需要用户要求）：

### 1. Thesis 自动检查
- 读取 `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/thesis.md`
- **如果 thesis 存在:**
  - 读取 Position History 表
  - 如果当前交易与 thesis 记录一致 → 自动添加新行到 Position History，输出 1 行摘要
  - 如果数据不一致（如 thesis 记录的方向/仓位与交易矛盾）→ 提示用户确认，不静默覆盖
  - 输出: "[Thesis: conviction High, last updated 15 days ago]"
- **如果 thesis 不存在:**
  - "{TICKER} 没有投资论文，建议 `/thesis {TICKER}` 创建"

### 2. Passed Record 自动检查
- 检查 `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/passed.md`
- **如果 passed.md 存在:**
  - "你曾在 {date} pass 了 {TICKER}，当时理由: {reason}。确定要交易？"
- **如果不存在:** 静默通过

### 3. Flashback 建议（不自动执行）
- 输出: "如需查看完整研究轨迹: `/flashback {TICKER}`"
- 不自动执行（扫描 12 个数据源，token 消耗大）

After exit trades (SELL/COVER), also prompt: "考虑更新 thesis: `/thesis {TICKER} update \"Exited — {REASON}\"`"

### 4. Auto-Task Creation (via task_manager)
交易记录完成后，自动创建跟进任务（7 天去重，不会重复创建）：
```python
try:
    import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
    from shared.task_manager import auto_create_task
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    auto_create_task(
        f"Update thesis after {ACTION} {TICKER}",
        source="post-trade", category="thesis", ticker=TICKER,
        priority=2, due_at=tomorrow, estimated_minutes=20,
        dedup_key=f"post-trade-thesis-{TICKER}-{date.today().isoformat()}"
    )
except ImportError:
    pass
```
只在终端简短提示: `[Auto-task: Update thesis after BUY NVDA — due tomorrow]`

## Decision Journal

Trade logging and decision journaling are **separate concerns**:
- `/trade` = execution record (speed, minimal friction, market hours)
- Decision Journal = thought process + emotions (captured via **Nightly Journal Check at 10 PM** through Telegram)

**Do NOT ask DJ questions during `/trade`.** The Telegram bot will automatically push each unrecorded trade at 10 PM and walk through the DJ flow (emotion → confidence → why now → what if wrong → alternatives).

If the user wants to record DJ immediately, tell them to use `/dj TICKER ACTION` in Telegram.

## 交易反思（自动追加）

交易记录完成后，自动追加 `shared/reflection_questions.yaml` 中的 post_trade 问题（T1-T3）。
