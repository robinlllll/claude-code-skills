"""Estimate vs Actual Statistics — generates markdown snippet for /review embedding.

Scans ~/Documents/Obsidian Vault/Estimates/ for completed estimate files
(those with both pre- and post-earnings data filled in).

Computes: overall accuracy, by-metric accuracy, confidence calibration.

Usage:
    python estimate_stats.py [--days 90]
    python estimate_stats.py --output markdown
"""

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

ESTIMATES_DIR = Path.home() / "Documents" / "Obsidian Vault" / "Estimates"


def parse_estimate_file(path: Path) -> dict | None:
    """Parse an Estimate vs Actual markdown file."""
    text = path.read_text(encoding="utf-8")

    # Parse frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None

    fm = {}
    for line in fm_match.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")

    # Only process files that have actuals filled in
    if "status" in fm and fm["status"] == "pre-earnings":
        return None

    # Check if post-earnings table exists and has data
    if "## 财报后实际" not in text:
        return None

    # Extract pre-earnings predictions
    pre_match = re.search(
        r"## 财报前预期.*?\n(\|.*?\n)+",
        text,
        re.DOTALL,
    )

    # Extract post-earnings actuals
    post_match = re.search(
        r"## 财报后实际.*?\n(\|.*?\n)+",
        text,
        re.DOTALL,
    )

    if not pre_match or not post_match:
        return None

    date_str = fm.get("date", "")
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    # Parse result rows — look for check/cross marks
    predictions = []
    post_section = post_match.group(0)
    for line in post_section.splitlines():
        if "|" not in line or "---" in line or "指标" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 4:
            metric = cells[0]
            prediction = cells[1]
            actual = cells[2]
            result = cells[3]

            correct = "✅" in result or "Correct" in result.lower()
            wrong = "❌" in result or "Wrong" in result.lower()

            if correct or wrong:
                # Try to extract confidence from pre-earnings table
                confidence = 5  # default
                for pre_line in pre_match.group(0).splitlines():
                    if metric.lower() in pre_line.lower():
                        # Find /10 pattern
                        conf_match = re.search(r"(\d+)/10", pre_line)
                        if conf_match:
                            confidence = int(conf_match.group(1))
                        break

                predictions.append({
                    "metric": metric,
                    "correct": correct,
                    "confidence": confidence,
                })

    if not predictions:
        return None

    return {
        "date": date,
        "ticker": fm.get("ticker", "?"),
        "quarter": fm.get("quarter", "?"),
        "predictions": predictions,
    }


def load_estimates(days: int = 90) -> list[dict]:
    """Load all completed estimate files within lookback window."""
    if not ESTIMATES_DIR.exists():
        return []

    cutoff = datetime.now().date() - timedelta(days=days)
    estimates = []

    for f in ESTIMATES_DIR.glob("*.md"):
        if f.name == "TEMPLATE.md":
            continue
        entry = parse_estimate_file(f)
        if entry and entry["date"] >= cutoff:
            estimates.append(entry)

    return estimates


def compute_stats(estimates: list[dict]) -> dict:
    """Compute aggregate estimate accuracy stats."""
    all_predictions = []
    for e in estimates:
        all_predictions.extend(e["predictions"])

    if not all_predictions:
        return {"count": 0}

    total = len(all_predictions)
    correct = sum(1 for p in all_predictions if p["correct"])

    # By confidence level
    high_conf = [p for p in all_predictions if p["confidence"] >= 7]
    low_conf = [p for p in all_predictions if p["confidence"] <= 4]

    high_correct = sum(1 for p in high_conf if p["correct"])
    low_correct = sum(1 for p in low_conf if p["correct"])

    return {
        "count": total,
        "correct": correct,
        "accuracy": correct / total if total > 0 else 0,
        "high_conf_total": len(high_conf),
        "high_conf_correct": high_correct,
        "high_conf_accuracy": high_correct / len(high_conf) if high_conf else 0,
        "low_conf_total": len(low_conf),
        "low_conf_correct": low_correct,
        "low_conf_accuracy": low_correct / len(low_conf) if low_conf else 0,
        "avg_confidence_correct": (
            sum(p["confidence"] for p in all_predictions if p["correct"]) / correct
            if correct > 0 else 0
        ),
        "avg_confidence_wrong": (
            sum(p["confidence"] for p in all_predictions if not p["correct"]) / (total - correct)
            if total - correct > 0 else 0
        ),
        "quarters_covered": len(estimates),
    }


def format_markdown(stats: dict, days: int) -> str:
    """Format stats as markdown for review embedding."""
    if stats["count"] == 0:
        return (
            f"### 预测校准 (过去 {days} 天)\n\n"
            f"*无已完成的 Estimate vs Actual 记录。*\n"
        )

    return f"""### 预测校准 (过去 {days} 天)

**总预测:** {stats['count']} | **正确:** {stats['correct']} | **准确率:** {stats['accuracy']:.0%}

| 指标 | 值 |
|------|-----|
| 高信心 (≥7) 准确率 | {stats['high_conf_accuracy']:.0%} ({stats['high_conf_correct']}/{stats['high_conf_total']}) |
| 低信心 (≤4) 准确率 | {stats['low_conf_accuracy']:.0%} ({stats['low_conf_correct']}/{stats['low_conf_total']}) |
| 正确预测平均信心 | {stats['avg_confidence_correct']:.1f}/10 |
| 错误预测平均信心 | {stats['avg_confidence_wrong']:.1f}/10 |
| 覆盖季度 | {stats['quarters_covered']} |

{"⚠️ **校准警告:** 高信心预测准确率低于低信心，存在过度自信倾向" if stats['high_conf_accuracy'] < stats['low_conf_accuracy'] and stats['high_conf_total'] >= 3 else ""}
"""


def main():
    parser = argparse.ArgumentParser(description="Estimate vs Actual Statistics")
    parser.add_argument("--days", type=int, default=90, help="Lookback period")
    parser.add_argument("--output", choices=["text", "markdown"], default="text")
    args = parser.parse_args()

    estimates = load_estimates(args.days)
    stats = compute_stats(estimates)

    if args.output == "markdown":
        print(format_markdown(stats, args.days))
    else:
        if stats["count"] == 0:
            print(f"No completed estimates in the past {args.days} days.")
            return
        print(f"Estimate Stats (past {args.days} days)")
        print(f"  Total predictions: {stats['count']}")
        print(f"  Accuracy: {stats['accuracy']:.0%}")
        print(f"  High conf accuracy: {stats['high_conf_accuracy']:.0%}")


if __name__ == "__main__":
    main()
