#!/usr/bin/env python3
"""
Parallel Debate - Run Gemini (quantitative) + GPT (qualitative) challenges simultaneously,
then conduct a rebuttal round where each AI responds to the other's challenges.

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

GEMINI_QUANTITATIVE_PROMPT = """你是一位量化投资分析师和魔鬼代言人。你的专长是数字、估值和可量化的假设。

## 你的专属领域：量化挑战

你只关注以下维度的质疑：
1. **数字验证** — 用户引用的任何数字（增长率、市场规模、利润率）是否合理？交叉验证来源
2. **时间线/概率** — 用户隐含的时间假设和成功概率是否经得起推敲？
3. **DCF/估值假设** — 折现率、终端增长率、利润率假设中的漏洞
4. **市场规模错误** — TAM/SAM/SOM 是否合理？是否犯了"人口 x 渗透率"的懒惰估算？
5. **财务不一致** — 收入增长 vs 利润率趋势、capex vs 折旧、现金流 vs 利润的矛盾
6. **基率谬误** — 用户的预测相对于行业基率是否异常？历史上类似情况的成功率是多少？

## 输出格式

严格返回以下 JSON（不要包含 ```json 标记）：

{{{{
  "challenges": [
    {{{{
      "type": "量化挑战类型：估值漏洞|数字验证|概率校准|基率谬误|财务矛盾|市场规模高估|时间错配",
      "target_claim": "直接引用用户的原话",
      "quantitative_challenge": "用数字反驳。例如：'用户假设30%增长率，但行业中位数是12%，且只有5%的公司维持>25%增长超过3年'",
      "data_to_verify": "要验证这个挑战，具体查什么数据？指明：数据源、指标、时间范围",
      "historical_base_rate": "历史上类似情况的基率数据。格式：'在N个类似案例中，X%的结果是...'",
      "severity": "minor|major|critical"
    }}}}
  ],
  "valuation_stress_test": {{{{
    "bull_case_assumptions": "用户的牛市假设列表",
    "bear_case_numbers": "如果关键假设下调20-30%，估值会变成什么？",
    "breakeven_analysis": "什么条件下这个投资的预期回报归零？"
  }}}},
  "confidence_calibration": {{{{
    "quantitative_score": 5,
    "score_rationale": "一句话解释",
    "most_fragile_number": "整个论证中最脆弱的一个数字假设"
  }}}}
}}}}

## 核心规则
1. 每个挑战必须包含具体数字或可查证的数据点
2. 禁止泛泛而谈 — "估值可能偏高"不如"用户隐含的EV/EBITDA 25x，而可比公司中位数是15x"
3. 禁止定性评论 — 那是你同事(GPT)的工作
4. quantitative_score 范围 1-10：1=数字完全站不住；5=关键假设未验证；10=量化论证极其稳固

---
主题：{topic}

当前论点和内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


GPT_QUALITATIVE_PROMPT = """你是一位资深的定性投资分析师和视角补充者。你的专长是竞争动态、管理层质量、叙事分析和行为金融。

## 你的专属领域：定性挑战

你只关注以下维度的分析：
1. **竞争动态** — 用户是否低估了竞争对手的反应？护城河是否真的存在？Porter五力分析中的薄弱环节
2. **管理层质量** — 管理层的历史执行记录、激励结构、资本配置能力、是否有"帝国建设"倾向
3. **叙事一致性** — 用户的投资故事是否自洽？是否有"为结论找证据"的倾向？叙事转变的风险
4. **市场情绪/行为偏差** — 当前市场对这个公司/行业的情绪定位。用户可能犯的行为偏差（锚定、确认偏误、过度自信等）
5. **利益相关者分析** — 用户忽略了哪些利益相关者（供应商、客户、监管者、员工）？他们的行为会如何影响论点？
6. **叙事风险** — 什么事件或信息会导致市场叙事180度转变？

## 输出格式

请提供结构化的分析（Markdown格式，不需要JSON）：

### 定性挑战

对每个挑战，使用以下格式：

**挑战 N: [类型]** (严重性: minor/major/critical)
- **目标主张:** "引用用户原话"
- **定性质疑:** 你的分析
- **被忽略的视角:** 谁的声音缺席了？
- **叙事转变风险:** 什么情况下市场会改变看法？

### 行为偏差诊断
- 用户可能犯的具体认知偏差（命名+解释为什么在这个语境下危险）

### 缺失的利益相关者
- 列出被忽略的关键利益相关者及其可能的反应

### 定性评分
- **定性稳固度:** X/10
- **最大定性风险:** 一句话总结
- **建议调查:** 需要做什么定性研究来补强论点

---
主题：{topic}

内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


GEMINI_REBUTTAL_PROMPT = """你是一位量化投资分析师。你的同事（定性分析师）刚刚提出了以下定性挑战：

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


GPT_REBUTTAL_PROMPT = """你是一位定性投资分析师。你的同事（量化分析师）刚刚提出了以下量化挑战：

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
    """Initialize Gemini client (matches existing devil.py pattern)."""
    try:
        import google.generativeai as genai

        config = load_config()
        api_key = config.get("gemini_api_key")
        if not api_key:
            raise ValueError("Gemini API key not configured. Run: config.py set-gemini-key YOUR_KEY")

        genai.configure(api_key=api_key)
        model_name = config.get("gemini_model", "gemini-3-pro-preview")
        return genai.GenerativeModel(model_name)

    except ImportError:
        raise ImportError("google-generativeai not installed. Run: pip install google-generativeai")


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
    """Call Gemini with quantitative-focused prompt."""
    model = _get_gemini_client()

    prompt = GEMINI_QUANTITATIVE_PROMPT.format(
        topic=topic,
        content=content,
        dialogue=dialogue,
    )

    # Run in executor since google.generativeai is synchronous
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, model.generate_content, prompt)
    result_text = response.text

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
    """Call GPT with qualitative-focused prompt."""
    client, model = _get_openai_client()

    prompt = GPT_QUALITATIVE_PROMPT.format(
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


async def _call_gemini_rebuttal(gpt_output: str, topic: str, content: str) -> dict:
    """Gemini rebuts GPT's qualitative challenges."""
    model = _get_gemini_client()

    prompt = GEMINI_REBUTTAL_PROMPT.format(
        gpt_output=gpt_output,
        topic=topic,
        content=content,
    )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, model.generate_content, prompt)
    result_text = response.text

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
    """Display Gemini quantitative challenges."""
    print("\n" + "=" * 60)
    print("GEMINI: QUANTITATIVE CHALLENGES")
    print("=" * 60)

    if "challenges" in result:
        for i, c in enumerate(result["challenges"], 1):
            severity = c.get("severity", "?").upper()
            print(f"\n  [{severity}] Challenge {i}: {c.get('type', 'N/A')}")
            print(f"  {'~' * 56}")
            print(f"  Target: \"{c.get('target_claim', 'N/A')}\"")
            print(f"  Quantitative challenge: {c.get('quantitative_challenge', 'N/A')}")
            print(f"  Data to verify: {c.get('data_to_verify', 'N/A')}")
            print(f"  Historical base rate: {c.get('historical_base_rate', 'N/A')}")

        vst = result.get("valuation_stress_test", {})
        if vst:
            print(f"\n  {'=' * 56}")
            print("  Valuation Stress Test")
            print(f"  {'~' * 56}")
            print(f"  Bull assumptions: {vst.get('bull_case_assumptions', 'N/A')}")
            print(f"  Bear case: {vst.get('bear_case_numbers', 'N/A')}")
            print(f"  Breakeven: {vst.get('breakeven_analysis', 'N/A')}")

        cc = result.get("confidence_calibration", {})
        if cc:
            print(f"\n  Quantitative Score: {cc.get('quantitative_score', '?')}/10 - {cc.get('score_rationale', '')}")
            print(f"  Most fragile number: {cc.get('most_fragile_number', 'N/A')}")
    else:
        print(result.get("raw_response", "No structured response"))


def _display_gpt_result(result_text: str):
    """Display GPT qualitative challenges."""
    print("\n" + "=" * 60)
    print("GPT: QUALITATIVE CHALLENGES")
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
    print("\nLaunching parallel debate: Gemini (quantitative) + GPT (qualitative)...")

    # Run both in parallel
    gemini_result, gpt_result = await asyncio.gather(
        _call_gemini_quantitative(topic, content, dialogue_text),
        _call_gpt_qualitative(topic, content, dialogue_text),
        return_exceptions=True,
    )

    # Handle errors
    gemini_ok = not isinstance(gemini_result, BaseException)
    gpt_ok = not isinstance(gpt_result, BaseException)

    if not gemini_ok:
        print(f"\nGemini error: {gemini_result}")
    if not gpt_ok:
        print(f"\nGPT error: {gpt_result}")

    if not gemini_ok and not gpt_ok:
        print("\nBoth AI calls failed. Check API keys with: config.py show")
        return None, None

    # Save results
    challenges_dir = session_path / "challenges"
    challenges_dir.mkdir(exist_ok=True)

    if gemini_ok:
        gemini_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "mode": "quantitative",
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
            "mode": "qualitative",
            "model": load_config().get("chatgpt_model", "gpt-5.2-chat-latest"),
            "response": gpt_result,
        }
        with open(challenges_dir / "gpt.json", "w", encoding="utf-8") as f:
            json.dump(gpt_record, f, indent=2, ensure_ascii=False)

        _display_gpt_result(gpt_result)

    # Auto-research suggestions
    all_text = ""
    if gemini_ok:
        all_text += json.dumps(gemini_result, ensure_ascii=False) if isinstance(gemini_result, dict) else str(gemini_result)
    if gpt_ok:
        all_text += "\n" + (gpt_result if isinstance(gpt_result, str) else str(gpt_result))
    _extract_tickers_and_suggest(all_text)

    print("\n" + "=" * 60)
    print("PARALLEL DEBATE COMPLETE")
    print("=" * 60)
    print(f"  Gemini (quantitative): {'OK' if gemini_ok else 'FAILED'}")
    print(f"  GPT (qualitative): {'OK' if gpt_ok else 'FAILED'}")
    print(f"\nNext steps:")
    print(f"  debate.py rebuttal --session {session_id}   # Run rebuttal round")
    print(f"  devil.py respond --session {session_id} --text '...'  # Record your response")

    return gemini_result if gemini_ok else None, gpt_result if gpt_ok else None


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

    # Run rebuttals in parallel
    gemini_rebuttal, gpt_rebuttal = await asyncio.gather(
        _call_gemini_rebuttal(gpt_output, topic, content),
        _call_gpt_rebuttal(gemini_output, topic, content),
        return_exceptions=True,
    )

    gemini_ok = not isinstance(gemini_rebuttal, BaseException)
    gpt_ok = not isinstance(gpt_rebuttal, BaseException)

    if not gemini_ok:
        print(f"\nGemini rebuttal error: {gemini_rebuttal}")
    if not gpt_ok:
        print(f"\nGPT rebuttal error: {gpt_rebuttal}")

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

    # Auto-research suggestions from rebuttals
    all_text = ""
    if gemini_ok:
        all_text += json.dumps(gemini_rebuttal, ensure_ascii=False) if isinstance(gemini_rebuttal, dict) else str(gemini_rebuttal)
    if gpt_ok:
        all_text += "\n" + (gpt_rebuttal if isinstance(gpt_rebuttal, str) else str(gpt_rebuttal))
    _extract_tickers_and_suggest(all_text)

    print("\n" + "=" * 60)
    print("REBUTTAL ROUND COMPLETE")
    print("=" * 60)
    print(f"  Gemini rebuttal: {'OK' if gemini_ok else 'FAILED'}")
    print(f"  GPT rebuttal: {'OK' if gpt_ok else 'FAILED'}")
    print(f"  Files saved:")
    if gemini_ok:
        print(f"    {challenges_dir / 'gemini_rebuttal.json'}")
    if gpt_ok:
        print(f"    {challenges_dir / 'gpt_rebuttal.json'}")
    print(f"\nNext steps:")
    print(f"  arbitrate.py compare --session {session_id}   # Compare all AI opinions")
    print(f"  export.py obsidian --session {session_id}      # Export to Obsidian")


async def cmd_full_debate(session_id: str):
    """Full debate: parallel challenges + rebuttal round."""
    print("=" * 60)
    print("FULL DEBATE: Parallel Challenges + Rebuttal")
    print("=" * 60)

    # Phase 1: Parallel challenges
    print("\n--- Phase 1: Parallel Challenges ---\n")
    gemini_result, gpt_result = await cmd_debate_parallel(session_id)

    if gemini_result is None and gpt_result is None:
        print("\nAborting debate: no challenges generated.")
        return

    # Phase 2: Rebuttal round (only if both succeeded)
    if gemini_result is not None and gpt_result is not None:
        print("\n\n--- Phase 2: Rebuttal Round ---\n")
        await cmd_rebuttal(session_id)
    else:
        print("\nSkipping rebuttal: requires both Gemini and GPT challenges.")
        print("Fix the failed API and run: debate.py rebuttal --session ID")


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
        "gemini.json": "Gemini (quantitative)",
        "gpt.json": "GPT (qualitative)",
        "gemini_rebuttal.json": "Gemini rebuttal",
        "gpt_rebuttal.json": "GPT rebuttal",
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
    has_rebuttal_g = (challenges_dir / "gemini_rebuttal.json").exists()
    has_rebuttal_p = (challenges_dir / "gpt_rebuttal.json").exists()

    print()
    if not has_gemini or not has_gpt:
        print(f"Next: debate.py challenge --session {session_id}")
    elif not has_rebuttal_g or not has_rebuttal_p:
        print(f"Next: debate.py rebuttal --session {session_id}")
    else:
        print(f"Debate complete! Next: arbitrate.py compare --session {session_id}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  debate.py run --session ID           # Full debate (challenges + rebuttals)")
        print("  debate.py challenge --session ID      # Parallel challenges only")
        print("  debate.py rebuttal --session ID       # Rebuttal round only")
        print("  debate.py status --session ID         # Show debate status")
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

    # Async commands
    try:
        if command == "run":
            asyncio.run(cmd_full_debate(session_id))
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
