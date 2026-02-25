# /link — Output Format Examples

Reference: sample terminal output for each mode. Do not modify — these are read-only examples.

---

## 预览模式输出（终端）

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

---

## 孤立笔记报告

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

---

## Vault 链接统计

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
