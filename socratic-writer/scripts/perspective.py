#!/usr/bin/env python3
"""
Perspective Agent - OpenAI API-powered supplementary views.
Provides alternative perspectives, identifies blind spots, and enriches arguments.

Uses OpenAI API directly (no manual paste needed).
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
from config import load_config
from session import load_session, get_session_path

PERSPECTIVE_PROMPT = """你是一个"视角补充者"。你的任务是为用户的论点提供额外的视角、盲点提醒和思考维度。

与"魔鬼代言人"不同，你不是来反驳的，而是来丰富和扩展思考的。

**你的角色：**
- 提供用户可能忽略的视角
- 补充相关但未被提及的因素
- 连接到更广泛的背景或趋势
- 提出"还可以考虑..."的建议
- 分享类似案例或历史参考

**你的风格：**
- 建设性、启发性
- 用"另一个角度是..."、"也许还可以考虑..."开头
- 不做价值判断，只提供新视角

请分析以下内容，提供3-5个补充视角：

---
主题：{topic}

内容：
{content}

问答历史：
{dialogue}
---

请用中文回应。"""


def get_openai_client():
    """Initialize OpenAI client."""
    try:
        from openai import OpenAI

        config = load_config()
        api_key = config.get("openai_api_key")

        if not api_key:
            print("Error: OpenAI API key not configured.")
            print("Run: python run.py config.py set openai_api_key YOUR_API_KEY")
            return None, None

        model = config.get("chatgpt_model", "gpt-5.2-chat-latest")
        client = OpenAI(api_key=api_key)
        return client, model

    except ImportError:
        print("Error: openai package not installed.")
        print("Run: pip install openai")
        return None, None


def build_prompt(session_id: str) -> tuple[str, Path]:
    """Build the perspective prompt for a session."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return None, None

    session_path = get_session_path(session_id)

    # Load dialogue
    dialogue_file = session_path / "dialogue.json"
    if not dialogue_file.exists():
        print("No dialogue found in session.")
        return None, None

    with open(dialogue_file, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    # Format dialogue
    dialogue_text = ""
    for entry in dialogue_data.get("entries", []):
        dialogue_text += f"Q: {entry.get('question', '')}\n"
        dialogue_text += f"A: {entry.get('answer', '')}\n\n"

    if not dialogue_text:
        print("No dialogue entries yet.")
        return None, None

    # Build prompt
    prompt = PERSPECTIVE_PROMPT.format(
        topic=state.get("topic", "Unknown"),
        content=state.get("summary", ""),
        dialogue=dialogue_text
    )

    return prompt, session_path


def cmd_challenge(session_id: str):
    """Call OpenAI API to get perspectives (fully automated)."""
    prompt, session_path = build_prompt(session_id)
    if not prompt:
        return

    client, model = get_openai_client()
    if not client:
        return

    print(f"Consulting {model} for perspectives...")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result_text = response.choices[0].message.content

        # Save result
        challenges_dir = session_path / "challenges"
        challenges_dir.mkdir(exist_ok=True)

        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "model": model,
            "response": result_text,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }

        with open(challenges_dir / "gpt.json", "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

        # Display
        print("\n" + "=" * 60)
        print("SUPPLEMENTARY PERSPECTIVES (GPT)")
        print("=" * 60)
        print(result_text)
        print("\n" + "=" * 60)
        print(f"Model: {model} | Tokens: {response.usage.total_tokens}")
        print(f"Saved to: {challenges_dir / 'gpt.json'}")

    except Exception as e:
        print(f"Error calling OpenAI API: {e}")


def cmd_prompt(session_id: str):
    """Generate prompt for manual use (fallback mode)."""
    prompt, session_path = build_prompt(session_id)
    if not prompt:
        return

    print("=" * 60)
    print("CHATGPT PROMPT (fallback manual mode)")
    print("=" * 60)
    print(prompt)
    print("=" * 60)

    # Try to copy to clipboard
    try:
        import subprocess
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
        process.communicate(prompt.encode('utf-8'))
        print("\nPrompt copied to clipboard!")
    except:
        print("\n(Manually copy the prompt above)")

    print(f"\nOr run the automated version:")
    print(f"  perspective.py challenge --session {session_id}")


def cmd_save(session_id: str, response: str):
    """Save response manually (fallback mode)."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    session_path = get_session_path(session_id)
    challenges_dir = session_path / "challenges"
    challenges_dir.mkdir(exist_ok=True)

    record = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "model": "manual",
        "response": response
    }

    with open(challenges_dir / "gpt.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"ChatGPT perspectives saved for session {session_id}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  perspective.py challenge --session ID   - Call OpenAI API (recommended)")
        print("  perspective.py prompt --session ID      - Generate prompt (manual fallback)")
        print("  perspective.py save --session ID --response '...'  - Save manual response")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = None
    response = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--response" and i + 1 < len(sys.argv):
            response = sys.argv[i + 1]

    if command == "challenge":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_challenge(session_id)

    elif command == "prompt":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_prompt(session_id)

    elif command == "save":
        if not session_id or not response:
            print("Error: --session and --response are required")
            return
        cmd_save(session_id, response)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
