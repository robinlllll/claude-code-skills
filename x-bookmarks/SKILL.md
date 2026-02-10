# X.com Bookmarks to Obsidian

Import X (Twitter) bookmarks exported via the [twitter-web-exporter](https://github.com/prinsss/twitter-web-exporter) Chrome extension into Obsidian notes.

## Project Location

`C:\Users\thisi\.claude\skills\x-bookmarks`

## When to Use This Skill

- User wants to import X/Twitter bookmarks into Obsidian
- User mentions "x bookmarks", "twitter bookmarks", or "tweet import"
- User has a JSON export from twitter-web-exporter

## Commands

| Command | Description |
|---------|-------------|
| `/x-bookmarks import {json_file}` | Import exported bookmarks JSON into Obsidian notes |
| `/x-bookmarks stats` | Show import statistics (total imported, by author, date range) |

### Import Bookmarks

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py import "C:\path\to\bookmarks.json"
```

### Show Statistics

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py stats
```

## Workflow

1. **Export:** Install [twitter-web-exporter](https://github.com/prinsss/twitter-web-exporter) Chrome extension
2. **Export:** Open X.com bookmarks page, click the extension to export as JSON
3. **Import:** Run `/x-bookmarks import path/to/bookmarks.json`
4. **Review:** Notes appear in `Documents/Obsidian Vault/X Bookmarks/`

## Features

1. **Thread Detection:** Multiple tweets from the same author in reply to each other are merged into a single note
2. **Ticker Detection:** Identifies $TICKER patterns and company names via shared entity dictionary
3. **Deduplication:** Uses shared ingestion_state.db to skip already-imported tweets
4. **Flexible Parsing:** Handles multiple JSON structures from twitter-web-exporter gracefully
5. **Media Links:** Preserves image/video URLs as markdown links
6. **Quoted Tweets:** Formats quoted tweets as blockquotes within the note

## Output

| Item | Detail |
|------|--------|
| Output folder | `Documents/Obsidian Vault/X Bookmarks/` |
| File naming | `YYYY-MM-DD - {author} - {first_20_chars}.md` |
| Frontmatter | Per DATA_CONTRACT: id=x_{tweet_id}, type=x, source_platform=x |
| Thread notes | Merged into single file with all tweets in chronological order |

## Frontmatter Example

```yaml
---
id: "x_1234567890"
type: x
source_platform: x
source_url: "https://x.com/author/status/1234567890"
author: "AuthorName"
published_at: 2025-10-10
ingested_at: 2026-02-07
tickers: [AAPL, TSLA]
tags: [x-bookmark]
favorite_count: 123
retweet_count: 45
is_thread: false
---
```

## Dependencies

- Python 3.x (no extra pip packages required beyond PyYAML for shared ticker detection)
- Shared utilities: `~/.claude/skills/shared/` (frontmatter_utils, ticker_detector)

## Framework Tagging (after ticker detection)

在 ticker 检测之后，自动标注内容属于分析框架的哪些维度：
```python
from shared.framework_tagger import tag_content
sections = tag_content(text, mode="keyword")  # keyword mode for X bookmarks (fast)
```
将结果添加到 frontmatter extra dict：
```yaml
framework_sections: [S1, S4.2, S7]
```
如果 `framework_tagger` 不可用或返回空列表，跳过（不报错）。

## Pipeline Tracking

**自动执行:** 每个 bookmark 处理后，记录到 ingestion pipeline（如果 task_manager 可用）：
```python
try:
    from shared.task_manager import record_pipeline_entry
    record_pipeline_entry(
        canonical_key=canonical_key,  # from record_ingestion()
        item_type="x-bookmark", item_title=tweet_text[:80],
        source_platform="x-bookmark", obsidian_path=str(output_path),
        has_frontmatter=True, has_tickers=bool(tickers),
        has_framework_tags=bool(framework_sections),
        tickers_found=tickers, framework_sections=framework_sections,
    )
except ImportError:
    pass
```

## Related

- `/telegram` - Telegram bot for photo/URL intake
- `/wechat-hao` - WeChat article exporter (similar pattern)
- `/chatgpt-organizer` - ChatGPT conversation importer (similar JSON-to-Obsidian pattern)
