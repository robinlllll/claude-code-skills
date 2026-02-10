# /today — 晨间综合简报

每日一键获取"今天我需要知道的一切"。

## 使用方式

```bash
/today                  # 完整晨间简报（含市场数据）
/today --quick          # 快速模式（跳过市场数据拉取）
```

## 执行步骤

1. 运行晨间简报脚本：
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/morning_brief.py
   ```
   或快速模式：
   ```bash
   cd ~/.claude/skills && /c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe shared/morning_brief.py --quick
   ```

2. 脚本自动聚合：
   - 📊 持仓价格变动（yfinance）
   - ✅ 今日任务计划（task_manager）
   - 📌 未解决研究问题（open_questions）
   - 📥 收件箱新笔记
   - ⚠️ 过期 thesis 提醒（>30天未更新）
   - 📚 知识库昨日新增
   - 📅 13F 截止日提醒

3. 展示在终端 + 保存到 `收件箱/{date} - 晨间简报.md`

4. 对异动 ticker（>3%），建议 WebSearch 查新闻

## 输出路径

`收件箱/YYYY-MM-DD - 晨间简报.md`

## 与其他 Skills 的关系

| Skill | 关系 |
|-------|------|
| `/task` | 读取今日任务计划 |
| `/research` | 异动 ticker 建议深入研究 |
| `/thesis` | 检测过期 thesis |
| `/kb-add` | 显示知识库新增统计 |

## 数据来源

- `shared/market_snapshot.py` / yfinance — 市场数据
- `shared/task_manager.py` — 任务 + open questions
- `PORTFOLIO/research/companies/` — thesis 文件
- `收件箱/` — Obsidian inbox
- `shared/task_manager.py` knowledge_index — KB 统计
