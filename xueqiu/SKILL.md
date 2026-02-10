---
name: xueqiu
description: Xueqiu Scraper - Scrape all posts and articles from any Xueqiu user profile
---

# Xueqiu Profile Scraper

Scrapes all posts and articles from any Xueqiu user profile. Outputs split text files for NotebookLM.

## Project Location

`C:\Users\thisi\xueqiu`

## When to Use This Skill

- User wants to scrape Xueqiu profiles
- User mentions Xueqiu URL or user ID
- User wants to export Chinese investment posts
- User mentions preparing content for NotebookLM

## Key Files

- `scrape_xueqiu.py` - Main scraper
- `setup_cookies.py` - Save login cookies
- `xueqiu_cookies.json` - Saved cookies

## Commands

### Scrape User Profile
```bash
cd "C:\Users\thisi\xueqiu" && python scrape_xueqiu.py [URL_OR_UID]
```

Example:
```bash
cd "C:\Users\thisi\xueqiu" && python scrape_xueqiu.py https://xueqiu.com/1965894836
cd "C:\Users\thisi\xueqiu" && python scrape_xueqiu.py 1965894836
```

### Setup Cookies (One-Time)
```bash
cd "C:\Users\thisi\xueqiu" && python setup_cookies.py
```

### Install Dependencies
```bash
cd "C:\Users\thisi\xueqiu" && pip install -r requirements.txt && playwright install chromium
```

## Output

`C:\Users\thisi\xueqiu\output\{username}\` with JSON and split TXT files.

## Obsidian Integration

After scraping, optionally export key posts to Obsidian with standardized frontmatter:

**Output path:** `~/Documents/Obsidian Vault/Xueqiu/{username}/`

**Frontmatter template:**
```yaml
---
date: YYYY-MM-DD
source: xueqiu
author: "{username}"
tickers: [TICKER1, TICKER2]
tags: [xueqiu, 投资]
---
```

**Ticker detection:** Use shared/ticker_detector for entity-aware tagging (supports Chinese company names like 贵州茅台 → 600519, 比亚迪 → BYDDF):
```python
import sys; sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
from shared.ticker_detector import detect_tickers
results = detect_tickers(post_text)
```

## Post-Scraping

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link 信息源/雪球/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。

## Framework Tagging (after ticker detection)

在 ticker 检测之后，自动标注内容属于分析框架的哪些维度：
```python
from shared.framework_tagger import tag_content
sections = tag_content(text, mode="hybrid")  # e.g. ["S1", "S4.2"]
```
将结果添加到 frontmatter extra dict：
```yaml
framework_sections: [S1, S4.2, S7]
```
如果 `framework_tagger` 不可用或返回空列表，跳过（不报错）。

## Pipeline Tracking

**自动执行:** 每个 xueqiu post 处理后，记录到 ingestion pipeline（如果 task_manager 可用）：
```python
try:
    from shared.task_manager import record_pipeline_entry
    record_pipeline_entry(
        canonical_key=canonical_key,  # from record_ingestion()
        item_type="xueqiu", item_title=post_title[:80],
        source_platform="xueqiu", obsidian_path=str(output_path),
        has_frontmatter=True, has_tickers=bool(tickers),
        has_framework_tags=bool(framework_sections),
        tickers_found=tickers, framework_sections=framework_sections,
    )
except ImportError:
    pass
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/notebooklm` | Split TXT files can be uploaded as NLM sources |
| `/moc` | Xueqiu posts appear in ticker MOC if tagged |
| `/research` | Chinese investor perspectives supplement research |
| `/link` | Auto-link Xueqiu posts to other vault content |
