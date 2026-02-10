---
name: socratic-writer
description: 苏格拉底式写作助手 - 通过问答细化想法，多AI协同(Gemini挑战+GPT补充)，自动研究，输出到Obsidian。适用于投资思考、观点文章写作。
---

# Socratic Writer - 苏格拉底式写作助手

通过苏格拉底式问答帮你细化、深化想法，发现研究缺口，多AI协同提供质疑和补充，最终输出结构化文章到Obsidian。

## When to Use This Skill

Trigger when user:
- 说"写文章"、"帮我写"、"想写一篇..."
- 提到"苏格拉底"或"问答式写作"
- 有一个初步想法需要深化和结构化
- 需要多AI协同来完善论点
- 使用 `/write` 或 `/socratic` 命令

## 配置
- 研究偏好：`shared/research_preferences.yaml`（投资风格、写作格式、来源标签）
- 分析框架：`shared/analysis_framework.yaml`（9 维度定义）

## Core Workflow

```
用户初始想法
    ↓
[1] Claude 苏格拉底式提问 (6类问题循环)
    ↓
[2] 识别研究缺口 → 自动研究
    • 网络搜索 (WebSearch)
    • 本地文件 (Grep/Read)
    ↓
[3] 多AI协同 (两种模式)
    ┌─ [推荐] debate.py run → 并行辩论 + 交叉反驳
    │   • Phase 1: Gemini(量化) + GPT(定性) 并行挑战
    │   • Phase 2: 交叉反驳 — 各自回应对方的挑战
    │   • Auto: 自动检测 ticker → 建议本地研究
    └─ [原始] devil.py + perspective.py 单独调用
    ↓
[4] 用户回应挑战 → 迭代深化
    ↓
[5] 输出到 Obsidian
    • 结构化文章
    • 研究笔记
    • 反论点记录（含反驳轮）
```

## Quick Start

### 1. 配置（首次使用）
```bash
# 设置 Gemini API key
python ~/.claude/skills/socratic-writer/scripts/run.py config.py set-gemini-key YOUR_API_KEY

# 配置 Obsidian vault 路径（已默认设置）
python ~/.claude/skills/socratic-writer/scripts/run.py config.py set-obsidian-path "C:\Users\thisi\Documents\Obsidian Vault"
```

### 2. 开始写作会话
```bash
# 创建新会话
python ~/.claude/skills/socratic-writer/scripts/run.py session.py new --topic "你的初始想法"

# 查看当前会话
python ~/.claude/skills/socratic-writer/scripts/run.py session.py status
```

### 3. 问答循环（Claude 主导）

Claude 会依次使用6类苏格拉底问题来深化你的想法：

| 问题类型 | 目的 | 示例 |
|----------|------|------|
| **澄清** | 明确概念 | "你说的「价值」具体指什么？" |
| **假设** | 暴露前提 | "这个观点基于什么假设？" |
| **证据** | 要求支撑 | "有什么数据支持这个判断？" |
| **反驳** | 压力测试 | "如果有人说「...」你怎么回应？" |
| **推论** | 延伸思考 | "如果这成立，会有什么推论？" |
| **视角** | 换位思考 | "从空头角度看，这个问题如何？" |

### 4. 触发研究

当发现信息缺口时：
```bash
# 网络搜索（Claude 自动调用 WebSearch）

# 搜索本地文件
python ~/.claude/skills/socratic-writer/scripts/run.py research.py local --query "关键词"
```

### 5. 多AI协同

```bash
# [推荐] 并行辩论 - Gemini(量化) + GPT(定性) 同时挑战，然后交叉反驳
python ~/.claude/skills/socratic-writer/scripts/run.py debate.py run --session SESSION_ID

# 只跑并行挑战（不含反驳轮）
python ~/.claude/skills/socratic-writer/scripts/run.py debate.py challenge --session SESSION_ID

# 单独跑反驳轮（需要先有挑战结果）
python ~/.claude/skills/socratic-writer/scripts/run.py debate.py rebuttal --session SESSION_ID

# Gemini 魔鬼代言人 - 通用质疑 (原始单独模式，仍然可用)
python ~/.claude/skills/socratic-writer/scripts/run.py devil.py challenge --session SESSION_ID

# GPT 补充视角 - 通用视角 (原始单独模式，仍然可用)
python ~/.claude/skills/socratic-writer/scripts/run.py perspective.py challenge --session SESSION_ID

# 手动模式 (fallback)
python ~/.claude/skills/socratic-writer/scripts/run.py perspective.py prompt --session SESSION_ID
python ~/.claude/skills/socratic-writer/scripts/run.py perspective.py save --session SESSION_ID --response "回复内容"
```

### 6. 导出到 Obsidian

```bash
# 导出完整文章
python ~/.claude/skills/socratic-writer/scripts/run.py export.py obsidian --session SESSION_ID

# 导出选项
--include-research    # 包含研究笔记
--include-challenges  # 包含AI挑战记录
--include-dialogue    # 包含问答过程
```

## Commands Reference

### Session Management
```bash
session.py new --topic "..."        # 新建会话
session.py list                     # 列出所有会话
session.py status                   # 当前会话状态
session.py resume --id ID           # 恢复会话
session.py close --id ID            # 关闭会话
```

### Research
```bash
research.py local --query "..."     # 本地文件搜索
research.py web --query "..."       # 网络搜索
research.py summary --session ID    # 研究摘要
```

### Parallel Debate (Recommended)
```bash
debate.py run --session ID           # Full debate: parallel challenges + rebuttal round
debate.py challenge --session ID     # Parallel challenges only (Gemini quantitative + GPT qualitative)
debate.py rebuttal --session ID      # Rebuttal round (each AI responds to the other)
debate.py status --session ID        # Show debate progress
```

**Debate flow:**
```
[1] debate.py challenge → Gemini(量化) + GPT(定性) 并行挑战
    ↓
[2] debate.py rebuttal  → 交叉反驳：
    • Gemini 回应 GPT 的定性挑战："哪些可以量化验证？"
    • GPT 回应 Gemini 的量化挑战："哪些数字背后有定性问题？"
    ↓
[3] Auto-research suggestions → 自动检测挑战中提到的 ticker，建议本地研究
```

**Model IDs:**

| Role | Model ID | Focus |
|------|----------|-------|
| Orchestrator | `claude-opus-4-6` | Socratic questioning, dialogue management |
| Devil's Advocate | `gemini-3-pro-preview` | 量化挑战 — 数字验证、DCF假设、市场规模、概率校准 |
| Perspective | `gpt-5.2-chat-latest` | 定性挑战 — 竞争动态、管理层质量、叙事一致性、行为偏差 |

**Rebuttal outputs saved to:**
- `challenges/gemini_rebuttal.json` — Gemini 对 GPT 定性挑战的量化回应
- `challenges/gpt_rebuttal.json` — GPT 对 Gemini 量化挑战的定性回应

### Multi-AI Collaboration (Individual Commands)
```bash
# Gemini (全自动 API 调用 — 通用模式)
devil.py challenge --session ID     # Gemini 质疑 (generic prompt)
devil.py respond --text "..."       # 记录你的回应

# GPT (全自动 API 调用 — 通用模式)
perspective.py challenge --session ID                 # OpenAI API 补充视角
perspective.py prompt --session ID                    # 手动 fallback: 生成 prompt
perspective.py save --session ID --response "..."     # 手动 fallback: 保存回复
```

### Claims Ledger (主张台账)
```bash
claims.py add --session ID --text "主张内容"   # 添加主张
claims.py list --session ID [--status X]       # 列出主张
claims.py show --session ID --id C1            # 查看主张详情
claims.py update --session ID --id C1 --status supported  # 更新状态
claims.py link --session ID --id C1 --type support --source S1 --text "证据"  # 关联证据

# 主张状态: unverified(待验证) | supported(已支持) | disputed(有争议) | abandoned(已放弃)
```

### Arbitration (仲裁机制)
```bash
arbitrate.py compare --session ID   # 对比所有AI意见
arbitrate.py table --session ID     # 生成Markdown对比表
arbitrate.py decide --session ID --topic "主题" --decision "决定" [--reasoning "理由"]
arbitrate.py decisions --session ID # 列出所有决策
```

### Export
```bash
export.py obsidian --session ID     # 导出到 Obsidian
export.py markdown --session ID     # 导出为 Markdown
export.py json --session ID         # 导出原始数据
```

### Configuration
```bash
config.py show                      # 显示配置
config.py set-gemini-key KEY        # 设置 Gemini API
config.py set-obsidian-path PATH    # 设置 Obsidian 路径
```

## Data Structure

```
data/sessions/{session_id}/
├── state.json              # 会话状态和元数据
├── dialogue.json           # 问答历史
│   └── [{ question, answer, type, timestamp }]
├── claims.json             # 主张台账
│   └── [{ id, text, status, evidence[], notes[] }]
├── research/               # 研究笔记
│   ├── research_log.json   # 研究记录
│   └── notes.md            # 整理后的研究笔记
├── challenges/             # AI 挑战
│   ├── gemini.json         # Gemini 质疑记录 (quantitative in debate mode)
│   ├── gpt.json            # GPT 补充记录 (qualitative in debate mode)
│   ├── gemini_rebuttal.json  # Gemini 对 GPT 定性挑战的反驳
│   ├── gpt_rebuttal.json     # GPT 对 Gemini 量化挑战的反驳
│   └── decisions.json      # 用户仲裁决策
└── drafts/                 # 文章草稿
    ├── v1.md
    └── v2.md
```

### Claims Status Flow

```
unverified (待验证)
    │
    ├──[找到支持证据]──→ supported (已支持)
    │
    ├──[找到反驳证据]──→ disputed (有争议)
    │                        │
    │                        └──[解决争议]──→ supported 或 abandoned
    │
    └──[决定不用]──→ abandoned (已放弃)
```

## Obsidian Output Format

```markdown
---
created: 2026-02-01
type: thought-piece
status: draft
tags: [投资, 观点]
---

# 文章标题

## 核心观点
...

## 论证
...

## 反论点与回应
| 挑战 | 来源 | 我的回应 |
|------|------|----------|
| ... | Gemini | ... |

## 研究笔记
...

## 问答过程
<details>
<summary>展开查看</summary>
...
</details>
```

## Pre-Debate Research (Grounded in YOUR Data)

When the writing topic involves a specific ticker or company, Claude should gather internal evidence BEFORE starting the multi-AI debate. This ensures the Socratic dialogue and challenges are grounded in the user's own research, not just model training data.

**Order: Research → THEN Debate**

### 1. Knowledge Base Search
```bash
# Search Obsidian vault for existing analysis
Grep ~/Documents/Obsidian Vault/研究/研究笔记/ for TICKER
Read ~/PORTFOLIO/research/companies/{TICKER}/thesis.md (if exists)
```
Feed findings to Claude as grounding context for Socratic questions.

### 2. NotebookLM Query (if relevant notebook exists)
```bash
# Check if a notebook is registered for this ticker
cd ~/.claude/skills && python shared/notebooklm_sync.py status

# If registered, query for evidence
cd ~/.claude/skills/notebooklm && python scripts/run.py ask_question.py \
  --notebook-id {ID} \
  --question "What evidence supports/contradicts: {user's thesis}?"
```
Feed citation-backed evidence to Gemini devil's advocate — makes challenges much sharper.

### 3. Supply Chain Context (if company-related)
```bash
# Check supply chain database for cross-references
cd ~/.claude/skills && python -c "
import sqlite3
from pathlib import Path
db = Path.home() / '.claude/skills/supply-chain/data/supply_chain.db'
if db.exists():
    conn = sqlite3.connect(str(db))
    rows = conn.execute('SELECT * FROM mentions WHERE mentioned_ticker = ? ORDER BY date', ('{TICKER}',)).fetchall()
    for r in rows: print(r)
    conn.close()
"
```
Feed supply chain signals to the perspective model for an angle the user may not have considered.

### 4. 13F Institutional Activity
```bash
cd ~/.claude/skills && python shared/13f_query.py {TICKER}
```
Smart money positioning can inform both bull and bear cases in the debate.

### 5. Framework Coverage (Optional Reference)
```bash
cd ~/.claude/skills && python shared/framework_coverage.py scan {TICKER} --format brief
```
- This is **supplementary context only** — do NOT let it drive the debate direction
- The Socratic dialogue should remain free-form, following wherever the argument leads
- If a coverage gap happens to overlap with a natural debate thread, mention it as an aside (e.g., "incidentally, your S5 management research is thin")
- Never restructure the debate around framework gaps — that's what `/research --coverage` is for

**Key principle:** The multi-AI debate (Gemini challenge + GPT perspective) becomes dramatically more useful when grounded in the user's own accumulated research rather than generic model knowledge. The debate itself should be driven by the strength of the argument, not a checklist.

## Integration with Existing Skills

- **Thesis Manager**: 如果是投资相关，可链接到 thesis
- **NotebookLM**: Pre-debate research queries against ticker notebooks
- **Supply Chain**: Cross-reference mentions from earnings transcripts
- **13F Query**: Institutional holdings context for investment topics
- **Knowledge Base**: Existing research and analysis as debate foundation

## Agent Teams Mode (Experimental)

对于投资相关主题，Agent Teams 将 pre-debate research 和 multi-AI debate 从串行变为真正并行 + 实时对抗。

### 启用条件
- 环境变量 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 已设置
- 用户使用 `/write --team` 参数
- 或主题明确涉及投资 ticker，且 Claude 判断多角度辩论有价值

### 团队结构

```
Lead Agent (Opus) — 苏格拉底主持人
  │  职责: 提问、仲裁、识别共识与分歧、生成最终文章
  │
  ├── Teammate "Researcher" (Sonnet)
  │   → 并行执行全部 Pre-Debate Research:
  │     • KB search (Obsidian Vault)
  │     • NotebookLM query (if notebook registered)
  │     • Supply Chain DB query
  │     • 13F institutional activity
  │     • Existing thesis reading
  │   → 输出: 结构化 evidence brief，发送给所有其他 teammates
  │   → 完成后自动终止（只需做一次）
  │
  ├── Teammate "Devil's Advocate" (Sonnet)
  │   → 角色: 魔鬼代言人（替代 Gemini API 调用）
  │   → 收到 Researcher 的 evidence brief 后开始工作
  │   → 职责: 找逻辑漏洞、挑战假设、stress-test 论点
  │   → 可直接与 Perspective 对话（互相看到对方的挑战）
  │
  ├── Teammate "Perspective" (Sonnet)
  │   → 角色: 补充视角（替代 ChatGPT 手动模式）
  │   → 收到 Researcher 的 evidence brief 后开始工作
  │   → 职责: 发现盲点、提供 user 没考虑的角度
  │   → 可直接与 Devil's Advocate 对话（形成真正的辩论）
  │
  └── [Optional] Teammate "Fact Checker" (Sonnet)
      → 仅在 claims ledger 有 ≥5 unverified claims 时 spawn
      → 职责: 验证具体数据点（价格、日期、财务数据）
      → 输出: claims 状态更新 (supported/disputed)
```

### vs 单 Agent 模式的关键差异

| 维度 | 单 Agent 模式 | Agent Teams 模式 |
|------|-------------|-----------------|
| Pre-debate research | 串行: KB → NLM → Supply Chain → 13F | Researcher 一个 teammate 全部并行 |
| Gemini 质疑 | API call → 等回复 → 记录 | Devil's Advocate teammate 持续参与 |
| ChatGPT 补充 | 手动复制 prompt → 粘贴回复 | Perspective teammate 全自动 |
| 多AI对抗 | 轮流发言（A→B→A→B） | **实时对话**（Devil's Advocate ↔ Perspective 直接辩论） |
| 事实核查 | Claude 自己判断 | 独立 Fact Checker 验证 |
| 用户参与 | 每轮都需要回应 | Lead 汇总后才找用户做关键决策 |

### 工作流程（Team 模式）

```
用户初始想法
    ↓
[1] Lead 分析主题，spawn Researcher
    ↓
[2] Researcher 并行查 5 个数据源 → 输出 evidence brief
    → brief 广播给 Devil's Advocate + Perspective
    → Researcher 退出
    ↓
[3] Devil's Advocate + Perspective 同时开始工作
    → 各自基于 evidence brief 形成观点
    → 互相直接对话 2-3 轮（真正辩论，非轮流独白）
    ↓
[4] Lead 收集双方论点 → 苏格拉底式提问给用户
    → "Devil's Advocate 认为 X 有问题，Perspective 认为 Y 是盲点"
    → "你怎么看？有哪些是你认同的？"
    ↓
[5] 用户回应 → Lead 判断是否需要第二轮辩论
    → 如需要 → Devil's Advocate + Perspective 再辩一轮
    → 如不需要 → 进入写作
    ↓
[6] Lead 综合所有材料 → 生成结构化文章 → 导出 Obsidian
```

### 成本对比

| 模式 | 适用场景 | 预计 Token |
|------|---------|-----------|
| 单 Agent（默认） | 快速想法记录、非投资话题 | ~20-40K |
| Agent Teams (`--team`) | 投资观点深度打磨、需多角度验证 | ~80-120K |

**核心优势：** 单 Agent 模式下 Gemini 和 ChatGPT 是"被动回应"（你问它答）。Agent Teams 模式下 Devil's Advocate 和 Perspective 是"主动辩论"（互相挑战），产出质量显著不同。

### Commands

```bash
/write --team "为什么 PM 的 ZYN 增长故事被低估了"    # Agent Teams 辩论
/write --team --ticker PM                            # 自动拉取 PM 相关研究
/socratic --team "AI 硬件链的下一个瓶颈在哪里"       # 非 ticker 主题也适用
```

## Best Practices

1. **初始想法不需要完整** - 一句话就够，问答会帮你展开
2. **诚实回答问题** - 不知道就说不知道，会触发研究
3. **用 `debate.py run` 替代单独调用** - 并行辩论 + 交叉反驳比单独调用效果显著更好，因为两个AI会互相检验对方的盲点
4. **关注反驳轮的交叉发现** - 反驳轮经常揭示初始挑战中遗漏的角度：Gemini 会量化 GPT 的定性风险，GPT 会质疑 Gemini 数字背后的定性假设
5. **跟进 auto-research 建议** - 当挑战提到具体 ticker 时，系统会自动建议本地研究命令
6. **迭代而非一次成文** - 通常需要2-3轮深化
7. **研究记录保留** - 导出时包含研究笔记，便于日后回溯

## Troubleshooting

| 问题 | 解决方案 |
|------|----------|
| Gemini API 失败 | 检查 API key: `config.py show` |
| Obsidian 导出路径错误 | 更新路径: `config.py set-obsidian-path` |
