#!/usr/bin/env python3
"""
Export module for Socratic Writer.
Exports sessions to Obsidian, Markdown, or JSON.
"""

import json
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from session import load_session, get_session_path
from config import load_config


def generate_obsidian_content(
    session_id: str,
    include_research: bool = True,
    include_challenges: bool = True,
    include_dialogue: bool = True,
) -> str:
    """Generate Obsidian-formatted markdown content."""
    state = load_session(session_id)
    if not state:
        return None

    session_path = get_session_path(session_id)

    # Start building content
    now = datetime.now()
    frontmatter = f"""---
created: {now.strftime("%Y-%m-%d")}
type: thought-piece
status: draft
source: socratic-writer
session_id: {session_id}
tags: [思考, 观点]
---

"""

    content = frontmatter
    content += f"# {state.get('topic', 'Untitled')}\n\n"

    # Core content from summary
    if state.get("summary"):
        content += "## 核心观点\n\n"
        content += state["summary"] + "\n\n"

    # Load dialogue
    dialogue_file = session_path / "dialogue.json"
    if dialogue_file.exists():
        with open(dialogue_file, "r", encoding="utf-8") as f:
            dialogue_data = json.load(f)

        # Extract key insights
        if dialogue_data.get("key_insights"):
            content += "## 关键洞察\n\n"
            for insight in dialogue_data["key_insights"]:
                content += f"- {insight}\n"
            content += "\n"

    # Grok Synthesis section (new: tensions + evaluation)
    synthesis_dir = session_path / "synthesis"
    tensions_file = synthesis_dir / "tensions.json"
    eval_file = synthesis_dir / "evaluation.json"
    response_file = synthesis_dir / "user_response.json"

    if tensions_file.exists():
        with open(tensions_file, "r", encoding="utf-8") as f:
            tensions_data = json.load(f)

        t_result = tensions_data.get("result", {})
        thesis_strength = t_result.get("thesis_strength", {})

        if thesis_strength:
            content += "## 论点评估\n\n"
            content += f"**论点强度:** {thesis_strength.get('score', '?')}/10\n\n"
            content += (
                f"- **最强点:** {thesis_strength.get('strongest_point', 'N/A')}\n"
            )
            content += f"- **最弱点:** {thesis_strength.get('weakest_point', 'N/A')}\n"
            content += f"- **最应修改:** {thesis_strength.get('one_thing_to_change', 'N/A')}\n\n"

        tensions = t_result.get("unresolved_tensions", [])
        if tensions:
            content += "## 核心张力\n\n"
            for i, t in enumerate(tensions, 1):
                content += f"### 张力 {i}: {t.get('tension', '')}\n\n"
                content += f"- **来源:** {t.get('from', '?')}\n"
                content += f"- **重要性:** {t.get('why_it_matters', '')}\n"
                content += f"- **聚焦问题:** {t.get('focused_question', '')}\n\n"

        resolved = t_result.get("resolved_points", [])
        if resolved:
            content += "### 已解决的点\n\n"
            for r in resolved:
                content += f"- {r}\n"
            content += "\n"

    # User response to tensions
    if response_file.exists():
        with open(response_file, "r", encoding="utf-8") as f:
            resp_data = json.load(f)
        if resp_data.get("response"):
            content += "## 作者回应（论点 v2）\n\n"
            content += resp_data["response"] + "\n\n"

    # Final evaluation
    if eval_file.exists():
        with open(eval_file, "r", encoding="utf-8") as f:
            eval_data = json.load(f)

        e_result = eval_data.get("result", {})
        content += "## 最终评估\n\n"
        content += f"**最终评分:** {e_result.get('final_score', '?')}/10 — {e_result.get('verdict', '?').upper()}\n\n"

        improvements = e_result.get("improvements", [])
        if improvements:
            content += "**改进:**\n"
            for imp in improvements:
                content += f"- {imp}\n"
            content += "\n"

        remaining = e_result.get("remaining_weaknesses", [])
        if remaining:
            content += "**待解决:**\n"
            for w in remaining:
                content += f"- {w}\n"
            content += "\n"

        if e_result.get("recommendation"):
            content += f"**建议:** {e_result['recommendation']}\n\n"

    # Challenges section
    if include_challenges:
        challenges_dir = session_path / "challenges"

        # Gemini challenges
        gemini_file = challenges_dir / "gemini.json"
        if gemini_file.exists():
            with open(gemini_file, "r", encoding="utf-8") as f:
                gemini_data = json.load(f)

            result = gemini_data.get("result", {})
            if "challenges" in result:
                content += "## 量化挑战 (Gemini)\n\n"
                content += "| 挑战 | 类型 | 严重性 |\n"
                content += "|------|------|--------|\n"

                for c in result["challenges"]:
                    challenge_text = (
                        c.get("quantitative_challenge", c.get("challenge", ""))
                        .replace("|", "\\|")
                        .replace("\n", " ")[:80]
                    )
                    content += f"| {challenge_text} | {c.get('type', 'N/A')} | {c.get('severity', '?')} |\n"

                content += "\n"

                cc = result.get("confidence_calibration", {})
                if cc:
                    content += f"**量化评分:** {cc.get('quantitative_score', '?')}/10\n"
                    content += (
                        f"**最脆弱假设:** {cc.get('most_fragile_number', 'N/A')}\n\n"
                    )

        # GPT qualitative
        gpt_file = challenges_dir / "gpt.json"
        if gpt_file.exists():
            with open(gpt_file, "r", encoding="utf-8") as f:
                gpt_data = json.load(f)

            if gpt_data.get("response"):
                content += "## 定性挑战 (GPT)\n\n"
                content += gpt_data["response"] + "\n\n"

        # Grok contrarian
        grok_file = challenges_dir / "grok.json"
        if grok_file.exists():
            with open(grok_file, "r", encoding="utf-8") as f:
                grok_data = json.load(f)

            if grok_data.get("response"):
                content += "## 逆向挑战 (Grok)\n\n"
                content += grok_data["response"] + "\n\n"

    # Research section
    if include_research:
        research_log = session_path / "research" / "research_log.json"
        if research_log.exists():
            with open(research_log, "r", encoding="utf-8") as f:
                log = json.load(f)

            if log.get("entries"):
                content += "## 研究笔记\n\n"
                for entry in log["entries"]:
                    content += (
                        f"### [{entry['source'].upper()}] {entry['query'][:50]}...\n\n"
                    )
                    if entry.get("response"):
                        response = entry["response"][:1000]
                        content += f"{response}\n\n"
                    content += f"*{entry['timestamp'][:16]}*\n\n"

    # Dialogue section (collapsed)
    if include_dialogue and dialogue_file.exists():
        with open(dialogue_file, "r", encoding="utf-8") as f:
            dialogue_data = json.load(f)

        if dialogue_data.get("entries"):
            content += "## 问答过程\n\n"
            content += "<details>\n<summary>展开查看完整问答</summary>\n\n"

            for entry in dialogue_data["entries"]:
                q_type = entry.get("type", "unknown")
                content += f"**Q ({q_type})**: {entry.get('question', '')}\n\n"
                content += f"**A**: {entry.get('answer', '')}\n\n"
                content += "---\n\n"

            content += "</details>\n\n"

    # Footer
    content += "---\n\n"
    content += f"*Generated by Socratic Writer on {now.strftime('%Y-%m-%d %H:%M')}*\n"

    return content


def cmd_obsidian(
    session_id: str,
    include_research: bool = True,
    include_challenges: bool = True,
    include_dialogue: bool = True,
):
    """Export session to Obsidian vault."""
    config = load_config()
    obsidian_path = Path(config.get("obsidian_path", ""))

    if not obsidian_path.exists():
        print(f"Error: Obsidian path not found: {obsidian_path}")
        print("Update with: config.py set-obsidian-path PATH")
        return

    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    # Generate content
    content = generate_obsidian_content(
        session_id, include_research, include_challenges, include_dialogue
    )

    if not content:
        print("Error generating content")
        return

    # Create filename
    topic = state.get("topic", "Untitled")
    # Sanitize filename
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:50]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str} {safe_topic}.md"

    output_path = obsidian_path / filename

    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓ Exported to Obsidian: {output_path}")
    return str(output_path)


def cmd_markdown(session_id: str, output_path: str = None):
    """Export session to standalone Markdown file."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    content = generate_obsidian_content(session_id, True, True, True)

    if not output_path:
        session_path = get_session_path(session_id)
        output_path = session_path / "export.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓ Exported to: {output_path}")
    return str(output_path)


def cmd_json(session_id: str, output_path: str = None):
    """Export session as JSON."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)

    # Collect all data
    export_data = {
        "state": state,
        "dialogue": None,
        "research": None,
        "challenges": {"gemini": None, "gpt": None, "grok": None},
        "synthesis": {"tensions": None, "user_response": None, "evaluation": None},
    }

    # Load dialogue
    dialogue_file = session_path / "dialogue.json"
    if dialogue_file.exists():
        with open(dialogue_file, "r", encoding="utf-8") as f:
            export_data["dialogue"] = json.load(f)

    # Load research
    research_log = session_path / "research" / "research_log.json"
    if research_log.exists():
        with open(research_log, "r", encoding="utf-8") as f:
            export_data["research"] = json.load(f)

    # Load challenges
    gemini_file = session_path / "challenges" / "gemini.json"
    if gemini_file.exists():
        with open(gemini_file, "r", encoding="utf-8") as f:
            export_data["challenges"]["gemini"] = json.load(f)

    gpt_file = session_path / "challenges" / "gpt.json"
    if gpt_file.exists():
        with open(gpt_file, "r", encoding="utf-8") as f:
            export_data["challenges"]["gpt"] = json.load(f)

    grok_file = session_path / "challenges" / "grok.json"
    if grok_file.exists():
        with open(grok_file, "r", encoding="utf-8") as f:
            export_data["challenges"]["grok"] = json.load(f)

    # Load synthesis data
    synthesis_dir = session_path / "synthesis"
    for key, fname in [
        ("tensions", "tensions.json"),
        ("user_response", "user_response.json"),
        ("evaluation", "evaluation.json"),
    ]:
        fpath = synthesis_dir / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                export_data["synthesis"][key] = json.load(f)

    if not output_path:
        output_path = session_path / "export.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Exported to: {output_path}")
    return str(output_path)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  export.py obsidian --session ID [options]")
        print("  export.py markdown --session ID [--output PATH]")
        print("  export.py json --session ID [--output PATH]")
        print()
        print("Options for obsidian:")
        print("  --include-research     Include research notes (default: yes)")
        print("  --include-challenges   Include AI challenges (default: yes)")
        print("  --include-dialogue     Include Q&A history (default: yes)")
        print("  --no-research          Exclude research notes")
        print("  --no-challenges        Exclude AI challenges")
        print("  --no-dialogue          Exclude Q&A history")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = output_path = None
    include_research = "--no-research" not in sys.argv
    include_challenges = "--no-challenges" not in sys.argv
    include_dialogue = "--no-dialogue" not in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    if command == "obsidian":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_obsidian(session_id, include_research, include_challenges, include_dialogue)

    elif command == "markdown":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_markdown(session_id, output_path)

    elif command == "json":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_json(session_id, output_path)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
