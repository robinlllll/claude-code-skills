# /kb-add — 知识库文档入库

将任意格式的研究资料一键导入知识库：提取文本、识别 ticker、标记分析维度、生成摘要、归档到 Obsidian。

## 使用方式

```
/kb-add FILE                    # 导入本地文件（PDF/Word/MD/TXT）
/kb-add URL                     # 导入网页文章
/kb-add search "关键词"          # 搜索知识库索引
/kb-add search --ticker TICKER  # 搜索特定 ticker 的资料
/kb-add stats [TICKER]          # 查看索引统计
```

## 配置
- 研究偏好：`shared/research_preferences.yaml`
- 分析框架：`shared/analysis_framework.yaml`

## 执行步骤（FILE）

1. 运行入库脚本：
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/kb_ingestion.py ingest "FILE_PATH" --org "来源机构" --author "作者"
   ```
2. 展示处理结果：标题、ticker、摘要、归档路径
3. 建议后续操作：
   - `/research TICKER` — 整合新资料进行研究
   - `/link 研究/研报摘要/` — 扫描新文件添加 wikilinks
   - `/thesis TICKER` — 如果资料与现有持仓相关

## 执行步骤（URL）

1. 判断 URL 类型：
   - 微信文章 → 提示使用 `/wechat-hao`
   - Substack → 提示使用 substack_fetcher
   - 其他 → 运行：
     ```bash
     cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/kb_ingestion.py url "URL"
     ```

## 执行步骤（search / stats）

```bash
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/kb_ingestion.py search "关键词"
cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/kb_ingestion.py stats TICKER
```

## 输出路径

`研究/研报摘要/{date} - {source_type}_{title}.md`

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/research` | 研究时自动检索 knowledge_index |
| `/link` | 入库后建议运行 wikilink 扫描 |
| `/thesis` | 资料与持仓相关时更新 thesis |
| `/notebooklm` | 如果 ticker 有注册 notebook，自动同步 |
| `/wechat-hao` | 微信 URL 路由到专用 skill |

## 依赖

- `shared/kb_ingestion.py` — 入库核心逻辑
- `shared/ticker_detector.py` — Ticker 检测
- `shared/framework_tagger.py` — 框架维度标记
- `shared/task_manager.py` — knowledge_index 表
- `pdfplumber` — PDF 文本提取
- `trafilatura` — 网页文本提取（URL 模式）
- `google.genai` — Gemini 摘要生成（可选，失败时 fallback）
