#!/usr/bin/env python3
"""
ChatGPT Selector Debugger
Opens visible browser, navigates to chatgpt.com, scans all selector groups
from config.py, and reports which selectors have matches.

Use when ChatGPT UI changes break the skill.
"""

import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CHATGPT_URL,
    INPUT_SELECTORS,
    SEND_BUTTON_SELECTORS,
    RESPONSE_SELECTORS,
    STOP_BUTTON_SELECTORS,
    MODEL_SELECTOR_BUTTONS,
    LOGIN_INDICATORS,
    NO_AUTH_INDICATORS,
    POPUP_DISMISS_SELECTORS,
    PAGE_LOAD_TIMEOUT,
)
from browser_utils import BrowserFactory


SELECTOR_GROUPS = {
    "INPUT_SELECTORS": INPUT_SELECTORS,
    "SEND_BUTTON_SELECTORS": SEND_BUTTON_SELECTORS,
    "RESPONSE_SELECTORS": RESPONSE_SELECTORS,
    "STOP_BUTTON_SELECTORS": STOP_BUTTON_SELECTORS,
    "MODEL_SELECTOR_BUTTONS": MODEL_SELECTOR_BUTTONS,
    "LOGIN_INDICATORS": LOGIN_INDICATORS,
    "NO_AUTH_INDICATORS": NO_AUTH_INDICATORS,
    "POPUP_DISMISS_SELECTORS": POPUP_DISMISS_SELECTORS,
}


def main():
    print("ChatGPT Selector Debugger")
    print("=" * 50)
    print("Opening browser and navigating to ChatGPT...\n")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=False)

        page = context.new_page()
        page.goto(CHATGPT_URL, wait_until="domcontentloaded")

        try:
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
        except Exception:
            pass
        time.sleep(5)  # Extra settle time

        print(f"Current URL: {page.url}\n")

        # Scan each selector group
        total_working = 0
        total_broken = 0

        for group_name, selectors in SELECTOR_GROUPS.items():
            print(f"--- {group_name} ---")
            group_found = False

            for selector in selectors:
                try:
                    elements = page.query_selector_all(selector)
                    count = len(elements)
                    if count > 0:
                        # Check visibility of first match
                        visible = False
                        try:
                            visible = elements[0].is_visible()
                        except Exception:
                            pass

                        status = "VISIBLE" if visible else "HIDDEN"
                        print(f"  [OK]   {selector}  ({count} match, {status})")
                        total_working += 1
                        group_found = True
                    else:
                        print(f"  [MISS] {selector}")
                        total_broken += 1
                except Exception as e:
                    print(f"  [ERR]  {selector}  ({e})")
                    total_broken += 1

            if not group_found:
                print(f"  *** NO WORKING SELECTORS IN THIS GROUP ***")
            print()

        # Summary
        print("=" * 50)
        print(f"Summary: {total_working} working, {total_broken} missing/broken")
        print()

        # Extra diagnostics: dump visible buttons
        print("--- VISIBLE BUTTONS ---")
        buttons = page.query_selector_all("button")
        visible_buttons = []
        for btn in buttons:
            try:
                if btn.is_visible():
                    text = btn.inner_text().strip()
                    if text and len(text) < 50:
                        attrs = {}
                        for attr in ["data-testid", "aria-label"]:
                            val = btn.get_attribute(attr)
                            if val:
                                attrs[attr] = val
                        visible_buttons.append((text, attrs))
            except Exception:
                continue

        for text, attrs in visible_buttons[:25]:
            attr_str = ", ".join(f'{k}="{v}"' for k, v in attrs.items())
            print(f"  '{text}'" + (f"  [{attr_str}]" if attr_str else ""))

        print(f"\n  ({len(visible_buttons)} total visible buttons)")
        print("\nPress Ctrl+C to close browser.")

        # Keep browser open for manual inspection
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nClosing...")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
