# Commands Reference — socratic-writer

## Grok Engine (Primary)
```bash
grok_engine.py socratic  --session ID [--topic T]  # 5 个尖锐问题
grok_engine.py diagnose  --session ID               # 研究诊断
grok_engine.py research  --session ID               # 自动执行研究
grok_engine.py synthesize --session ID              # 综合消化 → 3 张力
grok_engine.py evaluate  --session ID --response T  # 评估 v1→v2
```

## Session Management
```bash
session.py new --topic "..."        # 新建会话
session.py list                     # 列出所有会话
session.py status                   # 当前会话状态
session.py resume --id ID           # 恢复会话
session.py close --id ID            # 关闭会话
```

## Parallel Debate
```bash
debate.py run --session ID                    # 默认: 三方协同分析（无反驳）
debate.py run --session ID --with-rebuttal    # 完整模式（+106% 成本）
debate.py challenge --session ID              # 并行分析 only
debate.py rebuttal --session ID               # 反驳 round only
debate.py status --session ID                 # Show debate status
```

## Research
```bash
research.py local --query "..."     # 本地文件搜索
research.py nlm --question "..."    # NotebookLM 查询
research.py web --query "..."       # 网络搜索（Claude 执行）
research.py summary --session ID    # 研究摘要
```

## Arbitration
```bash
arbitrate.py compare --session ID   # 对比所有AI意见
arbitrate.py decide --session ID --topic "主题" --decision "决定"
```

## Export
```bash
export.py obsidian --session ID     # 导出到 Obsidian
export.py markdown --session ID     # 导出为 Markdown
export.py json --session ID         # 导出原始数据
```

## Legacy (still available)
```bash
devil.py challenge --session ID     # Gemini 单独质疑
perspective.py challenge --session ID  # GPT 单独视角
```
