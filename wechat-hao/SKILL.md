# 微信公众号文章导出 (WeChat Article Exporter)

Export WeChat articles to Notion and Obsidian with AI-powered analysis.

## Project Location

`C:\Users\thisi\wechat-exporter`

## When to Use This Skill

- User sends a WeChat article URL (`mp.weixin.qq.com`)
- User wants to export/save a WeChat article
- User mentions "微信文章", "公众号", or "wechat article"

## Features

1. **Article Export**: Fetch, parse, and convert WeChat articles to Markdown
2. **Multi-destination Sync**: Notion + Obsidian + Local canonical storage
3. **Deduplication**: Three-layer dedup (URL hash, content hash, weak key)
4. **AI Analysis**: Auto-detect content type and generate tailored ChatGPT prompts
5. **Telegram Integration**: Works via Telegram bot with inline analysis

## Content Types Detected

- `investment_thesis` - Investment research and analysis
- `market_commentary` - Market views and macro analysis
- `company_analysis` - Company/earnings analysis
- `opinion_essay` - Thought pieces and reflections
- `news_update` - News and announcements
- `tutorial` - Guides and how-tos
- `interview` - Interviews and dialogues

## Commands

### Basic Export (CLI)
```bash
cd "C:\Users\thisi\wechat-exporter"
python process_article.py "https://mp.weixin.qq.com/s/xxx"
```

### Export with Analysis
```bash
# Generate ChatGPT prompt
python process_article.py "URL" --analyze

# Run Claude analysis directly
python process_article.py "URL" --claude

# Save analysis to Obsidian note
python process_article.py "URL" --save-analysis
```

### Telegram Bot
Just send a WeChat article URL to the Telegram bot. Analysis is automatic:
- Exports article to Notion/Obsidian
- Detects content type
- Generates ChatGPT prompt (sent as reply)
- Saves analysis to Obsidian note

## Output Locations

| Destination | Path |
|-------------|------|
| Canonical | `wechat-exporter/data/canonical/` |
| Obsidian | `Documents/Obsidian Vault/收件箱/` |
| Notion | Weekly Inbox database |

## File Naming

Format: `YYYY-MM-DD_公众号_标题.md`

Example: `2026-02-05_Rome_Capital_关于估值的思考.md`

## Analysis Output

The Obsidian note includes:
1. Original article content (Markdown)
2. AI Analysis section with:
   - Content type
   - Key topics
   - ChatGPT deep analysis prompt

## Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
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

## Pipeline Tracking

**自动执行:** 导出完成后，记录到 ingestion pipeline（如果 task_manager 可用）：
```python
try:
    from shared.task_manager import record_pipeline_entry
    record_pipeline_entry(
        canonical_key=canonical_key,  # from record_ingestion()
        item_type="wechat", item_title=article_title,
        source_platform="wechat", obsidian_path=str(output_path),
        has_frontmatter=True, has_tickers=bool(tickers),
        has_framework_tags=bool(framework_sections),
        tickers_found=tickers, framework_sections=framework_sections,
    )
except ImportError:
    pass
```

## Post-Export

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link 收件箱/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。

## Related

- `/telegram` - Photo bot that also handles WeChat URLs
- `/notebooklm` - Query articles in NotebookLM
- `/link` - Auto-link new notes after export
