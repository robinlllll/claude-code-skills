---
name: podcast
description: "播客笔记投资洞察提取 - 处理 podwise 转录，提取 ticker、关键论点、投资相关信息，输出到 Obsidian。Use when user says 'podcast', '播客', 'podwise', or shares a podcast transcript."
---

# /podcast - 播客笔记投资洞察提取

从 podwise 同步的播客转录中提取投资相关洞察，添加 ticker 标签、关键引用、组合相关性分析。

## Quick Start

```
/podcast "Hidden Economics"           # Tier 2 深度分析：7-section 报告 + 组合交叉引用
/podcast scan                         # Tier 1 列出所有未处理的播客
/podcast scan --process 5             # Tier 1 批量处理前 5 篇
/podcast sync                         # 从 Notion 同步新 episode
/podcast sync --dry-run               # 预览同步
/podcast list / recent / stats        # 查看已处理/最近/统计
```

## Two-Tier Processing

| 命令 | Tier | 处理方式 |
|------|------|----------|
| `/podcast "关键词"` | **Tier 2 (Deep)** | 单篇 7-section 分析 + 组合交叉引用 + `prompts/prompt_podcast.py` |
| `/podcast scan --process N` | Tier 1 (Batch) | `process_batch.py`，regex ticker/topic 匹配 |
| `/podcast scan` | Tier 1 (Triage) | 列出未处理播客 |
| `/podcast sync` | Utility | Notion → Obsidian 同步。详见 `references/notion_sync.md` |

## Tier 2 Deep Analysis Workflow

```
"关键词" → [1] 搜索 信息源/播客/ 确认唯一匹配 → [2] detect_tickers + 组合上下文注入 → [3] get_podcast_prompt() → [4] Claude 生成 7-section 分析 → [5] 插入到 frontmatter 后/原始内容前 → [6] 终端摘要
```

**Ticker 检测 + 组合上下文：**
```python
import sys; sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "podcast"))
from prompts import build_portfolio_context, get_podcast_prompt

sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
from shared.ticker_detector import detect_tickers
results = detect_tickers(text)
tickers = [r["ticker"] for r in results]
ctx = build_portfolio_context(tickers)
prompt = get_podcast_prompt(
    podcast_name=frontmatter["podcast"],
    episode_title=frontmatter["title"],
    episode_date=str(frontmatter.get("publish_date", "")),
    tickers_detected=tickers, **ctx,
)
```

**交叉引用路径：** `研究/研究笔记/`, thesis files, `研究/财报分析/`, 13F data (via `shared/13f_query.py`)

**输出格式：** 详见 `references/output_format.md`（Tier 1 浅层 + Tier 2 七节深度）

## Frontmatter 更新

处理后更新: `status: "已处理"`, `enriched: true`, `enriched_date`, `tickers`, `topics`, `portfolio_relevance`。Tier 2 额外: `enriched_tier: 2`, `thesis_alignment`, `action_flags`。

## 关键规则

- **绝不修改原始 podwise 内容**（Summary/Takeaways/Q&A/Transcript）
- 新 section 插在 frontmatter 之后、原始内容之前
- 中英文播客都处理
- 已有 `enriched: true` 时提示用户是否重新处理

## Post-Processing Pipeline

处理完成后自动执行（失败则静默跳过）：

1. **Framework Tagging:** `shared.framework_tagger.tag_content()` → frontmatter `framework_sections`
2. **Pipeline Tracking:** `shared.task_manager.record_pipeline_entry()` → canonical_key `podcast_{hash}`
3. **Theme Tagging:** `shared.theme_tagger.tag_themes()` → frontmatter `themes`
4. **Auto Link:** 对输出文件夹执行 link 扫描，添加 `[[wikilinks]]`（用户说"跳过 link"时跳过）
