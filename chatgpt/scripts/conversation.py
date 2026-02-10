#!/usr/bin/env python3
"""
ChatGPT Multi-Turn Conversation Manager

Keeps browser open across multiple questions in the same conversation.
Uses element-count tracking to detect new responses (like NotebookLM).

Usage:
  conversation.py start [--model o3]     → opens browser, prints session_id
  conversation.py ask --question "..."   → types in existing page
  conversation.py end                    → closes browser, saves history
"""

import argparse
import json
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
    POPUP_DISMISS_SELECTORS,
    THINKING_MODELS,
    RESPONSE_TIMEOUT_STANDARD,
    RESPONSE_TIMEOUT_THINKING,
    STABILITY_INTERVAL,
    STABILITY_CHECKS,
    PROGRESS_INTERVAL,
    PAGE_LOAD_TIMEOUT,
    PAGE_EXTRA_WAIT,
    DATA_DIR,
)
from browser_utils import BrowserFactory, StealthUtils


SESSION_FILE = DATA_DIR / "active_session.json"


class ChatGPTSession:
    """
    Manages a multi-turn ChatGPT conversation.

    The browser stays open between questions. Response detection uses
    element counting: snapshot count before each question, wait for
    count to increase, then apply text stability polling.
    """

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self.model = None
        self.response_count = 0
        self.qa_pairs = []

    def start(self, model: str = None) -> bool:
        """
        Start a new conversation session.
        Opens browser, navigates to ChatGPT, optionally selects model.
        """
        auth = AuthManager()
        if not auth.is_authenticated():
            print("Not authenticated. Run: python run.py auth_manager setup")
            return False

        self.model = model
        print("Starting conversation session...")

        try:
            self.playwright = sync_playwright().start()
            self.context = BrowserFactory.launch_persistent_context(
                self.playwright, headless=False
            )

            self.page = self.context.new_page()
            self.page.goto(CHATGPT_URL, wait_until="domcontentloaded")

            try:
                self.page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
            except Exception:
                pass
            time.sleep(PAGE_EXTRA_WAIT)

            # Dismiss popups
            for selector in POPUP_DISMISS_SELECTORS:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(0.5)
                except Exception:
                    continue

            # Select model if requested
            if model:
                from ask_question import _select_model
                try:
                    _select_model(self.page, model)
                    time.sleep(1)
                except Exception as e:
                    print(f"  Model selection skipped: {e}")

            # Snapshot initial response count
            self.response_count = self._count_responses()

            # Save session state
            self._save_session()

            print("Session started. Use 'conversation.py ask --question ...' to ask.")
            return True

        except Exception as e:
            print(f"Error starting session: {e}")
            self.close()
            return False

    def ask(self, question: str) -> str:
        """
        Ask a question in the current conversation.
        Returns the answer text.
        """
        if not self.page:
            print("No active session. Run 'conversation.py start' first.")
            return ""

        print(f"Asking: {question[:80]}{'...' if len(question) > 80 else ''}")

        timeout = RESPONSE_TIMEOUT_STANDARD
        if self.model and self.model.lower() in THINKING_MODELS:
            timeout = RESPONSE_TIMEOUT_THINKING

        # Snapshot current response count
        initial_count = self._count_responses()

        # Find and focus input
        input_selector = None
        for selector in INPUT_SELECTORS:
            try:
                el = self.page.wait_for_selector(selector, timeout=5000, state="visible")
                if el:
                    el.click()
                    StealthUtils.random_delay(200, 400)
                    input_selector = selector
                    break
            except Exception:
                continue

        if not input_selector:
            print("Could not find input element")
            return ""

        # Type question
        StealthUtils.human_type(self.page, question)
        StealthUtils.random_delay(300, 600)

        # Send
        sent = False
        for selector in SEND_BUTTON_SELECTORS:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    sent = True
                    break
            except Exception:
                continue
        if not sent:
            self.page.keyboard.press("Enter")

        StealthUtils.random_delay(500, 1500)

        # Wait for response using same dual algorithm as ask_question.py
        answer = self._wait_for_response(initial_count, timeout)

        if answer:
            self.qa_pairs.append({"question": question, "answer": answer})
            self.response_count = self._count_responses()
            print("  Got answer!")
        else:
            print("  Timeout: no response received")

        return answer

    def end(self) -> list:
        """
        End the conversation session.
        Closes browser and saves all Q&A pairs to history.
        Returns the list of Q&A pairs.
        """
        print("Ending conversation session...")

        # Save all Q&A to history
        if self.qa_pairs:
            try:
                from history_manager import HistoryManager
                mgr = HistoryManager()
                for qa in self.qa_pairs:
                    mgr.save(qa["question"], qa["answer"], model=self.model or "default")
                print(f"  Saved {len(self.qa_pairs)} Q&A pairs to history")
            except Exception as e:
                print(f"  History save failed: {e}")

        # Refresh cookies before closing
        if self.context:
            try:
                auth = AuthManager()
                self.context.storage_state(path=str(auth.state_file))
            except Exception:
                pass

        pairs = list(self.qa_pairs)
        self.close()
        self._clear_session()

        print("Session ended.")
        return pairs

    def close(self):
        """Close browser resources."""
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
        self.page = None

    def _count_responses(self) -> int:
        """Count current assistant response elements."""
        if not self.page:
            return 0
        for selector in RESPONSE_SELECTORS:
            elements = self.page.query_selector_all(selector)
            if elements:
                return len(elements)
        return 0

    def _is_generating(self) -> bool:
        """Check if stop button is visible."""
        if not self.page:
            return False
        for selector in STOP_BUTTON_SELECTORS:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _wait_for_response(self, initial_count: int, timeout: int) -> str:
        """Wait for response with dual detection (stop button + text stability)."""
        deadline = time.time() + timeout
        start_time = time.time()
        last_progress = 0

        stable_count = 0
        last_text = ""
        response_detected = False

        while time.time() < deadline:
            elapsed = int(time.time() - start_time)

            if self._is_generating():
                if elapsed - last_progress >= PROGRESS_INTERVAL:
                    print(f"  Still generating... ({elapsed}s)")
                    last_progress = elapsed
                time.sleep(1)
                stable_count = 0
                last_text = ""
                continue

            current_count = self._count_responses()

            if current_count > initial_count or response_detected:
                if not response_detected:
                    response_detected = True

                # Get latest response text
                text = ""
                for selector in RESPONSE_SELECTORS:
                    elements = self.page.query_selector_all(selector)
                    if elements and len(elements) > initial_count:
                        try:
                            text = elements[-1].inner_text().strip()
                        except Exception:
                            pass
                        if text:
                            break

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
                if elapsed - last_progress >= PROGRESS_INTERVAL:
                    print(f"  Waiting for response... ({elapsed}s)")
                    last_progress = elapsed
                time.sleep(1)

        return last_text if last_text else ""

    def _save_session(self):
        """Save session metadata for CLI resumption."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        info = {
            "active": True,
            "model": self.model,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "qa_count": len(self.qa_pairs),
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(info, f, indent=2)

    def _clear_session(self):
        """Remove session file."""
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()


# ── Singleton for CLI usage ─────────────────────────────────────
# The CLI commands (start/ask/end) need to share one session object.
# Since each CLI invocation is a separate process, multi-turn via CLI
# requires the browser to stay open in one process.

_session = ChatGPTSession()


def main():
    parser = argparse.ArgumentParser(description="ChatGPT Multi-Turn Conversation")
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start conversation")
    start_parser.add_argument("--model", help="Model to use")

    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("--question", required=True, help="Question to ask")

    subparsers.add_parser("end", help="End conversation")

    # Interactive mode (recommended for multi-turn)
    interactive_parser = subparsers.add_parser("interactive", help="Interactive multi-turn session")
    interactive_parser.add_argument("--model", help="Model to use")

    args = parser.parse_args()

    if args.command == "start":
        if _session.start(model=args.model):
            print("\nSession active. Run 'conversation.py ask --question ...'")
            print("Or use 'conversation.py interactive' for a REPL.\n")
            # Keep browser open
            print("Press Ctrl+C to end session.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                _session.end()

    elif args.command == "interactive":
        model = args.model
        if not _session.start(model=model):
            sys.exit(1)

        print("\nInteractive mode. Type your questions (empty line to end).\n")
        try:
            while True:
                question = input("You: ").strip()
                if not question:
                    break
                answer = _session.ask(question)
                if answer:
                    print(f"\nChatGPT: {answer}\n")
                else:
                    print("\n(no response)\n")
        except (KeyboardInterrupt, EOFError):
            pass

        _session.end()

    elif args.command == "ask":
        # Note: This only works if 'start' is running in the same process.
        # For cross-process multi-turn, use 'interactive' mode.
        print("Note: 'ask' requires an active session in the same process.")
        print("Use 'conversation.py interactive' for multi-turn sessions.")

    elif args.command == "end":
        _session.end()

    else:
        parser.print_help()
        print("\nRecommended: Use 'conversation.py interactive --model o3' for multi-turn sessions.")


if __name__ == "__main__":
    main()
