#!/usr/bin/env python3
"""
Arbitration Module - Compare and reconcile opinions from multiple AIs.
When Claude, Gemini, and GPT have different views, generate a comparison
table to help the user make informed decisions.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from session import load_session, get_session_path
from config import load_config


def load_all_ai_opinions(session_id: str) -> Dict:
    """Load opinions from all AI sources for a session."""
    session_path = get_session_path(session_id)
    challenges_dir = session_path / "challenges"

    opinions = {
        "gemini": None,
        "gpt": None,
        "claude": None  # Will be populated from dialogue
    }

    # Load Gemini (Devil's Advocate)
    gemini_file = challenges_dir / "gemini.json"
    if gemini_file.exists():
        with open(gemini_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["gemini"] = {
                "source": "Gemini (魔鬼代言人)",
                "role": "质疑挑战",
                "timestamp": data.get("timestamp"),
                "content": data.get("result", {}),
                "raw": data
            }

    # Load GPT (Perspective)
    gpt_file = challenges_dir / "gpt.json"
    if gpt_file.exists():
        with open(gpt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["gpt"] = {
                "source": "ChatGPT (视角补充)",
                "role": "补充盲点",
                "timestamp": data.get("timestamp"),
                "content": data.get("response", ""),
                "raw": data
            }

    # Load Claude's perspective from dialogue insights
    dialogue_file = session_path / "dialogue.json"
    if dialogue_file.exists():
        with open(dialogue_file, "r", encoding="utf-8") as f:
            dialogue = json.load(f)
            insights = dialogue.get("key_insights", [])
            opinions["claude"] = {
                "source": "Claude (苏格拉底引导)",
                "role": "问答深化",
                "content": insights,
                "raw": dialogue
            }

    return opinions


def extract_key_points(opinions: Dict) -> List[Dict]:
    """Extract key discussion points from all opinions."""
    points = []

    # From Gemini challenges
    if opinions["gemini"] and "challenges" in opinions["gemini"].get("content", {}):
        for challenge in opinions["gemini"]["content"]["challenges"]:
            points.append({
                "topic": challenge.get("challenge", "")[:50] + "...",
                "type": "挑战",
                "gemini": challenge.get("challenge", ""),
                "gemini_severity": challenge.get("type", ""),
                "gpt": "",
                "claude": "",
                "user_decision": ""
            })

    return points


def cmd_compare(session_id: str):
    """Generate a comparison of all AI opinions."""
    opinions = load_all_ai_opinions(session_id)

    print("=" * 80)
    print("🔍 AI意见对比 - 仲裁面板")
    print("=" * 80)
    print(f"Session: {session_id}")
    print()

    # Summary of available opinions
    print("【已收集的AI意见】")
    print("-" * 40)

    for ai, data in opinions.items():
        if data:
            print(f"  ✓ {data['source']}")
            if data.get("timestamp"):
                print(f"      时间: {data['timestamp'][:16]}")
        else:
            print(f"  ✗ {ai.upper()} - 未收集")

    print()

    # Gemini Challenges
    if opinions["gemini"]:
        print("【Gemini 魔鬼代言人 - 质疑】")
        print("-" * 40)
        content = opinions["gemini"].get("content", {})

        if isinstance(content, dict) and "challenges" in content:
            for i, c in enumerate(content["challenges"], 1):
                print(f"  {i}. [{c.get('type', 'N/A')}] {c.get('challenge', '')}")
            if content.get("devil_rating"):
                print(f"\n  论证稳固度: {content['devil_rating']}/10")
            if content.get("overall_weakness"):
                print(f"  最大弱点: {content['overall_weakness']}")
        else:
            print(f"  {content}")
        print()

    # GPT Perspectives
    if opinions["gpt"]:
        print("【ChatGPT 视角补充 - 补充】")
        print("-" * 40)
        content = opinions["gpt"].get("content", "")
        # Truncate if too long
        if len(content) > 500:
            print(f"  {content[:500]}...")
            print(f"  [... 共 {len(content)} 字]")
        else:
            print(f"  {content}")
        print()

    # Claude insights
    if opinions["claude"] and opinions["claude"].get("content"):
        print("【Claude 苏格拉底引导 - 洞察】")
        print("-" * 40)
        for insight in opinions["claude"]["content"]:
            print(f"  • {insight}")
        print()

    # Conflict detection
    print("=" * 80)
    print("【冲突检测】")
    print("-" * 40)

    conflicts = detect_conflicts(opinions)
    if conflicts:
        for i, conflict in enumerate(conflicts, 1):
            print(f"\n冲突 {i}: {conflict['topic']}")
            print(f"  Gemini 说: {conflict.get('gemini_view', 'N/A')}")
            print(f"  GPT 说: {conflict.get('gpt_view', 'N/A')}")
            print(f"  → 你需要决定: {conflict.get('decision_needed', '?')}")
    else:
        print("  未检测到明显冲突。AI意见基本一致或互补。")

    print()
    print("=" * 80)
    print("【你的决策】")
    print("使用 'arbitrate.py decide' 来记录你的决定")


def detect_conflicts(opinions: Dict) -> List[Dict]:
    """Detect potential conflicts between AI opinions."""
    conflicts = []

    gemini_content = opinions.get("gemini", {}).get("content", {}) if opinions.get("gemini") else {}
    gpt_content = opinions.get("gpt", {}).get("content", "") if opinions.get("gpt") else ""

    # Simple heuristic: if Gemini challenges something and GPT doesn't mention it,
    # or if they have opposing views
    if isinstance(gemini_content, dict) and "challenges" in gemini_content:
        for challenge in gemini_content["challenges"]:
            challenge_text = challenge.get("challenge", "").lower()

            # Check if GPT addressed this
            if gpt_content and challenge_text:
                # Very simple: check if GPT mentions similar keywords
                key_words = [w for w in challenge_text.split() if len(w) > 4][:3]
                gpt_lower = gpt_content.lower()

                mentioned = any(word in gpt_lower for word in key_words)

                if not mentioned:
                    conflicts.append({
                        "topic": challenge.get("type", "未知"),
                        "gemini_view": challenge.get("challenge", "")[:100],
                        "gpt_view": "未直接回应此挑战",
                        "decision_needed": "是否需要回应此挑战？"
                    })

    return conflicts[:5]  # Limit to top 5 conflicts


def cmd_decide(session_id: str, topic: str, decision: str, reasoning: str = ""):
    """Record user's decision on a conflict or challenge."""
    session_path = get_session_path(session_id)
    decisions_file = session_path / "challenges" / "decisions.json"

    # Load existing decisions
    if decisions_file.exists():
        with open(decisions_file, "r", encoding="utf-8") as f:
            decisions = json.load(f)
    else:
        decisions = {"decisions": []}

    # Add new decision
    new_decision = {
        "id": f"D{len(decisions['decisions']) + 1}",
        "topic": topic,
        "decision": decision,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat()
    }
    decisions["decisions"].append(new_decision)

    # Save
    with open(decisions_file, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)

    print(f"✓ 决策已记录: {new_decision['id']}")
    print(f"  主题: {topic}")
    print(f"  决定: {decision}")


def cmd_decisions(session_id: str):
    """List all user decisions."""
    session_path = get_session_path(session_id)
    decisions_file = session_path / "challenges" / "decisions.json"

    if not decisions_file.exists():
        print("No decisions recorded yet.")
        return

    with open(decisions_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("【已记录的决策】")
    print("-" * 60)

    for d in data.get("decisions", []):
        print(f"\n{d['id']} - {d['timestamp'][:16]}")
        print(f"  主题: {d['topic']}")
        print(f"  决定: {d['decision']}")
        if d.get("reasoning"):
            print(f"  理由: {d['reasoning']}")


def cmd_table(session_id: str):
    """Generate a markdown comparison table for export."""
    opinions = load_all_ai_opinions(session_id)

    print("# AI意见对比表\n")
    print("| 维度 | Gemini (质疑) | GPT (补充) | Claude (引导) | 你的决定 |")
    print("|------|---------------|------------|---------------|----------|")

    # Extract key themes
    themes = ["核心论点", "论证逻辑", "证据支撑", "潜在风险", "盲点/遗漏"]

    for theme in themes:
        gemini_col = "-"
        gpt_col = "-"
        claude_col = "-"

        # Try to extract relevant content for each theme
        if opinions["gemini"]:
            content = opinions["gemini"].get("content", {})
            if isinstance(content, dict):
                if theme == "核心论点" and content.get("overall_weakness"):
                    gemini_col = content["overall_weakness"][:30]
                elif theme == "潜在风险" and content.get("challenges"):
                    gemini_col = content["challenges"][0].get("challenge", "")[:30] if content["challenges"] else "-"

        if opinions["gpt"]:
            content = opinions["gpt"].get("content", "")
            if content:
                gpt_col = content[:30] + "..."

        print(f"| {theme} | {gemini_col} | {gpt_col} | {claude_col} | *待定* |")

    print("\n*使用 `arbitrate.py decide` 填写你的决定*")


def main():
    if len(sys.argv) < 2:
        print("Arbitration Module - Compare and reconcile multi-AI opinions")
        print()
        print("Usage:")
        print("  arbitrate.py compare --session ID     - Compare all AI opinions")
        print("  arbitrate.py table --session ID       - Generate markdown comparison table")
        print("  arbitrate.py decide --session ID --topic 'X' --decision 'Y' [--reasoning 'Z']")
        print("  arbitrate.py decisions --session ID   - List all decisions")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = topic = decision = reasoning = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--topic" and i + 1 < len(sys.argv):
            topic = sys.argv[i + 1]
        if arg == "--decision" and i + 1 < len(sys.argv):
            decision = sys.argv[i + 1]
        if arg == "--reasoning" and i + 1 < len(sys.argv):
            reasoning = sys.argv[i + 1]

    if not session_id:
        print("Error: --session is required")
        return

    if command == "compare":
        cmd_compare(session_id)

    elif command == "table":
        cmd_table(session_id)

    elif command == "decide":
        if not topic or not decision:
            print("Error: --topic and --decision are required")
            return
        cmd_decide(session_id, topic, decision, reasoning or "")

    elif command == "decisions":
        cmd_decisions(session_id)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
