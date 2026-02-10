# /kb - 知识库管理

> ⚠️ **Deprecated** — 使用 `/research TICKER` 代替。原 Knowledge Base 文件夹已合并到 `研究/` 目录。

研究资料的统一管理入口：添加、检索、整理。

## 使用方式

```
/kb add FILE                        # 添加文件到知识库
/kb add URL                         # 添加网页/文章
/kb search "关键词"                  # 搜索知识库
/kb list TICKER                     # 列出某公司相关资料
/kb summary TICKER                  # 生成公司资料摘要
```

## 示例

```
/kb add ~/Downloads/研报_NVDA.pdf   # 添加研报
/kb add https://mp.weixin.qq.com/s/xxx  # 添加微信文章（自动调用 /wechat-hao）
/kb search "AI 芯片"                # 搜索相关资料
/kb list NVDA                       # 列出 NVDA 相关资料
/kb summary NVDA                    # 生成 NVDA 资料摘要
```

## 知识库结构

```
~/Documents/Obsidian Vault/
├── 收件箱/                    # 新导入的文章（/wechat-hao 输出）
├── 研究/研究笔记/              # 研究笔记（/research 输出）
├── 写作/技术概念/              # 技术学习笔记（/learn 输出）

~/PORTFOLIO/portfolio_monitor/research/
└── companies/{TICKER}/        # 投资相关文档
    ├── thesis.md              # 投资论点
    └── notes/                 # 研究笔记
```

## /kb add 流程

### 添加文件

1. **检测文件类型**
   - PDF → 使用 marker 转 Markdown
   - Word → 使用 pandoc 转 Markdown
   - Markdown/TXT → 直接处理

2. **提取元数据**
   - 标题、日期、来源
   - 相关 TICKER（从内容中提取）
   - 文档类型（研报/纪要/新闻/其他）

3. **生成摘要**
   - 3-5 句话核心内容
   - 关键数据点
   - 主要结论

4. **归档**
   - 按公司/主题分类
   - 重命名: `{类型}_{日期}_{标题}.md`
   - 更新 `_index.md`

5. **输出确认**
   ```
   ✅ 已添加到知识库
   📁 路径: 研究/NVDA/研报_20260205.md
   📝 摘要: ...
   🏷️ 标签: NVDA, AI芯片, 数据中心
   ```

### 添加 URL

- 微信文章 → 自动调用 `/wechat-hao`
- 其他网页 → 使用 WebFetch 抓取，转 Markdown

## /kb search 流程

1. **搜索范围**
   - 收件箱/ 目录
   - 研究/研究笔记/ 目录
   - PORTFOLIO research/ 目录

2. **搜索方式**
   - 文件名匹配
   - 内容全文搜索
   - 标签匹配

3. **输出格式**
   ```
   🔍 搜索结果: "AI 芯片" (共 5 条)

   1. [研报] NVDA Q4 展望 (2026-01-15)
      路径: 研究/NVDA/研报_20260115.md
      摘要: ...

   2. [文章] AI 芯片竞争格局分析 (2026-01-20)
      路径: 收件箱/2026-01-20_xxx.md
      摘要: ...
   ```

## /kb summary 流程

1. **收集资料**
   - 该公司所有研报、纪要、文章
   - 现有 thesis.md
   - 相关 Research Notes

2. **生成摘要**
   - 公司基本面概览
   - 关键数据点汇总
   - 主要观点/结论
   - 最近更新时间

3. **保存**
   - 路径: `研究/{TICKER}/_summary.md`
   - 同时在终端输出

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/wechat-hao` | 微信文章自动进入知识库 |
| `/research` | 研究时检索知识库 |
| `/thesis` | thesis 文件与知识库关联 |
| `/notebooklm` | 可将知识库上传到 NotebookLM |
| `/organizer-transcript` | 整理后的 transcript 进入知识库 |

## 依赖工具

| 工具 | 用途 | 安装 |
|------|------|------|
| marker | PDF → Markdown | `pip install marker-pdf` |
| pandoc | Word/其他 → Markdown | `choco install pandoc` |

## 注意事项

- PDF 转换可能丢失格式，建议检查
- 大文件（>50页）建议拆分
- 定期运行 `/kb summary` 更新摘要
