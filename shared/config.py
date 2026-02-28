#!/usr/bin/env python3
"""
Centralized configuration for the skill system.
All paths, API keys, and thresholds in one place.
"""

import os
from pathlib import Path

# ── Load .env files ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / "Screenshots" / ".env")
    load_dotenv(Path.home() / "13F-CLAUDE" / ".env", override=False)
except ImportError:
    pass

# ── Paths ────────────────────────────────────────────────────────────────────

HOME = Path.home()
VAULT = HOME / "Documents" / "Obsidian Vault"
SKILLS_DIR = HOME / ".claude" / "skills"
SHARED_DIR = SKILLS_DIR / "shared"
DATA_DIR = HOME / ".claude" / "data"
LOGS_DIR = HOME / ".claude" / "logs"
PYTHON = Path("/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe")

# Vault subdirectories
VAULT_INBOX = VAULT / "收件箱"
VAULT_RESEARCH = VAULT / "研究"
VAULT_RESEARCH_SUMMARY = VAULT / "研究" / "研报摘要"
VAULT_SELLSIDE = VAULT / "研究" / "卖方跟踪"
VAULT_EARNINGS = VAULT / "研究" / "财报分析"
VAULT_SOURCES = VAULT / "信息源"
VAULT_MEETINGS = VAULT / "周会"
VAULT_PORTFOLIO = VAULT / "PORTFOLIO"
VAULT_THESIS_DIR = VAULT_PORTFOLIO / "research" / "companies"

# Data files
VECTOR_MEMORY_DB = DATA_DIR / "vector_memory.db"
PRICE_ALERTS_LOG = DATA_DIR / "price_alerts.jsonl"
PRICE_MONITOR_STATE = DATA_DIR / "price_monitor_state.json"
INGESTION_STATE_DB = SHARED_DIR / "data" / "ingestion_state.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── API Keys ─────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "")

# Fallback: try prompt-optimizer config
if not GEMINI_API_KEY:
    _gemini_cfg = SKILLS_DIR / "prompt-optimizer" / "data" / "config.json"
    if _gemini_cfg.exists():
        import json
        _cfg = json.loads(_gemini_cfg.read_text(encoding="utf-8"))
        GEMINI_API_KEY = _cfg.get("GEMINI_API_KEY", "")

# ── Thresholds ───────────────────────────────────────────────────────────────

# Price monitor
PRICE_CHECK_INTERVAL_SECONDS = 600          # 10 minutes
PRICE_INTRADAY_THRESHOLD_PCT = 3.0          # Daily change to trigger alert
PRICE_RAPID_THRESHOLD_PCT = 2.0             # Change since last check
PRICE_VOLUME_THRESHOLD_RATIO = 2.0          # Volume vs 20-day avg
PRICE_DEDUP_WINDOW_HOURS = 2                # Same ticker+direction cooldown

# Morning brief
MORNING_BRIEF_MOVER_THRESHOLD = 3.0         # >3% flagged as big mover
MORNING_BRIEF_STALE_THESIS_DAYS = 30
MORNING_BRIEF_MAX_TICKERS = 20

# Vector memory
VECTOR_EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_EMBEDDING_DIM = 1536
VECTOR_MIN_SCORE = 0.70
VECTOR_MAX_CHUNK_CHARS = 4000

# Sellside tracker
SELLSIDE_DATA_DIR = SKILLS_DIR / "sellside-tracker" / "data"
SELLSIDE_TEMPLATES_DIR = SKILLS_DIR / "sellside-tracker" / "templates"

# Premium news domains
PREMIUM_NEWS_DOMAINS = {
    "bloomberg.com": "bloomberg",
    "wsj.com": "wsj",
    "ft.com": "ft",
    "reuters.com": "reuters",
    "barrons.com": "barrons",
}

# ── IBKR → yfinance Ticker Mapping ───────────────────────────────────────────

# Explicit overrides for tickers where IBKR format ≠ yfinance format
IBKR_TO_YFINANCE = {
    "AIRd": "AIR.PA",       # Airbus (Euronext Paris)
    "ADYEN": "ADYEN.AS",    # Adyen (Euronext Amsterdam)
    # "AS" = Amer Sports (NYSE), plain "AS" works on yfinance — no mapping needed
    "BURBY": "BRBY.L",      # Burberry (London)
    "MC": "MC.PA",          # LVMH (Euronext Paris)
    "PRX": "PRX.AS",        # Prosus (Euronext Amsterdam)
    "RMS": "RMS.PA",        # Hermès (Euronext Paris)
    "PUM": "PUM.DE",        # Puma (Frankfurt)
    "UBI": "UBI.PA",        # Ubisoft (Euronext Paris)
    "WOSG": "WOSG.L",       # Watches of Switzerland (London)
    "SMT": "SMT.L",         # Scottish Mortgage Trust (London)
    "S58": "S58.SI",        # SATS (Singapore)
    "BN": "BN.TO",          # Brookfield (Toronto)
    "690D": "6690.HK",      # Haier Smart Home (German listing → HK)
    "546": "0546.HK",       # Fufeng Group (Hong Kong)
    "960": "0960.HK",       # Longfor (Hong Kong)
}


def normalize_ticker_for_yfinance(ticker: str) -> str | None:
    """Convert IBKR ticker to yfinance format. Returns None to skip."""
    # Explicit mapping first
    if ticker in IBKR_TO_YFINANCE:
        return IBKR_TO_YFINANCE[ticker]
    # Pure 3-4 digit numbers → HK stocks (pad to 4 + .HK)
    if ticker.isdigit() and len(ticker) <= 4:
        return f"{int(ticker):04d}.HK"
    # Already has exchange suffix (.T, .L, .PA, etc.) → pass through
    if "." in ticker:
        return ticker
    # Standard US ticker → pass through
    return ticker


# ── Model Names ──────────────────────────────────────────────────────────────

MODEL_GEMINI_FLASH = "gemini-2.0-flash"
MODEL_GEMINI_PRO = "gemini-3-pro-preview"
MODEL_GPT = "gpt-5.2-chat-latest"
MODEL_GROK = "grok-4-1-fast-reasoning"
MODEL_EMBEDDING = "text-embedding-3-small"
