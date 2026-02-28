#!/usr/bin/env python3
"""
Grok Engine - Grok as the primary thinking engine for Socratic Writer.

5 stages:
    grok_engine.py socratic  --session ID [--topic TOPIC]   # Stage 1: Generate 5 probing questions
    grok_engine.py diagnose  --session ID                    # Stage 2: Research diagnosis from Q&A
    grok_engine.py research  --session ID                    # Stage 2b: Auto-execute research tasks
    grok_engine.py synthesize --session ID                   # Stage 4: Digest challenges → 3 tensions
    grok_engine.py evaluate  --session ID --response TEXT    # Stage 5: Evaluate v1→v2 thesis

Grok = thinking engine (questions, diagnosis, synthesis, evaluation)
Claude = pipe (call API, pass context, run scripts, display results)
"""

import asyncio
import json
import logging
import sys
import time

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
import subprocess
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))

# Import session/config modules
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from config import load_config
from session import load_session, save_session, get_session_path


# ============================================================
# Grok API Client
# ============================================================

def _get_grok_client(temperature: float = 0.7):
    """Initialize Grok client. Returns (client, model, temperature)."""
    try:
        from openai import OpenAI

        config = load_config()
        api_key = config.get("grok_api_key")
        if not api_key:
            raise ValueError("Grok API key not configured. Run: config.py set grok_api_key YOUR_KEY")

        model = config.get("grok_model", "grok-4-1-fast-reasoning")
        client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        return client, model, temperature

    except ImportError:
        raise ImportError("openai not installed. Run: pip install openai")


def _call_grok_sync(prompt: str, temperature: float = 0.7, max_retries: int = 3) -> str:
    """Synchronous Grok API call with exponential backoff retry.

    Retries on transient errors (connection, 429, 500/502/503).
    Does NOT retry on client errors (400, 401, 403).
    """
    from openai import APIConnectionError, APIStatusError

    client, model, _ = _get_grok_client(temperature)
    last_exception = None

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return resp.choices[0].message.content
        except APIConnectionError as e:
            last_exception = e
            delay = 2 ** attempt  # 1s, 2s, 4s
            logger.warning("Grok API connection error (attempt %d/%d), retrying in %ds: %s",
                           attempt + 1, max_retries, delay, e)
            time.sleep(delay)
        except APIStatusError as e:
            if e.status_code in (429, 500, 502, 503):
                last_exception = e
                delay = 2 ** attempt
                logger.warning("Grok API status %d (attempt %d/%d), retrying in %ds: %s",
                               e.status_code, attempt + 1, max_retries, delay, e)
                time.sleep(delay)
            else:
                # Client errors (400, 401, 403, etc.) — don't retry
                raise

    # All retries exhausted
    raise last_exception


def _parse_json_response(text: str) -> dict:
    """Extract JSON from response text, with fallback."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed: %s\nRaw response (first 500 chars): %.500s", e, text)
    else:
        # No JSON braces found at all
        logger.warning("No JSON object found in response. Raw response (first 500 chars): %.500s", text)
    return {"raw_response": text}


def _load_dialogue_text(session_path: Path) -> str:
    """Load dialogue as formatted text."""
    dialogue_file = session_path / "dialogue.json"
    if not dialogue_file.exists():
        return ""

    with open(dialogue_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    text = ""
    for entry in data.get("entries", []):
        text += f"Q ({entry.get('type', '?')}): {entry.get('question', '')}\n"
        text += f"A: {entry.get('answer', '')}\n\n"
    return text


# ============================================================
# Prompts
# ============================================================

GROK_SOCRATIC_PROMPT = """你是一个思维教练。你的目标不是挑战用户，而是帮助他把模糊的想法变清晰。

用户的初始想法：
{topic}

{description}

生成恰好 5 个问题。每个问题必须：
- 瞄准一个用户可能没想清楚的点
- 不能是泛泛的"你怎么看 XX"，要具体到能用 1-2 句话回答
- 按从基础到深入的顺序排列

5 种类型（每种恰好 1 个）：
1. 【边界】这个论点的适用边界在哪？什么条件下它不成立？
2. 【假设】这个论点最依赖哪个未验证的假设？
3. 【时间】这个论点的时间框架是什么？6个月和3年后结论一样吗？
4. 【反面】如果完全相反的观点是对的，最可能的原因是什么？
5. 【盲点】你在这个分析中最可能忽略了什么？

严格返回以下 JSON（不要包含 ```json 标记）：

{{
  "questions": [
    {{"type": "边界", "question": "..."}},
    {{"type": "假设", "question": "..."}},
    {{"type": "时间", "question": "..."}},
    {{"type": "反面", "question": "..."}},
    {{"type": "盲点", "question": "..."}}
  ]
}}

用中文回应。"""


GROK_SOCRATIC_REFINE_PROMPT = """你是一个资深对冲基金合伙人，管理过周期股和成长股的组合超过15年。你的同事写了下面这篇文章的初稿，请你帮忙找出文章自身逻辑中的问题。

**你的任务非常具体：找出文章中 5 个最大的内部逻辑矛盾或真正的盲点。**

**严格要求：**
1. 每个反驳必须**直接引用文章中的原文段落**（用引号标注），然后解释这段原文本身的逻辑为什么不自洽，或者它声称能解决的问题为什么其实解决不了
2. 不要用文章没讨论过的行业或案例去反驳——用文章自己举的例子来暴露矛盾
3. 如果文章已经有某个机制来处理某个问题（比如反证条件、承诺追踪），不要假装这个机制不存在——而是说明这个机制为什么在具体场景下仍然不够用
4. 每个反驳 250-350 字，覆盖文章的不同章节
5. 反驳之间不能重复同一个逻辑点

**绝对不要：**
- 提出文章已经有完善对策的反驳
- 用文章没涉及的外部案例来说「框架不适用」——那不是内部矛盾
- 泛泛地说「边界模糊」「假设太强」而不给出具体的逻辑链
- 生成看起来深刻但实际上没有真正读懂文章的反驳

**格式：先引原文，再拆逻辑。**

严格返回以下 JSON（不要包含 ```json 标记）：

{{
  "questions": [
    {{"type": "内部矛盾", "chapter": "涉及章节", "quote": "引用的原文", "question": "完整反驳（250-350字）"}},
    {{"type": "内部矛盾", "chapter": "涉及章节", "quote": "引用的原文", "question": "完整反驳（250-350字）"}},
    {{"type": "内部矛盾", "chapter": "涉及章节", "quote": "引用的原文", "question": "完整反驳（250-350字）"}},
    {{"type": "内部矛盾", "chapter": "涉及章节", "quote": "引用的原文", "question": "完整反驳（250-350字）"}},
    {{"type": "内部矛盾", "chapter": "涉及章节", "quote": "引用的原文", "question": "完整反驳（250-350字）"}}
  ]
}}

文章全文：

{topic}

用中文回应。"""


GROK_RESEARCH_DIAGNOSIS_PROMPT = """你是研究主管。读完以下论点和 Q&A，诊断哪些说法需要数据支撑。

主题：{topic}

Q&A 记录：
{dialogue}

输出 JSON，只列真正需要验证的（不超过 5 项）：

{{
  "research_tasks": [
    {{
      "claim": "用户说了什么（引用原话）",
      "what_to_verify": "具体要查什么",
      "source": "local|nlm|13f|web",
      "query": "搜索关键词或具体查询语句",
      "priority": "high|medium"
    }}
  ]
}}

source 路由规则：
- local: 搜 Obsidian vault 和本地文件（财报分析、thesis、研究笔记）
- nlm: 查 NotebookLM（适合从 earnings transcript 找管理层原话）
- 13f: 查 13F 持仓数据（持仓重合度、机构增减仓、拥挤度）
- web: 需要外部最新数据（市场共识、最新新闻、行业数据）

规则：
- 不要列"可能有用"的研究，只列"不查就有硬伤"的
- query 字段要足够具体，让搜索引擎能直接执行
- 如果 Q&A 中用户已经给出了数据来源，不需要再查

用中文回应。"""


GROK_SYNTHESIS_PROMPT = """你是辩论的首席仲裁官。你刚旁听了一场多方辩论（含魔鬼代言人）。

你的任务不是再提新挑战。你的任务是帮助作者消化这些挑战，找出最关键的未解决矛盾。

原始论点：
主题：{topic}
摘要：{summary}

用户的 Q&A：
{dialogue}

{research_section}

三方协同分析：

--- Gemini（假设核查）---
{gemini_challenge}

--- GPT（框架连接）---
{gpt_challenge}

--- Grok（盲点扫描）---
{grok_challenge}

--- Grok 魔鬼代言人（针对用户论点）---
{advocate_challenge}

{rebuttal_section}

输出 JSON：

{{
  "unresolved_tensions": [
    {{
      "tension": "一句话描述这个未解决的矛盾",
      "from": "gemini|gpt|grok|multiple",
      "why_it_matters": "为什么这个矛盾对最终结论最重要",
      "focused_question": "向作者提的一个聚焦问题（可以用1-2句话回答）"
    }}
  ],
  "resolved_points": [
    "辩论中已经充分解决的点（不需要再讨论）"
  ],
  "thesis_strength": {{
    "score": 7,
    "strongest_point": "论点最强的地方",
    "weakest_point": "论点最弱的地方",
    "one_thing_to_change": "如果只能修改一个假设，应该改哪个？"
  }}
}}

规则：
- unresolved_tensions 最多 3 个（聚焦！不要面面俱到）
- 每个 focused_question 必须具体到能用 1-2 句话回答
- 不要客气，不要"总体不错但是..."，直接说最重要的矛盾
- score 评分：1-3 核心硬伤 / 4-6 关键假设未验证 / 7-8 论点扎实 / 9-10 可直接行动

用中文回应。"""


GROK_EVALUATION_PROMPT = """用户的论点经历了以下演变：

v1（初始论点）：
主题：{topic}
摘要：{summary}

苏格拉底问答回答：
{dialogue}

多方分析产生的核心张力：
{tensions}

用户对张力的回应（v2）：
{user_response}

评估 v1 → v2 的演变。

输出 JSON：

{{
  "improvements": ["v2 比 v1 好在哪里（具体列出）"],
  "remaining_weaknesses": ["v2 仍然没有解决的问题"],
  "new_risks": ["v2 引入的新风险（如果有）"],
  "final_score": 7,
  "verdict": "ready|needs_work|fundamental_flaw",
  "recommendation": "一句话建议下一步做什么"
}}

评分标准：
- 1-3: 核心逻辑有硬伤，不应基于此行动
- 4-6: 方向对但关键假设未验证，需要更多研究
- 7-8: 论点扎实，有明确的风险边界，可以作为工作假说
- 9-10: 论证完备，可以直接转化为行动

verdict 判定：
- ready: score ≥ 7，论点可以用了
- needs_work: score 4-6，建议继续迭代
- fundamental_flaw: score ≤ 3，需要从头审视

用中文回应。"""


# ============================================================
# Stage 1: Socratic Questions
# ============================================================

def cmd_socratic(session_id: str, topic: str = None, mode: str = None):
    """Generate 5 probing questions via Grok.

    Auto-detects mode based on input length:
    - Short input (<500 chars): 'explore' mode — generic probing for unclear ideas
    - Long input (>=500 chars): 'refine' mode — quote-based internal contradiction analysis

    Can be overridden with --mode explore|refine.
    """
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    topic = topic or state.get("topic", "")
    summary = state.get("summary", "")
    description = summary if summary else "(用户尚未展开描述)"

    # Auto-detect mode: long input = article refinement, short = idea exploration
    REFINE_THRESHOLD = 500  # characters
    input_length = len(topic) + len(description)
    if mode is None:
        mode = "refine" if input_length >= REFINE_THRESHOLD else "explore"

    print(f"Session: {session_id}")
    print(f"Topic: {topic[:100]}{'...' if len(topic) > 100 else ''}")
    print(f"Mode: {mode} (input length: {input_length} chars)")

    if mode == "refine":
        print("\nGrok is analyzing article for internal contradictions (temp=0.5)...")
        prompt = GROK_SOCRATIC_REFINE_PROMPT.format(topic=topic)
        raw = _call_grok_sync(prompt, temperature=0.5)
    else:
        print("\nGrok is generating 5 probing questions (temp=0.7)...")
        prompt = GROK_SOCRATIC_PROMPT.format(topic=topic, description=description)
        raw = _call_grok_sync(prompt, temperature=0.7)
    result = _parse_json_response(raw)

    questions = result.get("questions", [])
    if not questions:
        print("\nFailed to parse structured questions. Raw response:")
        print(raw)
        # Save raw anyway
        _save_grok_output(session_id, "socratic", {"raw_response": raw})
        return

    # Display
    print("\n" + "=" * 60)
    print("GROK: 5 PROBING QUESTIONS")
    print("=" * 60)

    for i, q in enumerate(questions, 1):
        qtype = q.get("type", "?")
        question = q.get("question", "")
        print(f"\n  [{i}] 【{qtype}】{question}")

    print("\n" + "=" * 60)

    # Save to session
    _save_grok_output(session_id, "socratic", result)

    # Update session phase
    state["phase"] = "exploration"
    save_session(session_id, state)

    print(f"\nNext: User answers these 5 questions.")
    print(f"  Use session.py add-dialogue for each Q&A pair.")
    print(f"  Then: grok_engine.py diagnose --session {session_id}")

    return result


# ============================================================
# Stage 2: Research Diagnosis
# ============================================================

def cmd_diagnose(session_id: str):
    """Analyze Q&A and produce structured research task list."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)
    dialogue_text = _load_dialogue_text(session_path)

    if not dialogue_text:
        print("No dialogue entries yet. Run socratic + collect answers first.")
        return

    topic = state.get("topic", "")

    print(f"Session: {session_id}")
    print(f"Topic: {topic}")
    print("\nGrok is diagnosing research gaps (temp=0.3)...")

    prompt = GROK_RESEARCH_DIAGNOSIS_PROMPT.format(
        topic=topic,
        dialogue=dialogue_text,
    )
    raw = _call_grok_sync(prompt, temperature=0.3)
    result = _parse_json_response(raw)

    tasks = result.get("research_tasks", [])
    if not tasks:
        print("\nNo research tasks identified (or parse failed). Raw:")
        print(raw)
        _save_grok_output(session_id, "diagnosis", {"raw_response": raw})
        return

    # Display
    print("\n" + "=" * 60)
    print("GROK: RESEARCH DIAGNOSIS")
    print("=" * 60)

    for i, t in enumerate(tasks, 1):
        priority = t.get("priority", "?").upper()
        source = t.get("source", "?")
        print(f"\n  [{priority}] Task {i}: {t.get('what_to_verify', '')}")
        print(f"  Claim: \"{t.get('claim', '')}\"")
        print(f"  Source: {source}")
        print(f"  Query: {t.get('query', '')}")

    print("\n" + "=" * 60)

    # Save
    session_path = get_session_path(session_id)
    research_dir = session_path / "research"
    research_dir.mkdir(exist_ok=True)

    diagnosis_file = research_dir / "diagnosis.json"
    with open(diagnosis_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "result": result,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {diagnosis_file}")
    print(f"\nNext:")
    print(f"  grok_engine.py research --session {session_id}   # Auto-execute research tasks")
    print(f"  debate.py run --session {session_id}              # Skip to debate")

    # Update phase
    state["phase"] = "deepening"
    save_session(session_id, state)

    return result


# ============================================================
# Stage 2b: Auto-execute Research Tasks
# ============================================================

def cmd_auto_research(session_id: str):
    """Execute research tasks from diagnosis, routing to appropriate tools."""
    session_path = get_session_path(session_id)
    diagnosis_file = session_path / "research" / "diagnosis.json"

    if not diagnosis_file.exists():
        print(f"No diagnosis found. Run: grok_engine.py diagnose --session {session_id}")
        return

    with open(diagnosis_file, "r", encoding="utf-8") as f:
        diagnosis = json.load(f)

    tasks = diagnosis.get("result", {}).get("research_tasks", [])
    if not tasks:
        print("No research tasks in diagnosis.")
        return

    print(f"Session: {session_id}")
    print(f"Executing {len(tasks)} research tasks...\n")

    results = []
    for i, task in enumerate(tasks, 1):
        source = task.get("source", "local")
        query = task.get("query", "")
        priority = task.get("priority", "medium")

        print(f"[{i}/{len(tasks)}] [{source.upper()}] {task.get('what_to_verify', '')}")
        print(f"  Query: {query}")

        result_entry = {
            "task": task,
            "status": "pending",
            "output": None,
        }

        if source == "local":
            # Use research.py local
            try:
                from research import cmd_local
                res = cmd_local(query, session_id)
                result_entry["status"] = "done" if res else "no_results"
                result_entry["output"] = f"Found {len(res)} files" if res else "No matches"
            except Exception as e:
                result_entry["status"] = "error"
                result_entry["output"] = str(e)
                print(f"  Error: {e}")

        elif source == "nlm":
            # Use research.py nlm
            try:
                from research import cmd_nlm
                res = cmd_nlm(query, session_id)
                result_entry["status"] = "done" if res else "no_results"
                result_entry["output"] = res[:500] if res else "No response"
            except Exception as e:
                result_entry["status"] = "error"
                result_entry["output"] = str(e)
                print(f"  Error: {e}")

        elif source == "13f":
            # Route to 13f_query
            print(f"  → 13F query. Claude should run: 13f_query.py for '{query}'")
            result_entry["status"] = "needs_claude"
            result_entry["output"] = f"13F query needed: {query}"

        elif source == "web":
            # Claude does web search
            print(f"  → Web search. Claude should use WebSearch for: '{query}'")
            result_entry["status"] = "needs_claude"
            result_entry["output"] = f"Web search needed: {query}"

        results.append(result_entry)
        print()

    # Save research execution results
    exec_file = session_path / "research" / "research_execution.json"
    with open(exec_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    # Summary
    done = sum(1 for r in results if r["status"] == "done")
    needs_claude = sum(1 for r in results if r["status"] == "needs_claude")
    errors = sum(1 for r in results if r["status"] == "error")

    print("=" * 60)
    print("RESEARCH EXECUTION SUMMARY")
    print("=" * 60)
    print(f"  Completed: {done}")
    print(f"  Needs Claude: {needs_claude}")
    print(f"  Errors: {errors}")

    if needs_claude > 0:
        print(f"\n  Claude needs to handle {needs_claude} task(s) manually:")
        for r in results:
            if r["status"] == "needs_claude":
                print(f"    - [{r['task']['source']}] {r['task']['query']}")

    print(f"\nNext: debate.py run --session {session_id}")

    return results


# ============================================================
# Stage 4: Synthesis (after debate)
# ============================================================

def cmd_synthesize(session_id: str):
    """Digest all challenge files and extract 3 key tensions."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)
    challenges_dir = session_path / "challenges"

    # Load challenge files
    gemini_challenge = _load_challenge_text(challenges_dir / "gemini.json", "result")
    gpt_challenge = _load_challenge_text(challenges_dir / "gpt.json", "response")
    grok_challenge = _load_challenge_text(challenges_dir / "grok.json", "response")
    advocate_challenge = _load_challenge_text(challenges_dir / "grok_advocate.json", "response")

    if not gemini_challenge and not gpt_challenge and not grok_challenge:
        print("No challenge files found. Run debate.py first.")
        return

    # Load rebuttals (optional)
    rebuttal_section = ""
    gemini_reb = _load_challenge_text(challenges_dir / "gemini_rebuttal.json", "result")
    gpt_reb = _load_challenge_text(challenges_dir / "gpt_rebuttal.json", "response")
    grok_reb = _load_challenge_text(challenges_dir / "grok_rebuttal.json", "response")

    if gemini_reb or gpt_reb or grok_reb:
        rebuttal_section = "交叉反驳：\n"
        if gemini_reb:
            rebuttal_section += f"\n--- Gemini 反驳 ---\n{gemini_reb}\n"
        if gpt_reb:
            rebuttal_section += f"\n--- GPT 反驳 ---\n{gpt_reb}\n"
        if grok_reb:
            rebuttal_section += f"\n--- Grok 反驳 ---\n{grok_reb}\n"

    # Load research results (optional)
    research_section = ""
    research_log = session_path / "research" / "research_log.json"
    if research_log.exists():
        with open(research_log, "r", encoding="utf-8") as f:
            log = json.load(f)
        entries = log.get("entries", [])
        if entries:
            research_section = "研究发现：\n"
            for e in entries[:5]:
                research_section += f"- [{e['source']}] {e['query']}: {(e.get('response', '') or '')[:200]}\n"

    dialogue_text = _load_dialogue_text(session_path)
    topic = state.get("topic", "")
    summary = state.get("summary", "")

    print(f"Session: {session_id}")
    print(f"Topic: {topic}")

    # --- Pre-synthesis collective delusion detection ---
    delusion_result = None
    blind_spot_injection = ""
    challenge_texts = {
        "Gemini": gemini_challenge,
        "GPT": gpt_challenge,
        "Grok": grok_challenge,
        "Advocate": advocate_challenge,
    }
    # Only run if at least 2 challenges exist
    available = {k: v for k, v in challenge_texts.items() if v}
    if len(available) >= 2:
        print("\nRunning collective delusion detection...")
        delusion_result = _detect_collective_delusion(available)

        conv_pct = delusion_result.get("convergence_pct", 0)
        print(f"  Convergence: {conv_pct}%", end="")

        if delusion_result.get("delusion_warning"):
            print("  *** >80% — injecting meta-cognitive prompt ***")
            never_mentioned = delusion_result.get("themes_never_mentioned", [])
            blind_spot_injection = (
                f"\n\n⚠️ 集体谬误预警：AI分析师的主题收敛度为 {conv_pct}%（超过80%阈值）。"
                f"\n从未被任何AI提及的主题维度：{', '.join(never_mentioned) if never_mentioned else '无'}。"
                f"\n在提炼核心张力之前，请先回答：如果所有分析师都错了，最可能的共同盲点是什么？"
                f"\n请在输出的 unresolved_tensions 中优先包含一个关于集体盲点的张力。\n"
            )
        else:
            print("  (OK — below 80% threshold)")

        # Save delusion check
        synthesis_dir = session_path / "synthesis"
        synthesis_dir.mkdir(exist_ok=True)
        delusion_file = synthesis_dir / "delusion_check.json"
        with open(delusion_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "result": delusion_result,
            }, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {delusion_file}")

    print("\nGrok is synthesizing debate results (temp=0.5)...")

    prompt = GROK_SYNTHESIS_PROMPT.format(
        topic=topic,
        summary=summary or "(no summary yet)",
        dialogue=dialogue_text or "(no dialogue)",
        research_section=research_section or "(no research)",
        gemini_challenge=gemini_challenge or "(not available)",
        gpt_challenge=gpt_challenge or "(not available)",
        grok_challenge=grok_challenge or "(not available)",
        advocate_challenge=advocate_challenge or "(not available)",
        rebuttal_section=rebuttal_section or "(no rebuttals)",
    )

    # Inject blind spot warning if delusion detected
    if blind_spot_injection:
        prompt = blind_spot_injection + "\n" + prompt

    raw = _call_grok_sync(prompt, temperature=0.5)
    result = _parse_json_response(raw)

    tensions = result.get("unresolved_tensions", [])
    thesis = result.get("thesis_strength", {})

    # Display
    print("\n" + "=" * 60)
    print("GROK: SYNTHESIS & KEY TENSIONS")
    print("=" * 60)

    if thesis:
        score = thesis.get("score", "?")
        print(f"\n  Thesis Strength: {score}/10")
        print(f"  Strongest: {thesis.get('strongest_point', 'N/A')}")
        print(f"  Weakest: {thesis.get('weakest_point', 'N/A')}")
        print(f"  One thing to change: {thesis.get('one_thing_to_change', 'N/A')}")

    resolved = result.get("resolved_points", [])
    if resolved:
        print(f"\n  Resolved (no further discussion needed):")
        for r in resolved:
            print(f"    ✓ {r}")

    if tensions:
        print(f"\n  {'─' * 56}")
        print(f"  UNRESOLVED TENSIONS ({len(tensions)})")
        print(f"  {'─' * 56}")

        for i, t in enumerate(tensions, 1):
            print(f"\n  Tension {i}: {t.get('tension', '')}")
            print(f"  Source: {t.get('from', '?')}")
            print(f"  Why it matters: {t.get('why_it_matters', '')}")
            print(f"  → QUESTION: {t.get('focused_question', '')}")
    else:
        print("\n  No structured tensions found. Raw response:")
        print(raw[:1000])

    print("\n" + "=" * 60)

    # Save
    synthesis_dir = session_path / "synthesis"
    synthesis_dir.mkdir(exist_ok=True)

    tensions_file = synthesis_dir / "tensions.json"
    with open(tensions_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "result": result,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {tensions_file}")

    # Update phase
    state["phase"] = "challenging"
    save_session(session_id, state)

    print(f"\nNext: User responds to the {len(tensions)} tension(s) above.")
    print(f"  Then: grok_engine.py evaluate --session {session_id} --response 'your response'")

    return result


# ============================================================
# Stage 5: Evaluation
# ============================================================

def cmd_evaluate(session_id: str, user_response: str):
    """Evaluate user's response to tensions (v1→v2 comparison)."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)

    # Load tensions
    tensions_file = session_path / "synthesis" / "tensions.json"
    if not tensions_file.exists():
        print(f"No synthesis found. Run: grok_engine.py synthesize --session {session_id}")
        return

    with open(tensions_file, "r", encoding="utf-8") as f:
        tensions_data = json.load(f)

    tensions = tensions_data.get("result", {})
    tensions_text = json.dumps(tensions.get("unresolved_tensions", []), ensure_ascii=False, indent=2)

    dialogue_text = _load_dialogue_text(session_path)
    topic = state.get("topic", "")
    summary = state.get("summary", "")

    print(f"Session: {session_id}")
    print(f"Topic: {topic}")
    print("\nGrok is evaluating thesis evolution v1→v2 (temp=0.3)...")

    prompt = GROK_EVALUATION_PROMPT.format(
        topic=topic,
        summary=summary or "(no summary yet)",
        dialogue=dialogue_text or "(no dialogue)",
        tensions=tensions_text,
        user_response=user_response,
    )

    raw = _call_grok_sync(prompt, temperature=0.3)
    result = _parse_json_response(raw)

    # Display
    print("\n" + "=" * 60)
    print("GROK: THESIS EVALUATION (v1 → v2)")
    print("=" * 60)

    score = result.get("final_score", "?")
    verdict = result.get("verdict", "?")

    print(f"\n  Final Score: {score}/10")
    print(f"  Verdict: {verdict.upper()}")

    improvements = result.get("improvements", [])
    if improvements:
        print(f"\n  Improvements:")
        for imp in improvements:
            print(f"    ✓ {imp}")

    remaining = result.get("remaining_weaknesses", [])
    if remaining:
        print(f"\n  Remaining Weaknesses:")
        for w in remaining:
            print(f"    ✗ {w}")

    new_risks = result.get("new_risks", [])
    if new_risks:
        print(f"\n  New Risks Introduced:")
        for r in new_risks:
            print(f"    ⚠ {r}")

    recommendation = result.get("recommendation", "")
    if recommendation:
        print(f"\n  Recommendation: {recommendation}")

    print("\n" + "=" * 60)

    # Save
    synthesis_dir = session_path / "synthesis"
    synthesis_dir.mkdir(exist_ok=True)

    # Save user response
    response_file = synthesis_dir / "user_response.json"
    with open(response_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "response": user_response,
        }, f, indent=2, ensure_ascii=False)

    # Save evaluation
    eval_file = synthesis_dir / "evaluation.json"
    with open(eval_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "result": result,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {eval_file}")

    # Update session
    state["phase"] = "drafting" if verdict == "ready" else "challenging"
    save_session(session_id, state)

    # Next steps based on verdict
    if verdict == "ready":
        print(f"\nThesis is ready! Next:")
        print(f"  export.py obsidian --session {session_id}")
    elif verdict == "needs_work":
        print(f"\nThesis needs more work. Options:")
        print(f"  1. grok_engine.py synthesize --session {session_id}  # Re-synthesize with new context")
        print(f"  2. debate.py challenge --session {session_id}        # Run targeted challenge")
        print(f"  3. export.py obsidian --session {session_id}         # Export as-is (draft)")
    else:
        print(f"\nFundamental issues detected. Consider:")
        print(f"  1. Revisit core assumptions")
        print(f"  2. grok_engine.py socratic --session {session_id}    # Start fresh Q&A round")

    return result


# ============================================================
# Helpers
# ============================================================

def _load_challenge_text(filepath: Path, key: str) -> str:
    """Load a challenge file and return its main content as string."""
    if not filepath.exists():
        return ""

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = data.get(key, "")
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content) if content else ""


def _detect_collective_delusion(challenges: dict) -> dict:
    """Analyze convergence across AI challenge outputs.

    Uses Jaccard similarity on extracted themes. If >80% convergence,
    flags a collective delusion warning.

    Args:
        challenges: dict of {ai_name: challenge_text_or_dict}

    Returns:
        dict with convergence_pct, shared/unique themes, delusion_warning bool.
    """
    themes_by_ai = {}

    # General-purpose theme keywords (not investment-specific)
    theme_keywords = {
        "causality": ["因果", "causality", "cause", "导致", "因为", "原因", "驱动"],
        "evidence": ["证据", "evidence", "数据", "data", "验证", "实证", "来源"],
        "time": ["时间", "time", "周期", "timing", "短期", "长期", "窗口", "deadline"],
        "stakeholder": ["利益相关", "stakeholder", "用户", "客户", "受众", "影响"],
        "assumption": ["假设", "assumption", "前提", "隐含", "默认", "前置条件"],
        "incentive": ["激励", "incentive", "动机", "利益", "motivation", "驱动力"],
        "constraint": ["约束", "constraint", "限制", "瓶颈", "bottleneck", "边界"],
        "second_order": ["二阶", "second.order", "间接", "反馈", "连锁", "涟漪"],
        "alternative": ["替代", "alternative", "备选", "另一种", "反面", "相反"],
        "execution": ["执行", "execution", "实施", "落地", "操作", "可行"],
    }

    for ai_name, data in challenges.items():
        if data is None:
            continue

        if isinstance(data, dict):
            text = json.dumps(data, ensure_ascii=False)
        else:
            text = str(data)

        text_lower = text.lower()
        themes = set()
        for theme, keywords in theme_keywords.items():
            if any(kw.lower() in text_lower for kw in keywords):
                themes.add(theme)

        themes_by_ai[ai_name] = themes

    if len(themes_by_ai) < 2:
        return {"convergence_pct": 0, "delusion_warning": False,
                "error": "Need at least 2 AI outputs to compare"}

    # Pairwise Jaccard similarity
    ai_names = list(themes_by_ai.keys())
    pairwise_scores = {}
    for i in range(len(ai_names)):
        for j in range(i + 1, len(ai_names)):
            a, b = ai_names[i], ai_names[j]
            themes_a, themes_b = themes_by_ai[a], themes_by_ai[b]
            union = themes_a | themes_b
            overlap = len(themes_a & themes_b) / len(union) if union else 0.0
            pairwise_scores[f"{a}_vs_{b}"] = {
                "jaccard": round(overlap, 3),
                "shared": sorted(list(themes_a & themes_b)),
                "unique_to_first": sorted(list(themes_a - themes_b)),
                "unique_to_second": sorted(list(themes_b - themes_a)),
            }

    # Global convergence: themes shared by ALL / themes covered by ANY
    all_themes = set()
    for t in themes_by_ai.values():
        all_themes |= t

    shared_by_all = set.intersection(*themes_by_ai.values()) if themes_by_ai else set()
    convergence_pct = round(len(shared_by_all) / len(all_themes) * 100, 1) if all_themes else 0

    # Themes never mentioned by any AI
    all_possible = set(theme_keywords.keys())
    never_mentioned = all_possible - all_themes

    return {
        "convergence_pct": convergence_pct,
        "themes_shared_by_all": sorted(list(shared_by_all)),
        "themes_never_mentioned": sorted(list(never_mentioned)),
        "total_themes_covered": len(all_themes),
        "total_possible_themes": len(all_possible),
        "pairwise": pairwise_scores,
        "themes_by_ai": {k: sorted(list(v)) for k, v in themes_by_ai.items()},
        "delusion_warning": convergence_pct > 80,
    }


def _save_grok_output(session_id: str, stage: str, result: dict):
    """Save Grok output to synthesis directory."""
    session_path = get_session_path(session_id)
    synthesis_dir = session_path / "synthesis"
    synthesis_dir.mkdir(exist_ok=True)

    output_file = synthesis_dir / f"grok_{stage}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "stage": stage,
            "result": result,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {output_file}")


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Grok Engine - Primary thinking engine for Socratic Writer")
        print()
        print("Usage:")
        print("  grok_engine.py socratic  --session ID [--topic TOPIC]  # 5 probing questions")
        print("  grok_engine.py diagnose  --session ID                  # Research diagnosis")
        print("  grok_engine.py research  --session ID                  # Auto-execute research")
        print("  grok_engine.py synthesize --session ID                 # Digest debates → tensions")
        print("  grok_engine.py evaluate  --session ID --response TEXT  # Evaluate v1→v2")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = topic = response = mode = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--topic" and i + 1 < len(sys.argv):
            topic = sys.argv[i + 1]
        if arg == "--response" and i + 1 < len(sys.argv):
            response = sys.argv[i + 1]
        if arg == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]

    if not session_id:
        print("Error: --session is required")
        return

    try:
        if command == "socratic":
            cmd_socratic(session_id, topic, mode)
        elif command == "diagnose":
            cmd_diagnose(session_id)
        elif command == "research":
            cmd_auto_research(session_id)
        elif command == "synthesize":
            cmd_synthesize(session_id)
        elif command == "evaluate":
            if not response:
                print("Error: --response is required for evaluate")
                print("Usage: grok_engine.py evaluate --session ID --response 'your response text'")
                return
            cmd_evaluate(session_id, response)
        else:
            print(f"Unknown command: {command}")
    except ValueError as e:
        print(f"Error: {e}")
    except ImportError as e:
        print(f"Missing dependency: {e}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
