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


def _get_yesterday_themes() -> dict:
    """Get yesterday's ingested items grouped by theme.

    Returns:
        {
            "total": 12,
            "by_theme": {"NVDA": [{"title": "...", "type": "substack"}, ...], ...},
            "unthemed": [{"title": "...", "type": "podcast"}, ...],
        }
    """
    try:
        from shared.task_manager import get_db
        import json as _json

        conn = get_db()
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            today_str = datetime.now().strftime("%Y-%m-%d")
            rows = conn.execute(
                """SELECT item_title, item_type, themes_found, tickers_found, has_themes
                   FROM ingestion_pipeline
                   WHERE ingested_at >= ? AND ingested_at < ?""",
                (yesterday, today_str),
            ).fetchall()

            by_theme = {}
            unthemed = []
            for row in rows:
                r = dict(row)
                themes = _json.loads(r.get("themes_found") or "[]")
                if themes:
                    for t in themes:
                        by_theme.setdefault(t, []).append({
                            "title": r["item_title"][:60],
                            "type": r["item_type"],
                        })
                else:
                    unthemed.append({
                        "title": r["item_title"][:60],
                        "type": r["item_type"],
                    })

            return {
                "total": len(rows),
                "by_theme": by_theme,
                "unthemed": unthemed,
            }
        finally:
            conn.close()
    except Exception:
        return {"total": 0, "by_theme": {}, "unthemed": []}


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


def _get_overnight_alerts(hours: int = 16) -> list[dict]:
    """Get price alerts from the last N hours (overnight)."""
    alerts_log = Path.home() / ".claude" / "data" / "price_alerts.jsonl"
    if not alerts_log.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    alerts = []
    try:
        for line in alerts_log.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                alerts.append(entry)
    except Exception:
        pass
    return alerts


def _get_overnight_developments(tickers, threshold=2.0):
    """Get pre-market / after-hours movers >threshold% with one news headline each."""
    if not tickers:
        return []
    results = []
    try:
        import yfinance as yf
        for ticker in tickers[:15]:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                if not prev_close:
                    continue
                # Pre-market price
                pre_price = info.get("preMarketPrice")
                post_price = info.get("postMarketPrice")
                price = pre_price or post_price
                if not price:
                    continue
                change_pct = ((price - prev_close) / prev_close) * 100
                if abs(change_pct) < threshold:
                    continue
                session = "盘前" if pre_price else "盘后"
                # Grab latest news headline
                headline = ""
                try:
                    news = stock.news
                    if news:
                        first = news[0]
                        # Support both old and new yfinance news structure
                        content = first.get("content", {})
                        if content:
                            headline = content.get("title", "")
                        if not headline:
                            headline = first.get("title", "")
                except Exception:
                    pass
                results.append({
                    "ticker": ticker,
                    "change_pct": change_pct,
                    "session": session,
                    "headline": headline,
                })
            except Exception:
                continue
    except ImportError:
        pass
    results.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return results


def _get_earnings_reaction(tickers):
    """Check if any portfolio tickers reported earnings yesterday; return reaction table rows."""
    if not tickers:
        return []
    results = []
    yesterday = (datetime.now() - timedelta(days=1)).date()
    try:
        import yfinance as yf
        for ticker in tickers[:15]:
            try:
                stock = yf.Ticker(ticker)
                # Check calendar for earnings date
                cal = stock.calendar
                if cal is None:
                    continue
                # calendar can be a dict or a DataFrame; normalise to dict
                if hasattr(cal, "to_dict"):
                    cal = cal.to_dict()
                earn_date = None
                # Try common key names
                for key in ("Earnings Date", "earningsDate", "earnings_date"):
                    val = cal.get(key)
                    if val is not None:
                        # May be a list (range) or a single value
                        if isinstance(val, (list, tuple)) and val:
                            val = val[0]
                        try:
                            from pandas import Timestamp
                            if hasattr(val, "date"):
                                earn_date = val.date()
                            else:
                                earn_date = Timestamp(val).date()
                        except Exception:
                            pass
                        break
                if earn_date != yesterday:
                    continue
                # Fetch actuals vs estimates
                info = stock.info
                eps_est = info.get("epsEstimateCurrentYear") or info.get("epsForward")
                eps_act = info.get("trailingEps")
                rev_est = info.get("revenueEstimate") or info.get("revenueForecasts")
                rev_act = info.get("totalRevenue") or info.get("revenue")
                # After-hours reaction
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                post_price = info.get("postMarketPrice")
                reaction = ""
                if post_price and prev_close:
                    reaction_pct = ((post_price - prev_close) / prev_close) * 100
                    reaction = f"{reaction_pct:+.1f}%"

                def _fmt_rev(v):
                    if v is None:
                        return "N/A"
                    if v >= 1e9:
                        return f"${v/1e9:.1f}B"
                    if v >= 1e6:
                        return f"${v/1e6:.0f}M"
                    return f"${v:.0f}"

                def _fmt_eps(v):
                    return f"${v:.2f}" if v is not None else "N/A"

                results.append({
                    "ticker": ticker,
                    "eps_est": _fmt_eps(eps_est),
                    "eps_act": _fmt_eps(eps_act),
                    "rev_est": _fmt_rev(rev_est),
                    "rev_act": _fmt_rev(rev_act),
                    "reaction": reaction or "N/A",
                })
            except Exception:
                continue
    except ImportError:
        pass
    return results


def generate_trade_ideas():
    """Scan thesis files for actionable trade ideas (catalysts, conviction changes, revisit triggers)."""
    ideas = []
    companies_dir = str(THESIS_DIR)
    if not THESIS_DIR.exists():
        return ""

    today = datetime.now()
    five_days_out = today + timedelta(days=5)
    seven_days_ago = today - timedelta(days=7)

    for ticker_dir in THESIS_DIR.iterdir():
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name.upper()

        yaml_path = ticker_dir / "thesis.yaml"
        thesis_path = ticker_dir / "thesis.md"
        passed_path = ticker_dir / "passed.md"

        # --- 1. thesis.yaml: upcoming kill-criteria catalysts ---
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    kill_criteria = data.get("kill_criteria") or []
                    if isinstance(kill_criteria, list):
                        for kc in kill_criteria:
                            if not isinstance(kc, dict):
                                continue
                            expected = kc.get("expected_by", "")
                            if not expected:
                                continue
                            # Only parse concrete date strings, skip "Q1 2026" style
                            expected_str = str(expected)
                            if "Q" in expected_str.upper():
                                continue
                            try:
                                from dateutil.parser import parse as _parse
                                cat_date = _parse(expected_str).replace(tzinfo=None)
                                if today <= cat_date <= five_days_out:
                                    ideas.append({
                                        "ticker": ticker,
                                        "direction": "关注",
                                        "trigger": kc.get("criteria", "近期 kill criteria")[:30],
                                        "time": cat_date.strftime("%b %d"),
                                        "suggestion": "验证是否触发清仓条件",
                                    })
                            except Exception:
                                pass
            except Exception:
                pass

        # --- 2. thesis.md: conviction changes in last 7 days ---
        if thesis_path.exists():
            try:
                text = thesis_path.read_text(encoding="utf-8")
                # Look for "Conviction: X → Y" or "conviction: X" patterns in recent log entries
                import re
                # Match lines like: "Conviction: 3 → 4" or "conviction changed from 3 to 4"
                arrow_hits = re.findall(
                    r"conviction[:\s]+(\d)\s*[→\->]+\s*(\d)",
                    text,
                    re.IGNORECASE,
                )
                if arrow_hits:
                    # Check if the section containing this hit is recent (within 7 days)
                    # Heuristic: look for a date stamp nearby
                    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")
                    dated_sections = list(date_pattern.finditer(text))
                    for match in re.finditer(
                        r"conviction[:\s]+(\d)\s*[→\->]+\s*(\d)",
                        text,
                        re.IGNORECASE,
                    ):
                        # Find nearest date before this position
                        pos = match.start()
                        nearest_date_str = None
                        for dm in reversed(dated_sections):
                            if dm.start() <= pos:
                                nearest_date_str = dm.group(1)
                                break
                        if nearest_date_str:
                            try:
                                entry_date = datetime.strptime(nearest_date_str, "%Y-%m-%d")
                                if entry_date >= seven_days_ago:
                                    old_c, new_c = match.group(1), match.group(2)
                                    arrow = "↑" if int(new_c) > int(old_c) else "↓"
                                    ideas.append({
                                        "ticker": ticker,
                                        "direction": "持有" if arrow == "↑" else "减仓",
                                        "trigger": f"Conviction {arrow} ({old_c}→{new_c})",
                                        "time": nearest_date_str,
                                        "suggestion": "复查最新 thesis 更新",
                                    })
                                    break  # one entry per ticker
                            except Exception:
                                pass
            except Exception:
                pass

        # --- 3. passed.md: revisit trigger check ---
        if passed_path.exists():
            try:
                content = passed_path.read_text(encoding="utf-8")
                if "price_at_pass:" in content or "revisit_trigger" in content:
                    ideas.append({
                        "ticker": ticker,
                        "direction": "回顾",
                        "trigger": "Revisit trigger check",
                        "time": "—",
                        "suggestion": "检查是否满足 revisit 条件",
                    })
            except Exception:
                pass

    if not ideas:
        return ""

    lines = ["", "## 💡 交易建议\n"]
    lines.append("| Ticker | 方向 | 触发事件 | 时间 | 建议 |")
    lines.append("|--------|------|---------|------|------|")
    for idea in ideas:
        lines.append(
            f"| {idea['ticker']} | {idea['direction']} | {idea['trigger']} | {idea['time']} | {idea['suggestion']} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_brief(quick=False):
    """Generate the full morning brief."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# 📅 {date_str} 晨间简报\n"]

    # 1. Portfolio tickers
    tickers = _get_portfolio_tickers()

    # 1a. Overnight developments (pre/after-market movers >2%)
    if tickers and not quick:
        overnight_devs = _get_overnight_developments(tickers)
        if overnight_devs:
            lines.append("## 🌙 隔夜动态\n")
            for d in overnight_devs:
                headline_str = f' — "{d["headline"]}"' if d["headline"] else ""
                sign = "+" if d["change_pct"] > 0 else ""
                lines.append(f"**{d['ticker']}**: {sign}{d['change_pct']:.1f}% ({d['session']}){headline_str}")
            lines.append("")

    # 1b. Yesterday's earnings reaction
    if tickers and not quick:
        earnings_rows = _get_earnings_reaction(tickers)
        if earnings_rows:
            lines.append("## 📊 昨日财报反应\n")
            lines.append("| 公司 | EPS 预期 | EPS 实际 | 收入预期 | 收入实际 | 盘后反应 |")
            lines.append("|------|---------|---------|---------|---------|---------|")
            for r in earnings_rows:
                lines.append(
                    f"| {r['ticker']} | {r['eps_est']} | {r['eps_act']} | {r['rev_est']} | {r['rev_act']} | {r['reaction']} |"
                )
            lines.append("")

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

    # Overnight alerts (from price monitor)
    overnight = _get_overnight_alerts()
    if overnight:
        lines.append("")
        lines.append("## 异动监控回顾")
        lines.append("")
        lines.append("| Ticker | 变动 | 量比 | 原因 |")
        lines.append("|--------|------|------|------|")
        for a in overnight:
            lines.append(
                f"| {a['ticker']} | {a['change_pct']:+.1f}% | {a.get('volume_ratio', 'N/A')}x | {a.get('reason', 'N/A')[:40]} |"
            )

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

    # 6. Yesterday's ingestion by theme (§ 📥 昨日入库)
    theme_data = _get_yesterday_themes()
    if theme_data["total"] > 0:
        lines.append(f"## 📥 昨日入库 ({theme_data['total']} 条)\n")

        if theme_data["by_theme"]:
            lines.append("| Theme | Count | 代表性标题 |")
            lines.append("|-------|-------|-----------|")
            for theme, items in sorted(theme_data["by_theme"].items(), key=lambda x: -len(x[1])):
                rep_title = items[0]["title"]
                lines.append(f"| {theme} | {len(items)} | {rep_title} |")

        if theme_data["unthemed"]:
            lines.append(f"\n无主题: {len(theme_data['unthemed'])} 条")
            for item in theme_data["unthemed"][:3]:
                lines.append(f"- [{item['type']}] {item['title']}")

        lines.append("")
    else:
        # Fallback to original KB count if no pipeline data
        kb_count = _get_kb_recent()
        if kb_count > 0:
            lines.append(f"## 📚 知识库\n")
            lines.append(f"- 昨日新增 {kb_count} 份研究资料\n")

    # 7. Consensus downgrade alerts
    if tickers and not quick:
        try:
            from shared.consensus_data import scan_portfolio_downgrades, render_alerts_md
            alerts = scan_portfolio_downgrades(tickers[:10], track=True)
            if alerts:
                lines.append(render_alerts_md(alerts))
        except Exception:
            pass

    # 8. 13F deadline
    deadline_msg = _check_13f_deadline()
    if deadline_msg:
        lines.append(f"## 📅 提醒\n")
        lines.append(f"- {deadline_msg}\n")

    # 9. Trade ideas (catalyst-driven, conviction changes, revisit triggers)
    if not quick:
        trade_ideas_block = generate_trade_ideas()
        if trade_ideas_block:
            lines.append(trade_ideas_block)

    return "\n".join(lines)


def main():
    quick = "--quick" in sys.argv

    brief = generate_brief(quick=quick)

    # Save to Obsidian first (before print, which can fail if stdout closed)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{date_str} - 晨间简报.md"

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

    try:
        print(brief)
        print(f"\n💾 Saved to: {output_file.relative_to(VAULT_DIR)}")
    except ValueError:
        # stdout may be closed in some environments
        import sys as _sys
        _sys.stderr.write(f"💾 Saved to: {output_file.relative_to(VAULT_DIR)}\n")


if __name__ == "__main__":
    main()
