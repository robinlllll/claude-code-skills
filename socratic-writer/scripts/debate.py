#!/usr/bin/env python3
"""
Parallel Debate - Run Gemini (quantitative) + GPT (qualitative) + Grok (contrarian) challenges
simultaneously, then conduct a rebuttal round where each AI responds to the others' challenges.

Usage:
    debate.py run --session ID           # Full debate: parallel challenges + rebuttals
    debate.py challenge --session ID     # Parallel challenges only (no rebuttals)
    debate.py rebuttal --session ID      # Rebuttal round only (requires prior challenges)
    debate.py status --session ID        # Show debate status
"""

import asyncio
import json
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))

# Import session/config modules
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from config import load_config
from session import load_session, get_session_path

# --- Role-Specialized Prompts ---

GEMINI_ASSUMPTION_PROMPT = """你是一位假设核查员。你的目标不是推翻用户的论点，而是帮助用户识别哪些关键主张有客观证据支撑，哪些还是未验证的假设。

根据用户讨论的主题领域（投资、技术、商业、社会等）调整你的分析框架和具体例子。

## 你的专属领域：假设核查

按以下 6 个维度系统核查：
1. **可验证主张清单** — 论点中引用了哪些具体数字？哪个来源最容易查证？
2. **假设分层** — 将每个关键假设分为："已有公开数据"（可立即查证）vs "需要一手研究"（需调研获取）vs "本质上不可预测"（不可验证）
3. **压力测试参数** — 最值得测试的 2-3 个关键变量。如果这些变量偏离假设值 20-30%，结论如何变化？
4. **数据缺口地图** — 最大的数据空缺在哪里？填补的最快路径是什么？
5. **历史基率参考** — 类似主张的历史基率。格式："在 N 个类似案例中，X% 的结果是..."
6. **量化确信度** — 各子假设的可验证程度（1-10），标注哪些是整个论证的承重点

## 输出格式

严格返回以下 JSON（不要包含 ```json 标记）：

{{{{
  "assumption_map": [
    {{{{
      "claim": "直接引用用户的原话",
      "layer": "公开数据|一手研究|不可预测",
      "verification_path": "具体如何验证这个主张——数据源、指标、时间范围",
      "confidence": 5,
      "is_load_bearing": true
    }}}}
  ],
  "scenario_parameters": {{{{
    "key_variables": ["最值得压力测试的 2-3 个变量"],
    "base_case": "用户的隐含基准情景",
    "stress_scenario": "如果关键变量偏离 20-30%，结论如何变化",
    "data_gaps": ["最大的数据空缺及填补路径"]
  }}}},
  "verification_score": {{{{
    "overall": 5,
    "rationale": "一句话解释",
    "most_unverified_assumption": "整个论证中最关键的未验证假设",
    "base_rate": "类似主张的历史基率参考"
  }}}}
}}}}

## 核心规则
1. 每个主张必须分层——不能笼统说"需要验证"，要给出具体的验证路径
2. 标注"承重假设"（is_load_bearing）——如果这个假设错了，整个论点是否崩塌？
3. 禁止定性评论——那是你同事(GPT)的工作
4. overall 评分 1-10：1=几乎全部未验证；5=关键假设有缺口；10=核心主张均有数据支撑

---
主题：{topic}

当前论点和内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


GPT_FRAMEWORK_PROMPT = """你是一位跨学科知识库。帮助用户找到相关理论/框架、对比已有研究发现、提供历史类比。你的目标不是挑战论点，而是做知识桥接。

根据用户讨论的主题领域（投资、技术、商业、社会等）调整你的分析框架和具体例子。

## 你的专属领域：框架连接

按以下 6 个维度提供知识桥接：
1. **相关理论框架** — 哪个已知框架可以解释/检验用户的核心主张？（如：波特五力、创新者窘境、行为金融、反身性理论等）
2. **现有研究对比** — 学术界/实践者对类似主张有什么已知发现？哪些支持、哪些反对？
3. **类似案例库** — 2-3 个最相似的历史案例。每个案例说明：相似点、结局、与当前情况的关键差异
4. **框架适用边界** — 用户隐含使用了哪个框架？什么条件下这个框架不适用？
5. **概念精确化** — 关键词在学术/实践中的精确定义 vs 用户使用方式。是否有概念混用或滑坡？
6. **创新点识别** — 用户分析中超出现有框架的地方——这些是真正的原创洞察还是盲点？

## 输出格式

请提供结构化的分析（Markdown格式，不需要JSON）：

### 理论框架匹配

**框架 N: [框架名]**
- **适用性:** 这个框架如何解释用户的核心主张
- **已知发现:** 学术/实践中使用这个框架的已知结论
- **适用边界:** 什么条件下这个框架失效

### 历史类比库

**案例 N: [案例名]**
- **相似点:** 与当前情况的共性
- **结局:** 这个案例最终如何发展
- **关键差异:** 当前情况与历史案例的核心区别
- **教训:** 从这个案例中能学到什么

### 概念精确化
- 用户使用的关键术语 vs 学术/实践定义的对比
- 潜在的概念混用或逻辑滑坡

### 创新点 vs 盲点
- 用户分析中的原创洞察（超出现有框架的部分）
- 可能被误认为洞察的盲点

### 框架连接评分
- **知识桥接完整度:** X/10
- **最有价值的框架:** 一句话说明哪个框架最能帮助用户
- **建议阅读:** 1-2 个最值得深入了解的理论/案例

---
主题：{topic}

内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


GROK_BLINDSPOT_PROMPT = """你是一位系统性盲点扫描仪。找出缺席的声音、被忽略的变量、隐含的假设和未考虑的约束条件。你的目标不是"挑战"或"逆向"，而是系统性地审计覆盖范围。

根据用户讨论的主题领域（投资、技术、商业、社会等）调整你的分析框架和具体例子。

## 你的专属领域：盲点扫描

按以下 6 个维度逐一扫描：
1. **隐含假设清单** — 论点成立依赖哪些未明说的假设？逐一列出，标注"已验证/未验证/不可验证"
2. **缺席的利益相关者** — 谁会被影响但没出现在分析中？他们的反应可能如何改变结论？
3. **遗漏的变量** — 哪些变量被排除在分析之外？区分"有意简化"和"无意忽视"
4. **时间维度盲点** — 短期/中期/长期的结论是否一致？如果不一致，矛盾点在哪？
5. **边界条件** — 论点在什么条件下成立？条件变化的早期信号是什么？
6. **Kill Criteria 审查** — 有没有可观测、有时间框架的证伪条件？如果没有，建议具体的 kill criteria

## 输出格式

请用 Markdown 格式，每个维度一个章节：

### 1. 隐含假设清单
| # | 假设 | 状态 | 如果错了会怎样 |
|---|------|------|---------------|
| 1 | ... | 未验证 | ... |

### 2. 缺席的利益相关者
- **[利益相关者名]:** 为什么缺席？他们的反应可能是？

### 3. 遗漏的变量
- **有意简化:** 用户知道但选择不讨论的（标注为什么简化是合理/不合理的）
- **无意忽视:** 用户可能没想到的变量

### 4. 时间维度盲点
- 短期（<6月）/ 中期（6-18月）/ 长期（>18月）结论一致性检查
- 时间维度上最大的认知盲区

### 5. 边界条件
- 论点成立的前提条件
- 条件变化的早期信号（lead indicators）

### 6. Kill Criteria 审查
- 现有 kill criteria 评估（如果有）
- 建议补充的 kill criteria（可观测、有时间框架、可执行）

### 盲点扫描总评
- **覆盖完整度:** X/10（10=分析覆盖全面，无重大盲点）
- **最大盲点:** 一句话总结
- **立即行动项:** 1-2 个最优先的盲点填补动作

---
主题：{topic}

用户的论点和Q&A讨论：
{content}

{dialogue}
"""

GROK_DEVILS_ADVOCATE_PROMPT = """你是一位魔鬼代言人。你的唯一目标是：构建最强有力的反面论证来挑战用户的论点。

你不是在"帮助"用户——你在尽全力证明他们错了。如果他们的论点最终能经受住你的攻击，那它就是值得持有的。

## 你的任务

1. **核心反论点** — 用 3-5 段构建一个完整的、自洽的反面叙事。不要列要点——写一篇真正的反驳文章。
2. **最致命的弱点** — 用户论点中最脆弱的一环是什么？为什么这一点足以推翻整个论点？
3. **反身性陷阱** — 如果很多人都持有用户相同的观点，这本身会如何改变结果？（拥挤交易、自我实现/自我否定预言）
4. **历史类比打脸** — 找 1-2 个历史上类似论点最终被证明错误的案例
5. **如果你是对手** — 如果你是用户的直接对手（竞争对手/空头/反方），你会怎么行动？

## 输出格式

用 Markdown 格式，保持攻击性但有理有据：

### 核心反论点
[3-5 段连贯的反面叙事]

### 最致命的弱点
- **弱点:** [一句话]
- **为什么致命:** [展开]
- **用户可能的反驳:** [预判]
- **对反驳的再反驳:** [你的回应]

### 反身性陷阱
- 共识程度评估
- 拥挤度如何影响结果

### 历史类比打脸
| 历史案例 | 当时的论点 | 实际结果 | 与用户论点的相似度 |
|----------|-----------|---------|------------------|

### 如果你是对手
- 对手的最优策略
- 对手掌握的信息优势

### 魔鬼代言人总评
- **论点抗压评分:** X/10（10=无懈可击）
- **最大风险:** 一句话
- **"如果我错了"场景:** 什么情况下用户是对的、你是错的？

---
主题：{topic}

内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


GROK_REBUTTAL_PROMPT = """你是一位逆向思考者。你的两位同事分别从量化和定性角度提出了挑战：

量化挑战（Gemini）：
{gemini_output}

定性挑战（GPT）：
{gpt_output}

请从逆向/结构性角度回应：
1. 两位同事的挑战本身是否也陷入了某种共识思维？
2. 他们的分析框架有什么盲点？（例如：都假设市场是理性的）
3. 综合两者的观点，真正的"黑天鹅"风险是什么——一个他们都没提到的场景？
4. 如果把所有人的观点（包括原始论点和两位同事的挑战）都反转，最合理的逆向叙事是什么？

原始论点供参考：
主题：{topic}
内容：{content}

请用 Markdown 格式回应：

### 对同事分析框架的挑战
- 量化分析师的盲点
- 定性分析师的盲点

### 综合黑天鹅场景
- 所有人都没想到的风险场景

### 终极逆向叙事
- 如果一切都反过来，最合理的故事是什么？

### 共识陷阱警告
- 三位分析师（包括我自己）可能共同陷入的思维陷阱

用中文回应。"""


GEMINI_REBUTTAL_PROMPT = """你是一位量化分析师。你的同事（定性分析师）刚刚提出了以下定性挑战：

{gpt_output}

请从量化角度回应：
1. 哪些定性观点是可以量化验证的？具体用什么数据？
2. 哪些定性风险可以转化为概率估计？
3. 你同意哪些定性挑战？不同意哪些？为什么？
4. 从定性挑战中，你发现了哪些你之前遗漏的量化盲点？

原始论点供参考：
主题：{topic}
内容：{content}

严格返回 JSON：
{{{{
  "agreements": ["同意的定性观点及理由"],
  "quantifiable_points": [
    {{{{
      "qualitative_claim": "同事的定性观点",
      "quantitative_test": "如何用数据验证",
      "data_source": "具体数据来源"
    }}}}
  ],
  "new_blind_spots": ["从同事的挑战中发现的新量化盲点"],
  "probability_estimates": [
    {{{{
      "qualitative_risk": "定性风险描述",
      "estimated_probability": "X%",
      "reasoning": "概率估计的依据"
    }}}}
  ]
}}}}

用中文回应。"""


GPT_REBUTTAL_PROMPT = """你是一位定性分析师。你的同事（量化分析师）刚刚提出了以下量化挑战：

{gemini_output}

请从定性角度回应：
1. 哪些量化挑战你同意？哪些你认为忽略了重要的定性因素？
2. 你同事的数字背后，有哪些定性假设是有问题的？
3. 从量化挑战中，你发现了哪些之前遗漏的定性盲点？
4. 哪些量化指标可能会误导决策？（例如：利润率很高但护城河在消失）

原始论点供参考：
主题：{topic}
内容：{content}

请用 Markdown 格式回应：

### 对量化挑战的回应

**同意的量化观点:**
- ...

**定性补充/反驳:**
对于每个量化挑战，指出其背后可能忽略的定性因素

**新发现的定性盲点:**
- 从同事的数字中看到的新定性风险

**误导性指标警告:**
- 哪些数字看起来好但可能掩盖了定性问题

用中文回应。"""


def _load_session_data(session_id: str) -> tuple:
    """Load session state, dialogue, and session_path. Returns (state, dialogue_text, session_path) or raises."""
    state = load_session(session_id)
    if not state:
        raise ValueError(f"Session not found: {session_id}")

    session_path = get_session_path(session_id)

    dialogue_file = session_path / "dialogue.json"
    if not dialogue_file.exists():
        raise ValueError("No dialogue found in session.")

    with open(dialogue_file, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    dialogue_text = ""
    for entry in dialogue_data.get("entries", []):
        dialogue_text += f"Q ({entry.get('type', 'unknown')}): {entry.get('question', '')}\n"
        dialogue_text += f"A: {entry.get('answer', '')}\n\n"

    if not dialogue_text:
        raise ValueError("No dialogue entries yet. Start with Socratic questioning first.")

    return state, dialogue_text, session_path


def _get_gemini_client():
    """Initialize Gemini client (new google.genai SDK)."""
    try:
        from google import genai

        config = load_config()
        api_key = config.get("gemini_api_key")
        if not api_key:
            raise ValueError("Gemini API key not configured. Run: config.py set-gemini-key YOUR_KEY")

        client = genai.Client(api_key=api_key)
        model_name = config.get("gemini_model", "gemini-3-pro-preview")
        return client, model_name

    except ImportError:
        raise ImportError("google-genai not installed. Run: pip install google-genai")


def _get_openai_client():
    """Initialize OpenAI client (matches existing perspective.py pattern)."""
    try:
        from openai import OpenAI

        config = load_config()
        api_key = config.get("openai_api_key")
        if not api_key:
            raise ValueError("OpenAI API key not configured. Run: config.py set openai_api_key YOUR_KEY")

        model = config.get("chatgpt_model", "gpt-5.2-chat-latest")
        client = OpenAI(api_key=api_key)
        return client, model

    except ImportError:
        raise ImportError("openai not installed. Run: pip install openai")


def _get_grok_client():
    """Initialize Grok client (uses OpenAI SDK with xAI base_url)."""
    try:
        from openai import OpenAI

        config = load_config()
        api_key = config.get("grok_api_key")
        if not api_key:
            raise ValueError("Grok API key not configured. Run: config.py set grok_api_key YOUR_KEY")

        model = config.get("grok_model", "grok-4-1-fast-reasoning")
        client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        return client, model

    except ImportError:
        raise ImportError("openai not installed. Run: pip install openai")


def _extract_tickers_and_suggest(text: str):
    """Extract tickers from challenge text and print research suggestions."""
    try:
        sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
        from shared.ticker_detector import detect_tickers

        results = detect_tickers(text)
        if not results:
            return

        print("\n" + "-" * 60)
        print("AUTO-RESEARCH SUGGESTIONS")
        print("-" * 60)

        suggested = set()
        for r in results:
            ticker = r["ticker"]
            if ticker in suggested:
                continue
            suggested.add(ticker)

            # Check if thesis exists
            thesis_path = Path.home() / "PORTFOLIO" / "research" / "companies" / ticker / "thesis.md"
            if thesis_path.exists():
                print(f"  Challenge mentions {ticker} -- thesis exists at {thesis_path}")
                print(f"    Run: research.py local {ticker} to cross-reference")
            else:
                print(f"  Challenge mentions {ticker} -- no thesis found")
                print(f"    Run: research.py local {ticker} to search local files")

        print("-" * 60)

    except Exception:
        # Ticker detection is best-effort; don't crash the debate
        pass


async def _call_gemini_quantitative(topic: str, content: str, dialogue: str) -> dict:
    """Call Gemini with assumption verification prompt."""
    client, model_name = _get_gemini_client()

    prompt = GEMINI_ASSUMPTION_PROMPT.format(
        topic=topic,
        content=content,
        dialogue=dialogue,
    )

    # Run in executor since google.genai is synchronous
    loop = asyncio.get_event_loop()

    def _call():
        response = client.models.generate_content(model=model_name, contents=prompt)
        return response.text

    result_text = await loop.run_in_executor(None, _call)

    # Parse JSON
    try:
        start = result_text.find("{")
        end = result_text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(result_text[start:end])
    except json.JSONDecodeError:
        pass

    return {"raw_response": result_text}


async def _call_gpt_qualitative(topic: str, content: str, dialogue: str) -> str:
    """Call GPT with framework connection prompt."""
    client, model = _get_openai_client()

    prompt = GPT_FRAMEWORK_PROMPT.format(
        topic=topic,
        content=content,
        dialogue=dialogue,
    )

    loop = asyncio.get_event_loop()

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content, resp.usage

    result_text, usage = await loop.run_in_executor(None, _call)
    return result_text


async def _call_grok_contrarian(topic: str, content: str, dialogue: str) -> str:
    """Call Grok with blind spot scanning prompt."""
    client, model = _get_grok_client()

    prompt = GROK_BLINDSPOT_PROMPT.format(
        topic=topic,
        content=content,
        dialogue=dialogue,
    )

    loop = asyncio.get_event_loop()

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content, resp.usage

    result_text, usage = await loop.run_in_executor(None, _call)
    return result_text


async def _call_grok_devils_advocate(topic: str, content: str, dialogue: str) -> str:
    """Call Grok with devil's advocate prompt — adversarial challenge to user's thesis."""
    client, model = _get_grok_client()

    prompt = GROK_DEVILS_ADVOCATE_PROMPT.format(
        topic=topic,
        content=content,
        dialogue=dialogue,
    )

    loop = asyncio.get_event_loop()

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content, resp.usage

    result_text, usage = await loop.run_in_executor(None, _call)
    return result_text


async def _call_grok_rebuttal(gemini_output, gpt_output: str, topic: str, content: str) -> str:
    """Grok rebuts both Gemini and GPT from a contrarian perspective."""
    client, model = _get_grok_client()

    # Format gemini output for the prompt
    if isinstance(gemini_output, dict):
        gemini_text = json.dumps(gemini_output, ensure_ascii=False, indent=2)
    else:
        gemini_text = str(gemini_output)

    prompt = GROK_REBUTTAL_PROMPT.format(
        gemini_output=gemini_text,
        gpt_output=gpt_output,
        topic=topic,
        content=content,
    )

    loop = asyncio.get_event_loop()

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content

    return await loop.run_in_executor(None, _call)


async def _call_gemini_rebuttal(gpt_output: str, topic: str, content: str) -> dict:
    """Gemini rebuts GPT's qualitative challenges."""
    client, model_name = _get_gemini_client()

    prompt = GEMINI_REBUTTAL_PROMPT.format(
        gpt_output=gpt_output,
        topic=topic,
        content=content,
    )

    loop = asyncio.get_event_loop()

    def _call():
        response = client.models.generate_content(model=model_name, contents=prompt)
        return response.text

    result_text = await loop.run_in_executor(None, _call)

    try:
        start = result_text.find("{")
        end = result_text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(result_text[start:end])
    except json.JSONDecodeError:
        pass

    return {"raw_response": result_text}


async def _call_gpt_rebuttal(gemini_output: str, topic: str, content: str) -> str:
    """GPT rebuts Gemini's quantitative challenges."""
    client, model = _get_openai_client()

    # Format gemini output for the prompt
    if isinstance(gemini_output, dict):
        gemini_text = json.dumps(gemini_output, ensure_ascii=False, indent=2)
    else:
        gemini_text = str(gemini_output)

    prompt = GPT_REBUTTAL_PROMPT.format(
        gemini_output=gemini_text,
        topic=topic,
        content=content,
    )

    loop = asyncio.get_event_loop()

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content

    return await loop.run_in_executor(None, _call)


def _display_gemini_result(result: dict):
    """Display Gemini assumption verification results."""
    print("\n" + "=" * 60)
    print("GEMINI: ASSUMPTION VERIFICATION")
    print("=" * 60)

    if "assumption_map" in result:
        for i, a in enumerate(result["assumption_map"], 1):
            load_bearing = " [LOAD-BEARING]" if a.get("is_load_bearing") else ""
            print(f"\n  [{a.get('layer', '?')}] Assumption {i}{load_bearing}: confidence {a.get('confidence', '?')}/10")
            print(f"  {'~' * 56}")
            print(f"  Claim: \"{a.get('claim', 'N/A')}\"")
            print(f"  Verification path: {a.get('verification_path', 'N/A')}")

        sp = result.get("scenario_parameters", {})
        if sp:
            print(f"\n  {'=' * 56}")
            print("  Scenario Parameters")
            print(f"  {'~' * 56}")
            print(f"  Key variables: {', '.join(sp.get('key_variables', []))}")
            print(f"  Base case: {sp.get('base_case', 'N/A')}")
            print(f"  Stress scenario: {sp.get('stress_scenario', 'N/A')}")
            gaps = sp.get('data_gaps', [])
            if gaps:
                print(f"  Data gaps: {'; '.join(gaps)}")

        vs = result.get("verification_score", {})
        if vs:
            print(f"\n  Verification Score: {vs.get('overall', '?')}/10 - {vs.get('rationale', '')}")
            print(f"  Most unverified: {vs.get('most_unverified_assumption', 'N/A')}")
            print(f"  Base rate: {vs.get('base_rate', 'N/A')}")
    elif "challenges" in result:
        # Backward compat: old format
        for i, c in enumerate(result["challenges"], 1):
            severity = c.get("severity", "?").upper()
            print(f"\n  [{severity}] Challenge {i}: {c.get('type', 'N/A')}")
            print(f"  Target: \"{c.get('target_claim', 'N/A')}\"")
            print(f"  Challenge: {c.get('quantitative_challenge', 'N/A')}")
    else:
        print(result.get("raw_response", "No structured response"))


def _display_gpt_result(result_text: str):
    """Display GPT framework connection results."""
    print("\n" + "=" * 60)
    print("GPT: FRAMEWORK CONNECTION")
    print("=" * 60)
    print(result_text)


def _display_grok_result(result_text: str):
    """Display Grok blind spot scan results."""
    print("\n" + "=" * 60)
    print("GROK: BLIND SPOT SCAN")
    print("=" * 60)
    print(result_text)


def _display_grok_advocate_result(result_text: str):
    """Display Grok devil's advocate results."""
    print("\n" + "=" * 60)
    print("GROK: DEVIL'S ADVOCATE")
    print("=" * 60)
    print(result_text)


def _display_grok_rebuttal(result_text: str):
    """Display Grok's rebuttal to both Gemini and GPT."""
    print("\n" + "=" * 60)
    print("GROK REBUTTAL (Contrarian response to Gemini + GPT)")
    print("=" * 60)
    print(result_text)


def _display_gemini_rebuttal(result: dict):
    """Display Gemini's rebuttal to GPT."""
    print("\n" + "=" * 60)
    print("GEMINI REBUTTAL (Quantitative response to GPT)")
    print("=" * 60)

    if "raw_response" in result:
        print(result["raw_response"])
        return

    agreements = result.get("agreements", [])
    if agreements:
        print("\n  Agreements with GPT:")
        for a in agreements:
            print(f"    - {a}")

    qpoints = result.get("quantifiable_points", [])
    if qpoints:
        print("\n  Quantifiable points:")
        for q in qpoints:
            print(f"    Claim: {q.get('qualitative_claim', '')}")
            print(f"    Test: {q.get('quantitative_test', '')}")
            print(f"    Source: {q.get('data_source', '')}")
            print()

    blind_spots = result.get("new_blind_spots", [])
    if blind_spots:
        print("  New blind spots discovered:")
        for b in blind_spots:
            print(f"    - {b}")

    prob_estimates = result.get("probability_estimates", [])
    if prob_estimates:
        print("\n  Probability estimates for qualitative risks:")
        for p in prob_estimates:
            print(f"    Risk: {p.get('qualitative_risk', '')}")
            print(f"    Probability: {p.get('estimated_probability', '')}")
            print(f"    Reasoning: {p.get('reasoning', '')}")
            print()


def _display_gpt_rebuttal(result_text: str):
    """Display GPT's rebuttal to Gemini."""
    print("\n" + "=" * 60)
    print("GPT REBUTTAL (Qualitative response to Gemini)")
    print("=" * 60)
    print(result_text)


async def cmd_debate_parallel(session_id: str):
    """Run Gemini + GPT challenges in parallel."""
    state, dialogue_text, session_path = _load_session_data(session_id)
    topic = state.get("topic", "Unknown")
    content = state.get("summary", "")

    print(f"Session: {session_id}")
    print(f"Topic: {topic}")
    print("\nLaunching parallel analysis: Gemini (assumptions) + GPT (frameworks) + Grok (blind spots) + Grok (devil's advocate)...")

    # Run all four in parallel
    gemini_result, gpt_result, grok_result, advocate_result = await asyncio.gather(
        _call_gemini_quantitative(topic, content, dialogue_text),
        _call_gpt_qualitative(topic, content, dialogue_text),
        _call_grok_contrarian(topic, content, dialogue_text),
        _call_grok_devils_advocate(topic, content, dialogue_text),
        return_exceptions=True,
    )

    # Handle errors
    gemini_ok = not isinstance(gemini_result, BaseException)
    gpt_ok = not isinstance(gpt_result, BaseException)
    grok_ok = not isinstance(grok_result, BaseException)
    advocate_ok = not isinstance(advocate_result, BaseException)

    if not gemini_ok:
        print(f"\nGemini error: {gemini_result}")
    if not gpt_ok:
        print(f"\nGPT error: {gpt_result}")
    if not grok_ok:
        print(f"\nGrok error: {grok_result}")
    if not advocate_ok:
        print(f"\nGrok Devil's Advocate error: {advocate_result}")

    ok_count = sum([gemini_ok, gpt_ok, grok_ok, advocate_ok])
    if ok_count == 0:
        print("\nAll AI calls failed. Check API keys with: config.py show")
        return None, None, None, None

    # Save results
    challenges_dir = session_path / "challenges"
    challenges_dir.mkdir(exist_ok=True)

    if gemini_ok:
        gemini_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "mode": "assumption_verification",
            "result": gemini_result,
            "responses": [],
        }
        with open(challenges_dir / "gemini.json", "w", encoding="utf-8") as f:
            json.dump(gemini_record, f, indent=2, ensure_ascii=False)

        _display_gemini_result(gemini_result)

    if gpt_ok:
        gpt_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "mode": "framework_connection",
            "model": load_config().get("chatgpt_model", "gpt-5.2-chat-latest"),
            "response": gpt_result,
        }
        with open(challenges_dir / "gpt.json", "w", encoding="utf-8") as f:
            json.dump(gpt_record, f, indent=2, ensure_ascii=False)

        _display_gpt_result(gpt_result)

    if grok_ok:
        grok_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "mode": "blind_spot_scan",
            "model": load_config().get("grok_model", "grok-4-1-fast-reasoning"),
            "response": grok_result,
        }
        with open(challenges_dir / "grok.json", "w", encoding="utf-8") as f:
            json.dump(grok_record, f, indent=2, ensure_ascii=False)

        _display_grok_result(grok_result)

    if advocate_ok:
        advocate_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "mode": "devils_advocate",
            "model": load_config().get("grok_model", "grok-4-1-fast-reasoning"),
            "response": advocate_result,
        }
        with open(challenges_dir / "grok_advocate.json", "w", encoding="utf-8") as f:
            json.dump(advocate_record, f, indent=2, ensure_ascii=False)

        _display_grok_advocate_result(advocate_result)

    # Auto-research suggestions
    all_text = ""
    if gemini_ok:
        all_text += json.dumps(gemini_result, ensure_ascii=False) if isinstance(gemini_result, dict) else str(gemini_result)
    if gpt_ok:
        all_text += "\n" + (gpt_result if isinstance(gpt_result, str) else str(gpt_result))
    if grok_ok:
        all_text += "\n" + (grok_result if isinstance(grok_result, str) else str(grok_result))
    if advocate_ok:
        all_text += "\n" + (advocate_result if isinstance(advocate_result, str) else str(advocate_result))
    _extract_tickers_and_suggest(all_text)

    print("\n" + "=" * 60)
    print("PARALLEL ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"  Gemini (assumptions):     {'OK' if gemini_ok else 'FAILED'}")
    print(f"  GPT (frameworks):         {'OK' if gpt_ok else 'FAILED'}")
    print(f"  Grok (blind spots):       {'OK' if grok_ok else 'FAILED'}")
    print(f"  Grok (devil's advocate):  {'OK' if advocate_ok else 'FAILED'}")
    print(f"\nNext steps:")
    print(f"  grok_engine.py synthesize --session {session_id}  # Grok synthesizes tensions")
    print(f"  debate.py rebuttal --session {session_id}         # (optional) Run rebuttal round (+106% cost)")

    return (
        gemini_result if gemini_ok else None,
        gpt_result if gpt_ok else None,
        grok_result if grok_ok else None,
        advocate_result if advocate_ok else None,
    )


async def cmd_rebuttal(session_id: str):
    """Run rebuttal round: each AI responds to the other's challenges."""
    state, _, session_path = _load_session_data(session_id)
    topic = state.get("topic", "Unknown")
    content = state.get("summary", "")
    challenges_dir = session_path / "challenges"

    # Load prior challenges
    gemini_file = challenges_dir / "gemini.json"
    gpt_file = challenges_dir / "gpt.json"

    if not gemini_file.exists() or not gpt_file.exists():
        print("Error: Both Gemini and GPT challenges are required for rebuttal.")
        print("Run 'debate.py challenge --session ID' first.")
        return

    with open(gemini_file, "r", encoding="utf-8") as f:
        gemini_data = json.load(f)
    with open(gpt_file, "r", encoding="utf-8") as f:
        gpt_data = json.load(f)

    gemini_output = gemini_data.get("result", {})
    gpt_output = gpt_data.get("response", "")

    print(f"Session: {session_id}")
    print("Launching rebuttal round...")
    print("  Gemini will respond to GPT's qualitative challenges")
    print("  GPT will respond to Gemini's quantitative challenges")
    print("  Grok will challenge both from a contrarian perspective")

    # Run rebuttals in parallel (Grok rebuts both)
    gemini_rebuttal, gpt_rebuttal, grok_rebuttal = await asyncio.gather(
        _call_gemini_rebuttal(gpt_output, topic, content),
        _call_gpt_rebuttal(gemini_output, topic, content),
        _call_grok_rebuttal(gemini_output, gpt_output, topic, content),
        return_exceptions=True,
    )

    gemini_ok = not isinstance(gemini_rebuttal, BaseException)
    gpt_ok = not isinstance(gpt_rebuttal, BaseException)
    grok_ok = not isinstance(grok_rebuttal, BaseException)

    if not gemini_ok:
        print(f"\nGemini rebuttal error: {gemini_rebuttal}")
    if not gpt_ok:
        print(f"\nGPT rebuttal error: {gpt_rebuttal}")
    if not grok_ok:
        print(f"\nGrok rebuttal error: {grok_rebuttal}")

    # Save rebuttals
    if gemini_ok:
        rebuttal_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "type": "gemini_rebuttal_to_gpt",
            "result": gemini_rebuttal,
        }
        with open(challenges_dir / "gemini_rebuttal.json", "w", encoding="utf-8") as f:
            json.dump(rebuttal_record, f, indent=2, ensure_ascii=False)

        _display_gemini_rebuttal(gemini_rebuttal)

    if gpt_ok:
        rebuttal_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "type": "gpt_rebuttal_to_gemini",
            "response": gpt_rebuttal,
        }
        with open(challenges_dir / "gpt_rebuttal.json", "w", encoding="utf-8") as f:
            json.dump(rebuttal_record, f, indent=2, ensure_ascii=False)

        _display_gpt_rebuttal(gpt_rebuttal)

    if grok_ok:
        rebuttal_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "type": "grok_rebuttal_to_both",
            "response": grok_rebuttal,
        }
        with open(challenges_dir / "grok_rebuttal.json", "w", encoding="utf-8") as f:
            json.dump(rebuttal_record, f, indent=2, ensure_ascii=False)

        _display_grok_rebuttal(grok_rebuttal)

    # Auto-research suggestions from rebuttals
    all_text = ""
    if gemini_ok:
        all_text += json.dumps(gemini_rebuttal, ensure_ascii=False) if isinstance(gemini_rebuttal, dict) else str(gemini_rebuttal)
    if gpt_ok:
        all_text += "\n" + (gpt_rebuttal if isinstance(gpt_rebuttal, str) else str(gpt_rebuttal))
    if grok_ok:
        all_text += "\n" + (grok_rebuttal if isinstance(grok_rebuttal, str) else str(grok_rebuttal))
    _extract_tickers_and_suggest(all_text)

    print("\n" + "=" * 60)
    print("REBUTTAL ROUND COMPLETE")
    print("=" * 60)
    print(f"  Gemini rebuttal: {'OK' if gemini_ok else 'FAILED'}")
    print(f"  GPT rebuttal: {'OK' if gpt_ok else 'FAILED'}")
    print(f"  Grok rebuttal: {'OK' if grok_ok else 'FAILED'}")
    print(f"  Files saved:")
    if gemini_ok:
        print(f"    {challenges_dir / 'gemini_rebuttal.json'}")
    if gpt_ok:
        print(f"    {challenges_dir / 'gpt_rebuttal.json'}")
    if grok_ok:
        print(f"    {challenges_dir / 'grok_rebuttal.json'}")
    print(f"\nNext steps:")
    print(f"  arbitrate.py compare --session {session_id}   # Compare all AI opinions")
    print(f"  export.py obsidian --session {session_id}      # Export to Obsidian")


async def cmd_full_debate(session_id: str, with_rebuttal: bool = False):
    """Full debate: parallel challenges + optional rebuttal round.

    Rebuttal is now opt-in (--with-rebuttal) as M3MAD research shows
    +106% cost for marginal value. Default: cooperative analysis only.
    """
    mode_label = "Cooperative Analysis + Rebuttal" if with_rebuttal else "Cooperative Analysis"
    print("=" * 60)
    print(f"FULL DEBATE: {mode_label}")
    print("=" * 60)

    # Phase 1: Parallel cooperative analysis
    print("\n--- Phase 1: Parallel Cooperative Analysis ---\n")
    gemini_result, gpt_result, grok_result, advocate_result = await cmd_debate_parallel(session_id)

    if gemini_result is None and gpt_result is None and grok_result is None and advocate_result is None:
        print("\nAborting debate: no challenges generated.")
        return

    # Phase 2: Rebuttal round (only if explicitly requested)
    if with_rebuttal:
        if gemini_result is not None and gpt_result is not None:
            print("\n\n--- Phase 2: Rebuttal Round ---\n")
            await cmd_rebuttal(session_id)
        else:
            print("\nSkipping rebuttal: requires both Gemini and GPT challenges.")
            print("Fix the failed API and run: debate.py rebuttal --session ID")
    else:
        print("\n  Rebuttal skipped (default). Use --with-rebuttal for full mode (+106% cost).")


def cmd_status(session_id: str):
    """Show debate status for a session."""
    session_path = get_session_path(session_id)
    challenges_dir = session_path / "challenges"

    if not challenges_dir.exists():
        print(f"No debate data for session {session_id}")
        return

    print(f"Session: {session_id}")
    print("-" * 40)

    files = {
        "gemini.json": "Gemini (assumptions)",
        "gpt.json": "GPT (frameworks)",
        "grok.json": "Grok (blind spots)",
        "grok_advocate.json": "Grok (devil's advocate)",
        "gemini_rebuttal.json": "Gemini rebuttal",
        "gpt_rebuttal.json": "GPT rebuttal",
        "grok_rebuttal.json": "Grok rebuttal",
    }

    for fname, label in files.items():
        fpath = challenges_dir / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("timestamp", "N/A")[:16]
            mode = data.get("mode", data.get("type", ""))
            print(f"  {label}: YES (at {ts}) [{mode}]")
        else:
            print(f"  {label}: not yet")

    # Suggest next step
    has_gemini = (challenges_dir / "gemini.json").exists()
    has_gpt = (challenges_dir / "gpt.json").exists()
    has_grok = (challenges_dir / "grok.json").exists()
    has_rebuttal_g = (challenges_dir / "gemini_rebuttal.json").exists()
    has_rebuttal_p = (challenges_dir / "gpt_rebuttal.json").exists()
    has_rebuttal_k = (challenges_dir / "grok_rebuttal.json").exists()

    print()
    if not has_gemini or not has_gpt:
        print(f"Next: debate.py challenge --session {session_id}")
    elif not has_rebuttal_g or not has_rebuttal_p:
        print(f"Next: debate.py rebuttal --session {session_id}")
    else:
        print(f"Debate complete! Next: arbitrate.py compare --session {session_id}")
    has_advocate = (challenges_dir / "grok_advocate.json").exists()
    if not has_grok:
        print(f"  Note: Grok (blind spots) not yet run. Re-run challenge to include.")
    if not has_advocate:
        print(f"  Note: Grok (devil's advocate) not yet run. Re-run challenge to include.")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  debate.py run --session ID                  # Cooperative analysis (no rebuttal)")
        print("  debate.py run --session ID --with-rebuttal  # Full mode (+106% cost)")
        print("  debate.py challenge --session ID             # Parallel challenges only")
        print("  debate.py rebuttal --session ID              # Rebuttal round only")
        print("  debate.py status --session ID                # Show debate status")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]

    if command == "status":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_status(session_id)
        return

    if not session_id:
        print("Error: --session is required")
        return

    # Parse --with-rebuttal flag
    with_rebuttal = "--with-rebuttal" in sys.argv

    # Async commands
    try:
        if command == "run":
            asyncio.run(cmd_full_debate(session_id, with_rebuttal=with_rebuttal))
        elif command == "challenge":
            asyncio.run(cmd_debate_parallel(session_id))
        elif command == "rebuttal":
            asyncio.run(cmd_rebuttal(session_id))
        else:
            print(f"Unknown command: {command}")
    except ValueError as e:
        print(f"Error: {e}")
    except ImportError as e:
        print(f"Missing dependency: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
