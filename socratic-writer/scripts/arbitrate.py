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
from grok_engine import _detect_collective_delusion, _load_challenge_text


def load_all_ai_opinions(session_id: str) -> Dict:
    """Load opinions from all AI sources for a session."""
    session_path = get_session_path(session_id)
    challenges_dir = session_path / "challenges"

    opinions = {
        "gemini": None,
        "gpt": None,
        "grok": None,
        "grok_advocate": None,
        "claude": None  # Will be populated from dialogue
    }

    # Load Gemini (Assumption Verifier)
    gemini_file = challenges_dir / "gemini.json"
    if gemini_file.exists():
        with open(gemini_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["gemini"] = {
                "source": "Gemini (假设核查员)",
                "role": "假设验证",
                "timestamp": data.get("timestamp"),
                "content": data.get("result", {}),
                "raw": data
            }

    # Load GPT (Framework Connector)
    gpt_file = challenges_dir / "gpt.json"
    if gpt_file.exists():
        with open(gpt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["gpt"] = {
                "source": "ChatGPT (框架连接器)",
                "role": "知识桥接",
                "timestamp": data.get("timestamp"),
                "content": data.get("response", ""),
                "raw": data
            }

    # Load Grok (Blind Spot Scanner)
    grok_file = challenges_dir / "grok.json"
    if grok_file.exists():
        with open(grok_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["grok"] = {
                "source": "Grok (盲点扫描仪)",
                "role": "盲点扫描",
                "timestamp": data.get("timestamp"),
                "content": data.get("response", ""),
                "raw": data
            }

    # Load Grok Devil's Advocate
    advocate_file = challenges_dir / "grok_advocate.json"
    if advocate_file.exists():
        with open(advocate_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            opinions["grok_advocate"] = {
                "source": "Grok (魔鬼代言人)",
                "role": "对抗论证",
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

    if opinions["gemini"]:
        content = opinions["gemini"].get("content", {})
        # New format: assumption_map
        if isinstance(content, dict) and "assumption_map" in content:
            for item in content["assumption_map"]:
                points.append({
                    "topic": item.get("claim", "")[:50] + "...",
                    "type": "假设",
                    "gemini": item.get("claim", ""),
                    "gemini_severity": item.get("layer", ""),
                    "gpt": "",
                    "claude": "",
                    "user_decision": ""
                })
        # Old format: challenges
        elif isinstance(content, dict) and "challenges" in content:
            for challenge in content["challenges"]:
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

    # Gemini Assumption Verification
    if opinions["gemini"]:
        print("【Gemini 假设核查员 - 验证】")
        print("-" * 40)
        content = opinions["gemini"].get("content", {})

        if isinstance(content, dict) and "assumption_map" in content:
            for i, item in enumerate(content["assumption_map"], 1):
                layer = item.get("layer", "N/A")
                conf = item.get("confidence", "?")
                load_bearing = " [承重]" if item.get("is_load_bearing") else ""
                print(f"  {i}. [{layer}] {item.get('claim', '')}{load_bearing}")
                if item.get("verification_path"):
                    print(f"     验证路径: {item['verification_path']}")
            if content.get("verification_score"):
                print(f"\n  整体可验证度: {content['verification_score']}/10")
        elif isinstance(content, dict) and "challenges" in content:
            # Backward compat: old challenge format
            for i, c in enumerate(content["challenges"], 1):
                print(f"  {i}. [{c.get('type', 'N/A')}] {c.get('challenge', '')}")
            if content.get("devil_rating"):
                print(f"\n  论证稳固度: {content['devil_rating']}/10")
            if content.get("overall_weakness"):
                print(f"  最大弱点: {content['overall_weakness']}")
        else:
            print(f"  {content}")
        print()

    # GPT Framework Connection
    if opinions["gpt"]:
        print("【ChatGPT 框架连接器 - 桥接】")
        print("-" * 40)
        content = opinions["gpt"].get("content", "")
        # Truncate if too long
        if len(content) > 500:
            print(f"  {content[:500]}...")
            print(f"  [... 共 {len(content)} 字]")
        else:
            print(f"  {content}")
        print()

    # Grok Blind Spot Scan
    if opinions["grok"]:
        print("【Grok 盲点扫描仪 - 扫描】")
        print("-" * 40)
        content = opinions["grok"].get("content", "")
        if len(content) > 500:
            print(f"  {content[:500]}...")
            print(f"  [... 共 {len(content)} 字]")
        else:
            print(f"  {content}")
        print()

    # Grok Devil's Advocate
    if opinions["grok_advocate"]:
        print("【Grok 魔鬼代言人 - 对抗论证】")
        print("-" * 40)
        content = opinions["grok_advocate"].get("content", "")
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

    # Convergence analysis
    print("=" * 80)
    print("【收敛度分析】")
    print("-" * 40)

    analysis = detect_conflicts(opinions)
    convergence = analysis.get("convergence")

    if convergence:
        pct = convergence.get("convergence_pct", 0)
        print(f"  主题收敛度: {pct}%")
        print(f"  覆盖主题数: {convergence.get('total_themes_covered', 0)}/{convergence.get('total_possible_themes', 10)}")

        if analysis.get("warning"):
            print(f"\n  ⚠️  收敛度 > 80% — 集体谬误风险")
            print(f"  共同主题: {', '.join(convergence.get('themes_shared_by_all', []))}")
            print(f"  ❓ 如果三个AI都错了，最可能的共同盲点是什么？")

        # Show each AI's unique contribution
        unique = analysis.get("unique_topics", {})
        if any(v for v in unique.values()):
            print(f"\n  【各AI独家覆盖（信息增量）】")
            for ai, topics in unique.items():
                if topics:
                    print(f"    {ai.upper()}: {', '.join(topics)}")

        # Show never-mentioned themes
        never = convergence.get("themes_never_mentioned", [])
        if never:
            print(f"\n  未覆盖主题: {', '.join(never)}")
    else:
        print("  分析数据不足（需要至少2个AI输出）。")

    print()
    print("=" * 80)
    print("【你的决策】")
    print("使用 'arbitrate.py decide' 来记录你的决定")


def detect_conflicts(opinions: Dict) -> Dict:
    """Detect convergence and unique coverage across AI opinions.

    Uses _detect_collective_delusion() for theme-based Jaccard analysis.
    Returns convergence info + per-AI unique topics (real information delta).
    """
    # Build challenge texts dict for delusion detection
    challenges = {}

    if opinions.get("gemini") and opinions["gemini"].get("content"):
        content = opinions["gemini"]["content"]
        if isinstance(content, dict):
            challenges["gemini"] = content
        else:
            challenges["gemini"] = str(content)

    if opinions.get("gpt") and opinions["gpt"].get("content"):
        content = opinions["gpt"]["content"]
        challenges["gpt"] = str(content) if not isinstance(content, dict) else content

    if opinions.get("grok") and opinions["grok"].get("content"):
        content = opinions["grok"]["content"]
        challenges["grok"] = str(content)

    if opinions.get("grok_advocate") and opinions["grok_advocate"].get("content"):
        content = opinions["grok_advocate"]["content"]
        challenges["grok_advocate"] = str(content)

    if opinions.get("claude") and opinions["claude"].get("content"):
        content = opinions["claude"]["content"]
        if isinstance(content, list):
            challenges["claude"] = " ".join(str(i) for i in content)
        else:
            challenges["claude"] = str(content)

    if len(challenges) < 2:
        return {"convergence": None, "unique_topics": {}, "warning": None}

    result = _detect_collective_delusion(challenges)

    return {
        "convergence": result,
        "unique_topics": {
            ai: sorted(list(set(result["themes_by_ai"].get(ai, [])) - set(result.get("themes_shared_by_all", []))))
            for ai in result.get("themes_by_ai", {})
        },
        "warning": result.get("delusion_warning", False),
    }


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
    print("| 维度 | Gemini (假设核查) | GPT (框架连接) | Claude (引导) | 你的决定 |")
    print("|------|-------------------|----------------|---------------|----------|")

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
                # New format: assumption_map
                if "assumption_map" in content:
                    if theme == "核心论点" and content["assumption_map"]:
                        load_bearing = [a for a in content["assumption_map"] if a.get("is_load_bearing")]
                        gemini_col = load_bearing[0].get("claim", "")[:30] if load_bearing else content["assumption_map"][0].get("claim", "")[:30]
                    elif theme == "证据支撑" and content.get("verification_score"):
                        gemini_col = f"可验证度: {content['verification_score']}/10"
                # Old format: challenges
                elif "challenges" in content:
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
