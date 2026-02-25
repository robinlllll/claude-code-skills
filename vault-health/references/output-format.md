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
