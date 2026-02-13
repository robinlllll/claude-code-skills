---
name: socratic-writer
description: 苏格拉底式写作助手 - Grok 主导思维引擎，多AI协同(Gemini量化+GPT定性+Grok逆向)，自动研究，输出到Obsidian。适用于任何需要深度思考的话题（投资、商业、技术、社会等）。
---

# Socratic Writer - 苏格拉底式写作助手

Grok 作为思维主引擎，通过尖锐提问、研究诊断、综合消化、论点评估，帮你把模糊的想法变成经得起考验的清晰论点。适用于任何话题——投资、商业决策、技术判断、社会议题。Claude 只做管道（调 API、传上下文、跑脚本）。

## When to Use This Skill

Trigger when user:
- 说"写文章"、"帮我写"、"想写一篇..."
- 提到"苏格拉底"或"问答式写作"
- 有一个初步想法需要深化和结构化
- 需要多AI协同来完善论点
- 使用 `/write` 或 `/socratic` 命令

## Core Workflow (Grok-Centric)

```
用户初始想法
    ↓
[1] Grok 苏格拉底提问 (5 个尖锐问题, temp=0.7)
    • 边界 / 假设 / 时间 / 反面 / 盲点
    ↓
[2] Grok 研究诊断 (结构化研究清单, temp=0.3)
    → 自动路由: local / NLM / 13F / web
    ↓
[3] 三方辩论 (debate.py run)
    • Phase 1: Gemini(量化) + GPT(定性) + Grok(逆向) 并行
    • Phase 2: 交叉反驳
    ↓
[4] Grok 综合消化 (3 个核心张力, temp=0.5)
    • 从 6 个挑战文件提炼最关键矛盾
    • 向作者提聚焦问题
    ↓
[5] 用户回应张力 → 论点 v2
    ↓
[6] Grok 评估 v1→v2 (temp=0.3)
    • score < 7 → 回到 [4] 迭代
    • score ≥ 7 → 导出
    ↓
[7] 导出到 Obsidian
```

## AI Role Assignment

| AI | Role | What It Does | What It Does NOT Do |
|----|------|-------------|---------------------|
| **Grok** | 思维主引擎 | 提问、诊断、挑战、综合、评估 | — |
| **Gemini** | 量化专家 | 数字验证、模型压测、基率 | 不提问、不综合 |
| **GPT** | 定性专家 | 竞争动态、叙事分析、行为偏差 | 不提问、不综合 |
| **Claude** | 管道工 | 调API、传上下文、跑脚本、展示结果 | 不分析、不判断 |

## Quick Start

### 1. 配置（首次使用）
```bash
# 设置 API keys
python ~/.claude/skills/socratic-writer/scripts/run.py config.py set grok_api_key YOUR_GROK_KEY
python ~/.claude/skills/socratic-writer/scripts/run.py config.py set-gemini-key YOUR_GEMINI_KEY
python ~/.claude/skills/socratic-writer/scripts/run.py config.py set openai_api_key YOUR_OPENAI_KEY
```

### 2. 完整流程（推荐）

```bash
# Step 1: 创建会话
python run.py session.py new --topic "你的初始想法"

# Step 2: Grok 生成 5 个提问
python run.py grok_engine.py socratic --session SESSION_ID

# Step 3: 用户回答（Claude 收集答案）
python run.py session.py add-dialogue --session ID --question "Q" --answer "A" --type "边界"
# ... 重复 5 次

# Step 4: Grok 研究诊断
python run.py grok_engine.py diagnose --session SESSION_ID

# Step 5: 自动执行研究
python run.py grok_engine.py research --session SESSION_ID

# Step 6: 三方辩论
python run.py debate.py run --session SESSION_ID

# Step 7: Grok 综合消化
python run.py grok_engine.py synthesize --session SESSION_ID

# Step 8: 用户回应张力 → Grok 评估
python run.py grok_engine.py evaluate --session SESSION_ID --response "你的回应"

# Step 9: 导出
python run.py export.py obsidian --session SESSION_ID
```

## Commands Reference

### Grok Engine (NEW - Primary)
```bash
grok_engine.py socratic  --session ID [--topic T]  # 5 个尖锐问题
grok_engine.py diagnose  --session ID               # 研究诊断
grok_engine.py research  --session ID               # 自动执行研究
grok_engine.py synthesize --session ID              # 综合消化 → 3 张力
grok_engine.py evaluate  --session ID --response T  # 评估 v1→v2
```

### Session Management
```bash
session.py new --topic "..."        # 新建会话
session.py list                     # 列出所有会话
session.py status                   # 当前会话状态
session.py resume --id ID           # 恢复会话
session.py close --id ID            # 关闭会话
```

### Parallel Debate
```bash
debate.py run --session ID           # Full: challenges + rebuttals
debate.py challenge --session ID     # Parallel challenges only
debate.py rebuttal --session ID      # Rebuttal round only
debate.py status --session ID        # Show debate status
```

### Research
```bash
research.py local --query "..."     # 本地文件搜索
research.py nlm --question "..."    # NotebookLM 查询
research.py web --query "..."       # 网络搜索（Claude 执行）
research.py summary --session ID    # 研究摘要
```

### Arbitration
```bash
arbitrate.py compare --session ID   # 对比所有AI意见
arbitrate.py decide --session ID --topic "主题" --decision "决定"
```

### Export
```bash
export.py obsidian --session ID     # 导出到 Obsidian
export.py markdown --session ID     # 导出为 Markdown
export.py json --session ID         # 导出原始数据
```

### Legacy (still available)
```bash
devil.py challenge --session ID     # Gemini 单独质疑
perspective.py challenge --session ID  # GPT 单独视角
```

## Data Structure

```
data/sessions/{session_id}/
├── state.json              # 会话状态
├── dialogue.json           # Q&A 历史
├── claims.json             # 主张台账
├── research/
│   ├── diagnosis.json      # Grok 研究诊断
│   ├── research_log.json   # 研究执行记录
│   └── research_execution.json  # 自动研究结果
├── challenges/
│   ├── gemini.json         # Gemini 量化挑战
│   ├── gpt.json            # GPT 定性挑战
│   ├── grok.json           # Grok 逆向挑战
│   ├── gemini_rebuttal.json
│   ├── gpt_rebuttal.json
│   ├── grok_rebuttal.json
│   └── decisions.json      # 仲裁决策
├── synthesis/              # Grok 综合分析
│   ├── grok_socratic.json  # 苏格拉底提问
│   ├── tensions.json       # 核心张力
│   ├── user_response.json  # 用户回应
│   └── evaluation.json     # v1→v2 评估
└── drafts/
```

## Grok Temperature Strategy

| Stage | Temp | Rationale |
|-------|------|-----------|
| Socratic questions | 0.7 | 发散性，问出意想不到的问题 |
| Research diagnosis | 0.3 | 精准判断，不瞎编研究任务 |
| Contrarian challenge | 0.7 | 创造性逆向叙事 |
| Meta-critique (rebuttal) | 0.5 | 平衡——尖锐但公正 |
| Synthesis | 0.5 | 准确提炼张力 + 洞察力 |
| Evaluation | 0.3 | 严谨评分 |

## Pre-Debate Research

Claude 管道在辩论前自动收集相关内部资料（基于话题类型）：

**投资话题：**
1. `Grep ~/Documents/Obsidian Vault/研究/ for TICKER`
2. `Read ~/PORTFOLIO/research/companies/{TICKER}/thesis.md`
3. NotebookLM query
4. `python shared/13f_query.py {TICKER}`
5. supply_chain.db

**其他话题：**
1. `Grep ~/Documents/Obsidian Vault/ for 关键词`
2. NotebookLM query（如有相关 notebook）
3. Web search

Grok 的 diagnose 阶段会自动判断需要哪些数据源。

## Best Practices

1. **初始想法不需要完整** - 一句话就够，Grok 的 5 个问题会帮你展开
2. **诚实回答** - 不知道就说不知道，Grok 会把它列入研究清单
3. **用 `debate.py run` 跑完整辩论** - 并行 + 交叉反驳效果远好于单独调用
4. **关注 synthesize 输出的 3 个张力** - 这是整个流程最高价值的环节
5. **迭代直到 score ≥ 7** - evaluate 评分 < 7 说明论点还有硬伤
6. **不要跳过研究诊断** - Grok 的 diagnose 会精确识别你需要补什么数据

## Troubleshooting

| 问题 | 解决方案 |
|------|----------|
| Grok API 失败 | 检查 key: `config.py show`，确认 grok_api_key 已设置 |
| Gemini API 失败 | 检查 key: `config.py set-gemini-key KEY` |
| GPT API 失败 | 检查 key: `config.py set openai_api_key KEY` |
| 研究诊断没输出 | 先跑 socratic + 收集至少 3 个 Q&A |
| synthesize 解析失败 | 先跑 debate.py run 生成挑战文件 |
