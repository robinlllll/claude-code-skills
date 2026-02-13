# Substack RSS to Obsidian

Sync Substack newsletter articles into Obsidian vault with automatic summarization, ticker detection, and copyright-compliant excerpts.

## Project Location

`C:\Users\thisi\.claude\skills\substack`

## When to Use This Skill

- User says `/substack sync` to pull all new articles
- User says `/substack add {url}` to add a new subscription
- User says `/substack list` to show current subscriptions
- User says `/substack status` to check feed health
- User says `/substack remove` to unsubscribe from a feed
- User mentions "substack", "newsletter sync", or "RSS feed"

## Commands

### Sync All Feeds
```bash
/substack sync
```
Pulls all new articles from subscribed feeds, deduplicates, and saves summaries to Obsidian.

### Add Subscription
```bash
/substack add https://doomberg.substack.com
```
Accepts either `https://name.substack.com` or `https://name.substack.com/feed`. Normalizes to feed URL automatically. **Auto-verifies** feed reachability on add.

### List Subscriptions
```bash
/substack list
```
Shows all configured Substack feeds with add dates.

### Feed Status Dashboard
```bash
/substack status
```
Shows per-feed health: article count, last sync date, RSS reachability. Useful for spotting dead feeds or sync issues.

### Remove Feed
```bash
/substack remove 1                 # by index from 'list'
/substack remove doomberg          # by name substring
```
Removes a feed from config. Shows updated list after removal.

## CLI Usage

```bash
python "C:\Users\thisi\.claude\skills\substack\substack_fetcher.py" sync
python "C:\Users\thisi\.claude\skills\substack\substack_fetcher.py" add "https://doomberg.substack.com"
python "C:\Users\thisi\.claude\skills\substack\substack_fetcher.py" list
python "C:\Users\thisi\.claude\skills\substack\substack_fetcher.py" status
python "C:\Users\thisi\.claude\skills\substack\substack_fetcher.py" remove 1
```

## Scheduled Sync

Daily auto-sync at 08:00 via Windows Task Scheduler:
- **Script:** `~/scripts/substack_daily_sync.py`
- **Wrapper:** `~/scripts/substack_daily_sync.bat`
- **Register:** `~/scripts/register_substack_daily.bat` (run once as admin)
- **Log:** `~/scripts/logs/substack_sync.log`

## Workflow

1. **Read feeds** - Parse RSS via `fastfeedparser` for each subscription
2. **Dedup** - Skip articles already ingested (shared `ingestion_state.db`)
3. **Extract** - If RSS content is truncated (<500 chars), fetch full text via `trafilatura`
4. **Cache** - Save raw HTML to local `raw_cache/` (not synced to Obsidian)
5. **Summarize** - Generate summary (<=500 words) + key excerpts (<=3 paragraphs)
6. **Detect tickers** - Scan content for investment-relevant ticker symbols
7. **Save** - Write Obsidian note with standardized frontmatter

## Output

| Item | Location |
|------|----------|
| Obsidian notes | `Documents/Obsidian Vault/Substack/{author_name}/YYYY-MM-DD - {title}.md` |
| Raw HTML cache | `.claude/skills/substack/raw_cache/` (local only) |
| Feed config | `.claude/skills/substack/substack_feeds.yaml` |

## Note Format

Each note contains:
- Standardized frontmatter (id, type=substack, source_platform, author, published_at, ingested_at, tickers, tags)
- Summary (<=500 words) -- not full text (copyright compliance)
- Key excerpts (<=3 paragraphs)
- Link to original article

## Dependencies

```bash
pip install fastfeedparser trafilatura markdownify pyyaml
```

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

## Post-Ingestion

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link 信息源/Substack/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。

## Related

- `/wechat-hao` - Similar pipeline for WeChat articles
- `/podcast` - Newsletter-like ingestion for podcast transcripts
- `/link` - Auto-link new notes after ingestion
- Shared utilities: `shared/frontmatter_utils.py`, `shared/ticker_detector.py`
