#!/usr/bin/env python3
"""
Dashboard Updater — generates a '最近更新' section in Dashboard.md
Uses frontmatter dates (not mtime) to avoid showing old files touched by automation.
Grouped bullet-list format (no tables) to avoid wikilink pipe conflicts.
"""

import re
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

VAULT = Path.home() / "Documents" / "Obsidian Vault"
DASHBOARD = VAULT / "导航" / "Dashboard.md"

SCAN_FOLDERS = [
    "收件箱",
    "研究/财报分析",
    "研究/研报摘要",
    "研究/研究笔记",
    "研究/13F",
    "研究/供应链",
    "研究/估值",
    "13F",
    "信息源/剪藏",
    "信息源/播客",
    "信息源/Substack",
    "写作/投资回顾",
    "写作/思考性文章",
    "导航/MOC",
    "导航/Flashback",
    "导航/NotebookLM",
    "周会",
]

CATEGORY_MAP = {
    "收件箱": "收件箱",
    "研究/财报分析": "财报分析",
    "研究/研报摘要": "研报摘要",
    "研究/研究笔记": "研究笔记",
    "研究/13F": "13F",
    "研究/供应链": "供应链",
    "研究/估值": "估值",
    "13F": "13F 经理分析",
    "信息源/剪藏": "剪藏",
    "信息源/播客": "播客",
    "信息源/Substack": "Substack",
    "写作/投资回顾": "投资回顾",
    "写作/思考性文章": "思考文章",
    "导航/MOC": "MOC",
    "导航/Flashback": "Flashback",
    "导航/NotebookLM": "NotebookLM",
    "周会": "周会",
}

# Max inline links per category-row before showing "+N"
MAX_INLINE = 5

# Categories where ALL items must be shown (no cap)
SHOW_ALL_CATS = {"财报分析", "收件箱", "思考文章", "投资回顾", "研究笔记", "周会", "MOC", "估值", "13F", "13F 经理分析", "研报摘要"}


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(filepath: Path) -> dict:
    """Fast YAML-lite frontmatter parser (no PyYAML dependency)."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[4:end]
    fm: dict = {}
    for line in block.splitlines():
        m = re.match(r"^(\w[\w_-]*)\s*:\s*(.+)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                items = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
                fm[key] = items
            else:
                fm[key] = val.strip('"').strip("'")
    return fm


def _parse_date(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _content_date(fm: dict) -> datetime | None:
    for key in ("date", "created", "publish_date", "published"):
        dt = _parse_date(fm.get(key))
        if dt:
            return dt
    return None


# ---------------------------------------------------------------------------
# Display name formatters
# ---------------------------------------------------------------------------

_COUNTRY_SUFFIXES = re.compile(r"-(US|HK|IT|DK|FR|GB|JP|KR|CN|SG|AU|CA|DE|NL|SE|CH|TW)$", re.I)


def _clean_ticker(t: str) -> str:
    return _COUNTRY_SUFFIXES.sub("", t) if t else ""


def _display_name(category: str, fm: dict, stem: str) -> str:
    ticker = _clean_ticker(fm.get("ticker") or "")

    if category == "财报分析":
        quarters = fm.get("quarters", [])
        q = quarters[0] if isinstance(quarters, list) and quarters else ""
        if not q:
            # Try extracting from event field: "Q4 2025 Earnings"
            event = fm.get("event", "")
            m = re.search(r"(Q\d\s+\d{4}|FY\d{4})", event)
            if m:
                q = m.group(1)
        if ticker and q:
            return f"{ticker} {q}"
        return ticker or stem

    if category == "研报摘要":
        source = fm.get("source", "")
        if ticker and source:
            return f"{ticker} — {source}"
        return stem[:50] + "…" if len(stem) > 50 else stem

    if category == "供应链":
        return ticker or stem.replace("_mentions", "")

    if category in ("MOC", "Flashback"):
        return ticker or stem.replace("_flashback", "")

    if category == "播客":
        title = fm.get("title", "")
        if title:
            return title[:40] + "…" if len(title) > 40 else title
        return stem[:40] + "…" if len(stem) > 40 else stem

    if category == "收件箱":
        name = re.sub(r"^\d{4}-\d{2}-\d{2}[_\s-]*", "", stem)
        return name[:40] + "…" if len(name) > 40 else name

    if category in ("13F", "13F 经理分析"):
        manager = fm.get("manager", "")
        name = manager or stem
        return name[:40] + "…" if len(name) > 40 else name

    if category == "周会":
        return stem

    return stem[:45] + "…" if len(stem) > 45 else stem


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_recent_notes(days: int = 7) -> list[dict]:
    """Scan vault for recently updated notes (no limit, all recent files)."""
    cutoff = datetime.now() - timedelta(days=days)
    all_notes: list[dict] = []

    for folder_rel in SCAN_FOLDERS:
        folder = VAULT / folder_rel
        if not folder.exists():
            continue
        category = CATEGORY_MAP.get(folder_rel, folder_rel)

        for md_file in folder.rglob("*.md"):
            if md_file.name.startswith((".", "_")):
                continue
            # Skip template files and UUID-named files
            if md_file.stem.upper() == "TEMPLATE":
                continue
            if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", md_file.stem):
                continue

            mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
            if mtime < cutoff:
                continue

            fm = _parse_frontmatter(md_file)
            c_date = _content_date(fm)

            # Skip old content merely touched by automation
            if c_date and c_date < cutoff:
                continue

            display_date = c_date or mtime
            rel_path = md_file.relative_to(VAULT)
            wikilink = str(rel_path).replace("\\", "/").removesuffix(".md")
            display = _display_name(category, fm, md_file.stem)

            all_notes.append({
                "path": wikilink,
                "display": display,
                "category": category,
                "sort_date": display_date,
                "date_key": display_date.strftime("%m-%d"),
            })

    all_notes.sort(key=lambda x: x["sort_date"], reverse=True)
    return all_notes


# ---------------------------------------------------------------------------
# Dashboard writer — grouped bullet list format
# ---------------------------------------------------------------------------

def generate_recent_section(days: int = 7) -> str:
    notes = scan_recent_notes(days=days)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group by date → category
    date_groups: dict[str, dict[str, list]] = {}
    for note in notes:
        dk = note["date_key"]
        cat = note["category"]
        date_groups.setdefault(dk, {}).setdefault(cat, []).append(note)

    lines = [
        "## 最近更新",
        f"> 最近 {days} 天 · 更新于 {now}",
        "",
    ]

    for date_key in sorted(date_groups.keys(), reverse=True):
        cats = date_groups[date_key]
        lines.append(f"**{date_key}**")

        for cat in sorted(cats.keys()):
            items = cats[cat]
            if cat in SHOW_ALL_CATS:
                # Show every item — no cap
                link_strs = [f"[[{n['path']}|{n['display']}]]" for n in items]
            else:
                link_strs = [f"[[{n['path']}|{n['display']}]]" for n in items[:MAX_INLINE]]
                if len(items) > MAX_INLINE:
                    link_strs.append(f"(+{len(items) - MAX_INLINE})")
            lines.append(f"- {cat}: {' · '.join(link_strs)}")

        lines.append("")

    if not notes:
        lines.append("_无最近更新_")
        lines.append("")

    return "\n".join(lines)


def update_dashboard(days: int = 7) -> str:
    if not DASHBOARD.exists():
        return "Dashboard not found"

    content = DASHBOARD.read_text(encoding="utf-8")
    section = generate_recent_section(days=days)

    pattern = r"## 最近更新\n.*?(?=\n## |\Z)"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, section.rstrip(), content, flags=re.DOTALL)
    else:
        m = re.search(r"(# 投资工作台\n)", content)
        if m:
            pos = m.end()
            content = content[:pos] + "\n" + section + "\n" + content[pos:]
        else:
            content += "\n" + section

    DASHBOARD.write_text(content, encoding="utf-8")
    total = sum(1 for _ in scan_recent_notes(days))
    return f"Dashboard updated — {total} notes (last {days} days)"


if __name__ == "__main__":
    result = update_dashboard()
    print(result)
