---
name: moc
description: Map of Content 生成器 - 跨全 Vault 搜索 ticker/主题，生成统一知识地图，输出到 Obsidian
---

# /moc - Map of Content 生成器

为 ticker 或投资主题生成跨文件夹的知识地图（Map of Content），把分散在 13+ 个文件夹的信息汇聚成一个可导航的索引。

## Important Rules

**Search scope — MUST search all 8 vault top-level folders and related paths:**
1. `研究/研究笔记/` - 研究笔记（文件名含 TICKER）
2. `研究/财报分析/{TICKER}/` - 财报分析
3. `收件箱/` - frontmatter 中 `tickers: []` 字段 + 正文提及
4. `信息源/播客/` - 播客笔记（搜索正文）
5. `周会/` - 周会实录（搜索"提到公司"行 + 正文）
6. `信息源/雪球/` - 雪球帖子
7. `研究/13F 持仓/` - 机构持仓
8. `信息源/剪藏/` - 剪藏
9. `写作/思考性文章/` - 思考文章
10. `写作/技术概念/` - 技术概念
11. `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/` - thesis 文件
12. `~/Documents/Obsidian Vault/导航/NotebookLM/` - NotebookLM Q&A 历史记录
13. `~/Documents/Obsidian Vault/研究/供应链/` - 供应链提及（{TICKER}_mentions.md）
    - 也可查询 `~/.claude/skills/supply-chain/data/supply_chain.db`
14. `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` - ChatGPT 投资分析对话
15. `~/Documents/Obsidian Vault/写作/投资回顾/` - 历史回顾报告中对该 ticker 的提及

**Output guardrails:**
- MUST include `[[wikilinks]]` to source notes in every entry (not plain text filenames)
- NEVER create a MOC file if one already exists at the same path — update it instead
- NEVER overwrite content after `<!-- USER NOTES -->` marker — preserve user-added text
- MUST carry exactly one source tag per entry (e.g. `[Vault]`, `[Podcast]`) — see Source Tags below
- MUST auto-create `~/Documents/Obsidian Vault/导航/MOC/` if it does not exist
- Output path: `~/Documents/Obsidian Vault/导航/MOC/{TICKER 或 TOPIC}.md`
- Use Grep tool for content search, Glob for filename search — never raw bash grep

**Search strategy:**
- TICKER query: search ticker symbol + company full name + common aliases (e.g. NVDA → NVIDIA → 英伟达)
- TOPIC query: search topic keywords + related sub-topics
- Search both Chinese and English content
- For 周会 files: prioritize first 10 lines (contain "提到公司" summary) then full body
- frontmatter `tickers` field is a YAML array — match individual array elements

## Core Workflow

```
输入 TICKER 或 TOPIC
       ↓
[1] 识别搜索关键词
    • TICKER → ticker + 公司名 + 别名（中英文）
    • TOPIC → 主题词 + 子主题
       ↓
[2] 并行搜索所有 Vault 文件夹
    • 文件名匹配
    • frontmatter tickers 字段
    • 正文内容搜索
       ↓
[3] 分类汇总
    • 按来源类型分组
    • 提取每篇笔记的标题、日期、摘要
       ↓
[4] 生成 MOC 笔记
    • 带 YAML frontmatter
    • 按来源类型分 section
    • 每条记录包含 [[wikilink]]、日期、一句话摘要、source tag
       ↓
[5] 保存到 Obsidian
    • 路径: ~/Documents/Obsidian Vault/导航/MOC/{TICKER 或 TOPIC}.md
    • 如果已存在则更新
```

## Quick Start

```
/moc NVDA                    # NVDA 的所有相关笔记
/moc UBER                    # UBER 相关内容汇总
/moc "AI Infrastructure"     # AI 基础设施主题
/moc "China Consumer"        # 中国消费主题
/moc list                    # 列出所有已生成的 MOC
```

## 输出格式

MOC 文件的 YAML frontmatter 和 section 结构如下（完整示例见 `references/output-template.md`）：

```markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: moc
ticker: TICKER
aliases: [CompanyName, 中文名]
total_notes: N
tags: [moc, TICKER]
---

# TICKER - Map of Content

> 跨 Vault 知识地图，自动生成于 YYYY-MM-DD，共找到 N 条相关笔记。

## 📊 投资论点 (Thesis)
## 📝 研究笔记 (研究/研究笔记)
## 📈 财报分析 (研究/财报分析)
## 🎙️ 播客提及 (信息源/播客)
## 📬 收件箱
## 🗓️ 周会讨论
## 🏦 机构持仓 (13F)
## 🇨🇳 雪球讨论 (信息源/雪球)
## 📎 其他 (剪藏 / 思考 / 技术概念)
## 📚 NotebookLM Q&A
## 🔗 Supply Chain Mentions
## 💬 ChatGPT Analysis History
## 📐 Framework Coverage View

---
<!-- USER NOTES -->
（用户手动添加的笔记保留在此处）
```

## Source Attribution

**Every entry in the MOC MUST carry a source tag to enable traceability.**

### Source Tags

| Tag | Source |
|-----|--------|
| `[Vault]` | General Obsidian vault notes (收件箱, 剪藏, 思考文章, 技术概念) |
| `[NLM]` | NotebookLM Q&A history |
| `[13F]` | 13F institutional holdings data |
| `[SC]` | Supply chain database / mentions |
| `[Web]` | Web search results |
| `[Thesis]` | Thesis document from PORTFOLIO |
| `[Transcript]` | Earnings transcripts / 财报分析 |
| `[ChatGPT]` | ChatGPT export conversations |
| `[Review]` | Investment review notes (投资回顾) |
| `[Podcast]` | Podcast notes (播客) |
| `[Meeting]` | Weekly meeting transcripts (周会) |
| `[Xueqiu]` | Xueqiu posts (雪球) |

### Tag Rules

1. Every entry in every section must have exactly one source tag
2. For entries matching multiple sources, use the **primary** source where the content was found
3. When a section has no results, the `（无相关记录）` placeholder does NOT need a tag
4. Tags are plain text in square brackets — not Obsidian tags (no `#` prefix)

See `references/output-template.md` for a full tag placement example.

## /moc list 命令

列出 `导航/MOC/` 目录下所有已生成的 MOC，displaying ticker/topic, note count, and last updated date. See `references/output-template.md` for example output.

## Commands Reference

```bash
/moc {TICKER}                # 生成/更新 ticker 的 MOC
/moc {TOPIC}                 # 生成/更新主题的 MOC
/moc list                    # 列出所有 MOC
/moc {TICKER} --refresh      # 强制重新生成（不保留缓存）
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/research` | MOC 汇总 research 输出 |
| `/thesis` | MOC 包含 thesis 文件链接 |
| `/kb` | MOC 索引 KB 中的内容 |
| `/earnings` | MOC 索引财报分析 |
| `/podcast` | MOC 索引播客提及 |
| `/notebooklm` | MOC 索引 NotebookLM Q&A 历史 |
| `/supply-chain` | MOC 展示供应链关系图 |
| `/chatgpt-organizer` | MOC 索引 ChatGPT 投资分析对话 |
| `/review` | MOC 索引历史回顾中的提及 |

## 📐 Framework Coverage View (在 MOC 中生成)

在按来源类型分组的 section 之后，添加 Framework Coverage View 表格：

1. 运行覆盖度扫描获取数据：
   ```bash
   cd ~/.claude/skills && python shared/framework_coverage.py scan TICKER --format json
   ```
2. 解析 JSON 输出，生成 9 行的覆盖度表格
3. 显示每个 section 的源数量、覆盖级别（✅/⚠️/❌）
4. 末尾显示总分和 gap 提示

如果 `framework_coverage.py` 不可用或失败，跳过此 section（不报错）。

## When to Use This Skill

- 用户使用 `/moc TICKER` 或 `/moc TOPIC`
- 用户说"汇总一下关于 XX 的所有资料"
- 用户想了解某个 ticker 在 vault 中的所有相关笔记

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）
