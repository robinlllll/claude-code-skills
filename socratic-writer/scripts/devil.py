#!/usr/bin/env python3
"""
Devil's Advocate - Gemini-powered challenger.
Generates challenges, counterarguments, and stress-tests your ideas.
"""

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

# Import config
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from config import load_config
from session import load_session, get_session_path

DEVIL_PROMPT = """你是一位资深的投资分析魔鬼代言人。你的使命不是泛泛质疑，而是像对冲基金的首席风控官一样，对论点进行系统性的压力测试——找出会让这个投资论点彻底失败的关键断裂点。

## 你的思维框架

**第一层：锁定可挑战点**
不要攻击整体论点。从用户论述中识别核心主张，提炼出 4-6 个具体的可挑战点（直接引用原文或其关键推论）。一个主张可以从不同角度产生多个挑战。质量优先于数量——4个尖锐的挑战胜过6个平庸的。

**第二层：多层穿透**
对每个可挑战点，你必须完成三步穿透：
1. **表面质疑**：最显而易见的反驳
2. **深层质疑**：用户大概率没想到的二阶效应或结构性问题——写清因果链。如果其他行业存在高度相似的结构性模式，在此处引入跨领域类比来揭示盲点。
3. **钢铁人反论**：站在对手方最聪明的人的立场，构建他们能提出的最强反驳。测试标准：如果用户读了不感到一丝不舒服，说明你写得不够好

**第三层：结构性诊断**
跳出个别主张，审视整个论证的推理模式：
- 用户是否犯了可命名的认知偏误？（锚定效应、幸存者偏差、基率忽视、确认偏误、叙事谬误、后视偏差等——必须指名道姓，并解释为什么在这个具体语境下它是危险的）
- 哪些利益相关者的视角完全缺席？他们会怎么看这个问题？
- 论证的时间维度是否自洽？（是否混淆了短期催化剂和长期结构性趋势？）
- 这个论点是否可证伪？如果没有任何证据能改变用户想法，那论点本身就有问题

## 输出格式

严格返回以下 JSON（不要包含 ```json 标记，不要在 JSON 外写任何文字）：

{{{{
  "challenges": [
    {{{{
      "type": "选择最贴切的类型，例如：假设质疑、逻辑漏洞、反面证据、风险盲点、替代解释、基率谬误、时间错配、因果倒置等",
      "target_claim": "直接引用用户的原话",
      "surface_challenge": "最直接的反驳——一句话点明要害",
      "deeper_challenge": "用户大概率没想到的二阶问题。必须写清因果链：A导致B，B导致C，所以用户的结论D不成立。如有合适的跨领域类比，在此融入。",
      "steel_man_counter": "对手方最聪明的人会怎么反驳？这个反论点必须逻辑自洽、有据可查，让用户读了不舒服",
      "evidence_request": "要验证或反驳这个挑战，具体应该查什么？指明：数据源名称、具体指标、时间范围（例如：'查Bloomberg上NVDA过去5年capex/revenue比率，对比AMD和INTC同期数据'）",
      "historical_parallel": "历史上类似推理导致失败的具体案例。必须包含：公司/事件名称、年份、当时的主流叙事、实际结果、与当前情况的关键相似点",
      "severity": "minor|major|critical"
    }}}}
  ],
  "structural_critique": {{{{
    "reasoning_pattern": "用户使用的推理模式名称，以及为什么在这个具体语境下它是危险的",
    "missing_stakeholders": "这个分析完全忽略了谁的视角？他们会怎么看这个问题？具体描述。",
    "time_horizon_mismatch": "论证中是否存在时间维度的混淆？短期逻辑和长期逻辑是否矛盾？如果没有则写'未发现'。",
    "unfalsifiability_check": "什么样的具体、可观察的证据会让用户改变主意？如果这个问题很难回答，这本身就是最大的红旗。"
  }}}},
  "kill_scenario": "描述一个具体的、合理的（>5%概率）灰犀牛场景。格式：触发事件（什么时候、什么条件下发生）→ 因果链（第一步、第二步、第三步）→ 最终结果（对论点的具体影响）→ 时间框架（多久内会显现）。不要写黑天鹅，要写看得见但被低估的风险。",
  "confidence_calibration": {{{{
    "devil_rating": 5,
    "rating_rationale": "对评分的一句话解释",
    "weakest_link": "整个论证链中最薄弱的一环——如果这一个主张被证伪，其他所有论点都将失去支撑。明确指出是哪个。",
    "suggested_bet": "如果用户真的相信自己的论点，他应该愿意做出什么可在6个月内验证的具体预测？格式：'到YYYY年MM月，[具体可量化的预测]'。"
  }}}}
}}}}

## 核心规则

1. **严重性递进**：challenges 列表必须按 severity 从 minor → major → critical 排序，呈现逐步加压的节奏感。
2. **禁止泛泛而谈**：每个挑战必须引用或指向用户的具体原话。"市场可能崩盘"、"宏观环境可能变化"这类话永远不要说。
3. **禁止重复包装**：5个换了措辞的同一质疑，不如1个真正尖锐的新角度。每个挑战必须攻击不同的维度。
4. **禁止重述用户的不确定性**：如果用户已经表达了对某事的疑虑，不要把它包装成你的挑战。你的工作是发现用户自己没看到的盲点，而非重复他已知的弱点。除非你能挖掘出该不确定性背后更深层的、用户未提及的结构性风险。
5. **历史案例必须具体**：必须包含公司/事件名称、年份、当时的主流叙事、实际结果。"历史上有过类似情况"不算。优先引用非近年（2020年之前）的案例以避免近因偏差。
6. **钢铁人必须让人不舒服**：如果这个反论点读起来像稻草人，重写。测试：一个聪明的对手方真的会这样论述吗？
7. **devil_rating 范围**：devil_rating 字段必须是 1 到 10 的整数。1=论证极其脆弱；5=有道理但关键假设未验证；10=极其稳固。

## 现在开始

---
主题：{topic}

当前论点和内容：
{content}

问答历史：
{dialogue}
---

用中文回应。"""


def get_gemini_client():
    """Initialize Gemini client."""
    try:
        import google.generativeai as genai

        config = load_config()
        api_key = config.get("gemini_api_key")

        if not api_key:
            print("Error: Gemini API key not configured.")
            print("Run: python run.py config.py set-gemini-key YOUR_API_KEY")
            return None

        genai.configure(api_key=api_key)
        # Use configured model, default to gemini-3-pro-preview
        model_name = config.get("gemini_model", "gemini-3-pro-preview")
        return genai.GenerativeModel(model_name)

    except ImportError:
        print("Error: google-generativeai not installed. Run setup first.")
        return None


def cmd_challenge(session_id: str):
    """Generate challenges for a session's current content."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)

    # Load dialogue
    dialogue_file = session_path / "dialogue.json"
    if not dialogue_file.exists():
        print("No dialogue found in session.")
        return

    with open(dialogue_file, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    # Format dialogue for prompt
    dialogue_text = ""
    for entry in dialogue_data.get("entries", []):
        dialogue_text += f"Q ({entry.get('type', 'unknown')}): {entry.get('question', '')}\n"
        dialogue_text += f"A: {entry.get('answer', '')}\n\n"

    if not dialogue_text:
        print("No dialogue entries yet. Start with Socratic questioning first.")
        return

    # Get Gemini client
    model = get_gemini_client()
    if not model:
        return

    # Build prompt
    prompt = DEVIL_PROMPT.format(
        topic=state.get("topic", "Unknown"),
        content=state.get("summary", ""),
        dialogue=dialogue_text
    )

    print("Consulting Gemini Devil's Advocate...")

    try:
        response = model.generate_content(prompt)
        result_text = response.text

        # Try to parse as JSON
        try:
            # Find JSON in response
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(result_text[start:end])
            else:
                result = {"raw_response": result_text}
        except json.JSONDecodeError:
            result = {"raw_response": result_text}

        # Save challenges
        challenges_dir = session_path / "challenges"
        challenges_dir.mkdir(exist_ok=True)

        challenge_record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "result": result,
            "responses": []  # User will fill this
        }

        with open(challenges_dir / "gemini.json", "w", encoding="utf-8") as f:
            json.dump(challenge_record, f, indent=2, ensure_ascii=False)

        # Display results
        print("\n" + "=" * 60)
        print("DEVIL'S ADVOCATE CHALLENGES")
        print("=" * 60)

        if "challenges" in result:
            for i, c in enumerate(result["challenges"], 1):
                severity = c.get('severity', '?').upper()
                print(f"\n{'='*60}")
                print(f"  [{severity}] 挑战 {i}: {c.get('type', 'N/A')}")
                print(f"{'='*60}")
                print(f"  目标主张: \"{c.get('target_claim', 'N/A')}\"")
                print(f"\n  表面质疑: {c.get('surface_challenge', 'N/A')}")
                print(f"\n  深层质疑: {c.get('deeper_challenge', 'N/A')}")
                print(f"\n  钢铁人反论: {c.get('steel_man_counter', 'N/A')}")
                print(f"\n  验证方法: {c.get('evidence_request', 'N/A')}")
                hp = c.get("historical_parallel", "N/A")
                if isinstance(hp, dict):
                    print(f"\n  历史案例: {hp.get('company_event', '')} ({hp.get('year', '')})")
                    print(f"    当时叙事: {hp.get('mainstream_narrative', '')}")
                    print(f"    实际结果: {hp.get('actual_result', '')}")
                    print(f"    相似点: {hp.get('key_similarity', '')}")
                else:
                    print(f"\n  历史案例: {hp}")

            # Structural critique
            sc = result.get("structural_critique", {})
            if sc:
                print(f"\n{'='*60}")
                print("  结构性诊断")
                print(f"{'='*60}")
                print(f"  推理模式: {sc.get('reasoning_pattern', 'N/A')}")
                print(f"  缺失视角: {sc.get('missing_stakeholders', 'N/A')}")
                print(f"  时间错配: {sc.get('time_horizon_mismatch', 'N/A')}")
                print(f"  可证伪性: {sc.get('unfalsifiability_check', 'N/A')}")

            # Kill scenario
            ks = result.get("kill_scenario")
            if ks:
                print(f"\n{'='*60}")
                print("  致命场景 (Kill Scenario)")
                print(f"{'='*60}")
                if isinstance(ks, dict):
                    print(f"  触发: {ks.get('trigger_event', '')}")
                    print(f"  因果链: {ks.get('causal_chain', '')}")
                    print(f"  结果: {ks.get('final_result', '')}")
                    print(f"  时间: {ks.get('time_frame', '')}")
                else:
                    print(f"  {ks}")

            # Confidence calibration
            cc = result.get("confidence_calibration", {})
            if cc:
                print(f"\n{'='*60}")
                print("  信心校准")
                print(f"{'='*60}")
                print(f"  论证稳固度: {cc.get('devil_rating', '?')}/10 - {cc.get('rating_rationale', '')}")
                print(f"  最薄弱环节: {cc.get('weakest_link', 'N/A')}")
                print(f"  建议对赌: {cc.get('suggested_bet', 'N/A')}")
        else:
            print(result.get("raw_response", "No response"))

        print("\n" + "-" * 60)
        print("Use 'devil.py respond --session ID --text \"...\"' to record your response")

    except Exception as e:
        print(f"Error calling Gemini: {e}")


def cmd_respond(session_id: str, text: str):
    """Record user's response to challenges."""
    session_path = get_session_path(session_id)
    challenges_file = session_path / "challenges" / "gemini.json"

    if not challenges_file.exists():
        print("No challenges found. Run 'devil.py challenge' first.")
        return

    with open(challenges_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    response = {
        "timestamp": datetime.now().isoformat(),
        "text": text
    }
    data["responses"].append(response)

    with open(challenges_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Response recorded for session {session_id}")


def cmd_status(session_id: str):
    """Show challenge status for a session."""
    session_path = get_session_path(session_id)
    challenges_file = session_path / "challenges" / "gemini.json"

    if not challenges_file.exists():
        print(f"No Gemini challenges for session {session_id}")
        return

    with open(challenges_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Session: {session_id}")
    print(f"Challenged at: {data.get('timestamp', 'N/A')}")

    result = data.get("result", {})
    if "challenges" in result:
        print(f"Challenges: {len(result['challenges'])}")
        print(f"Devil Rating: {result.get('devil_rating', '?')}/10")
    else:
        print("Raw response recorded (not structured)")

    print(f"Responses recorded: {len(data.get('responses', []))}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  devil.py challenge --session ID   - Generate challenges")
        print("  devil.py respond --session ID --text '...'  - Record response")
        print("  devil.py status --session ID      - Show challenge status")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = None
    text = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--text" and i + 1 < len(sys.argv):
            text = sys.argv[i + 1]

    if command == "challenge":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_challenge(session_id)

    elif command == "respond":
        if not session_id or not text:
            print("Error: --session and --text are required")
            return
        cmd_respond(session_id, text)

    elif command == "status":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_status(session_id)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
