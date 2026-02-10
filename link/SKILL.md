---
name: link
description: 自动链接器 - 扫描 Vault 笔记，自动添加 [[wikilinks]]，发现孤立笔记，增强知识图谱连接度
---

# /link - 自动链接器

扫描 Obsidian Vault 中的笔记，发现未链接的实体引用（ticker、公司名、概念），自动或半自动添加 `[[wikilinks]]`，增强知识图谱的连接度。

## Instructions for Claude

**实体字典构建：** 执行前先扫描 Vault 构建可链接实体字典：
1. 所有 `.md` 文件的文件名（去掉扩展名）→ 可链接目标
2. `研究/研究笔记/` 中的 TICKER（从文件名提取）
3. `研究/财报分析/` 子目录名
4. `写作/技术概念/` 中的概念名
5. `导航/MOC/` 中的主题名

**链接规则：**
- 只链接首次出现（每篇笔记中同一实体只链接第一次提及）
- 不在 frontmatter 中添加链接
- 不在代码块中添加链接
- 不在已有链接中嵌套链接（如 `[[NVDA]]` 内部不再链接）
- 不修改 URL 中的文本
- 保守策略：只链接确切匹配，不做模糊匹配

**操作模式：**
- **预览模式**（默认）：只报告发现，不修改文件
- **交互模式** (`--apply`)：逐个确认后修改
- **自动模式** (`--auto`)：自动应用所有高置信度链接

## When to Use This Skill

- 用户使用 `/link` 命令
- 用户说"帮我添加链接"、"连接笔记"
- 用户想提高 Vault 的知识图谱质量

## Core Workflow

```
输入：文件夹名或 --all
       ↓
[1] 构建实体字典
    • 扫描所有文件名 → 实体列表
    • 提取 tickers, 公司名, 概念名
    • 构建别名映射（NVDA → [[NVDA_2026-02-05|NVDA]], 英伟达 → [[NVDA_2026-02-05|英伟达]]）
       ↓
[2] 扫描目标文件
    • 读取每篇笔记正文
    • 查找未链接的实体提及
    • 记录：文件、行号、原文、建议链接
       ↓
[3] 输出报告（预览模式）
    • 按文件分组列出发现
    • 统计：可添加的链接数、孤立笔记数
       ↓
[4] 应用链接（--apply 或 --auto 模式）
    • 逐个或批量修改文件
    • 使用 Edit 工具精确替换
       ↓
[5] 报告结果
    • 已添加的链接数
    • 孤立笔记列表
    • 建议创建的新笔记
       ↓
[6] 整理建议（可选）
    • 对孤立/错位的笔记，建议移动目标
    • 用 mcp__obsidian__move-note 执行移动（自动更新 wikilinks）
    • 见下方 "MCP move-note 整理流程"
```

## Quick Start

```
/link                           # 预览全 Vault 的链接机会（不修改文件）
/link 信息源/播客                # 只扫描播客文件夹
/link 周会                       # 只扫描周会文件夹
/link --apply                   # 交互模式，逐个确认
/link --auto                    # 自动应用高置信度链接
/link orphans                   # 只列出孤立笔记
/link stats                     # Vault 链接统计
```

## 输出格式

### 预览模式输出（终端）

```
🔗 Link Opportunities Report
============================

📂 信息源/播客/ (12 files with opportunities)

  The Hidden Economics Powering AI.md:
    Line 26: "...marked by a 99% cost reduction..."
      → NVDA (mentioned in context of GPU) → [[NVDA_2026-02-05|NVDA]]
    Line 30: "...Google five and a half times..."
      → GOOGL → [[会议实录 2026-01-03|GOOGL]] (周会中有讨论)


  #407.拆解华为算力真相与中芯困局.md:
    Line 15: "...华为..." → 无匹配笔记（建议创建）
    Line 22: "...中芯国际..." → 无匹配笔记（建议创建）

📂 周会/ (8 files with opportunities)

  会议实录 2026-01-03.md:
    Line 48: "TSM" → [[研究/研究笔记/TSM]] (如果存在)
    Line 52: "美光（Micron）" → 无匹配笔记

────────────────────────────
📊 Summary:
  Files scanned: 150
  Link opportunities found: 87
  High confidence: 45 (auto-applicable)
  Medium confidence: 30 (need review)
  Low confidence: 12 (skipped)

  Orphan notes: 15 (no incoming/outgoing links)
  Suggested new notes: 8 (frequently mentioned, no note exists)
```

### 孤立笔记报告

```
🏝️ Orphan Notes (15)
====================

| 笔记 | 文件夹 | 创建日期 | 建议操作 |
|------|--------|----------|---------|
| Docker.md | 写作/技术概念 | 2026-02-05 | 添加到相关技术笔记 |
| 2026-01-23 - Daily Checklist.md | 收件箱 | 2026-01-23 | 🔀 移动到 归档/ |
| random note.md | 收件箱 | 2026-01-15 | 🔀 移动到 研究/研究笔记/ |
| ... | | | |

💡 Tip: 对标记 🔀 的笔记，运行 /link organize 可批量移动（MCP move-note 自动更新链接）
```

### Vault 链接统计

```
📊 Vault Link Stats
===================

| 文件夹 | 文件数 | 有出链 | 有入链 | 平均链接数 | 孤立 |
|--------|--------|--------|--------|-----------|------|
| 研究/研究笔记 | 1 | 1 | 0 | 5 | 0 |
| 周会 | 42 | 0 | 3 | 0 | 39 |
| 信息源/播客 | 58 | 0 | 0 | 0 | 58 |
| 收件箱 | 88 | 5 | 0 | 0.1 | 83 |
| 写作/技术概念 | 1 | 1 | 2 | 3 | 0 |
```

## Commands Reference

```bash
# 扫描
/link                          # 预览全 Vault（默认）
/link {folder}                 # 扫描指定文件夹
/link --all                    # 扫描全 Vault

# 应用
/link --apply                  # 交互模式（逐个确认）
/link --auto                   # 自动应用高置信度
/link {folder} --apply         # 对指定文件夹应用

# 分析
/link orphans                  # 列出孤立笔记
/link stats                    # Vault 链接统计
/link suggest                  # 建议创建的新笔记

# 整理（使用 MCP move-note，自动更新 wikilinks）
/link move {file} {dest}       # 移动单个笔记到目标文件夹
/link organize                 # 扫描收件箱，建议并移动到正确文件夹
/link organize --auto          # 自动移动高置信度分类
```

## Note 移动整理流程

**实现方式：** `shared.obsidian_utils.move_note()` 移动文件时自动扫描 Vault 更新所有指向该文件的 `[[wikilinks]]`。无需 MCP。

### `/link move {file} {dest}` — 单个笔记移动

```python
sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.obsidian_utils import move_note, search_vault

# [1] 确认源文件存在
results = search_vault(filename, search_type="filename")
# [2] 确认目标路径合理（属于 8 个顶级文件夹之一）
# [3] 向用户展示：源路径 → 目标路径，请求确认
# [4] 执行移动（自动更新 wikilinks）
result = move_note("收件箱/Docker学习笔记.md", "写作/技术概念/Docker学习笔记.md")
# [5] 报告结果
print(f"移动成功，更新了 {result['links_updated']} 个 wikilinks")
```

### `/link organize` — 批量收件箱整理

```
[1] 扫描收件箱（和其他杂乱文件夹）中的文件
       ↓
[2] 对每篇笔记分析内容，推断最佳目标文件夹：
    • 含 ticker/公司名 → 研究/研究笔记/
    • 含技术概念 → 写作/技术概念/
    • 含播客关键词 → 信息源/播客/
    • 含周会关键词 → 周会/
    • 无法分类 → 保留原位
       ↓
[3] 输出分类建议表（预览模式）
       ↓
[4] --auto 模式：自动移动高置信度项
    默认模式：逐个确认
       ↓
[5] 对每个确认的移动，调用 obsidian_utils.move_note()
       ↓
[6] 汇总报告：移动了 N 篇，跳过 M 篇，链接更新数
```

### 分类规则（目标文件夹映射）

| 内容特征 | 目标文件夹 |
|---------|-----------|
| 含 ticker 符号或公司名 | `研究/研究笔记/` |
| 含财报分析、earnings 关键词 | `研究/财报分析/{TICKER}/` |
| 含技术概念（Docker, API, LLM 等） | `写作/技术概念/` |
| 含播客来源标记 | `信息源/播客/` |
| 含微信公众号来源 | `信息源/微信公众号/` |
| 含周会日期格式 | `周会/` |
| 已处理完毕的旧笔记 | `归档/` |

### 注意事项（移动）

- **始终先预览**，不要未经确认就移动
- `move_note()` 会在目标已存在时抛出 `FileExistsError`（防止覆盖）
- 移动后建议运行 `/link stats` 验证链接健康度

## 别名映射

常见实体的别名映射（自动检测）：

| 实体 | 别名 |
|------|------|
| NVDA | Nvidia, NVIDIA, 英伟达 |
| GOOGL | Google, Alphabet, 谷歌 |
| MSFT | Microsoft, 微软 |
| UBER | Uber |
| TSM | TSMC, 台积电 |
| AAPL | Apple, 苹果 |

对于中文 ticker（如 600519.SH → 贵州茅台 → 茅台），也建立别名表。

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/moc` | link 发现的关系可以补充 MOC |
| `/podcast` | 处理后的播客笔记需要 link |
| `/learn` | 技术概念已有良好的链接模式，可作为范例 |
| `/vault-health` | link stats 是 vault health 的一部分 |

## Pipeline Tracking

**自动执行:** 每次 `/link` 成功为文件添加 wikilinks 后，更新 ingestion pipeline 的 `has_wikilinks` 阶段：
```python
try:
    from shared.task_manager import update_pipeline_stage_by_path
    for file_path in linked_files:
        update_pipeline_stage_by_path(str(file_path), has_wikilinks=True)
except ImportError:
    pass
```
这让 `/task pipeline` 的 "Links" 列准确反映实际链接状态。

## 注意事项

- 使用 Grep 和 Read 工具，不使用 bash grep
- **移动/重命名笔记时**，使用 `obsidian_utils.move_note()`（自动更新 wikilinks）
- 大 Vault 扫描可能需要较长时间，分批处理
- 保守策略：宁可漏掉也不要错误链接
- 不修改文件的其他内容，只添加 [[]] 括号
- 处理后建议运行 `/link stats` 验证效果
- 中英文混合内容都要处理
