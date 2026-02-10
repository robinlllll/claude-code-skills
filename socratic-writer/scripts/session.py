#!/usr/bin/env python3
"""
Session management for Socratic Writer.
Handles creating, listing, resuming writing sessions.
"""

import json
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))
SESSIONS_DIR = SKILL_DIR / "data" / "sessions"

def generate_session_id() -> str:
    """Generate a short unique session ID."""
    return uuid.uuid4().hex[:12]

def get_session_path(session_id: str) -> Path:
    """Get the path to a session directory."""
    return SESSIONS_DIR / session_id

def load_session(session_id: str) -> Optional[dict]:
    """Load a session's state."""
    state_file = get_session_path(session_id) / "state.json"
    if not state_file.exists():
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_session(session_id: str, state: dict):
    """Save a session's state."""
    session_path = get_session_path(session_id)
    session_path.mkdir(parents=True, exist_ok=True)

    state["updated_at"] = datetime.now().isoformat()

    with open(session_path / "state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def cmd_new(topic: str):
    """Create a new writing session."""
    session_id = generate_session_id()
    session_path = get_session_path(session_id)

    # Create directory structure
    session_path.mkdir(parents=True, exist_ok=True)
    (session_path / "research").mkdir(exist_ok=True)
    (session_path / "challenges").mkdir(exist_ok=True)
    (session_path / "drafts").mkdir(exist_ok=True)

    # Initialize state
    state = {
        "id": session_id,
        "topic": topic,
        "status": "active",
        "phase": "exploration",  # exploration, deepening, challenging, drafting, complete
        "question_round": 0,
        "current_question_type": "clarification",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "tags": [],
        "summary": ""
    }
    save_session(session_id, state)

    # Initialize dialogue
    dialogue = {
        "entries": [],
        "research_gaps": [],
        "key_insights": []
    }
    with open(session_path / "dialogue.json", "w", encoding="utf-8") as f:
        json.dump(dialogue, f, indent=2, ensure_ascii=False)

    print(f"✓ Created new session: {session_id}")
    print(f"  Topic: {topic}")
    print(f"  Path: {session_path}")
    print(f"\nNext: Claude will begin Socratic questioning to deepen your idea.")

    return session_id

def cmd_list():
    """List all sessions."""
    if not SESSIONS_DIR.exists():
        print("No sessions found.")
        return

    sessions = []
    for session_dir in SESSIONS_DIR.iterdir():
        if session_dir.is_dir():
            state = load_session(session_dir.name)
            if state:
                sessions.append(state)

    if not sessions:
        print("No sessions found.")
        return

    # Sort by updated_at descending
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

    print(f"{'ID':<14} {'Status':<10} {'Phase':<12} {'Topic':<40} {'Updated':<20}")
    print("-" * 100)

    for s in sessions:
        topic = s.get("topic", "")[:38]
        updated = s.get("updated_at", "")[:16]
        print(f"{s['id']:<14} {s.get('status', 'unknown'):<10} {s.get('phase', 'unknown'):<12} {topic:<40} {updated:<20}")

def cmd_status(session_id: Optional[str] = None):
    """Show status of current or specified session."""
    if not session_id:
        # Find most recent active session
        if not SESSIONS_DIR.exists():
            print("No sessions found. Create one with: session.py new --topic 'your idea'")
            return

        active_sessions = []
        for session_dir in SESSIONS_DIR.iterdir():
            if session_dir.is_dir():
                state = load_session(session_dir.name)
                if state and state.get("status") == "active":
                    active_sessions.append(state)

        if not active_sessions:
            print("No active sessions. Create one with: session.py new --topic 'your idea'")
            return

        # Get most recent
        active_sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        state = active_sessions[0]
        session_id = state["id"]
    else:
        state = load_session(session_id)
        if not state:
            print(f"Session not found: {session_id}")
            return

    session_path = get_session_path(session_id)

    print("=" * 60)
    print(f"Session: {session_id}")
    print("=" * 60)
    print(f"Topic: {state.get('topic', 'N/A')}")
    print(f"Status: {state.get('status', 'N/A')}")
    print(f"Phase: {state.get('phase', 'N/A')}")
    print(f"Question Round: {state.get('question_round', 0)}")
    print(f"Current Question Type: {state.get('current_question_type', 'N/A')}")
    print(f"Created: {state.get('created_at', 'N/A')}")
    print(f"Updated: {state.get('updated_at', 'N/A')}")

    # Load dialogue stats
    dialogue_file = session_path / "dialogue.json"
    if dialogue_file.exists():
        with open(dialogue_file, "r", encoding="utf-8") as f:
            dialogue = json.load(f)
        print(f"\nDialogue entries: {len(dialogue.get('entries', []))}")
        print(f"Research gaps identified: {len(dialogue.get('research_gaps', []))}")
        print(f"Key insights: {len(dialogue.get('key_insights', []))}")

    # Check for challenges
    challenges_dir = session_path / "challenges"
    if challenges_dir.exists():
        gemini_file = challenges_dir / "gemini.json"
        gpt_file = challenges_dir / "gpt.json"
        print(f"\nGemini challenges: {'Yes' if gemini_file.exists() else 'No'}")
        print(f"GPT supplements: {'Yes' if gpt_file.exists() else 'No'}")

    # Check for drafts
    drafts_dir = session_path / "drafts"
    if drafts_dir.exists():
        drafts = list(drafts_dir.glob("*.md"))
        print(f"\nDrafts: {len(drafts)}")

def cmd_resume(session_id: str):
    """Resume a session."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    if state.get("status") == "complete":
        print(f"Session {session_id} is already complete.")
        response = input("Reopen? (y/n): ")
        if response.lower() != "y":
            return

    state["status"] = "active"
    save_session(session_id, state)
    print(f"✓ Resumed session: {session_id}")
    cmd_status(session_id)

def cmd_close(session_id: str):
    """Close/complete a session."""
    state = load_session(session_id)
    if not state:
        print(f"Session not found: {session_id}")
        return

    state["status"] = "complete"
    state["phase"] = "complete"
    save_session(session_id, state)
    print(f"✓ Closed session: {session_id}")

def cmd_add_dialogue(session_id: str, question: str, answer: str, question_type: str):
    """Add a dialogue entry to a session."""
    session_path = get_session_path(session_id)
    dialogue_file = session_path / "dialogue.json"

    if not dialogue_file.exists():
        print(f"Session not found: {session_id}")
        return

    with open(dialogue_file, "r", encoding="utf-8") as f:
        dialogue = json.load(f)

    entry = {
        "question": question,
        "answer": answer,
        "type": question_type,
        "timestamp": datetime.now().isoformat()
    }
    dialogue["entries"].append(entry)

    with open(dialogue_file, "w", encoding="utf-8") as f:
        json.dump(dialogue, f, indent=2, ensure_ascii=False)

    print(f"✓ Added dialogue entry to session {session_id}")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  session.py new --topic 'your idea'   - Create new session")
        print("  session.py list                      - List all sessions")
        print("  session.py status [session_id]       - Show session status")
        print("  session.py resume --id SESSION_ID    - Resume a session")
        print("  session.py close --id SESSION_ID     - Close a session")
        return

    command = sys.argv[1]

    if command == "new":
        # Parse --topic argument
        topic = ""
        for i, arg in enumerate(sys.argv):
            if arg == "--topic" and i + 1 < len(sys.argv):
                topic = sys.argv[i + 1]
                break

        if not topic:
            print("Error: --topic is required")
            print("Usage: session.py new --topic 'your idea'")
            return

        cmd_new(topic)

    elif command == "list":
        cmd_list()

    elif command == "status":
        session_id = None
        for i, arg in enumerate(sys.argv):
            if arg == "--id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                break
        if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
            session_id = sys.argv[2]
        cmd_status(session_id)

    elif command == "resume":
        session_id = None
        for i, arg in enumerate(sys.argv):
            if arg == "--id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                break
        if not session_id:
            print("Error: --id is required")
            return
        cmd_resume(session_id)

    elif command == "close":
        session_id = None
        for i, arg in enumerate(sys.argv):
            if arg == "--id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                break
        if not session_id:
            print("Error: --id is required")
            return
        cmd_close(session_id)

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
