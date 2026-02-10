#!/usr/bin/env python3
"""
Universal runner for ChatGPT skill scripts.
Ensures all scripts run with the correct virtual environment.
"""

import os
import sys
import subprocess
from pathlib import Path


def get_venv_python():
    """Get the virtual environment Python executable"""
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"

    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    return venv_python


def ensure_venv():
    """Ensure virtual environment exists"""
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"
    setup_script = skill_dir / "scripts" / "setup_environment.py"

    if not venv_dir.exists():
        print("First-time setup: Creating virtual environment...")
        print("   This may take a minute...")

        result = subprocess.run([sys.executable, str(setup_script)])
        if result.returncode != 0:
            print("Failed to set up environment")
            sys.exit(1)

        print("Environment ready!")

    return get_venv_python()


def main():
    """Main runner"""
    if len(sys.argv) < 2:
        print("Usage: python run.py <script_name> [args...]")
        print("\nAvailable scripts:")
        print("  ask_question.py      - One-shot Q&A with ChatGPT")
        print("  conversation.py      - Multi-turn conversation sessions")
        print("  auth_manager.py      - Handle authentication")
        print("  history_manager.py   - Search/list Q&A history")
        print("  debug_selectors.py   - Diagnose selector breakage")
        print("  setup_environment.py - First-time setup")
        sys.exit(1)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    # Handle both "scripts/script.py" and "script.py" formats
    if script_name.startswith("scripts/"):
        script_name = script_name[8:]

    # Ensure .py extension
    if not script_name.endswith(".py"):
        script_name += ".py"

    # Get script path
    skill_dir = Path(__file__).parent.parent
    script_path = skill_dir / "scripts" / script_name

    if not script_path.exists():
        print(f"Script not found: {script_name}")
        print(f"   Looked for: {script_path}")
        sys.exit(1)

    # Ensure venv exists and get Python executable
    venv_python = ensure_venv()

    # Build command
    cmd = [str(venv_python), str(script_path)] + script_args

    # Set UTF-8 encoding for Windows compatibility
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # Run the script
    try:
        result = subprocess.run(cmd, env=env)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
