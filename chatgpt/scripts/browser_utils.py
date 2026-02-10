"""
Browser Utilities for ChatGPT Skill

Per Patchright official best practice (README):
  launch_persistent_context(user_data_dir, channel="chrome", headless=False, no_viewport=True)
  Do NOT add custom browser headers or user_agent.
  Do NOT add args that Patchright already handles internally.
See: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python#best-practice
"""

import json
import time
import random
from typing import Optional

from patchright.sync_api import Playwright, BrowserContext, Page
from config import BROWSER_PROFILE_DIR, STATE_FILE


class BrowserFactory:
    """Factory for creating configured browser contexts"""

    @staticmethod
    def launch_persistent_context(
        playwright: Playwright,
        headless: bool = False,
        user_data_dir: str = str(BROWSER_PROFILE_DIR),
    ) -> BrowserContext:
        """
        Launch persistent context per Patchright best practice.
        Minimal config — let Patchright handle anti-detection internally.
        """
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=headless,
            no_viewport=True,
            # Patchright handles everything else:
            #   - auto-adds --disable-blink-features=AutomationControlled
            #   - auto-removes --enable-automation
            #   - patches Runtime.enable, Console.enable, etc.
        )

        # Cookie workaround for Playwright bug #36139
        # Session cookies (expires=-1) don't persist in user_data_dir
        BrowserFactory._inject_cookies(context)

        return context

    @staticmethod
    def _inject_cookies(context: BrowserContext):
        """Inject cookies from state.json if available"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    if "cookies" in state and len(state["cookies"]) > 0:
                        context.add_cookies(state["cookies"])
            except Exception as e:
                print(f"  Warning: Could not load state.json: {e}")


class StealthUtils:
    """Human-like interaction utilities"""

    @staticmethod
    def random_delay(min_ms: int = 100, max_ms: int = 500):
        """Add random delay to mimic human timing"""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    @staticmethod
    def human_type(page: Page, text: str):
        """
        Type text with human-like speed using page.keyboard.type().

        Unlike element.fill(), keyboard.type() fires real key events that
        ProseMirror's contenteditable div actually processes. The element
        must already be focused before calling this.
        """
        for char in text:
            page.keyboard.type(char, delay=random.uniform(25, 75))
            # Occasional micro-pause (5% chance) to mimic natural rhythm
            if random.random() < 0.05:
                time.sleep(random.uniform(0.15, 0.4))

    @staticmethod
    def focus_input(page: Page, selectors: list) -> Optional[str]:
        """
        Find and click-focus an input element from a list of selectors.
        Returns the selector that matched, or None if nothing found.
        """
        for selector in selectors:
            try:
                element = page.wait_for_selector(selector, timeout=5000, state="visible")
                if element:
                    element.click()
                    StealthUtils.random_delay(200, 400)
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    def realistic_click(page: Page, selector: str) -> bool:
        """Click with realistic mouse movement"""
        element = page.query_selector(selector)
        if not element:
            return False

        box = element.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            page.mouse.move(x, y, steps=5)

        StealthUtils.random_delay(100, 300)
        element.click()
        StealthUtils.random_delay(100, 300)
        return True
