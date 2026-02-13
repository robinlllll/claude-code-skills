# X.com Bookmarks to Obsidian

Import X (Twitter) bookmarks exported via the [twitter-web-exporter](https://github.com/prinsss/twitter-web-exporter) Chrome extension into Obsidian notes. Also supports saving individual tweets by URL.

## Project Location

`C:\Users\thisi\.claude\skills\x-bookmarks`

## When to Use This Skill

- User wants to import X/Twitter bookmarks into Obsidian
- User mentions "x bookmarks", "twitter bookmarks", or "tweet import"
- User has a JSON export from twitter-web-exporter
- User wants to save a single tweet URL

## Commands

| Command | Description |
|---------|-------------|
| `/x-bookmarks import` | Auto-find export in ~/Downloads and import |
| `/x-bookmarks import {json_file}` | Import from explicit JSON path |
| `/x-bookmarks save {tweet_url}` | Save a single tweet by URL (uses yt-dlp) |
| `/x-bookmarks stats` | Show import statistics (total imported, by author, date range) |

### Import Bookmarks (auto-find)

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py import
```
Scans `~/Downloads` for `twitter-Bookmarks-*.json`, `twitter-*.json`, `bookmarks*.json`, or `*bookmark*.json` (newest first).

### Import Bookmarks (explicit path)

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py import "C:\path\to\bookmarks.json"
```

### Save Single Tweet

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py save "https://x.com/user/status/1234567890"
```
Fetches tweet metadata via `yt-dlp` (uses Chrome cookies for auth), then saves to Obsidian. No browser extension needed.

### Show Statistics

```bash
cd "C:\Users\thisi\.claude\skills\x-bookmarks"
python x_bookmark_converter.py stats
```

## Workflow

1. **Export:** Install [twitter-web-exporter](https://github.com/prinsss/twitter-web-exporter) Chrome extension
2. **Export:** Open X.com bookmarks page, click the extension to export as JSON
3. **Import:** Run `/x-bookmarks import` (auto-finds in Downloads) or `/x-bookmarks import path/to/bookmarks.json`
4. **Review:** Notes appear in `Documents/Obsidian Vault/X Bookmarks/`

**Single tweet workflow:** Just run `/x-bookmarks save <url>` — no export needed.

## Features

1. **Auto-Find Export:** Scans ~/Downloads for bookmark JSON files, picks newest
2. **Single Tweet Save:** Save individual tweets by URL via yt-dlp (no extension needed)
3. **Thread Detection:** Multiple tweets from the same author in reply to each other are merged into a single note
4. **Ticker Detection:** Identifies $TICKER patterns and company names via shared entity dictionary
5. **Framework Tagging:** Auto-tags content with analysis framework sections (keyword mode)
6. **Pipeline Tracking:** Records each import to ingestion pipeline for stage tracking
7. **Deduplication:** Uses shared ingestion_state.db to skip already-imported tweets
8. **Flexible Parsing:** Handles multiple JSON structures from twitter-web-exporter gracefully
9. **Media Links:** Preserves image/video URLs as markdown links
10. **Quoted Tweets:** Formats quoted tweets as blockquotes within the note

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

- Python 3.x + PyYAML (for shared ticker detection)
- `yt-dlp` (for single tweet save mode): `pip install yt-dlp`
- Shared utilities: `~/.claude/skills/shared/` (frontmatter_utils, ticker_detector, framework_tagger, task_manager)

## Related

- `/telegram` - Telegram bot for photo/URL intake
- `/wechat-hao` - WeChat article exporter (similar pattern)
- `/chatgpt-organizer` - ChatGPT conversation importer (similar JSON-to-Obsidian pattern)
