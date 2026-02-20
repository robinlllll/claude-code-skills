"""Configuration for coverage initiation pipeline."""

import os
import sys
from pathlib import Path

# UTF-8 console fix for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
from dotenv import load_dotenv

for env_path in [
    Path.home() / "Screenshots" / ".env",
    Path.home() / ".env",
    Path.home() / "13F-CLAUDE" / ".env",
]:
    if env_path.exists():
        load_dotenv(env_path, override=False)

# --------------- API Keys ---------------
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get(
    "GOOGLE_API_KEY", ""
)
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --------------- Models ---------------
MODELS = {
    "perplexity": "sonar-pro",
    "claude_analysis": "claude-sonnet-4-6",
    "claude_synthesis": "claude-opus-4-6",
    "gpt": "gpt-5.2-chat-latest",
    "gemini": "gemini-3-pro-preview",
    "grok": "grok-4-1-fast-reasoning",
}

# --------------- Paths ---------------
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
PROMPTS_DIR = SKILL_DIR / "prompts"
RUNS_DIR = SKILL_DIR / "runs"

VAULT_PATH = Path.home() / "Documents" / "Obsidian Vault"
OUTPUT_DIR = VAULT_PATH / "研究" / "Coverage Initiation"

SHARED_DIR = Path.home() / ".claude" / "skills" / "shared"

# --------------- SEC EDGAR ---------------
SEC_USER_AGENT = "Robin Research thisisrobin66@gmail.com"
SEC_BASE_URL = "https://data.sec.gov"
SEC_EFTS_URL = "https://efts.sec.gov/LATEST"
SEC_RATE_LIMIT = 0.12  # seconds between requests (10/sec max)

# --------------- Cache ---------------
CACHE_TTL_DAYS = 7

# --------------- Perplexity ---------------
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_MAX_QUERIES = 8  # max queries per collection run


# --------------- Preflight ---------------
def preflight_check() -> dict:
    """Validate all required API keys and dependencies."""
    results = {
        "perplexity": bool(PERPLEXITY_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "xai": bool(XAI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
    }
    results["ready"] = results["perplexity"] and (
        results["openai"] or results["gemini"]
    )
    return results
