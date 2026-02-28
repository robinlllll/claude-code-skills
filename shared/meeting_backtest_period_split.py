"""
Meeting Backtest: Time-period split analysis.
Splits 49 meetings into Old (42, ≤2026-01-03) vs New (7, >2026-01-03).
"""
import re
from pathlib import Path
from collections import defaultdict

REPORT_PATH = Path.home() / "Documents" / "Obsidian Vault" / "写作" / "投资回顾" / "2026-02-25_meeting_backtest.md"
OUTPUT_PATH = Path.home() / "Documents" / "Obsidian Vault" / "写作" / "投资回顾" / "2026-02-25_meeting_backtest_period_split.md"
CUTOFF = "2026-01-03"  # last meeting in old backtest

# SPY returns for excess calculation (approximate from the backtest data)
# We'll compute raw returns only, since we don't have per-pick SPY data here


def parse_data_table(report_path):
    """Parse the full data table from the backtest report."""
    picks = []
    in_table = False
    header_seen = False

    with open(report_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "## 完整数据表" in line:
                in_table = True
                continue
            if in_table and line.startswith("| 日期"):
                header_seen = True
                continue
            if in_table and header_seen and line.startswith("| ---"):
                continue
            if in_table and header_seen and line.startswith("|"):
                parts = [p.strip() for p in line.split("|")]
                parts = [p for p in parts if p]  # remove empty strings
                if len(parts) < 8:
                    continue
                date = parts[0]
                ticker = parts[1]
                sentiment = parts[2]
                acted = parts[3]
                # Parse returns - handle N/A
                def parse_pct(s):
                    s = s.strip().replace("%", "")
                    if s == "N/A" or s == "—" or s == "":
                        return None
                    try:
                        return float(s)
                    except ValueError:
                        return None

                ret_7d = parse_pct(parts[4])
                ret_30d = parse_pct(parts[5])
                ret_90d = parse_pct(parts[6])
                ret_180d = parse_pct(parts[7]) if len(parts) > 7 else None

                # Group is the last field
                group = parts[-1] if len(parts) >= 9 else "Unknown"

                is_acted = acted not in ("✗", "否")
                is_bullish = sentiment == "多"
                is_bearish = sentiment == "空"

                picks.append({
                    "date": date,
                    "ticker": ticker,
                    "sentiment": sentiment,
                    "acted": is_acted,
                    "acted_raw": acted,
                    "group": group,
                    "ret_7d": ret_7d,
                    "ret_30d": ret_30d,
                    "ret_90d": ret_90d,
                    "ret_180d": ret_180d,
                    "is_bullish": is_bullish,
                    "is_bearish": is_bearish,
                })
            elif in_table and header_seen and not line.startswith("|"):
                break  # end of table

    return picks


def compute_stats(picks, label=""):
    """Compute group statistics for a set of picks."""
    groups = {
        "Bullish + Acted On": [],
        "Bullish + Discussed Only": [],
        "Bearish + Acted On": [],
        "Bearish + Discussed Only": [],
        "Neutral / Unknown": [],
    }

    for p in picks:
        if p["is_bullish"] and p["acted"]:
            groups["Bullish + Acted On"].append(p)
        elif p["is_bullish"] and not p["acted"]:
            groups["Bullish + Discussed Only"].append(p)
        elif p["is_bearish"] and p["acted"]:
            groups["Bearish + Acted On"].append(p)
        elif p["is_bearish"] and not p["acted"]:
            groups["Bearish + Discussed Only"].append(p)
        else:
            groups["Neutral / Unknown"].append(p)

    results = {}
    for gname, gpicks in groups.items():
        n = len(gpicks)
        if n == 0:
            results[gname] = {"n": 0}
            continue

        def avg(vals):
            valid = [v for v in vals if v is not None]
            return sum(valid) / len(valid) if valid else None

        def median(vals):
            valid = sorted([v for v in vals if v is not None])
            if not valid:
                return None
            mid = len(valid) // 2
            if len(valid) % 2 == 0:
                return (valid[mid - 1] + valid[mid]) / 2
            return valid[mid]

        def winrate(vals):
            valid = [v for v in vals if v is not None]
            if not valid:
                return None
            return sum(1 for v in valid if v > 0) / len(valid) * 100

        results[gname] = {
            "n": n,
            "7d_avg": avg([p["ret_7d"] for p in gpicks]),
            "30d_avg": avg([p["ret_30d"] for p in gpicks]),
            "90d_avg": avg([p["ret_90d"] for p in gpicks]),
            "180d_avg": avg([p["ret_180d"] for p in gpicks]),
            "30d_median": median([p["ret_30d"] for p in gpicks]),
            "30d_winrate": winrate([p["ret_30d"] for p in gpicks]),
            "90d_winrate": winrate([p["ret_90d"] for p in gpicks]),
        }

    return results


def fmt(v, suffix="%"):
    if v is None:
        return "N/A"
    return f"{v:.1f}{suffix}"


def main():
    print("Parsing full data table...")
    picks = parse_data_table(REPORT_PATH)
    print(f"  Total picks: {len(picks)}")

    old_picks = [p for p in picks if p["date"] <= CUTOFF]
    new_picks = [p for p in picks if p["date"] > CUTOFF]

    old_dates = sorted(set(p["date"] for p in old_picks))
    new_dates = sorted(set(p["date"] for p in new_picks))

    print(f"  Old period: {len(old_picks)} picks across {len(old_dates)} meetings")
    print(f"  New period: {len(new_picks)} picks across {len(new_dates)} meetings")
    print(f"  New meetings: {', '.join(new_dates)}")

    old_stats = compute_stats(old_picks)
    new_stats = compute_stats(new_picks)
    all_stats = compute_stats(picks)

    # Count acted-on rates
    old_acted = sum(1 for p in old_picks if p["acted"])
    new_acted = sum(1 for p in new_picks if p["acted"])

    # New period ticker details
    new_bullish_acted = [p for p in new_picks if p["is_bullish"] and p["acted"]]
    new_bullish_disc = [p for p in new_picks if p["is_bullish"] and not p["acted"]]

    # Build report
    lines = [
        "---",
        "date: 2026-02-25",
        "type: backtest-period-split",
        "tags: [backtest, meeting-picks, period-comparison]",
        f"related: \"[[2026-02-25_meeting_backtest]]\"",
        "---",
        "",
        "# 周会选股回测 — 分时段对比",
        "",
        "> 将 49 场周会分为「旧期」(42场, ≤2026-01-03) 和「新期」(7场, 2026-01-09 至 2026-02-21)。",
        "> 检验新增数据是否拖累了整体表现。",
        "",
        "## 数据概览",
        "",
        f"| 指标 | 旧期 (≤{CUTOFF}) | 新期 (>{CUTOFF}) | 全部 |",
        "| --- | ---: | ---: | ---: |",
        f"| 周会数 | {len(old_dates)} | {len(new_dates)} | {len(old_dates) + len(new_dates)} |",
        f"| 提及数 | {len(old_picks)} | {len(new_picks)} | {len(picks)} |",
        f"| 不同股票 | {len(set(p['ticker'] for p in old_picks))} | {len(set(p['ticker'] for p in new_picks))} | {len(set(p['ticker'] for p in picks))} |",
        f"| 已执行数 | {old_acted} ({old_acted/len(old_picks)*100:.0f}%) | {new_acted} ({new_acted/len(new_picks)*100:.0f}%) | {old_acted+new_acted} ({(old_acted+new_acted)/len(picks)*100:.0f}%) |",
        "",
        f"新期周会日期: {', '.join(new_dates)}",
        "",
    ]

    # Main comparison table
    lines.append("## 核心对比 (原始收益)")
    lines.append("")
    lines.append("| 组别 | 期间 | N | 7d均值 | 30d均值 | 30d中位数 | 30d胜率 | 90d均值 | 180d均值 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    for gname in ["Bullish + Acted On", "Bullish + Discussed Only", "Bearish + Acted On", "Bearish + Discussed Only", "Neutral / Unknown"]:
        for period, stats in [("旧期", old_stats), ("新期", new_stats), ("全部", all_stats)]:
            s = stats[gname]
            if s["n"] == 0:
                lines.append(f"| {gname} | {period} | 0 | — | — | — | — | — | — |")
            else:
                lines.append(f"| {gname} | {period} | {s['n']} | {fmt(s['7d_avg'])} | {fmt(s['30d_avg'])} | {fmt(s['30d_median'])} | {fmt(s['30d_winrate'])} | {fmt(s['90d_avg'])} | {fmt(s['180d_avg'])} |")
        lines.append("| | | | | | | | | |")

    # Delta analysis
    lines.append("")
    lines.append("## 新旧差异 (Δ = 新期 - 旧期)")
    lines.append("")
    lines.append("| 组别 | Δ 30d均值 | Δ 30d胜率 | Δ 90d均值 | 解读 |")
    lines.append("| --- | ---: | ---: | ---: | --- |")

    for gname in ["Bullish + Acted On", "Bullish + Discussed Only", "Bearish + Acted On", "Bearish + Discussed Only"]:
        os = old_stats[gname]
        ns = new_stats[gname]
        if os["n"] == 0 or ns["n"] == 0:
            lines.append(f"| {gname} | N/A | N/A | N/A | 样本不足 |")
            continue

        d30 = (ns["30d_avg"] or 0) - (os["30d_avg"] or 0)
        dwr = (ns["30d_winrate"] or 0) - (os["30d_winrate"] or 0)
        d90 = (ns["90d_avg"] or 0) - (os["90d_avg"] or 0) if ns["90d_avg"] is not None and os["90d_avg"] is not None else None

        if d30 > 2:
            interp = "新期显著改善"
        elif d30 > 0:
            interp = "新期略好"
        elif d30 > -2:
            interp = "新期略差"
        else:
            interp = "新期显著恶化"

        lines.append(f"| {gname} | {d30:+.1f}% | {dwr:+.1f}% | {fmt(d90, '%') if d90 is not None else 'N/A'} | {interp} |")

    # New period detail
    lines.append("")
    lines.append("## 新期逐条明细")
    lines.append("")
    lines.append("### 看多+已执行 (新期)")
    lines.append("")
    if new_bullish_acted:
        lines.append("| 日期 | 股票 | 持仓状态 | 7d | 30d | 90d |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for p in sorted(new_bullish_acted, key=lambda x: x["date"]):
            lines.append(f"| {p['date']} | {p['ticker']} | {p['acted_raw']} | {fmt(p['ret_7d'])} | {fmt(p['ret_30d'])} | {fmt(p['ret_90d'])} |")
    else:
        lines.append("> 无数据")

    lines.append("")
    lines.append("### 看多+仅讨论 (新期)")
    lines.append("")
    if new_bullish_disc:
        lines.append("| 日期 | 股票 | 7d | 30d | 90d |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for p in sorted(new_bullish_disc, key=lambda x: x["date"]):
            lines.append(f"| {p['date']} | {p['ticker']} | {fmt(p['ret_7d'])} | {fmt(p['ret_30d'])} | {fmt(p['ret_90d'])} |")
    else:
        lines.append("> 无数据")

    # New period all picks
    lines.append("")
    lines.append("### 全部新期 picks")
    lines.append("")
    lines.append("| 日期 | 股票 | 看法 | 持仓 | 30d | 分组 |")
    lines.append("| --- | --- | --- | --- | ---: | --- |")
    for p in sorted(new_picks, key=lambda x: (x["date"], x["ticker"])):
        lines.append(f"| {p['date']} | {p['ticker']} | {p['sentiment']} | {p['acted_raw']} | {fmt(p['ret_30d'])} | {p['group']} |")

    # Conclusion
    lines.append("")
    lines.append("## 结论")
    lines.append("")

    ob = old_stats["Bullish + Acted On"]
    nb = new_stats["Bullish + Acted On"]
    od = old_stats["Bullish + Discussed Only"]
    nd = new_stats["Bullish + Discussed Only"]

    lines.append(f"1. **看多+已执行:** 旧期 30d {fmt(ob['30d_avg'])} → 新期 {fmt(nb['30d_avg'])}{'，新期恶化' if (nb['30d_avg'] or 0) < (ob['30d_avg'] or 0) else '，新期改善'}")
    lines.append(f"2. **看多+仅讨论:** 旧期 30d {fmt(od['30d_avg'])} → 新期 {fmt(nd['30d_avg'])}{'，新期恶化' if (nd['30d_avg'] or 0) < (od['30d_avg'] or 0) else '，新期改善'}")
    lines.append(f"3. **执行率:** 旧期 {old_acted/len(old_picks)*100:.0f}% → 新期 {new_acted/len(new_picks)*100:.0f}%")
    lines.append("")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  Report saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
