"""Review Aggregator — generates structured weekly/monthly review for /review skill.

Aggregates 10 data sources into a single Obsidian-formatted markdown review file.

Usage:
    python review_aggregator.py --period week [--days 7]
    python review_aggregator.py --period month [--days 30]
    python review_aggregator.py --dry-run  # print to stdout, don't save

Data sources:
    1. Portfolio trades (PM API / SQLite)
    2. Research Notes (Obsidian)
    3. Earnings Analysis (Obsidian)
    4. Thesis updates (thesis.md/yaml mtime)
    5. 周会 (Obsidian)
    6. Weekly Inbox (Obsidian)
    7. Podcast (Obsidian)
    8. BiasEngine dashboard (PM API)
    9. Kill Criteria scan (thesis.yaml)
    10. Decision Journal stats (decision_stats.py)
"""

import argparse
import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml

# ── Paths ──────────────────────────────────────────────────────────────────

HOME = Path.home()
PORTFOLIO_API = "http://localhost:8000"
PORTFOLIO_DB = HOME / "PORTFOLIO" / "portfolio_monitor" / "data" / "portfolio.db"
THESIS_DIR = HOME / "PORTFOLIO" / "research" / "companies"
VAULT = HOME / "Documents" / "Obsidian Vault"
REVIEWS_DIR = VAULT / "写作" / "投资回顾"
ESTIMATES_DIR = VAULT / "研究" / "估值"
JOURNAL_DIR = HOME / "PORTFOLIO" / "decisions" / "journal"

# Obsidian data source folders (restructured 2026-02-07)
RESEARCH_NOTES = VAULT / "研究" / "研究笔记"
EARNINGS_ANALYSIS = VAULT / "研究" / "财报分析"
ZHOUHUI = VAULT / "周会"
WEEKLY_INBOX = VAULT / "收件箱"
PODCAST = VAULT / "信息源" / "播客"

REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

PYTHON = str(HOME / "AppData" / "Local" / "Python" / "pythoncore-3.14-64" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable

DECISION_STATS = Path(__file__).parent / "decision_stats.py"
ESTIMATE_STATS = Path(__file__).parent / "estimate_stats.py"


# ── Helpers ────────────────────────────────────────────────────────────────

def files_in_period(folder: Path, days: int, extensions: tuple = (".md",)) -> list[Path]:
    """Find files date-prefixed within the lookback window.

    Uses date prefix in filename (YYYY-MM-DD) as primary filter.
    Falls back to mtime only for files without date prefixes AND only if
    the file was recently created (not just synced/touched).
    """
    if not folder.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    results = []
    for f in folder.rglob("*"):
        if f.suffix not in extensions or f.name.startswith("TEMPLATE"):
            continue
        # Try date prefix first (YYYY-MM-DD)
        match = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
        if match:
            if match.group(1) >= cutoff_str:
                results.append(f)
            continue  # Always skip mtime fallback if file has date prefix
        # Fall back to creation time (not mtime, which Syncthing updates)
        try:
            ctime = datetime.fromtimestamp(f.stat().st_ctime)
            if ctime >= cutoff:
                results.append(f)
        except Exception:
            pass
    results.sort(key=lambda p: p.name)
    return results


# ── Data Source Fetchers ───────────────────────────────────────────────────

async def fetch_trades(days: int) -> str:
    """Source 1: Recent trades from PM API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{PORTFOLIO_API}/api/trades")
            if resp.status_code != 200:
                return "_Portfolio Monitor API 不可用_\n"
            data = resp.json()
            trades = data.get("trades", [])
    except Exception:
        # SQLite fallback
        try:
            import sqlite3
            conn = sqlite3.connect(str(PORTFOLIO_DB))
            conn.row_factory = sqlite3.Row
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            cur = conn.execute(
                "SELECT * FROM trades WHERE entry_date >= ? ORDER BY entry_date DESC", (cutoff,)
            )
            trades = [dict(r) for r in cur.fetchall()]
            conn.close()
        except Exception as e:
            return f"_交易数据不可用: {e}_\n"

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [t for t in trades if (t.get("entry_date") or "") >= cutoff]

    if not recent:
        return "本期无交易。\n"

    lines = ["| 日期 | 方向 | Ticker | 数量 | 价格 |",
             "|------|------|--------|------|------|"]
    for t in recent[:20]:
        lines.append(
            f"| {t.get('entry_date', '?')} | {t.get('direction', '?')} | "
            f"{t.get('ticker', '?')} | {t.get('quantity', 0)} | "
            f"${t.get('entry_price', 0):.2f} |"
        )
    if len(recent) > 20:
        lines.append(f"_... +{len(recent) - 20} more_")
    return "\n".join(lines) + "\n"


def fetch_obsidian_files(folder: Path, label: str, days: int) -> str:
    """Sources 2-7: List recent Obsidian files from a folder."""
    files = files_in_period(folder, days)
    if not files:
        return f"本期无{label}。\n"
    lines = []
    for f in files[:15]:
        name = f.stem
        rel = f.relative_to(VAULT) if str(f).startswith(str(VAULT)) else f.name
        lines.append(f"- [[{name}]]")
    if len(files) > 15:
        lines.append(f"_... +{len(files) - 15} more_")
    return "\n".join(lines) + "\n"


async def fetch_bias_dashboard(days: int) -> str:
    """Source 8: BiasEngine dashboard."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{PORTFOLIO_API}/api/bias/dashboard",
                params={"lookback_days": days},
            )
            if resp.status_code != 200:
                return "_BiasEngine API 不可用_\n"
            data = resp.json()
    except Exception:
        return "_BiasEngine API 不可用 (Portfolio Monitor 未运行?)_\n"

    # Parse dashboard
    overall = data.get("overall_health", {})
    biases = data.get("biases", {})

    lines = [
        f"**Overall Health:** {overall.get('label', '?')} ({overall.get('score', '?')})\n",
        "| Bias | Severity | Confidence |",
        "|------|----------|------------|",
    ]

    # Flatten biases across instrument types
    seen = set()
    for inst_type, bias_list in biases.items():
        if isinstance(bias_list, list):
            for b in bias_list:
                bias_id = b.get("bias_id", "?")
                if bias_id in seen:
                    continue
                seen.add(bias_id)
                score = b.get("severity_score", 0)
                icon = "🟢" if score < 50 else "🟡" if score < 70 else "🔴"
                lines.append(
                    f"| {b.get('display_name', bias_id)} | {score:.0f} {icon} | "
                    f"{b.get('confidence', '?')} |"
                )

    # Flagged episodes
    insights = data.get("insights", {})
    multi_flagged = insights.get("multi_flagged_episodes", [])
    if multi_flagged:
        lines.append(f"\n**多重触发:** {len(multi_flagged)} 个 episode 被多个检测器标记")

    return "\n".join(lines) + "\n"


def scan_kill_criteria(days: int) -> str:
    """Source 9: Kill Criteria scan across all thesis.yaml files."""
    if not THESIS_DIR.exists():
        return "_No thesis directory_\n"

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    overdue_threshold_quant = 30  # days
    overdue_threshold_qual = 14  # days

    all_tickers = []
    overdue = []
    warnings = []
    no_kc = []
    violations = []  # KC fail_detected_at > 48h unresolved

    for d in sorted(THESIS_DIR.iterdir()):
        if not d.is_dir():
            continue
        yf = d / "thesis.yaml"
        if not yf.exists():
            continue
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception:
            continue

        ticker = d.name
        kcs = data.get("kill_criteria", [])

        if not kcs:
            no_kc.append(ticker)
            all_tickers.append({"ticker": ticker, "total": 0, "pass": 0, "warning": 0, "fail": 0, "unchecked": 0})
            continue

        stats = {"ticker": ticker, "total": len(kcs), "pass": 0, "warning": 0, "fail": 0, "unchecked": 0}
        for kc in kcs:
            result = kc.get("check_result", "unchecked")
            stats[result] = stats.get(result, 0) + 1

            # Check overdue
            last_checked = kc.get("last_checked", "")
            if last_checked:
                try:
                    checked_date = datetime.strptime(str(last_checked), "%Y-%m-%d")
                    age_days = (datetime.now() - checked_date).days
                    kc_type = kc.get("type", "quantitative")
                    threshold = overdue_threshold_qual if kc_type == "qualitative" else overdue_threshold_quant
                    if age_days > threshold:
                        overdue.append({
                            "ticker": ticker,
                            "condition": kc.get("condition", "?")[:50],
                            "last_checked": last_checked,
                            "days": age_days,
                        })
                except ValueError:
                    pass

            if result == "warning":
                warnings.append({"ticker": ticker, "condition": kc.get("condition", "?")[:50]})
            elif result == "fail":
                warnings.append({"ticker": ticker, "condition": f"FAIL: {kc.get('condition', '?')[:50]}"})

            # Check for discipline violations: fail_detected_at > 48h
            fail_at = kc.get("fail_detected_at")
            if fail_at:
                try:
                    if isinstance(fail_at, str):
                        fail_dt = datetime.fromisoformat(fail_at)
                    elif isinstance(fail_at, datetime):
                        fail_dt = fail_at
                    else:
                        fail_dt = None
                    if fail_dt:
                        hours_since = (datetime.now() - fail_dt).total_seconds() / 3600
                        if hours_since > 48:
                            violations.append({
                                "ticker": ticker,
                                "condition": kc.get("condition", "?")[:60],
                                "hours": round(hours_since),
                            })
                except (ValueError, TypeError):
                    pass

        all_tickers.append(stats)

    lines = []

    # Discipline Violations (highest priority — shown first)
    if violations:
        lines.append("### 🔴 DISCIPLINE VIOLATIONS — 纪律违规")
        lines.append("")
        lines.append("> Kill criteria 触发超过 48 小时未处理。必须立即行动。")
        lines.append("")
        lines.append("| Ticker | Failed Condition | Hours Unresolved |")
        lines.append("|--------|-----------------|------------------|")
        for v in violations:
            lines.append(f"| **{v['ticker']}** | {v['condition']} | {v['hours']}h |")
        lines.append("")

    # Overdue section
    if overdue:
        lines.append("### 需要立即检查（过期）")
        lines.append("| Ticker | Condition | Last Checked | Days |")
        lines.append("|--------|-----------|--------------|------|")
        for o in overdue:
            lines.append(f"| {o['ticker']} | {o['condition']} | {o['last_checked']} | {o['days']}d |")
        lines.append("")

    # Warnings
    if warnings:
        lines.append("### Warning/Fail 条件")
        for w in warnings:
            lines.append(f"- **{w['ticker']}**: {w['condition']}")
        lines.append("")

    # Summary table
    lines.append("### 全部持仓 Kill Criteria 总览")
    lines.append("| Ticker | Total | Pass | Warning | Fail | Unchecked |")
    lines.append("|--------|-------|------|---------|------|-----------|")
    for s in all_tickers:
        lines.append(
            f"| {s['ticker']} | {s['total']} | {s['pass']} | {s['warning']} | "
            f"{s['fail']} | {s['unchecked']} |"
        )
    lines.append("")

    # No KC warning
    if no_kc:
        lines.append("### 无 Kill Criteria 的持仓")
        for t in no_kc:
            lines.append(f"- **{t}** ← 没有定义退出条件")
        lines.append("")

    return "\n".join(lines) + "\n"


def fetch_decision_stats(days: int) -> str:
    """Source 10: Decision Journal stats."""
    if DECISION_STATS.exists():
        try:
            result = subprocess.run(
                [PYTHON, str(DECISION_STATS), "--days", str(days), "--output", "markdown"],
                capture_output=True, text=True, timeout=10, encoding="utf-8",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip() + "\n"
        except Exception:
            pass
    return "_Decision Journal 统计不可用_\n"


def fetch_estimate_stats(days: int) -> str:
    """Bonus: Estimate stats if available."""
    if ESTIMATE_STATS.exists():
        try:
            result = subprocess.run(
                [PYTHON, str(ESTIMATE_STATS), "--days", str(days), "--output", "markdown"],
                capture_output=True, text=True, timeout=10, encoding="utf-8",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip() + "\n"
        except Exception:
            pass
    return ""


def fetch_peers_reminder(days: int) -> str:
    """Source: Peers earnings/events reminder."""
    if not THESIS_DIR.exists():
        return ""

    peers_map = {}  # peer_ticker → [holding_ticker, ...]
    for d in sorted(THESIS_DIR.iterdir()):
        if not d.is_dir():
            continue
        yf = d / "thesis.yaml"
        if not yf.exists():
            continue
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for p in data.get("peers", []):
            peer_ticker = p.get("ticker", "")
            if peer_ticker:
                peers_map.setdefault(peer_ticker, []).append(d.name)

    if not peers_map:
        return ""

    # Check if any peer has recent earnings analysis
    recent_analysis = set()
    if EARNINGS_ANALYSIS.exists():
        for f in files_in_period(EARNINGS_ANALYSIS, days):
            # Extract ticker from folder name or filename
            for peer in peers_map:
                if peer.upper() in f.name.upper() or peer.upper() in str(f.parent).upper():
                    recent_analysis.add(peer)

    # Check 周会 mentions
    zhouhui_mentions = set()
    if ZHOUHUI.exists():
        for f in files_in_period(ZHOUHUI, days):
            try:
                content = f.read_text(encoding="utf-8")
                for peer in peers_map:
                    if peer.upper() in content.upper():
                        zhouhui_mentions.add(peer)
            except Exception:
                pass

    lines = []
    if recent_analysis or zhouhui_mentions or peers_map:
        lines.append("| 你的持仓 | Peer | 近期动态 |")
        lines.append("|---------|------|---------|")
        for peer, holdings in peers_map.items():
            events = []
            if peer in recent_analysis:
                events.append("有财报分析")
            if peer in zhouhui_mentions:
                events.append("周会提及")
            if not events:
                events.append("未关注")
            lines.append(f"| {', '.join(holdings)} | {peer} | {' + '.join(events)} |")

    return "\n".join(lines) + "\n" if lines else ""


async def compute_sizing_deviations() -> str:
    """Compute position sizing vs actual for all tickers with sizing data."""
    if not THESIS_DIR.exists():
        return ""

    # Get actual portfolio weights
    actual_weights = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{PORTFOLIO_API}/api/portfolio")
            if resp.status_code == 200:
                data = resp.json()
                nav = data.get("total_value", 0)
                if nav > 0:
                    for pos in data.get("positions", []):
                        ticker = pos.get("symbol", "").split()[0].upper()
                        mkt_val = abs(float(pos.get("market_value", 0)))
                        actual_weights[ticker] = mkt_val / nav * 100
    except Exception:
        pass

    conv_mult = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.5, 5: 2.0}
    qual_mult = {"A": 1.2, "B": 1.0, "C": 0.7}

    rows = []
    for d in sorted(THESIS_DIR.iterdir()):
        if not d.is_dir():
            continue
        yf = d / "thesis.yaml"
        if not yf.exists():
            continue
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception:
            continue

        ticker = d.name
        conviction = data.get("conviction", 3)
        quality = data.get("quality_grade", "C")
        base = data.get("base_size_pct", 5)

        suggested = min(
            base * conv_mult.get(conviction, 1.0) * qual_mult.get(quality, 1.0),
            10,
        )
        actual = actual_weights.get(ticker, 0)

        if actual > 0 or data.get("sizing_result_pct"):
            diff = actual - suggested
            icon = "✅" if abs(diff) < 2 else "⚠️"
            rows.append(
                f"| {ticker} | {suggested:.1f}% | {actual:.1f}% | {diff:+.1f}% {icon} |"
            )

    if not rows:
        return ""

    lines = [
        "| Ticker | 建议仓位 | 实际仓位 | 偏差 |",
        "|--------|---------|---------|------|",
    ] + rows

    return "\n".join(lines) + "\n"


def fetch_attribution_summary() -> str:
    """Source 11: Research ROI from attribution_report.py."""
    try:
        skills_dir = HOME / ".claude" / "skills"
        sys.path.insert(0, str(skills_dir))
        from shared.attribution_report import (
            generate_attribution_report,
        )
        report = generate_attribution_report(save=False)
    except Exception as e:
        return f"_Attribution 数据不可用: {e}_\n"

    # Extract the key sections: Source Efficiency Ranking + Conviction Calibration + Coverage vs Returns
    lines = []
    in_section = False
    target_headers = [
        "### Source Efficiency Ranking",
        "### Conviction Calibration",
        "### Coverage vs Returns",
    ]
    for line in report.split("\n"):
        if any(line.startswith(h) for h in target_headers):
            in_section = True
            lines.append(line)
            continue
        if in_section:
            if line.startswith("## ") or line.startswith("---"):
                in_section = False
                lines.append("")
                continue
            lines.append(line)

    if not lines:
        return "_无 attribution 数据（需要先设置 idea_source）_\n"

    return "\n".join(lines) + "\n"


def generate_forced_questions(days: int, trades_text: str, bias_text: str, kc_text: str) -> str:
    """Generate forced reflection questions based on data."""
    lines = [
        "> 以下问题由系统自动生成，基于本期数据。你必须认真回答。",
        "",
        "### Q1: 本期最大的一个错误/遗憾是什么？",
        "",
    ]

    # Extract hints from data
    hints = []
    if "🔴" in bias_text:
        hints.append("BiasEngine 有高 severity alert")
    if "过期" in kc_text or "FAIL" in kc_text:
        hints.append("有 Kill Criteria 过期或触发")
    if hints:
        lines.append(f"_提示: {'; '.join(hints)}_")
    lines.append("")
    lines.append("**你的回答：** ___")
    lines.append("")
    lines.append("### Q2: 如果重来，你会改变什么？")
    lines.append("**你的回答：** ___")
    lines.append("")
    lines.append("### Q3: 你的哪个持仓你最不想去想？")
    lines.append("> 提示：这个就是你最该研究的。")
    lines.append("**你的回答：** ___")

    return "\n".join(lines) + "\n"


# ── Main Assembly ──────────────────────────────────────────────────────────

async def assemble_review(period: str, days: int) -> str:
    """Assemble the full review markdown."""
    today = datetime.now().strftime("%Y-%m-%d")
    period_label = "周" if period == "week" else "月"

    # Fetch all data sources (async where possible)
    trades_text = await fetch_trades(days)
    bias_text = await fetch_bias_dashboard(days)

    # Sync sources
    research_text = fetch_obsidian_files(RESEARCH_NOTES, "研究笔记", days)
    earnings_text = fetch_obsidian_files(EARNINGS_ANALYSIS, "财报分析", days)
    thesis_text = fetch_obsidian_files(THESIS_DIR, "Thesis 更新", days)
    zhouhui_text = fetch_obsidian_files(ZHOUHUI, "周会记录", days)
    inbox_text = fetch_obsidian_files(WEEKLY_INBOX, "Weekly Inbox", days)
    podcast_text = fetch_obsidian_files(PODCAST, "播客笔记", days)
    kc_text = scan_kill_criteria(days)
    dj_text = fetch_decision_stats(days)
    attribution_text = fetch_attribution_summary()
    estimate_text = fetch_estimate_stats(days)
    peers_text = fetch_peers_reminder(days)
    sizing_text = await compute_sizing_deviations()
    questions_text = generate_forced_questions(days, trades_text, bias_text, kc_text)

    # Build markdown
    md = f"""---
date: {today}
type: {period}-review
period: {days}d
tags: [review, {period}]
---

# {period_label}回顾: {today}

> 回顾期: 过去 {days} 天

---

## 📊 交易记录

{trades_text}

---

## 📝 研究活动

### 研究笔记
{research_text}

### 财报分析
{earnings_text}

### Thesis 更新
{thesis_text}

### 周会
{zhouhui_text}

### Weekly Inbox
{inbox_text}

### 播客
{podcast_text}

---

## 🧠 行为偏差检查

{bias_text}

### 🔴 必须回答（不允许跳过）
1. 本期 BiasEngine 触发了哪些 alert？你是否采取了行动？
   **回答：** ___
2. 如果没有行动，原因是什么？
   **回答：** ___
3. 上一期 review 中你承诺的改进，执行了吗？
   **回答：** ___

---

## ⚠️ Kill Criteria 状态

{kc_text}

---

## 📋 Decision Journal

{dj_text}

---

## 📊 Research ROI

{attribution_text}

---
"""

    if estimate_text:
        md += f"""## 📈 预测校准

{estimate_text}

---
"""

    if sizing_text:
        md += f"""## 📐 Position Sizing 审查

{sizing_text}

---
"""

    if peers_text:
        md += f"""## 👥 竞争对手动态

{peers_text}

---
"""

    md += f"""## 🪞 强制反思（不允许回答"没有"）

{questions_text}

---

## ✍️ 本期承诺

> 写下你下一期要改进的 1-2 件事。

**承诺：** ___

---
*Generated by review_aggregator.py on {today}*
"""

    return md


async def main():
    parser = argparse.ArgumentParser(description="Investment Review Aggregator")
    parser.add_argument("--period", choices=["week", "month"], default="week")
    parser.add_argument("--days", type=int, default=None, help="Override lookback days")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout only")
    args = parser.parse_args()

    days = args.days or (7 if args.period == "week" else 30)

    review_md = await assemble_review(args.period, days)

    if args.dry_run:
        print(review_md)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}_{args.period}_review.md"
        filepath = REVIEWS_DIR / filename
        filepath.write_text(review_md, encoding="utf-8")
        print(f"Review saved to: {filepath}")


if __name__ == "__main__":
    asyncio.run(main())
