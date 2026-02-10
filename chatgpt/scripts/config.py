"""
Configuration for ChatGPT Skill
Centralizes constants, selectors, and paths.

When ChatGPT UI changes, ONLY this file needs updating.
"""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
HISTORY_FILE = DATA_DIR / "history.json"

# Obsidian output
OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian Vault" / "ChatGPT"

# ── ChatGPT URL ────────────────────────────────────────────────

CHATGPT_URL = "https://chatgpt.com/"

# ── Input Selectors ────────────────────────────────────────────
# ChatGPT uses ProseMirror contenteditable; textarea is legacy fallback.
# Order: most specific first, broadest last.

INPUT_SELECTORS = [
    "#prompt-textarea",                                    # Primary (current)
    'div[contenteditable="true"][class*="ProseMirror"]',   # ProseMirror div
    'textarea[placeholder*="Message"]',                    # Legacy textarea
    'div[contenteditable="true"]',                         # Generic fallback
]

# ── Send Button Selectors ──────────────────────────────────────

SEND_BUTTON_SELECTORS = [
    'button[data-testid="send-button"]',      # Primary data-testid
    'button[aria-label*="Send"]',             # Aria label
    'button[aria-label*="send"]',             # Lowercase variant
]

# ── Response Selectors ─────────────────────────────────────────
# Used to find assistant responses in the DOM.

RESPONSE_SELECTORS = [
    'div[data-message-author-role="assistant"] .markdown',   # Primary
    'div[data-message-author-role="assistant"]',             # Without .markdown
    'div.agent-turn .markdown',                              # Agent turn variant
    'div[class*="response"] .markdown',                      # Class-based fallback
]

# ── Stop / Generating Indicators ──────────────────────────────
# Visible while ChatGPT is still generating a response.

STOP_BUTTON_SELECTORS = [
    'button[aria-label*="Stop"]',             # Primary
    'button[data-testid="stop-button"]',      # data-testid variant
    'button[aria-label*="stop"]',             # Lowercase
]

# ── Model Selection ────────────────────────────────────────────

MODEL_SELECTOR_BUTTONS = [
    'button[data-testid="model-selector"]',
    'button[aria-haspopup="menu"][class*="model"]',
    'div[class*="model-selector"] button',
    '[data-testid="model-switcher"]',
]

MODEL_MENU_ITEMS = [
    '[role="menuitem"]',
    '[role="option"]',
    'li[class*="menu"]',
    'div[class*="option"]',
]

# Maps user-friendly names → list of text fragments to search in the menu.
# When ChatGPT renames models, update the right-hand side.
MODEL_MAPPINGS = {
    "o3":                ["o3"],
    "gpt-4o":            ["4o", "GPT-4o"],
    "gpt-4":             ["GPT-4", "4-turbo"],
    "gpt-4.5":           ["4.5"],
    "o4-mini":           ["o4-mini"],
    "o4-mini-high":      ["o4-mini-high"],
    "deep-research":     ["deep research", "Deep Research"],
}

# ── Login / Auth Indicators ────────────────────────────────────

# Elements that prove the user IS logged in
LOGIN_INDICATORS = [
    'button[data-testid="profile-button"]',    # Profile menu
    'img[alt*="User"]',                        # User avatar
    'nav button[aria-label*="New"]',           # New-chat button in nav
]

# Elements that prove the user is NOT logged in
NO_AUTH_INDICATORS = [
    '[data-testid="modal-no-auth-login"]',     # Unauthenticated modal
]

# ── Popup Dismiss Selectors ────────────────────────────────────
# Overlays / modals that may appear and need dismissing.

POPUP_DISMISS_SELECTORS = [
    'button:has-text("Dismiss")',
    'button:has-text("Continue")',
    'button:has-text("Got it")',
    'button:has-text("Stay logged out")',
    '[aria-label="Close"]',
    'button:has-text("No thanks")',
    'button:has-text("Maybe later")',
]

# ── Browser Configuration ──────────────────────────────────────
# Per Patchright best practices (README):
#   - Do NOT add custom browser headers or user_agent
#   - Do NOT add args Patchright already handles internally
#   - Patchright auto-adds: --disable-blink-features=AutomationControlled
#   - Patchright auto-removes: --enable-automation
# See: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python#best-practice

# ── Timeouts ───────────────────────────────────────────────────

AUTH_TIMEOUT_MINUTES = 5            # Manual login window
AUTH_EXPIRY_DAYS = 3                # ChatGPT sessions expire faster than Google

RESPONSE_TIMEOUT_STANDARD = 120     # 2 min for normal models
RESPONSE_TIMEOUT_THINKING = 300     # 5 min for o3, deep-research, etc.

STABILITY_INTERVAL = 1.5            # Seconds between text stability checks
STABILITY_CHECKS = 3                # Consecutive identical checks to declare stable

PROGRESS_INTERVAL = 15              # Seconds between "still thinking" messages

PAGE_LOAD_TIMEOUT = 60000           # ms — networkidle wait
PAGE_EXTRA_WAIT = 3                 # seconds after page load before interaction

# Models that use extended timeout
THINKING_MODELS = {"o3", "o4-mini-high", "deep-research"}
