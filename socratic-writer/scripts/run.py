#!/usr/bin/env python3
"""
Wrapper script that ensures virtual environment is set up before running any skill scripts.
Automatically creates venv, installs dependencies, and executes the target script.
"""

import subprocess
import sys
import os
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
VENV_DIR = SKILL_DIR / ".venv"
REQUIREMENTS = SKILL_DIR / "requirements.txt"

def get_python():
    """Get the correct Python executable."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def get_pip():
    """Get the correct pip executable."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"

def setup_venv():
    """Create virtual environment if it doesn't exist."""
    if not VENV_DIR.exists():
        print(f"Creating virtual environment in {VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        print("Virtual environment created.")

    # Install/update dependencies
    pip = get_pip()
    if REQUIREMENTS.exists():
        print("Installing dependencies...")
        subprocess.run([str(pip), "install", "-q", "-r", str(REQUIREMENTS)], check=True)

        # Install Playwright browsers for ChatGPT automation
        python = get_python()
        result = subprocess.run(
            [str(python), "-c", "import patchright"],
            capture_output=True
        )
        if result.returncode == 0:
            # Check if chromium is installed
            browser_check = subprocess.run(
                [str(python), "-c", "from patchright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium; p.stop()"],
                capture_output=True
            )
            if browser_check.returncode != 0:
                print("Installing Chromium browser...")
                subprocess.run([str(python), "-m", "patchright", "install", "chromium"], check=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <script.py> [args...]")
        print("\nAvailable scripts:")
        scripts_dir = SKILL_DIR / "scripts"
        for script in scripts_dir.glob("*.py"):
            if script.name != "run.py":
                print(f"  - {script.name}")
        sys.exit(1)

    script_name = sys.argv[1]
    script_path = SKILL_DIR / "scripts" / script_name

    if not script_path.exists():
        print(f"Error: Script '{script_name}' not found in {SKILL_DIR / 'scripts'}")
        sys.exit(1)

    # Setup venv
    setup_venv()

    # Run the target script
    python = get_python()
    args = [str(python), str(script_path)] + sys.argv[2:]

    # Set environment variables
    env = os.environ.copy()
    env["SKILL_DIR"] = str(SKILL_DIR)
    env["PYTHONPATH"] = str(SKILL_DIR / "scripts")

    result = subprocess.run(args, env=env)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
