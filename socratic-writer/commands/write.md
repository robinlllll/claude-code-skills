---
name: write
description: Start a Socratic writing session to develop and refine your ideas through guided questioning
---

# Socratic Writer Session

User wants to start a writing session. Follow this workflow:

## Step 1: Get the Initial Idea

If user provided a topic, use it. Otherwise ask:
"你想写什么？可以是一个初步的想法、一个问题、或者一个观点。"

## Step 2: Create Session

```bash
python ~/.claude/skills/socratic-writer/scripts/run.py session.py new --topic "USER_TOPIC"
```

## Step 3: Socratic Questioning (Adaptive Depth)

### Question Types
Use 6 types of questions, but NOT in rigid rotation — adapt to the conversation:

1. **Clarification** (澄清): Define key terms
2. **Assumption** (假设): Expose hidden premises
3. **Evidence** (证据): Require supporting data
4. **Counter** (反驳): Pressure test with opposition
5. **Implication** (推论): Explore consequences
6. **Perspective** (视角): Consider other viewpoints

### Adaptive Depth Protocol

**不要机械轮转6种问题类型。** 你必须判断哪些议题是核心支撑点，值得深挖。

After each user answer, make a judgment:
- **浅层回答**（模糊、缺乏具体性、依赖直觉）→ 必须追问，用同类型或升级类型再问 1-2 轮
- **深层回答**（有具体数据、清晰逻辑链、承认了局限性）→ 可以转下一个类型
- **核心主张**（用户论点的关键支柱）→ 至少追问 2-3 轮，从不同角度穿透

**深度信号（需要追问）：**
- 用户给出的理由只有一个 → 追问"还有其他理由吗？如果这个理由不成立呢？"
- 用户引用数据但未说明来源 → 追问数据的可靠性和时间范围
- 用户说"我觉得"、"应该是"、"一般来说" → 追问具体证据
- 用户跳过了因果链的中间步骤 → 追问"A 怎么导致 B？中间经历了什么？"
- 用户的回答与之前的回答存在潜在矛盾 → 指出矛盾，要求调和

**充分信号（可以前进）：**
- 用户给出了具体数据 + 来源 + 时间范围
- 用户主动承认了不确定性并说明了风险
- 用户从多个角度论证了同一观点
- 继续追问已无法产生新信息

**实际操作：每个核心主张的对话节奏应该像这样：**
```
Q1 (澄清): 你说的 X 具体指什么？
→ 用户回答（浅层）
Q2 (澄清-追问): 你提到了 A，但 A 的范围似乎很广，能缩窄到最关键的部分吗？
→ 用户回答（有改善）
Q3 (证据): 有什么数据支持这个被缩窄后的 A？
→ 用户给出数据
Q4 (假设): 这个数据背后的假设是什么？如果假设不成立呢？
→ 用户给出深层回答
✓ 可以转入下一个主张
```

而不是:
```
Q1 (澄清): ...
Q2 (假设): ...  ← 机械跳转，没有深入
Q3 (证据): ...
...
```

After each answer, record it:
```bash
python ~/.claude/skills/socratic-writer/scripts/run.py session.py add-dialogue --id SESSION_ID --question "Q" --answer "A" --type "TYPE"
```

## Step 4: Research (深度优先)

### Trigger Conditions
When user says "不知道", "不确定", "需要查一下" — OR when YOU identify a gap the user hasn't noticed:
- A claim with no supporting data
- A causal chain with a missing link
- An assumption about market behavior with no historical validation

### Research Execution (多源、多层)

**不要只做一次搜索就停下来。** 对每个研究缺口，执行以下流程：

**第一层：快速扫描（找到线索）**
- Local files first: `research.py local --query "..." --session SESSION_ID`
  - Search Obsidian Vault (earnings analysis, thesis docs, knowledge base)
  - Search PORTFOLIO data (trade records, thesis files)
- NotebookLM: `research.py nlm --question "..." --session SESSION_ID`
  - Use when user has relevant notebooks (check registered notebooks first)
- WebSearch: Quick search for the specific claim or data point

**第二层：交叉验证（验证线索）**
- If local search found a data point → WebSearch to verify/update it
- If WebSearch found a claim → check against local earnings transcripts or thesis docs
- If NotebookLM gave an answer → WebSearch for counter-evidence or more recent data

**第三层：补充视角（拓宽认知）**
- After finding data, search for OPPOSING views:
  - WebSearch: "[topic] bear case" or "[topic] risks" or "[topic] criticism"
  - Local: Search for analyst concerns or management credibility issues
- Search for ANALOGOUS cases:
  - WebSearch: "similar to [situation] historical example"
  - Local: Search for related companies or industries in the vault

**Research Summary:** After completing research on a topic, synthesize findings into 2-3 sentences and present to the user before continuing the dialogue. State clearly:
- What the data says (with source)
- What's still uncertain
- What contradicts the user's current position (if anything)

## Step 5: Multi-AI Challenge

After the core questioning is complete (typically 8-15 exchanges, not just 6), trigger:

```bash
# Devil's Advocate (Gemini) — deep, multi-layered pushback
python ~/.claude/skills/socratic-writer/scripts/run.py devil.py challenge --session SESSION_ID

# Supplementary Perspectives (ChatGPT) — recommended: manual mode
python ~/.claude/skills/socratic-writer/scripts/run.py perspective.py prompt --session SESSION_ID
# Then user pastes to ChatGPT and saves: perspective.py save --session ID --response "..."
```

Present the Devil's Advocate challenges to the user one at a time. For each challenge:
1. Show the challenge (target_claim + surface + deeper + steel_man)
2. Ask the user to respond
3. If the response is weak → press harder with follow-up questions
4. If the response is strong → move to the next challenge
5. Record responses: `devil.py respond --session ID --text "..."`

## Step 6: Iterate

Based on challenges and user responses:
- If any challenge was rated "critical" and user couldn't respond well → trigger another round of research on that specific topic
- If new evidence emerged → update claims ledger
- Continue questioning if there are unresolved weak points

## Step 7: Export

When user is satisfied:

```bash
python ~/.claude/skills/socratic-writer/scripts/run.py export.py obsidian --session SESSION_ID
```

## Key Principles

1. **Ask, don't tell** — Your role is to draw out the user's ideas, not lecture
2. **One question at a time** — Don't overwhelm
3. **Follow the depth, not the schedule** — A single claim worth 5 questions beats 5 claims with 1 question each
4. **Research proactively** — Don't wait for user to say "I don't know"; if you see a gap, fill it
5. **Cross-validate** — Never trust a single source; always look for confirming AND disconfirming evidence
6. **Devil's advocate is essential** — Always challenge before finalizing
7. **Contradictions are gold** — When you find a contradiction between user's claims, research findings, or AI challenges, highlight it immediately
