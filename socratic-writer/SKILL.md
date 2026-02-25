---
name: socratic-writer
description: 苏格拉底式写作助手 - Grok 主导思维引擎，多AI协同(Gemini假设核查+GPT框架连接+Grok盲点扫描)，自动研究，输出到Obsidian。适用于任何需要深度思考的话题（投资、商业、技术、社会等）。
---

# Socratic Writer - 苏格拉底式写作助手

Grok 作为思维主引擎，通过尖锐提问、研究诊断、综合消化、论点评估，帮你把模糊的想法变成经得起考验的清晰论点。三个AI从"对抗辩论"转向"探索式协同"：Gemini核查假设、GPT连接框架、Grok扫描盲点。适用于任何话题——投资、商业决策、技术判断、社会议题。Claude 只做管道（调 API、传上下文、跑脚本）。

## Important Rules

- **MUST use Grok as primary thinking engine** — Grok runs socratic, diagnose, synthesize, and evaluate. Claude is pipeline only; never substitute Claude analysis for Grok.
- **NEVER skip the Socratic questioning phase** — Collect all 5 Grok questions and user answers before moving to research or debate. Skipping degrades output quality.
- **MUST complete research diagnosis before debate** — Run `grok_engine.py diagnose` first; debate.py needs the research context to run meaningful analysis.
- **NEVER summarize or condense AI model outputs** — Show full unabridged responses from Grok, Gemini, and GPT. Summarizing destroys the multi-AI value.
- **MUST verify all API keys before starting a session** — Check Grok, Gemini, and OpenAI keys are live before invoking any model. Never silently fall back to a single provider.
- **MUST include citations/sources in final export** — All factual claims from research phases must be traceable. Export to Obsidian must carry source references.
- **Iterate until score ≥ 7** — If `evaluate` scores < 7, loop back to synthesize. Never export a sub-7 draft without flagging it to the user.
- **Default to no-rebuttal mode** — `debate.py run` without `--with-rebuttal` saves ~106% cost. Only add rebuttal for high-stakes or highly contested topics.

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
[3] 四方并行分析 (debate.py run)
    • Gemini(假设核查) + GPT(框架连接) + Grok(盲点扫描) — 协同
    • Grok(魔鬼代言人) — 对抗你的论点
    • 可选: --with-rebuttal 启用交叉反驳 (+106% 成本)
    ↓
[3.5] 集体谬误检测 (自动)
    • 主题收敛度 > 80% → 注入元认知 prompt
    ↓
[4] Grok 综合消化 (3 个核心张力, temp=0.5)
    • 从 4 个分析文件提炼最关键矛盾
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
| **Grok** | 思维主引擎 + 盲点扫描仪 | 提问、诊断、扫描盲点(隐含假设/缺席利益相关者/遗漏变量/边界条件/Kill Criteria)、综合、评估 | — |
| **Grok** | 魔鬼代言人 | 针对**用户论点**的对抗挑战：核心反论点、致命弱点、反身性陷阱、历史类比打脸、对手最优策略 | 不与其他AI辩论 |
| **Gemini** | 假设核查员 | 可验证主张清单、假设分层、压力测试参数、数据缺口地图、历史基率、量化确信度 | 不提问、不综合 |
| **GPT** | 框架连接器 | 相关理论框架、现有研究对比、类似案例库、框架适用边界、概念精确化、创新点识别 | 不提问、不综合 |
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

# Step 6: 三方协同分析 (默认无反驳，节省 106% 成本)
python run.py debate.py run --session SESSION_ID
# 完整模式（含交叉反驳）:
# python run.py debate.py run --session SESSION_ID --with-rebuttal

# Step 7: Grok 综合消化
python run.py grok_engine.py synthesize --session SESSION_ID

# Step 8: 用户回应张力 → Grok 评估
python run.py grok_engine.py evaluate --session SESSION_ID --response "你的回应"

# Step 9: 导出
python run.py export.py obsidian --session SESSION_ID
```

## Commands Reference

See [`references/commands-reference.md`](references/commands-reference.md) for all CLI commands (grok_engine, session, debate, research, arbitrate, export, legacy).

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
│   ├── gemini.json         # Gemini 假设核查
│   ├── gpt.json            # GPT 框架连接
│   ├── grok.json           # Grok 盲点扫描
│   ├── grok_advocate.json  # Grok 魔鬼代言人（针对用户论点）
│   ├── gemini_rebuttal.json  # (opt-in: --with-rebuttal)
│   ├── gpt_rebuttal.json     # (opt-in: --with-rebuttal)
│   ├── grok_rebuttal.json    # (opt-in: --with-rebuttal)
│   └── decisions.json      # 仲裁决策
├── synthesis/              # Grok 综合分析
│   ├── grok_socratic.json  # 苏格拉底提问
│   ├── delusion_check.json # 集体谬误检测结果
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
| Blind spot scan | 0.7 | 创造性盲点发现 |
| Devil's advocate | 0.7 | 激进对抗，找最致命反论点 |
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
3. **用 `debate.py run` 跑协同分析** - 默认无反驳（省成本），仅在争议大的话题加 `--with-rebuttal`
4. **关注 synthesize 输出的 3 个张力** - 收敛度 > 80% 时会自动注入集体谬误检测
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
