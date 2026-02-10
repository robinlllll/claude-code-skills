#!/usr/bin/env python3
"""
Authentication Manager for ChatGPT Skill
Handles ChatGPT login detection and browser state persistence.

ChatGPT auth detection is DOM-based (not URL-based like Google):
- Logged in:  profile-button, user avatar, new-chat nav button
- Logged out: modal-no-auth-login modal

Uses persistent browser context for fingerprint consistency +
manual cookie injection for session cookies (Playwright bug #36139).
"""

import json
import time
import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, Any

from patchright.sync_api import sync_playwright, BrowserContext

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    BROWSER_STATE_DIR,
    STATE_FILE,
    AUTH_INFO_FILE,
    DATA_DIR,
    CHATGPT_URL,
    LOGIN_INDICATORS,
    NO_AUTH_INDICATORS,
    AUTH_TIMEOUT_MINUTES,
    AUTH_EXPIRY_DAYS,
)
from browser_utils import BrowserFactory


class AuthManager:
    """
    Manages authentication and browser state for ChatGPT.

    Features:
    - Interactive login with DOM-based detection
    - Browser state persistence (cookies + profile)
    - Session validation
    - 3-day expiry warning
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

        self.state_file = STATE_FILE
        self.auth_info_file = AUTH_INFO_FILE
        self.browser_state_dir = BROWSER_STATE_DIR

    def is_authenticated(self) -> bool:
        """Check if valid authentication exists (state file present and not too old)"""
        if not self.state_file.exists():
            return False

        age_days = (time.time() - self.state_file.stat().st_mtime) / 86400
        if age_days > AUTH_EXPIRY_DAYS:
            print(f"  Warning: Browser state is {age_days:.1f} days old, may need re-authentication")

        return True

    def get_auth_info(self) -> Dict[str, Any]:
        """Get authentication information"""
        info = {
            "authenticated": self.is_authenticated(),
            "state_file": str(self.state_file),
            "state_exists": self.state_file.exists(),
        }

        if self.auth_info_file.exists():
            try:
                with open(self.auth_info_file, "r") as f:
                    saved_info = json.load(f)
                    info.update(saved_info)
            except Exception:
                pass

        if info["state_exists"]:
            info["state_age_hours"] = (time.time() - self.state_file.stat().st_mtime) / 3600

        return info

    def _check_logged_in(self, page) -> bool:
        """
        Check if user is logged in by probing DOM elements.
        Ported from chatgpt_bridge.py:77-111.

        Returns True if logged in, False if not or uncertain.
        """
        try:
            current_url = page.url

            # Skip if on auth/login pages
            if "auth" in current_url.lower() or "login" in current_url.lower():
                return False

            # Check for NO-AUTH modal — definitive "not logged in"
            for selector in NO_AUTH_INDICATORS:
                no_auth = page.query_selector(selector)
                if no_auth:
                    return False

            # Check for logged-in indicators
            for selector in LOGIN_INDICATORS:
                element = page.query_selector(selector)
                if element:
                    # Double-check: wait 1s and re-verify no-auth modal didn't appear
                    time.sleep(1)
                    for na_selector in NO_AUTH_INDICATORS:
                        if page.query_selector(na_selector):
                            return False
                    return True

        except Exception:
            pass

        return False

    def setup_auth(self, timeout_minutes: float = None) -> bool:
        """
        Perform interactive authentication setup.
        Opens visible browser, waits for manual login.

        Returns True if authentication successful.
        """
        if timeout_minutes is None:
            timeout_minutes = AUTH_TIMEOUT_MINUTES

        print("Starting authentication setup...")
        print(f"  Timeout: {timeout_minutes} minutes")

        playwright = None
        context = None

        try:
            playwright = sync_playwright().start()

            # Always visible for login
            context = BrowserFactory.launch_persistent_context(
                playwright, headless=False
            )

            page = context.new_page()
            page.goto(CHATGPT_URL, wait_until="domcontentloaded")

            # Wait for page to fully settle (no-auth modal loads async)
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            time.sleep(5)  # Critical: no-auth modal renders after initial load

            # Check if already authenticated
            if self._check_logged_in(page):
                print("  Already authenticated!")
                self._save_browser_state(context)
                self._save_auth_info()
                return True

            # Wait for manual login
            print("\n  Please log in to ChatGPT in the browser window...")
            print(f"  Waiting up to {timeout_minutes} minutes for login...")

            timeout_seconds = timeout_minutes * 60
            start_time = time.time()
            last_status = 0

            while time.time() - start_time < timeout_seconds:
                if self._check_logged_in(page):
                    print("  Login successful!")
                    self._save_browser_state(context)
                    self._save_auth_info()
                    return True

                elapsed = int(time.time() - start_time)
                if elapsed - last_status >= 10:
                    print(f"  Still waiting... ({elapsed}s / {int(timeout_seconds)}s)")
                    last_status = elapsed

                time.sleep(2)

            print("  Authentication timeout")
            return False

        except Exception as e:
            print(f"  Error: {e}")
            return False

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

    def _save_browser_state(self, context: BrowserContext):
        """Save browser state (cookies, localStorage) to disk"""
        try:
            context.storage_state(path=str(self.state_file))
            print(f"  Saved browser state to: {self.state_file}")
        except Exception as e:
            print(f"  Failed to save browser state: {e}")
            raise

    def _save_auth_info(self):
        """Save authentication metadata"""
        try:
            info = {
                "authenticated_at": time.time(),
                "authenticated_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.auth_info_file, "w") as f:
                json.dump(info, f, indent=2)
        except Exception:
            pass

    def clear_auth(self) -> bool:
        """Clear all authentication data"""
        print("Clearing authentication data...")

        try:
            if self.state_file.exists():
                self.state_file.unlink()
                print("  Removed browser state")

            if self.auth_info_file.exists():
                self.auth_info_file.unlink()
                print("  Removed auth info")

            if self.browser_state_dir.exists():
                shutil.rmtree(self.browser_state_dir)
                self.browser_state_dir.mkdir(parents=True, exist_ok=True)
                print("  Cleared browser data")

            return True

        except Exception as e:
            print(f"  Error clearing auth: {e}")
            return False

    def re_auth(self, timeout_minutes: float = None) -> bool:
        """Re-authenticate (clear + setup)"""
        print("Starting re-authentication...")
        self.clear_auth()
        return self.setup_auth(timeout_minutes)

    def validate_auth(self) -> bool:
        """
        Validate that stored authentication works by opening ChatGPT
        and checking login state.
        """
        if not self.is_authenticated():
            return False

        print("Validating authentication...")

        playwright = None
        context = None

        try:
            playwright = sync_playwright().start()

            # Validate with visible browser (ChatGPT blocks headless)
            context = BrowserFactory.launch_persistent_context(
                playwright, headless=False
            )

            page = context.new_page()
            page.goto(CHATGPT_URL, wait_until="domcontentloaded")

            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                time.sleep(5)

            time.sleep(3)  # Let JS hydrate

            if self._check_logged_in(page):
                # Refresh cookies while we're here
                self._save_browser_state(context)
                print("  Authentication is valid")
                return True
            else:
                print("  Authentication is invalid or expired")
                return False

        except Exception as e:
            print(f"  Validation failed: {e}")
            return False

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
    """Command-line interface for authentication management"""
    parser = argparse.ArgumentParser(description="Manage ChatGPT authentication")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    setup_parser = subparsers.add_parser("setup", help="Setup authentication")
    setup_parser.add_argument(
        "--timeout", type=float, default=AUTH_TIMEOUT_MINUTES,
        help=f"Login timeout in minutes (default: {AUTH_TIMEOUT_MINUTES})",
    )

    subparsers.add_parser("status", help="Check authentication status")
    subparsers.add_parser("validate", help="Validate authentication")
    subparsers.add_parser("clear", help="Clear authentication")

    reauth_parser = subparsers.add_parser("reauth", help="Re-authenticate (clear + setup)")
    reauth_parser.add_argument(
        "--timeout", type=float, default=AUTH_TIMEOUT_MINUTES,
        help=f"Login timeout in minutes (default: {AUTH_TIMEOUT_MINUTES})",
    )

    args = parser.parse_args()
    auth = AuthManager()

    if args.command == "setup":
        if auth.setup_auth(timeout_minutes=args.timeout):
            print("\nAuthentication setup complete!")
            print("You can now use ask_question.py to query ChatGPT")
        else:
            print("\nAuthentication setup failed")
            sys.exit(1)

    elif args.command == "status":
        info = auth.get_auth_info()
        print("\nAuthentication Status:")
        print(f"  Authenticated: {'Yes' if info['authenticated'] else 'No'}")
        if info.get("state_age_hours"):
            print(f"  State age: {info['state_age_hours']:.1f} hours")
        if info.get("authenticated_at_iso"):
            print(f"  Last auth: {info['authenticated_at_iso']}")
        print(f"  State file: {info['state_file']}")

    elif args.command == "validate":
        if auth.validate_auth():
            print("Authentication is valid and working")
        else:
            print("Authentication is invalid or expired")
            print("Run: python run.py auth_manager setup")

    elif args.command == "clear":
        if auth.clear_auth():
            print("Authentication cleared")

    elif args.command == "reauth":
        if auth.re_auth(timeout_minutes=args.timeout):
            print("\nRe-authentication complete!")
        else:
            print("\nRe-authentication failed")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
