#!/usr/bin/env python3
"""
ChatGPT One-Shot Q&A Interface

Primary entry point for the ChatGPT skill.
Stateless per-question: opens browser, asks, extracts answer, closes.

Response detection uses a dual algorithm:
  Layer 1 (progress): Stop button visible → still generating
  Layer 2 (completion): Text stability polling — 3 identical reads at 1.5s intervals

Uses page.keyboard.type() for ProseMirror compatibility (not element.fill()).
"""

import argparse
import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from config import (
    CHATGPT_URL,
    INPUT_SELECTORS,
    SEND_BUTTON_SELECTORS,
    RESPONSE_SELECTORS,
    STOP_BUTTON_SELECTORS,
    MODEL_SELECTOR_BUTTONS,
    MODEL_MENU_ITEMS,
    MODEL_MAPPINGS,
    POPUP_DISMISS_SELECTORS,
    THINKING_MODELS,
    RESPONSE_TIMEOUT_STANDARD,
    RESPONSE_TIMEOUT_THINKING,
    STABILITY_INTERVAL,
    STABILITY_CHECKS,
    PROGRESS_INTERVAL,
    PAGE_LOAD_TIMEOUT,
    PAGE_EXTRA_WAIT,
)
from browser_utils import BrowserFactory, StealthUtils


def _dismiss_popups(page):
    """Dismiss any overlays/modals that may block interaction."""
    for selector in POPUP_DISMISS_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                StealthUtils.random_delay(300, 600)
        except Exception:
            continue


def _select_model(page, model_name: str) -> bool:
    """
    Select a model from ChatGPT's model picker.
    Returns True if selection succeeded.
    """
    model_key = model_name.lower()
    search_terms = [model_name, model_name.replace("-", " "), model_name.upper()]

    if model_key in MODEL_MAPPINGS:
        search_terms.extend(MODEL_MAPPINGS[model_key])

    print(f"  Selecting model: {model_name}...")

    # Step 1: Open the model selector dropdown
    selector_btn = None
    for selector in MODEL_SELECTOR_BUTTONS:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                selector_btn = el
                break
        except Exception:
            continue

    # Fallback: scan all buttons for model-related text
    if not selector_btn:
        buttons = page.query_selector_all("button")
        for btn in buttons:
            try:
                text = btn.inner_text().lower()
                if any(kw in text for kw in ["gpt", "model", "o3", "o4", "4o"]):
                    if btn.is_visible():
                        selector_btn = btn
                        break
            except Exception:
                continue

    if not selector_btn:
        print("  Model selector not found, using default model")
        return False

    selector_btn.click()
    time.sleep(1)

    # Step 2: Find and click the target model in the menu
    for item_selector in MODEL_MENU_ITEMS:
        try:
            items = page.query_selector_all(item_selector)
            for item in items:
                try:
                    item_text = item.inner_text().lower()
                    for term in search_terms:
                        if term.lower() in item_text:
                            item.click()
                            print(f"  Selected model: {item.inner_text().strip()}")
                            time.sleep(0.5)
                            return True
                except Exception:
                    continue
        except Exception:
            continue

    # Close dropdown if model not found
    page.keyboard.press("Escape")
    print(f"  Model '{model_name}' not found in menu, using default")
    return False


def _find_input(page) -> str:
    """
    Find the chat input element from selector fallback chain.
    Returns the selector that worked, or raises RuntimeError.
    """
    for selector in INPUT_SELECTORS:
        try:
            element = page.wait_for_selector(selector, timeout=8000, state="visible")
            if element:
                return selector
        except Exception:
            continue

    raise RuntimeError("Could not find chat input. ChatGPT UI may have changed.")


def _click_send(page):
    """Click the send button, or fallback to pressing Enter."""
    for selector in SEND_BUTTON_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                return
        except Exception:
            continue

    # Fallback: press Enter
    page.keyboard.press("Enter")


def _count_responses(page) -> int:
    """Count current assistant response elements."""
    for selector in RESPONSE_SELECTORS:
        elements = page.query_selector_all(selector)
        if elements:
            return len(elements)
    return 0


def _get_latest_response_text(page, min_index: int = 0) -> str:
    """
    Get text from the latest assistant response element.
    Only considers elements at index >= min_index (to skip pre-existing responses).
    """
    for selector in RESPONSE_SELECTORS:
        elements = page.query_selector_all(selector)
        if elements and len(elements) > min_index:
            # Take the last element that's after min_index
            latest = elements[-1]
            try:
                text = latest.inner_text().strip()
                if text:
                    return text
            except Exception:
                continue
    return ""


def _is_generating(page) -> bool:
    """Check if ChatGPT is still generating (stop button visible)."""
    for selector in STOP_BUTTON_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                return True
        except Exception:
            continue
    return False


def _wait_for_response(page, initial_count: int, timeout: int) -> str:
    """
    Wait for ChatGPT to finish generating and return the response text.

    Dual detection algorithm:
      Layer 1: Stop button visible → still generating (progress every 15s)
      Layer 2: Text stability — poll text at STABILITY_INTERVAL, declare done
               after STABILITY_CHECKS consecutive identical non-empty reads
    """
    deadline = time.time() + timeout
    start_time = time.time()
    last_progress = 0

    stable_count = 0
    last_text = ""
    response_detected = False

    while time.time() < deadline:
        elapsed = int(time.time() - start_time)

        # Layer 1: Progress reporting while generating
        if _is_generating(page):
            if elapsed - last_progress >= PROGRESS_INTERVAL:
                print(f"  Still generating... ({elapsed}s)")
                last_progress = elapsed
            time.sleep(1)
            # Reset stability since we know it's still going
            stable_count = 0
            last_text = ""
            continue

        # Layer 2: Text stability polling
        current_count = _count_responses(page)

        if current_count > initial_count or response_detected:
            if not response_detected:
                response_detected = True
                print(f"  Response detected (elements: {initial_count} -> {current_count})")

            text = _get_latest_response_text(page, min_index=initial_count)

            if text:
                if text == last_text:
                    stable_count += 1
                    if stable_count >= STABILITY_CHECKS:
                        return text
                else:
                    stable_count = 0
                    last_text = text

            time.sleep(STABILITY_INTERVAL)
        else:
            # No new elements yet — maybe still loading
            if elapsed - last_progress >= PROGRESS_INTERVAL:
                print(f"  Waiting for response... ({elapsed}s)")
                last_progress = elapsed
            time.sleep(1)

    # Timeout — return whatever we have
    if last_text:
        print(f"  Warning: Timeout reached but returning partial response")
        return last_text

    return ""


def ask_chatgpt(question: str, model: str = None, no_history: bool = False) -> str:
    """
    Ask a question to ChatGPT and return the answer.

    Args:
        question: The question to ask
        model: Optional model to select (e.g., "o3", "gpt-4o")
        no_history: If True, skip saving to history

    Returns:
        Answer text, or empty string on failure
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("Not authenticated. Run: python run.py auth_manager setup")
        return ""

    print(f"Question: {question[:80]}{'...' if len(question) > 80 else ''}")
    if model:
        print(f"Model: {model}")

    # Determine timeout based on model
    timeout = RESPONSE_TIMEOUT_STANDARD
    if model and model.lower() in THINKING_MODELS:
        timeout = RESPONSE_TIMEOUT_THINKING
        print(f"  Using extended timeout ({timeout}s) for thinking model")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()

        # Always visible — ChatGPT blocks headless
        context = BrowserFactory.launch_persistent_context(playwright, headless=False)

        page = context.new_page()
        print("  Opening ChatGPT...")
        page.goto(CHATGPT_URL, wait_until="domcontentloaded")

        # Wait for page to fully load (no-auth modal renders async)
        try:
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
        except Exception:
            print("  Page load slow, waiting extra...")
        time.sleep(5)  # Critical: no-auth modal loads after initial render

        # Check for auth redirect (definitive "not logged in")
        if "auth.openai.com" in page.url or "login" in page.url.lower():
            print("  Session expired. Please re-authenticate:")
            print("  python run.py auth_manager setup")
            return ""

        # Check for no-auth modal (definitive "not logged in")
        from config import NO_AUTH_INDICATORS
        for selector in NO_AUTH_INDICATORS:
            no_auth = page.query_selector(selector)
            if no_auth:
                print("  Not logged in (no-auth modal detected).")
                print("  Please re-authenticate: python run.py auth_manager setup")
                return ""

        # Dismiss any popups (consent, "got it", etc.)
        _dismiss_popups(page)

        # Select model if requested
        if model:
            try:
                _select_model(page, model)
                time.sleep(1)
            except Exception as e:
                print(f"  Model selection skipped: {e}")

        # Dismiss popups again (model selection can trigger new ones)
        _dismiss_popups(page)

        # Find and focus input
        print("  Finding input...")
        input_selector = _find_input(page)

        # Snapshot response count before typing
        initial_count = _count_responses(page)

        # Click to focus the input element
        input_el = page.query_selector(input_selector)
        if input_el:
            input_el.click()
            StealthUtils.random_delay(200, 400)

        # Type the question using keyboard (ProseMirror compatible)
        print("  Typing question...")
        StealthUtils.human_type(page, question)

        StealthUtils.random_delay(300, 600)

        # Send
        print("  Sending...")
        _click_send(page)
        StealthUtils.random_delay(500, 1500)

        # Wait for response
        print("  Waiting for response...")
        answer = _wait_for_response(page, initial_count, timeout)

        if not answer:
            print("  Timeout: no response received")
            return ""

        print("  Got answer!")

        # Refresh cookies (keep session alive)
        try:
            context.storage_state(path=str(auth.state_file))
        except Exception:
            pass

        # Save to history
        if not no_history:
            try:
                from history_manager import HistoryManager
                mgr = HistoryManager()
                mgr.save(question, answer, model=model or "default")
            except Exception as e:
                print(f"  (history save failed: {e})", file=sys.stderr)

        return answer

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        return ""

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


def main():
    parser = argparse.ArgumentParser(description="Ask ChatGPT a question")

    parser.add_argument("--question", required=True, help="Question to ask")
    parser.add_argument("--model", help="Model to use (e.g., o3, gpt-4o)")
    parser.add_argument("--no-history", action="store_true", help="Skip saving to history")

    args = parser.parse_args()

    answer = ask_chatgpt(
        question=args.question,
        model=args.model,
        no_history=args.no_history,
    )

    if answer:
        print("\n" + "=" * 60)
        print(f"Question: {args.question}")
        print("=" * 60)
        print()
        print(answer)
        print()
        print("=" * 60)
        return 0
    else:
        print("\nFailed to get answer")
        return 1


if __name__ == "__main__":
    sys.exit(main())
