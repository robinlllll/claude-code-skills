---
name: vault-health
description: Vault 健康检查 - 扫描孤立笔记、断链、缺失 frontmatter、空文件，生成健康报告并自动修复
---

# /vault-health - Vault 健康检查

全面扫描 Obsidian Vault 的质量问题：孤立笔记、断链、缺失 frontmatter、空文件、重复内容，生成健康报告并提供自动修复。

## Instructions for Claude

**扫描范围：** `~/Documents/Obsidian Vault/` 下所有 `.md` 文件，排除：
- `.obsidian/` 目录
- `.stfolder/` 目录
- `.trash/` 目录

**检查项（按优先级排序）：**

### 1. 空文件与极短文件
- 文件大小 < 50 bytes（可能只有 frontmatter 没有正文）
- 只有标题没有内容

### 2. 缺失/不完整 Frontmatter
- 完全没有 frontmatter（没有 `---` 包裹的 YAML）
- 缺少关键字段（每种类型有不同要求）：
  - 收件箱: 需要 `date`, `processed`, `tickers`, `type`
  - 信息源/播客: 需要 `title`, `podcast`, `publish_date`, `status`
  - 周会: 无 frontmatter 要求（纯文本格式）
  - 研究/研究笔记: 需要 `ticker`, `date`, `type`
  - 所有文件: 推荐有 `created`, `tags`

### 3. 断链 (Broken Links)
- 扫描所有 `[[...]]` wikilinks
- 检查目标文件是否存在
- 区分：完全断链 vs 可能是别名

### 4. 孤立笔记 (Orphan Notes)
- 没有任何出站链接
- 没有任何入站链接
- 按文件夹统计孤立率

### 5. 重复内容
- 同名文件（不同文件夹）
- 高度相似的标题
- 完全相同的内容（hash 比较）

### 6. 陈旧笔记
- 超过 90 天未修改
- thesis 文件超过 30 天未更新（可能需要 review）
- 收件箱中 `processed: false` 超过 30 天

### 7. 格式问题
- frontmatter YAML 语法错误
- 异常大的文件（>100KB，可能需要拆分）
- 文件名含特殊字符（可能跨平台问题）

## When to Use This Skill

- 用户使用 `/vault-health` 命令
- 用户说"检查一下 vault 质量"
- 定期维护（建议每月运行一次）

## Core Workflow

```
输入：无参数（全 vault）或指定文件夹
       ↓
[1] 索引全 Vault
    • 列出所有 .md 文件
    • 读取 frontmatter
    • 提取所有 [[wikilinks]]
       ↓
[2] 执行检查
    • 空文件检测
    • Frontmatter 完整性
    • 链接有效性
    • 孤立笔记识别
    • 重复检测
    • 陈旧检测
       ↓
[3] 生成健康报告
    • 按严重程度排序
    • 按文件夹分组统计
    • 整体健康评分
       ↓
[4] 提供修复建议
    • 自动可修复项（--fix）
    • 需要人工判断项
       ↓
[5] 保存报告（可选）
    • ~/Documents/Obsidian Vault/vault-health-YYYY-MM-DD.md
```

## Quick Start

```
/vault-health                        # 完整健康检查（只报告）
/vault-health --fix                  # 检查并自动修复简单问题
/vault-health 信息源/播客             # 只检查播客文件夹
/vault-health --quick                # 快速检查（只看严重问题）
/vault-health frontmatter            # 只检查 frontmatter
/vault-health links                  # 只检查链接
```

## 输出格式

### 终端输出（主要报告）

```
🏥 Vault Health Report — YYYY-MM-DD
=====================================

Overall Score: 72/100 ⚠️

📊 Overview
───────────
Total files: 205
Total folders: 15
Total wikilinks: 234
Avg links per note: 1.1

🔴 Critical Issues (5)
───────────────────────

1. Empty files (3):
   - Untitled 1.base (~/root)
   - Untitled.base (~/root)
   - _summary.md (已删除的 Knowledge Base 遗留文件)

2. Broken wikilinks (2):
   - 写作/思考性文章/xxx.md → [[不存在的笔记]]
   - 研究/研究笔记/NVDA_2026-02-05.md → [[NVDA thesis]]

🟡 Warnings (18)
─────────────────

3. Missing frontmatter (8):
   - 周会/会议实录 2025-01-25.md (无 frontmatter)
   - 周会/会议实录 2025-02-01.md (无 frontmatter)
   - ... (6 more)

4. Stale inbox items (15):
   - 收件箱: 15 items with processed: false older than 14 days

5. Unprocessed podcasts (23):
   - 信息源/播客: 23 items with status: "未开始"

🟢 Suggestions (12)
────────────────────

6. Orphan notes (58):
   - 信息源/播客/ folder: 58/58 files are orphans (0% link density)
   - 周会/ folder: 39/42 files are orphans

7. Large files that may need splitting (2):
   - 周会/会议实录 2026-01-03.md (48KB)
   - 信息源/播客/某篇长文.md (35KB)

📁 Per-Folder Stats
────────────────────

| Folder | Files | Avg Size | Has FM | Has Links | Orphan % | Staleness |
|--------|-------|----------|--------|-----------|----------|-----------|
| 收件箱 | 88 | 1.2KB | 88/88 | 5/88 | 94% | 15 stale |
| 信息源/播客 | 58 | 8.5KB | 58/58 | 0/58 | 100% | 23 unproc |
| 周会 | 42 | 25KB | 0/42 | 3/42 | 93% | OK |
| 研究/财报分析 | 6 | 15KB | 6/6 | 6/6 | 0% | OK |
| 研究/研究笔记 | 1 | 12KB | 1/1 | 1/1 | 0% | OK |
| 写作/思考性文章 | 2 | 18KB | 2/2 | 2/2 | 0% | OK |
| 写作/技术概念 | 1 | 3KB | 1/1 | 1/1 | 0% | OK |

🔧 Auto-Fixable Issues (--fix)
───────────────────────────────
- Delete 2 empty .base files
- Add missing `created` field to 8 周会 files (from filename date)
- Standardize date format in 3 收件箱 files
- Fix 2 broken wikilinks (suggest closest match)

Run `/vault-health --fix` to apply auto-fixes.
```

### 保存的报告格式（Obsidian）

```markdown
---
created: YYYY-MM-DD
type: vault-health
score: 72
total_files: 205
critical: 5
warnings: 18
suggestions: 12
tags: [vault-health, maintenance]
---

# Vault Health Report — YYYY-MM-DD

[Same content as terminal output but in full Markdown format]
```

## --fix 自动修复范围

**会自动修复的（安全操作）：**
- 添加缺失的 `created` 字段（从文件名或文件系统时间推断）
- 删除空的 `.base` 文件
- 标准化日期格式到 `YYYY-MM-DD`
- 修复明显的 frontmatter YAML 语法错误

**不会自动修复的（需要用户确认）：**
- 删除任何有内容的文件
- 修改笔记正文
- 重命名文件
- 合并重复文件
- 修复断链（会建议但不自动修改）

## 健康评分算法

```
Score = 100 - penalties

Penalties:
- Empty file: -2 per file
- Broken wikilink: -3 per link
- Missing frontmatter: -1 per file
- Orphan note: -0.5 per note
- Stale inbox (>14 days): -0.5 per item
- Duplicate content: -2 per pair
- Format error: -1 per issue
```

## Commands Reference

```bash
/vault-health                     # 完整检查
/vault-health --fix               # 检查 + 自动修复
/vault-health --quick             # 快速检查（只看 critical）
/vault-health {folder}            # 检查指定文件夹
/vault-health frontmatter         # 只检查 frontmatter
/vault-health links               # 只检查链接
/vault-health orphans             # 只列孤立笔记
/vault-health --save              # 保存报告到 Vault
```

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/link` | vault-health 的 orphan 检测与 link 互补 |
| `/inbox` | vault-health 提示未处理的 inbox 项 |
| `/podcast` | vault-health 提示未处理的播客 |
| `/moc` | vault-health 建议为高频 ticker 创建 MOC |

## 注意事项

- 使用 Glob 扫描文件，Read 读取内容，Grep 搜索链接
- 大 Vault 完整扫描可能需要 1-2 分钟
- --quick 模式只检查 critical 级别，速度更快
- 不删除任何用户内容（除非 --fix 且是空文件）
- 报告中的文件路径使用相对于 Vault 根目录的路径
- 中英文文件名都要正确处理
