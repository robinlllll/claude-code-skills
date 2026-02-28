"""Merge Stage 2 briefings into vault meeting files for backtest compatibility.

Reads briefing files from ~/Documents/会议实录/, normalizes format to match
the backtest parser expectations, and writes to vault 周会/ directory.

Format requirements for backtest:
  - frontmatter with `tickers:` list
  - `## $TICKER` sections (H2)
  - `### 潜在行动提示（强化版）` (H3)
"""

import re
import sys
from pathlib import Path

BRIEFING_DIR = Path.home() / "Documents" / "会议实录"
VAULT_MEETING_DIR = Path.home() / "Documents" / "Obsidian Vault" / "周会"

# Meetings to process
MEETINGS = [
    "2026-01-16",
    "2026-01-23",
    "2026-01-31",
]

# Regex to find $TICKER patterns anywhere in text
TICKER_RE = re.compile(r'\$([A-Z][A-Z0-9]{1,5}(?:\.[A-Z]{1,2})?)\b')

# Non-US tickers to exclude from the backtest (not in yfinance simple format)
EXCLUDE_TICKERS = {"SK", "CFR", "CNC"}  # SK Hynix = 000660.KS, CFR = Richemont in Swiss


def extract_all_tickers(text: str) -> list[str]:
    """Extract all unique $TICKER mentions from text."""
    tickers = set()
    for m in TICKER_RE.finditer(text):
        t = m.group(1)
        if t not in EXCLUDE_TICKERS and len(t) >= 2:
            tickers.add(t)
    return sorted(tickers)


def normalize_format(text: str, date: str) -> str:
    """Normalize briefing format for backtest compatibility.

    Handles three format variants:
    1. `## $TICKER` + `**潜在行动提示**` (bold) → add ### prefix
    2. `### **$TICKER**` + `#### **hint**` → promote to ## and ###
    3. `## $TICKER` + `### 潜在行动提示` → already correct
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        # Pattern 1: ### **$TICKER (Company)** → ## $TICKER（Company）
        if re.match(r'^###\s+\*\*\$([A-Z])', line):
            # Remove ** and promote to ##
            line = re.sub(r'^###\s+\*\*(.+?)\*\*\s*$', r'## \1', line)

        # Pattern 2: #### **核心观点摘要** → ### 核心观点摘要
        elif re.match(r'^####\s+\*\*(.+?)\*\*', line):
            line = re.sub(r'^####\s+\*\*(.+?)\*\*\s*$', r'### \1', line)

        # Pattern 3: **潜在行动提示** (bold, no #) → ### 潜在行动提示（强化版）
        elif re.match(r'^\*\*潜在行动提示\*\*\s*$', line):
            line = '### 潜在行动提示（强化版）'

        # Pattern 4: **核心观点摘要** (bold, no #) → ### 核心观点摘要
        elif re.match(r'^\*\*(核心观点摘要|正文复述|关键跟踪点)\*\*\s*$', line):
            inner = re.match(r'^\*\*(.+?)\*\*', line).group(1)
            line = f'### {inner}'

        # Pattern 5: ### 潜在行动提示 → ### 潜在行动提示（强化版）
        elif re.match(r'^###\s+潜在行动提示\s*$', line):
            line = '### 潜在行动提示（强化版）'

        # Pattern 6: #### 潜在行动提示 → ### 潜在行动提示（强化版）
        elif re.match(r'^####\s+潜在行动提示\s*$', line):
            line = '### 潜在行动提示（强化版）'

        # Promote ## section titles that don't have $ (sector headers) to stay as ##
        # These are fine: ## $LVMH, ## Memory Sector ($MU...)
        # Keep as-is

        result.append(line)

    return '\n'.join(result)


def build_vault_file(briefing_text: str, date: str, tickers: list[str]) -> str:
    """Build the vault meeting file with proper frontmatter."""
    # Strip existing frontmatter from briefing
    body = briefing_text
    if body.startswith('---'):
        end = body.find('---', 3)
        if end > 0:
            body = body[end + 3:].lstrip('\n')

    # Remove "好的，这是根据您的要求整理的会议纪要。" preamble if present
    body = re.sub(r'^好的[，,]这是根据.*?[。.]\s*\n*---\s*\n*', '', body)

    # Normalize format
    body = normalize_format(body, date)

    # Build frontmatter
    tickers_str = ', '.join(tickers)
    frontmatter = f"""---
created: {date}
type: 周会
tags: [周会, meeting-notes]
tickers: [{tickers_str}]
---"""

    return f"{frontmatter}\n\n# 会议实录 {date}\n\n{body}"


def main():
    for date in MEETINGS:
        briefing_path = BRIEFING_DIR / f"{date}-周会分析.md"
        vault_path = VAULT_MEETING_DIR / f"会议实录 {date}.md"

        if not briefing_path.exists():
            print(f"  SKIP {date}: no briefing file at {briefing_path}")
            continue

        print(f"\n[{date}]")
        briefing_text = briefing_path.read_text(encoding='utf-8')

        # Extract tickers
        tickers = extract_all_tickers(briefing_text)
        print(f"  Tickers found: {len(tickers)} → {tickers}")

        # Build vault file
        vault_content = build_vault_file(briefing_text, date, tickers)

        # Count format markers
        h2_tickers = len(re.findall(r'^\s*##\s+\$[A-Z]', vault_content, re.MULTILINE))
        h3_actions = len(re.findall(r'###\s+潜在行动提示', vault_content, re.MULTILINE))
        print(f"  Format check: {h2_tickers} ticker sections (##), {h3_actions} action hints (###)")

        # Write
        vault_path.write_text(vault_content, encoding='utf-8')
        print(f"  Written: {vault_path.name} ({len(vault_content):,} chars)")


if __name__ == "__main__":
    main()
