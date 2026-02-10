#!/usr/bin/env python3
"""
Research Agent - Multi-source research for Socratic Writer.
Integrates web search and local file search.
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
from session import load_session, get_session_path, save_session
from config import load_config


def cmd_local(query: str, session_id: str = None, path: str = None):
    """Search local files for research."""
    config = load_config()

    # Default search paths
    search_paths = [
        Path.home() / "Documents",
        Path.home() / "PORTFOLIO",
        Path.home() / "13F-CLAUDE"
    ]

    if path:
        search_paths = [Path(path)]

    print(f"Searching local files for: {query}")

    results = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Use grep-like search
        try:
            # Search markdown and text files
            for pattern in ["*.md", "*.txt", "*.json"]:
                for file_path in search_path.rglob(pattern):
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if query.lower() in content.lower():
                            # Extract context around match
                            lines = content.split("\n")
                            matching_lines = []
                            for i, line in enumerate(lines):
                                if query.lower() in line.lower():
                                    start = max(0, i - 1)
                                    end = min(len(lines), i + 2)
                                    context = "\n".join(lines[start:end])
                                    matching_lines.append({
                                        "line": i + 1,
                                        "context": context
                                    })

                            if matching_lines:
                                results.append({
                                    "file": str(file_path),
                                    "matches": matching_lines[:3]  # Limit matches per file
                                })
                    except:
                        pass

        except Exception as e:
            print(f"Error searching {search_path}: {e}")

    # Format results
    if results:
        print(f"\nFound {len(results)} files with matches:\n")
        for r in results[:10]:  # Limit to 10 files
            print(f"📄 {r['file']}")
            for m in r['matches']:
                print(f"   Line {m['line']}:")
                print(f"   {m['context'][:200]}...")
                print()

        # Save to session
        if session_id:
            save_research(session_id, "local", query, json.dumps(results, ensure_ascii=False))

        return results
    else:
        print("No matches found.")
        return None


def cmd_nlm(question: str, session_id: str = None, notebook_id: str = None):
    """Query NotebookLM for source-grounded answers.

    Calls the notebooklm skill's ask_question.py via its run.py wrapper.
    """
    import subprocess

    nlm_skill = Path.home() / ".claude" / "skills" / "notebooklm"
    run_py = nlm_skill / "scripts" / "run.py"

    if not run_py.exists():
        print("NotebookLM skill not found at ~/.claude/skills/notebooklm")
        return None

    # Find the venv python
    if os.name == "nt":
        venv_python = nlm_skill / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = nlm_skill / ".venv" / "bin" / "python"

    if not venv_python.exists():
        # Fall back to system python through run.py (it will create venv)
        venv_python = sys.executable

    cmd = [str(venv_python), str(run_py), "ask_question.py", "--question", question]
    if notebook_id:
        cmd.extend(["--notebook-id", notebook_id])

    print(f"Querying NotebookLM: {question[:80]}...")
    if notebook_id:
        print(f"Notebook: {notebook_id}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        output = result.stdout
        if result.returncode != 0:
            error = result.stderr or result.stdout
            print(f"NotebookLM error: {error[:300]}")
            if "auth" in error.lower() or "login" in error.lower():
                print("Run: cd ~/.claude/skills/notebooklm && .venv/Scripts/notebooklm login")
            return None

        print(output)

        # Save to session research log
        if session_id:
            save_research(session_id, "nlm", question, output)

        return output

    except subprocess.TimeoutExpired:
        print("NotebookLM query timed out (120s)")
        return None
    except Exception as e:
        print(f"Error calling NotebookLM: {e}")
        return None


def cmd_web(query: str, session_id: str = None):
    """
    Web search placeholder.
    Note: Actual web search is done by Claude via WebSearch tool.
    This just logs the research need.
    """
    print("=" * 50)
    print("Web Search Request")
    print("=" * 50)
    print(f"Query: {query}")
    print()
    print("NOTE: Claude will use WebSearch tool for this.")
    print("This function logs the research need for the session.")

    if session_id:
        save_research(session_id, "web_request", query, "Pending - Claude will execute")

    return None


def save_research(session_id: str, source: str, query: str, response: str):
    """Save research to session."""
    session_path = get_session_path(session_id)
    research_dir = session_path / "research"
    research_dir.mkdir(exist_ok=True)

    # Load or create research log
    log_file = research_dir / "research_log.json"
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = {"entries": []}

    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "query": query,
        "response": response[:5000] if response else None  # Truncate long responses
    }
    log["entries"].append(entry)

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Research saved to session {session_id}")


def cmd_summary(session_id: str):
    """Show research summary for a session."""
    session_path = get_session_path(session_id)
    log_file = session_path / "research" / "research_log.json"

    if not log_file.exists():
        print(f"No research found for session {session_id}")
        return

    with open(log_file, "r", encoding="utf-8") as f:
        log = json.load(f)

    entries = log.get("entries", [])

    print(f"Session: {session_id}")
    print(f"Research entries: {len(entries)}")
    print()

    for i, e in enumerate(entries, 1):
        print(f"[{i}] {e['source'].upper()} - {e['timestamp'][:16]}")
        print(f"    Query: {e['query'][:80]}...")
        if e.get('response'):
            print(f"    Response: {e['response'][:100]}...")
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  research.py local --query '...' [--session ID] [--path PATH]")
        print("  research.py nlm --question '...' [--session ID] [--notebook-id ID]")
        print("  research.py web --query '...' [--session ID]")
        print("  research.py summary --session ID")
        return

    command = sys.argv[1]

    # Parse arguments
    query = session_id = path = notebook_id = None
    for i, arg in enumerate(sys.argv):
        if arg in ["--question", "--query"] and i + 1 < len(sys.argv):
            query = sys.argv[i + 1]
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--path" and i + 1 < len(sys.argv):
            path = sys.argv[i + 1]
        if arg == "--notebook-id" and i + 1 < len(sys.argv):
            notebook_id = sys.argv[i + 1]

    if command == "local":
        if not query:
            print("Error: --query is required")
            return
        cmd_local(query, session_id, path)

    elif command == "nlm":
        if not query:
            print("Error: --question is required")
            return
        cmd_nlm(query, session_id, notebook_id)

    elif command == "web":
        if not query:
            print("Error: --query is required")
            return
        cmd_web(query, session_id)

    elif command == "summary":
        if not session_id:
            print("Error: --session is required")
            return
        cmd_summary(session_id)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
