"""Lightweight Telegram push sender. Zero bot dependencies."""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / "Screenshots" / ".env")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "")


def notify(text: str, parse_mode: str = "Markdown", sensitive: bool = False) -> bool:
    """Push message to Robin's Telegram. Best-effort, never raises.

    If sensitive=True, sends only a generic alert (no financial data in message body).
    """
    if not BOT_TOKEN or not CHAT_ID:
        return False
    if sensitive:
        text = text.split("\n")[0] + "\n📎 Details on localhost dashboard"
    if len(text) > 4000:
        text = text[:3980] + "\n\n... (truncated)"
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def notify_file(file_path: str, caption: str = "") -> bool:
    """Send a file to Robin's Telegram. Best-effort, never raises."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": CHAT_ID, "caption": caption[:1024]},
                files={"document": f},
                timeout=30,
            )
        return resp.status_code == 200
    except Exception:
        return False
