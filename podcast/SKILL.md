---
name: podcast
description: 播客笔记投资洞察提取 - 处理 podwise 转录，提取 ticker、关键论点、投资相关信息，输出到 Obsidian
---

# /podcast - 播客笔记投资洞察提取

从 podwise 同步的播客转录中提取投资相关洞察，添加 ticker 标签、关键引用、组合相关性分析。

## Instructions for Claude

**搜索路径：** `~/Documents/Obsidian Vault/信息源/播客/`

**处理模式：**
- **单篇处理** (`/podcast "标题关键词"`)：找到并处理指定播客
- **批量扫描** (`/podcast scan`)：找出所有 `status: "未开始"` 的播客，列出待处理清单
- **批量处理** (`/podcast scan --process N`)：处理前 N 篇未处理的播客
- **Notion 同步** (`/podcast sync`)：从 Notion Podwise Database 同步新 episode 到 Obsidian

**Ticker 识别：** 使用 shared/ticker_detector 进行标准化 ticker 检测（支持中文公司名、entity_dictionary 39 家公司）：
```python
import sys; sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
from shared.ticker_detector import detect_tickers
results = detect_tickers(text)  # Returns [{"ticker": "NVDA", "confidence": 0.95, ...}]
```
Fallback: 如果 shared 模块不可用，使用 regex `$TICKER` + 公司名匹配。

**交叉引用：** 处理时扫描以下目录，为提到的 ticker/公司添加 `[[wikilinks]]`：
- `研究/研究笔记/` 中的研究笔记
- `~/PORTFOLIO/portfolio_monitor/research/companies/` 中的 thesis
- `研究/财报分析/` 中的财报分析
- `13F-CLAUDE/output/` 中的 13F 机构持仓数据（通过 `shared/13f_query.py`）

**原始内容保护：** 绝不修改 podwise 原始同步的 Summary、Takeaways、Q&A、Transcript 内容。只在文件顶部（frontmatter 之后、原始内容之前）插入新的 section。

## When to Use This Skill

- 用户使用 `/podcast` 命令
- 用户说"处理一下播客笔记"
- 用户想从播客中提取投资相关信息

## Core Workflow

```
输入：标题关键词 或 scan 命令
       ↓
[1] 查找播客笔记
    • 按标题模糊搜索 信息源/播客/ 目录
    • 或扫描所有 status: "未开始" 的文件
       ↓
[2] 阅读全文
    • 读取 Summary、Takeaways、Q&A、Transcript
    • 识别语言（中文/英文）
       ↓
[3] 提取投资洞察
    • 提到的 tickers（含上下文）
    • 关键投资论点（bull/bear）
    • 行业/宏观主题
    • 值得记录的引用
    • 数据点/统计数字
       ↓
[4] 交叉引用
    • 检查提到的 ticker 是否有现有研究/thesis
    • 添加 [[wikilinks]]
    • 标注与当前持仓的相关性
       ↓
[5] 写入增强内容
    • 更新 frontmatter（添加 tickers, topics, enriched: true）
    • 在原始内容前插入 "Investment Insights" section
    • 更新 status: "已处理"
       ↓
[6] 输出摘要到终端
```

## Quick Start

```
/podcast "Hidden Economics"           # 处理包含关键词的播客
/podcast "华为"                       # 搜索中文标题
/podcast scan                         # 列出所有未处理的播客
/podcast scan --process 5             # 批量处理前 5 篇
/podcast list                         # 列出所有已处理的播客摘要
/podcast recent                       # 最近 7 天的播客
/podcast sync                         # 从 Notion 同步新 episode 到 Obsidian
/podcast sync --dry-run               # 预览同步（不创建文件）
```

## 输出格式（插入到原始笔记顶部）

在 frontmatter 之后、原始 Summary 之前插入：

```markdown
## 🎯 Investment Insights (Auto-Generated)

**Tickers Mentioned:** [[NVDA]], [[MSFT]], [[GOOGL]]
**Topics:** AI Infrastructure, Data Center Economics, GPU Compute
**Portfolio Relevance:** 🔴 High（提到持仓 NVDA 的竞争格局变化）

### 关键投资论点
1. **AI 成本下降 99%** - frontier model 访问成本每 7 个月减半，利好应用层 [来源: Summary]
2. **硬件→能源瓶颈转移** - 算力不再是瓶颈，冷却和电力成为关键 [来源: Takeaway #6]
3. **消费者 AI 比 B2B 更粘** - consumer AI 留存率更高，有利于持续研发投入 [来源: Takeaway #10]

### 值得记录的引用
> "AI companies are achieving scale and distribution at an unprecedented rate, reaching levels that took Google five and a half times longer to achieve."

### 数据点
- AI 公司增长速度：达到 Google 用 5.5 倍时间才达到的规模
- 成本下降：99% cost reduction in frontier model access
- 能力翻倍周期：every 7 months

---
```

### 更新后的 frontmatter

```yaml
---
title: "The Hidden Economics Powering AI"
podcast: "The a16z Show"
link: "https://podwise.ai/dashboard/episodes/6973681"
publish_date: 2026-01-26
status: "已处理"
created: 2026-01-26
enriched: true
enriched_date: 2026-02-05
tickers: [NVDA, MSFT, GOOGL]
topics: [AI Infrastructure, Data Center, GPU]
portfolio_relevance: high
tags:
  - podcast
  - podwise
  - enriched
---
```

## /podcast scan 输出

```
📻 未处理的播客笔记 (23/58)
============================

| # | 标题 | 发布日期 | 语言 | 预估相关性 |
|---|------|----------|------|-----------|
| 1 | The Hidden Economics Powering AI | 2026-01-26 | EN | 🔴 High |
| 2 | #407.拆解华为算力真相与中芯困局 | 2026-01-xx | CN | 🔴 High |
| 3 | Healthcare 2026: AI Doctors, GLP-1s | 2026-01-xx | EN | 🟡 Medium |
| ... | | | | |

提示：使用 /podcast scan --process 5 处理前 5 篇
```

## Commands Reference

```bash
# 处理
/podcast "关键词"                # 搜索并处理指定播客
/podcast scan                   # 列出未处理的播客
/podcast scan --process N       # 批量处理 N 篇
/podcast list                   # 列出已处理的播客
/podcast recent                 # 最近 7 天的播客
/podcast stats                  # 统计：已处理/未处理/按主题分布

# Notion 同步
/podcast sync                   # 从 Notion 同步新 episode（去重）
/podcast sync --dry-run         # 预览同步，不创建文件
/podcast sync --recent 7        # 只同步最近 7 天
/podcast sync --status "未开始"  # 只同步特定状态
```

## Notion Sync (`/podcast sync`)

从 Notion Podwise Database 同步新 episode 到本地 Obsidian `信息源/播客/` 文件夹。

### Notion Database 信息

- **Database ID:** `2e80e07f-cb27-8192-93fa-d81d489145a8`
- **Data Source URL:** `collection://2e80e07f-cb27-81b8-b2e3-000be8b0c4a1`
- **View URL (按发布时间倒序):** `view://2e80e07f-cb27-81e8-8416-000c627703d6`

### Database Schema

| Column | Type | 说明 |
|--------|------|------|
| Episode | title | Episode 标题 |
| Publish Time | date | 发布日期 |
| Podcast | text | 播客节目名 |
| Link | url | Podwise 链接 (`https://podwise.ai/dashboard/episodes/{ID}`) |
| 状态 | status | `未开始` / `进行中` / `完成` |

### Sync Workflow

```
/podcast sync
       ↓
[1] 查询 Notion Database
    • 使用 notion-query-database-view 查询 Podwise view
    • 获取所有 episode 列表（Episode, Link, Podcast, Publish Time, 状态）
       ↓
[2] 构建本地索引
    • 扫描 ~/Documents/Obsidian Vault/信息源/播客/ 所有 .md 文件
    • 从每个文件的 frontmatter 提取 link 字段
    • 构建 Set: existing_links = {link1, link2, ...}
       ↓
[3] 去重比较
    • 对 Notion 中每条记录，检查其 Link 是否在 existing_links 中
    • 匹配规则：精确匹配 Podwise URL（这是全局唯一 ID）
    • 如果 URL 完全匹配 → 跳过（已存在）
    • 如果不匹配 → 标记为新 episode
       ↓
[4] 获取新 episode 内容
    • 对每个新 episode，使用 notion-fetch 获取完整页面内容
    • 页面包含：Summary, Takeaways, Q&A, Transcript
       ↓
[5] 创建 Obsidian 文件
    • 文件名: 直接使用 Episode 标题（与 Notion 页面标题一致）
    • 路径: ~/Documents/Obsidian Vault/信息源/播客/{Episode Title}.md
    • 文件名清理: 移除 / \ : * ? " < > | 等文件系统非法字符
    • 写入 frontmatter + Notion 页面内容
       ↓
[6] 输出同步结果
    • 新增数量、跳过数量、失败数量
    • 列出新增的 episode 标题
```

### 去重策略（关键）

**主键：Podwise Link URL**

```
Notion Link: https://podwise.ai/dashboard/episodes/6973681
                                                    ↕ 精确匹配
Obsidian frontmatter link: https://podwise.ai/dashboard/episodes/6973681
```

**为什么用 Link 而不是标题：**
- Link 是全局唯一的 episode ID
- 标题可能有微小差异（空格、标点、大小写）
- Link 在 Notion 和 Obsidian 中完全一致

**Fallback 匹配（如果 link 为空）：**
- 用 Episode 标题做模糊匹配（忽略大小写、去掉特殊字符后比较）
- 只在 link 字段缺失时使用

### 新文件的 Frontmatter 模板

```yaml
---
title: "{Episode Title}"
podcast: "{Podcast Name}"
link: "{Podwise URL}"
publish_date: YYYY-MM-DD
status: "未开始"
created: YYYY-MM-DD
notion_id: "{Notion Page ID}"
tags:
  - podcast
  - podwise
---
```

**注意 `notion_id` 字段：** 保存 Notion 页面 ID，方便后续双向同步或回溯。

### Sync Commands

```bash
/podcast sync                    # 同步所有新 episode
/podcast sync --dry-run          # 预览：只显示会同步哪些，不实际创建文件
/podcast sync --recent 7         # 只同步最近 7 天的新 episode
/podcast sync --status "未开始"   # 只同步特定状态的 episode
```

### Sync 输出

```
📻 Podcast Sync Report
======================

Notion 总计: 85 episodes
本地已有: 58 episodes
本次新增: 27 episodes
跳过(重复): 58 episodes

新增 Episodes:
  ✅ Vibe Coding Could Change Everything (2026-02-05)
  ✅ Moltbook Mania Explained (2026-02-05)
  ✅ Why This Isn't the Dot-Com Bubble (2026-02-05)
  ✅ Vol.244 迷失在税中的小餐馆 (2026-02-05)
  ... (23 more)

提示：使用 /podcast scan 查看未处理的播客
```

### 注意事项

- **Notion MCP 工具：** 使用 `notion-query-database-view` 查询数据库，`notion-fetch` 获取页面内容
- **速率限制：** Notion API 有速率限制，批量获取时注意间隔
- **内容格式转换：** Notion 返回的 Markdown 可能需要轻微格式调整以适配 Obsidian
- **不修改 Notion：** sync 是单向的（Notion → Obsidian），不会修改 Notion 中的数据
- **幂等性：** 多次运行 sync 不会创建重复文件（基于 Link URL 去重）
- **文件名冲突：** 如果标题完全相同但 Link 不同（不太可能），在文件名后加 `_2`

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/moc` | 播客中提到的 ticker 会出现在 MOC 中 |
| `/research` | 播客洞察补充研究笔记 |
| `/kb` | 关键发现可补充研究资料 |
| `/link` | 播客笔记通过 wikilink 连接到其他内容 |

## 注意事项

- 绝不修改原始 podwise 同步内容（Summary/Takeaways/Q&A/Transcript）
- 只在 frontmatter 后插入新 section
- 中文和英文播客都要处理
- ticker 识别要考虑：$NVDA、NVDA、Nvidia、英伟达 等多种写法
- Portfolio relevance 基于用户的实际持仓（查看 PORTFOLIO 数据库）
- 如果播客已经有 `enriched: true`，提示用户是否要重新处理

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

**自动执行:** 处理完每篇播客后，记录到 ingestion pipeline 跟踪（如果 task_manager 可用）：
```python
try:
    from shared.task_manager import record_pipeline_entry
    record_pipeline_entry(
        canonical_key=f"podcast_{url_hash_or_title_hash}",
        item_type="podcast",
        item_title=episode_title,
        source_platform="podcast",
        obsidian_path=str(output_path),
        has_frontmatter=True,
        has_tickers=bool(tickers),
        has_framework_tags=bool(framework_sections),
        tickers_found=tickers,
        framework_sections=framework_sections,
    )
except ImportError:
    pass
```
用 podwise link URL hash 或标题 hash 作为 canonical_key。

## Post-Ingestion

**自动执行:** 完成所有处理后，立即对输出文件夹执行 link 扫描（等同于 `/link 信息源/播客/`），为新增笔记添加 [[wikilinks]]。
用户说"跳过 link"时跳过此步。
