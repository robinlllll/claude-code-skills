"""Decision Journal Statistics — generates markdown snippet for /review embedding.

Scans ~/PORTFOLIO/decisions/journal/ for completed DJ files.
Computes: avg confidence, emotion distribution, 'what would make this wrong' hit rate.

Usage:
    python decision_stats.py [--days 30]
    python decision_stats.py --output markdown
"""

import argparse
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

JOURNAL_DIR = Path.home() / "PORTFOLIO" / "decisions" / "journal"

EMOTION_EMOJIS = {
    "neutral": "😐",
    "excited": "😃",
    "anxious": "😰",
    "fomo": "😱",
    "fearful": "😨",
}


def parse_journal(path: Path) -> dict | None:
    """Parse a Decision Journal markdown file into a dict."""
    text = path.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None

    fm = {}
    for line in fm_match.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")

    date_str = fm.get("date", "")
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    confidence = 5
    conf_str = fm.get("confidence", "5")
    try:
        confidence = int(conf_str)
    except ValueError:
        pass

    # Extract "What Would Make This Wrong" section
    wrong_match = re.search(
        r"## What Would Make This Wrong\s*\n(.*?)(?=\n## |\n---|\Z)",
        text,
        re.DOTALL,
    )
    wrong_text = wrong_match.group(1).strip() if wrong_match else ""

    return {
        "date": date,
        "ticker": fm.get("ticker", "?"),
        "decision_type": fm.get("decision_type", "?"),
        "emotional_state": fm.get("emotional_state", "neutral"),
        "confidence": confidence,
        "wrong_prediction": wrong_text,
        "path": path,
    }


def load_journals(days: int = 30) -> list[dict]:
    """Load all journal entries within the lookback window."""
    if not JOURNAL_DIR.exists():
        return []

    cutoff = datetime.now().date() - timedelta(days=days)
    journals = []

    for f in JOURNAL_DIR.glob("*.md"):
        if f.name == "TEMPLATE.md":
            continue
        entry = parse_journal(f)
        if entry and entry["date"] >= cutoff:
            journals.append(entry)

    journals.sort(key=lambda x: x["date"])
    return journals


def compute_stats(journals: list[dict]) -> dict:
    """Compute aggregate statistics from journal entries."""
    if not journals:
        return {
            "count": 0,
            "avg_confidence": 0,
            "emotions": {},
            "by_ticker": {},
            "by_type": {},
            "high_confidence_count": 0,
            "low_confidence_count": 0,
        }

    confidences = [j["confidence"] for j in journals]
    emotions = Counter(j["emotional_state"] for j in journals)
    by_ticker = Counter(j["ticker"] for j in journals)
    by_type = Counter(j["decision_type"] for j in journals)

    return {
        "count": len(journals),
        "avg_confidence": sum(confidences) / len(confidences),
        "median_confidence": sorted(confidences)[len(confidences) // 2],
        "high_confidence_count": sum(1 for c in confidences if c >= 7),
        "low_confidence_count": sum(1 for c in confidences if c <= 3),
        "emotions": dict(emotions.most_common()),
        "by_ticker": dict(by_ticker.most_common(10)),
        "by_type": dict(by_type.most_common()),
    }


def format_markdown(stats: dict, days: int) -> str:
    """Format stats as markdown snippet for /review embedding."""
    if stats["count"] == 0:
        return (
            f"### Decision Journal (过去 {days} 天)\n\n"
            f"*无决策日志记录。Nightly Journal Check 是否在运行？*\n"
        )

    lines = [
        f"### Decision Journal (过去 {days} 天)",
        "",
        f"**总记录:** {stats['count']} 笔决策",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 平均信心 | {stats['avg_confidence']:.1f}/10 |",
        f"| 中位信心 | {stats['median_confidence']}/10 |",
        f"| 高信心 (≥7) | {stats['high_confidence_count']} 笔 |",
        f"| 低信心 (≤3) | {stats['low_confidence_count']} 笔 |",
        "",
    ]

    # Emotion distribution
    if stats["emotions"]:
        lines.append("**情绪分布:**")
        lines.append("")
        for emotion, count in stats["emotions"].items():
            emoji = EMOTION_EMOJIS.get(emotion, "❓")
            pct = count / stats["count"] * 100
            lines.append(f"- {emoji} {emotion}: {count} ({pct:.0f}%)")
        lines.append("")

    # By ticker
    if stats["by_ticker"]:
        lines.append("**最活跃 Ticker:**")
        lines.append("")
        for ticker, count in stats["by_ticker"].items():
            lines.append(f"- {ticker}: {count} 笔")
        lines.append("")

    # By decision type
    if stats["by_type"]:
        lines.append("**决策类型:**")
        lines.append("")
        for dtype, count in stats["by_type"].items():
            lines.append(f"- {dtype}: {count}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Decision Journal Statistics")
    parser.add_argument("--days", type=int, default=30, help="Lookback period in days")
    parser.add_argument(
        "--output",
        choices=["text", "markdown"],
        default="text",
        help="Output format",
    )
    args = parser.parse_args()

    journals = load_journals(args.days)
    stats = compute_stats(journals)

    if args.output == "markdown":
        print(format_markdown(stats, args.days))
    else:
        if stats["count"] == 0:
            print(f"No journal entries in the past {args.days} days.")
            return
        print(f"Decision Journal Stats (past {args.days} days)")
        print(f"  Total entries: {stats['count']}")
        print(f"  Avg confidence: {stats['avg_confidence']:.1f}/10")
        print(f"  Emotions: {stats['emotions']}")
        print(f"  Top tickers: {stats['by_ticker']}")
        print(f"  Decision types: {stats['by_type']}")


if __name__ == "__main__":
    main()
