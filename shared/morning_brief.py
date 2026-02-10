#!/usr/bin/env python3
"""
Morning Brief Generator.
Aggregates portfolio changes, news, tasks, inbox, thesis alerts.
"""

import sys
import io
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
PORTFOLIO_DIR = Path.home() / "PORTFOLIO"
INBOX_DIR = VAULT_DIR / "收件箱"
THESIS_DIR = PORTFOLIO_DIR / "research" / "companies"
OUTPUT_DIR = VAULT_DIR / "收件箱"


def _get_portfolio_tickers():
    """Get current portfolio tickers from portfolio.db or thesis directories."""
    tickers = []
    # Try reading from portfolio database
    try:
        import sqlite3
        db_path = PORTFOLIO_DIR / "portfolio_monitor" / "data" / "portfolio.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            # Get tickers that have trades (simple heuristic for current holdings)
            cursor = conn.execute("""
                SELECT DISTINCT ticker
                FROM trades
                WHERE ticker NOT LIKE '%/%'
                  AND ticker NOT LIKE '% %'
                  AND LENGTH(ticker) <= 6
                  AND ticker NOT LIKE 'ZN%'
                  AND ticker NOT LIKE 'SPX%'
                  AND ticker NOT LIKE 'NDX%'
                ORDER BY ticker
            """)
            rows = cursor.fetchall()
            conn.close()
            # Filter to reasonable stock tickers (exclude options, futures, currencies)
            for row in rows:
                ticker = row[0]
                # Skip currency pairs, bonds, and options
                if '.' in ticker and ticker.count('.') > 1:
                    continue
                if ticker.endswith('.USD') or ticker.endswith('.GBP') or ticker.endswith('.HKD'):
                    continue
                if any(x in ticker for x in ['USD.', 'EUR.', 'GBP.', 'HKD.', 'JPY.']):
                    continue
                if ticker.isdigit() and len(ticker) == 4:
                    # Hong Kong stocks
                    continue
                tickers.append(ticker)
    except Exception:
        pass

    # Fallback: use thesis directories
    if not tickers and THESIS_DIR.exists():
        for d in THESIS_DIR.iterdir():
            if d.is_dir() and (d / "thesis.md").exists():
                tickers.append(d.name.upper())

    return tickers[:20]  # Limit to top 20 to avoid API overload


def _get_market_data(tickers, quick=False):
    """Get price changes for portfolio tickers."""
    if quick:
        return []

    results = []
    try:
        import yfinance as yf
        for ticker in tickers[:15]:  # Limit to avoid API overload
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                if price and prev_close:
                    change_pct = ((price - prev_close) / prev_close) * 100
                    week52_high = info.get("fiftyTwoWeekHigh", 0)
                    week52_low = info.get("fiftyTwoWeekLow", 0)
                    note = ""
                    if week52_high and price > week52_high * 0.95:
                        note = "接近 52 周新高"
                    elif week52_low and price < week52_low * 1.05:
                        note = "接近 52 周新低"
                    results.append({
                        "ticker": ticker,
                        "price": price,
                        "change_pct": change_pct,
                        "note": note,
                    })
            except Exception:
                continue
    except ImportError:
        pass
    # Sort by absolute change
    results.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return results


def _get_inbox_count():
    """Count new notes in inbox from last 24 hours."""
    if not INBOX_DIR.exists():
        return 0, []
    cutoff = datetime.now() - timedelta(hours=24)
    new_files = []
    for f in INBOX_DIR.glob("*.md"):
        if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
            new_files.append(f.name)
    return len(new_files), new_files[:5]


def _get_stale_theses(days=30):
    """Find theses not updated in N days."""
    stale = []
    if not THESIS_DIR.exists():
        return stale
    cutoff = datetime.now() - timedelta(days=days)
    for d in THESIS_DIR.iterdir():
        thesis_file = d / "thesis.md"
        if thesis_file.exists():
            mtime = datetime.fromtimestamp(thesis_file.stat().st_mtime)
            if mtime < cutoff:
                days_old = (datetime.now() - mtime).days
                stale.append({"ticker": d.name.upper(), "days": days_old})
    stale.sort(key=lambda x: x["days"], reverse=True)
    return stale


def _get_tasks_summary():
    """Get today's task summary."""
    try:
        from shared.task_manager import suggest_daily_plan, open_questions_summary
        plan = suggest_daily_plan()
        oq = open_questions_summary()
        return plan, oq
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, []


def _get_kb_recent(days=1):
    """Get recently added knowledge base items."""
    try:
        from shared.task_manager import search_knowledge_index
        results = search_knowledge_index(days=days)
        return len(results)
    except Exception:
        return 0


def _check_13f_deadline():
    """Check if within 7 days of a 13F deadline."""
    deadlines = [
        (2, 14, "Q4"),   # Feb 14
        (5, 15, "Q1"),   # May 15
        (8, 14, "Q2"),   # Aug 14
        (11, 14, "Q3"),  # Nov 14
    ]
    today = datetime.now()
    for month, day, quarter in deadlines:
        deadline = datetime(today.year, month, day)
        days_until = (deadline - today).days
        if 0 <= days_until <= 7:
            return f"距离 {quarter} 13F 截止日还有 {days_until} 天"
    return None


def generate_brief(quick=False):
    """Generate the full morning brief."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# 📅 {date_str} 晨间简报\n"]

    # 1. Portfolio tickers
    tickers = _get_portfolio_tickers()

    # 2. Market data
    if tickers:
        lines.append("## 📊 持仓动态\n")
        market = _get_market_data(tickers, quick=quick)
        if market:
            lines.append("| Ticker | 价格 | 变动 | 备注 |")
            lines.append("|--------|------|------|------|")
            for m in market:
                emoji = "🟢" if m["change_pct"] > 0 else "🔴" if m["change_pct"] < 0 else "⚪"
                lines.append(f"| {m['ticker']} | ${m['price']:.2f} | {m['change_pct']:+.1f}% {emoji} | {m['note']} |")
            lines.append("")

            # Flag big movers for news search
            big_movers = [m["ticker"] for m in market if abs(m["change_pct"]) > 3]
            if big_movers and not quick:
                lines.append(f"**异动 ticker（>3%）：** {', '.join(big_movers)} — 建议 WebSearch 查新闻\n")
        else:
            lines.append("*市场数据暂不可用*\n")

    # 3. Tasks
    lines.append("## ✅ 今日任务\n")
    try:
        plan, oq = _get_tasks_summary()
        if plan and plan.get("tasks"):
            task_list = plan["tasks"][:7]
            for i, t in enumerate(task_list, 1):
                priority = t.get("priority", "?")
                title = t.get("title", str(t))
                ticker = t.get("ticker")
                ticker_str = f" [{ticker}]" if ticker else ""
                lines.append(f"{i}. [P{priority}] {title}{ticker_str}")

            # Add summary stats
            total_min = plan.get("total_minutes", 0)
            overdue = plan.get("overdue_count", 0)
            util = plan.get("utilization_pct", 0)
            lines.append("")
            stats = []
            if total_min:
                stats.append(f"{total_min}分钟")
            if overdue:
                stats.append(f"{overdue}项逾期")
            if util:
                stats.append(f"容量{util}%")
            if stats:
                lines.append(f"*{' | '.join(stats)}*")
        else:
            lines.append("*无计划任务*")
        lines.append("")

        # Open questions summary
        if oq:
            lines.append("## 📌 未解决研究问题\n")
            lines.append("| Ticker | 问题数 | 高优先 | 最早 |")
            lines.append("|--------|--------|--------|------|")
            for q in oq:
                lines.append(f"| {q[0]} | {q[1]} | {q[2]} | {q[3][:10] if q[3] else '-'} |")
            lines.append("")
    except Exception as e:
        import traceback
        traceback.print_exc()
        lines.append(f"*任务加载失败: {e}*\n")

    # 4. Inbox
    inbox_count, inbox_files = _get_inbox_count()
    if inbox_count > 0:
        lines.append("## 📥 收件箱\n")
        lines.append(f"- {inbox_count} 篇新笔记待处理")
        for f in inbox_files:
            lines.append(f"  - {f}")
        lines.append("")

    # 5. Stale theses
    stale = _get_stale_theses()
    if stale:
        lines.append("## ⚠️ 需要关注\n")
        for s in stale[:5]:
            lines.append(f"- **{s['ticker']}** thesis 已 {s['days']} 天未更新")
        lines.append("")

    # 6. KB recent
    kb_count = _get_kb_recent()
    if kb_count > 0:
        lines.append(f"## 📚 知识库\n")
        lines.append(f"- 昨日新增 {kb_count} 份研究资料\n")

    # 7. 13F deadline
    deadline_msg = _check_13f_deadline()
    if deadline_msg:
        lines.append(f"## 📅 提醒\n")
        lines.append(f"- {deadline_msg}\n")

    return "\n".join(lines)


def main():
    quick = "--quick" in sys.argv

    brief = generate_brief(quick=quick)
    print(brief)

    # Save to Obsidian
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{date_str} - 晨间简报.md"

    # Add frontmatter
    content = f"""---
tags: [morning-brief, auto-generated]
date: {date_str}
type: morning-brief
---

{brief}
"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n💾 Saved to: {output_file.relative_to(VAULT_DIR)}")


if __name__ == "__main__":
    main()
