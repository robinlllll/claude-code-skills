# Podcast Notion Sync Reference

## Notion Database Info

- **Database ID:** `2e80e07f-cb27-8192-93fa-d81d489145a8`
- **Data Source URL:** `collection://2e80e07f-cb27-81b8-b2e3-000be8b0c4a1`
- **View URL (按发布时间倒序):** `view://2e80e07f-cb27-81e8-8416-000c627703d6`

## Database Schema

| Column | Type | 说明 |
|--------|------|------|
| Episode | title | Episode 标题 |
| Publish Time | date | 发布日期 |
| Podcast | text | 播客节目名 |
| Link | url | Podwise 链接 (`https://podwise.ai/dashboard/episodes/{ID}`) |
| 状态 | status | `未开始` / `进行中` / `完成` |

## Sync Workflow

```
/podcast sync
       ↓
[1] 查询 Notion Database (notion-query-database-view → Podwise view)
       ↓
[2] 扫描 信息源/播客/ 已有 .md 文件，从 frontmatter 提取 link 字段构建去重 Set
       ↓
[3] 去重：用 Podwise Link URL 精确匹配（全局唯一 ID）。Fallback: 标题模糊匹配
       ↓
[4] notion-fetch 获取新 episode 完整页面内容（Summary/Takeaways/Q&A/Transcript）
       ↓
[5] 创建 Obsidian 文件：信息源/播客/{Episode Title}.md（清理非法文件名字符）
       ↓
[6] 输出同步结果（新增/跳过/失败数量）
```

## 新文件 Frontmatter 模板

```yaml
---
title: "{Episode Title}"
podcast: "{Podcast Name}"
link: "{Podwise URL}"
publish_date: YYYY-MM-DD
status: "未开始"
created: YYYY-MM-DD
notion_id: "{Notion Page ID}"
tags: [podcast, podwise]
---
```

## 注意事项
- Notion MCP 工具：`notion-query-database-view` 查询，`notion-fetch` 获取内容
- 单向同步（Notion → Obsidian），不修改 Notion
- 幂等：多次运行不创建重复文件
- 标题冲突时文件名后加 `_2`
