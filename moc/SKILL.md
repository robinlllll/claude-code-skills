---
name: moc
description: Map of Content 生成器 - 跨全 Vault 搜索 ticker/主题，生成统一知识地图，输出到 Obsidian
---

# /moc - Map of Content 生成器

为 ticker 或投资主题生成跨文件夹的知识地图（Map of Content），把分散在 13+ 个文件夹的信息汇聚成一个可导航的索引。

## Instructions for Claude

**自动创建目录：** 如果 `~/Documents/Obsidian Vault/导航/MOC/` 不存在，自动创建。

**搜索范围：** 必须搜索以下所有位置：
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
12. `~/PORTFOLIO/portfolio_monitor/research/companies/{TICKER}/` - thesis 文件
13. `~/Documents/Obsidian Vault/导航/NotebookLM/` - NotebookLM Q&A 历史记录
14. `~/Documents/Obsidian Vault/研究/供应链/` - 供应链提及（{TICKER}_mentions.md）
    - 也可查询 `~/.claude/skills/supply-chain/data/supply_chain.db`
    - 展示哪些公司在财报中提到了该 ticker
15. `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` - ChatGPT 投资分析对话
    - 搜索文件内容中 ticker / 公司名 / 别名的提及
16. `~/Documents/Obsidian Vault/写作/投资回顾/` - 历史回顾报告中对该 ticker 的提及

**搜索策略：**
- 对 TICKER 类查询：搜索 ticker 本身 + 公司全名 + 常见别名（如 NVDA → NVIDIA → 英伟达）
- 对 TOPIC 类查询：搜索主题关键词 + 相关子主题
- 使用 Grep 工具搜索文件内容，Glob 搜索文件名
- 对 导航/NotebookLM/ 目录：搜索 Q&A 正文中 ticker 或公司名的提及

**更新机制：** 如果 MOC 文件已存在，更新而不是覆盖。保留用户手动添加的内容（在 `<!-- USER NOTES -->` 标记之后的内容）。

## When to Use This Skill

- 用户使用 `/moc TICKER` 或 `/moc TOPIC`
- 用户说"汇总一下关于 XX 的所有资料"
- 用户想了解某个 ticker 在 vault 中的所有相关笔记

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

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

````markdown
---
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: moc
ticker: NVDA
aliases: [NVIDIA, 英伟达]
total_notes: 15
tags: [moc, NVDA]
---

# NVDA - Map of Content

> 跨 Vault 知识地图，自动生成于 YYYY-MM-DD，共找到 15 条相关笔记。

## 📊 投资论点 (Thesis)
- [[thesis]] - 核心投资逻辑 (PORTFOLIO) | 更新于 YYYY-MM-DD [Thesis]

## 📝 研究笔记 (研究/研究笔记)
- [[NVDA_2026-02-05]] - 深度研究，覆盖估值/竞争/风险 | 2026-02-05 [Vault]

## 📈 财报分析 (研究/财报分析)
- （无相关记录）

## 🎙️ 播客提及 (信息源/播客)
- [[The Hidden Economics Powering AI]] - a16z Show, AI基础设施经济学 | 2026-01-26 [Podcast]
- [[#407.拆解华为算力真相与中芯困局]] - 芯片出口管制复盘 | 2026-01-xx [Podcast]

## 📬 收件箱
- [[2026-01-25 - NVDA earnings preview]] - 财报前瞻 | 2026-01-25 [Vault]

## 🗓️ 周会讨论
- [[会议实录 2026-01-03]] - AI硬件/半导体偏多，存储股两周涨40% | 2026-01-03 [Meeting]

## 🏦 机构持仓 (13F)
- （无相关记录）

## 🇨🇳 雪球讨论 (信息源/雪球)
- （无相关记录）

## 📎 其他 (剪藏 / 思考 / 技术概念)
- （无相关记录）

## 📚 NotebookLM Q&A
- [[导航/NotebookLM/Oracle Cloud Unit Economics]] - Q: "What drives OCI margins?" | 2026-01-25 [NLM]
- （无相关记录）

## 🔗 Supply Chain Mentions
- TSM Q4 2025 财报提到 NVDA CoWoS 扩产 | 2025-12-15 [SC]
- AVGO Q3 2025 提到 NVDA networking 需求 | 2025-09-20 [SC]
- （无相关记录）

## 💬 ChatGPT Analysis History
- [[ChatGPT/Investment Research/2026-01-20 - NVDA估值讨论]] | 2026-01-20 [ChatGPT]
- （无相关记录）

## 📐 Framework Coverage View

| # | Section | Sources | Level |
|---|---------|---------|-------|
| S1 | 📈 Market & Growth | 4 (2p+2s) | ✅ |
| S2 | 🏟️ Competitive Landscape | 3 (2p+1s) | ✅ |
| S3 | 🏰 Barriers & Moat | 2 (1p+1s) | ⚠️ |
| S4 | 📊 Company & Financials | 5 (3p+2s) | ✅ |
| S5 | 👔 Management | 0 | ❌ |
| S6 | 💰 Valuation | 1 (0p+1s) | ⚠️ |
| S7 | ⚠️ Risks | 2 (1p+1s) | ⚠️ |
| S8 | 🎯 Investment Conclusion | 1 (1p+0s) | ⚠️ |
| S9 | 🔍 Research Gaps | 0 | ❌ |

Score: 56% | Gaps: S5 管理层, S9 研究盲区
→ Run `/research TICKER --deep` to fill gaps

---
<!-- USER NOTES -->
（用户手动添加的笔记保留在此处）
````

## Source Attribution

**Every entry in the MOC MUST carry a source tag to enable traceability.** When generating or updating a MOC, append the appropriate tag after each entry line.

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

### Tag Placement

Place the tag at the end of each entry line, after the date or description:

```markdown
### 研究笔记
- [[2025-01-15 - PM earnings Q4 analysis]] - 财报深度拆解 | 2025-01-15 [Transcript]
- [[2025-02-01 - PM ZYN growth thesis]] - ZYN 增长逻辑 | 2025-02-01 [Thesis]

### 机构持仓
- 19 institutional holders in Q4 2025 [13F]

### 供应链信号
- IQOS manufacturing expansion in Italy mentioned by STMicroelectronics [SC]

### 播客提及
- [[The Hidden Economics Powering AI]] - a16z Show | 2026-01-26 [Podcast]

### ChatGPT Analysis
- [[2026-01-20 - NVDA估值讨论]] - 估值模型对比 | 2026-01-20 [ChatGPT]

### 投资回顾
- 2025-Q4 review 中提到 PM 减仓决策 [Review]
```

### Rules

1. **Every entry** in every section of the MOC must have exactly one source tag
2. For entries matching multiple sources, use the **primary** source where the content was found
3. When a section has no results, the `（无相关记录）` placeholder does NOT need a tag
4. Tags are plain text in square brackets — not Obsidian tags (no `#` prefix)

## /moc list 命令

列出 `导航/MOC/` 目录下所有已生成的 MOC：

```
已生成的 Map of Content (3 个)
============================

| Ticker/主题 | 相关笔记数 | 最后更新 |
|-------------|-----------|----------|
| NVDA | 15 | 2026-02-05 |
| UBER | 8 | 2026-02-04 |
| AI Infrastructure | 22 | 2026-02-03 |
```

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

## 注意事项

- 搜索使用 Grep 工具，不使用 bash grep
- 对中文内容和英文内容都要搜索
- 周会文件搜索时重点看前 10 行（包含"提到公司"摘要行）和正文
- frontmatter 中 tickers 字段是 YAML 数组，搜索时匹配数组元素
- 输出路径使用 pathlib.Path 兼容 Windows/Mac
