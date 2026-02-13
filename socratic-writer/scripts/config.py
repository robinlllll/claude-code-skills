#!/usr/bin/env python3
"""
Configuration management for Socratic Writer.
Handles API keys, paths, and preferences.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))
CONFIG_FILE = SKILL_DIR / "data" / "config.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "openai_api_key": "",
    "grok_api_key": "",
    "gemini_model": "gemini-3-pro-preview",  # Gemini 3 Pro for devil's advocate
    "obsidian_path": r"C:\Users\thisi\Documents\Obsidian Vault\思考性文章",
    "chatgpt_model": "gpt-5.2-chat-latest",  # OpenAI model for perspective
    "grok_model": "grok-4-1-fast-reasoning",  # xAI Grok for contrarian analysis
    "default_question_depth": 3,  # How many rounds of questions per type
    "auto_research": True,  # Automatically trigger research on gaps
    "include_research_in_export": True,
    "include_challenges_in_export": True,
    "created_at": "",
    "updated_at": ""
}

def load_config() -> dict:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Merge with defaults for any missing keys
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value

    return config

def save_config(config: dict):
    """Save configuration to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config["updated_at"] = datetime.now().isoformat()
    if not config.get("created_at"):
        config["created_at"] = config["updated_at"]

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def cmd_show():
    """Show current configuration."""
    config = load_config()
    print("=" * 50)
    print("Socratic Writer Configuration")
    print("=" * 50)

    for key, value in config.items():
        if "key" in key.lower() and value:
            # Mask API keys
            display_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        else:
            display_value = value
        print(f"{key}: {display_value}")

    # Check status
    print("\n" + "-" * 50)
    print("Status:")

    if config.get("gemini_api_key"):
        print("  ✓ Gemini API configured")
    else:
        print("  ✗ Gemini API not configured (run: config.py set-gemini-key YOUR_KEY)")

    if config.get("grok_api_key"):
        print("  ✓ Grok API configured")
    else:
        print("  ✗ Grok API not configured (run: config.py set grok_api_key YOUR_KEY)")

    obsidian_path = Path(config.get("obsidian_path", ""))
    if obsidian_path.exists():
        print(f"  ✓ Obsidian path exists: {obsidian_path}")
    else:
        print(f"  ✗ Obsidian path not found: {obsidian_path}")

def cmd_set_gemini_key(key: str):
    """Set Gemini API key."""
    config = load_config()
    config["gemini_api_key"] = key
    save_config(config)
    print(f"✓ Gemini API key saved (ends with ...{key[-4:]})")

def cmd_set_obsidian_path(path: str):
    """Set Obsidian vault path."""
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"Warning: Path does not exist: {path}")
        print("Creating directory...")
        path_obj.mkdir(parents=True, exist_ok=True)

    config = load_config()
    config["obsidian_path"] = str(path_obj)
    save_config(config)
    print(f"✓ Obsidian path set to: {path_obj}")

def cmd_set(key: str, value: str):
    """Set a configuration value."""
    config = load_config()

    # Type conversion for known keys
    if key in ["default_question_depth"]:
        value = int(value)
    elif key in ["auto_research", "include_research_in_export", "include_challenges_in_export"]:
        value = value.lower() in ["true", "1", "yes"]

    config[key] = value
    save_config(config)
    print(f"✓ {key} = {value}")

def main():
    if len(sys.argv) < 2:
        cmd_show()
        return

    command = sys.argv[1]

    if command == "show":
        cmd_show()
    elif command == "set-gemini-key" and len(sys.argv) > 2:
        cmd_set_gemini_key(sys.argv[2])
    elif command == "set-obsidian-path" and len(sys.argv) > 2:
        cmd_set_obsidian_path(" ".join(sys.argv[2:]))  # Handle paths with spaces
    elif command == "set" and len(sys.argv) > 3:
        cmd_set(sys.argv[2], sys.argv[3])
    else:
        print("Usage:")
        print("  config.py show                      - Show configuration")
        print("  config.py set-gemini-key KEY        - Set Gemini API key")
        print("  config.py set-obsidian-path PATH    - Set Obsidian vault path")
        print("  config.py set KEY VALUE             - Set any config value")

if __name__ == "__main__":
    main()
