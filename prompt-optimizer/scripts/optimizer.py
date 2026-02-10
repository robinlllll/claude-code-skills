#!/usr/bin/env python3
"""
Prompt Optimizer CLI - MVP Version
6 core commands: configure, new, add-version, review, feedback, finalize

Multi-AI review: Gemini (Spec Compliance Auditor) + GPT (Edge Case Hunter)
run in parallel with auto-synthesized results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add scripts directory to path
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from gemini_client import GeminiClient
from gpt_client import GPTClient
from session_manager import SessionManager
from version_manager import VersionManager
from conversation_manager import ConversationManager, RoundRecord

# Timeout for each model review call (seconds)
REVIEW_TIMEOUT = 90


def base_dir() -> Path:
    """Get skill base directory"""
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Get data directory"""
    return base_dir() / "data"


def config_path() -> Path:
    """Get config file path"""
    return data_dir() / "config.json"


def load_api_key(key_name: str = "GEMINI_API_KEY") -> str | None:
    """Load API key from env var or config file"""
    # Priority: environment variable > config file
    if os.getenv(key_name):
        return os.getenv(key_name)
    p = config_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get(key_name)
    return None


# =============================================================================
# Commands
# =============================================================================


def cmd_configure(args) -> int:
    """Configure Gemini API key"""
    data_dir().mkdir(parents=True, exist_ok=True)
    config_path().write_text(
        json.dumps({"GEMINI_API_KEY": args.api_key}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"API key saved to {config_path()}")
    print("Tip: For better security, use environment variable GEMINI_API_KEY instead.")
    return 0


def cmd_status(args) -> int:
    """Check system status"""
    print("=== Prompt Optimizer Status ===\n")

    # Check Gemini API key
    api_key = load_api_key("GEMINI_API_KEY")
    if api_key:
        print("Gemini API key: configured")
        try:
            client = GeminiClient(api_key=api_key)
            if client.health_check():
                print(f"Gemini API: connected (model: {client.model})")
            else:
                print("Gemini API: connection failed")
        except Exception as e:
            print(f"Gemini API: error - {e}")
    else:
        print("Gemini API key: NOT configured")
        print("  Run: optimizer.py configure --api-key YOUR_KEY")
        print("  Or set: export GEMINI_API_KEY=YOUR_KEY")

    # Check OpenAI API key
    openai_key = load_api_key("OPENAI_API_KEY")
    if openai_key:
        print("OpenAI API key: configured")
        try:
            gpt = GPTClient(api_key=openai_key)
            if gpt.health_check():
                print(f"OpenAI API: connected (model: {gpt.model})")
            else:
                print("OpenAI API: connection failed")
        except Exception as e:
            print(f"OpenAI API: error - {e}")
    else:
        print("OpenAI API key: NOT configured (GPT review disabled)")
        print("  Set: export OPENAI_API_KEY=YOUR_KEY")

    # Check sessions
    sm = SessionManager(data_dir() / "sessions")
    sessions = sm.list_sessions()
    print(f"\nSessions: {len(sessions)}")
    return 0


def cmd_new(args) -> int:
    """Create new optimization session"""
    sm = SessionManager(data_dir() / "sessions")
    session_dir = sm.create(goal=args.goal)
    session_id = session_dir.name

    print(f"Created session: {session_id}")
    print(f"Goal: {args.goal}")
    print(f"\nDirectory: {session_dir}")
    print("\nNext steps:")
    print("  1. Edit spec.md to define requirements")
    print("  2. Add test cases in tests/")
    print("  3. Create first prompt version with add-version")
    return 0


def cmd_list(args) -> int:
    """List all sessions"""
    sm = SessionManager(data_dir() / "sessions")
    sessions = sm.list_sessions()

    if not sessions:
        print("No sessions found.")
        return 0

    print(f"{'ID':<15} {'Status':<15} {'Version':<8} {'Goal'}")
    print("-" * 70)
    for s in sessions:
        v = f"v{s['active_version']}" if s["active_version"] else "-"
        print(f"{s['id']:<15} {s['status']:<15} {v:<8} {s['goal']}")
    return 0


def cmd_show(args) -> int:
    """Show session details"""
    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    state = sm.load(args.session)
    session_dir = sm.get_session_dir(args.session)

    print(f"Session: {state.session_id}")
    print(f"Status: {state.status}")
    print(f"Goal: {state.goal}")
    print(
        f"Active version: v{state.active_version}"
        if state.active_version
        else "Active version: none"
    )
    print(f"Active round: {state.active_round}")

    # Show spec preview
    spec_path = session_dir / "spec.md"
    if spec_path.exists():
        spec = spec_path.read_text(encoding="utf-8")
        print("\n--- spec.md preview ---")
        print(spec[:500] + "..." if len(spec) > 500 else spec)

    # Show versions
    vm = VersionManager(session_dir)
    versions = vm.list_versions()
    if versions:
        print(f"\n--- Versions ({len(versions)}) ---")
        for v in versions:
            print(f"  v{v['version']}: {v['chars']} chars, from {v['source']}")

    # Show rounds
    cm = ConversationManager(session_dir)
    rounds = cm.list_rounds()
    if rounds:
        print(f"\n--- Review Rounds ({len(rounds)}) ---")
        for r in rounds:
            fb = "✓ feedback" if r["has_feedback"] else "no feedback"
            print(f"  Round {r['round']}: v{r['prompt_version']}, {r['model']}, {fb}")

    return 0


def cmd_add_version(args) -> int:
    """Add a new prompt version"""
    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    session_dir = sm.get_session_dir(args.session)
    vm = VersionManager(session_dir)

    # Read prompt from file or stdin
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("Enter prompt (Ctrl+D or Ctrl+Z to finish):")
        text = sys.stdin.read()

    text = text.strip()
    if not text:
        print("Error: empty prompt")
        return 1

    meta = vm.add_version(text=text, source=args.source, notes=args.notes or "")

    # Update session state
    sm.update(args.session, active_version=meta.version, status="HAS_VERSION")

    print(f"Saved as v{meta.version}.md ({meta.chars} chars)")
    return 0


def _extract_issues(review_text: str) -> list[str]:
    """Extract individual issue lines from a review output.

    Looks for numbered items (1. / 1) / - ) under Issues sections, and also
    captures lines from Edge Case Test Cases and Spec Compliance Checklist.
    Returns a list of lowercase issue strings for comparison.
    """
    issues: list[str] = []
    for line in review_text.splitlines():
        stripped = line.strip()
        # Match numbered items: "1. ...", "1) ...", or bullet "- ..."
        if re.match(r"^(\d+[\.\)]\s+|- )", stripped):
            # Clean up the prefix
            text = re.sub(r"^(\d+[\.\)]\s+|- )", "", stripped).strip()
            if len(text) > 5:  # skip trivially short lines
                issues.append(text.lower())
        # Match checklist items: "[PASS] ...", "[FAIL] ..."
        elif re.match(r"^\[(PASS|FAIL)\]", stripped, re.IGNORECASE):
            text = re.sub(
                r"^\[(PASS|FAIL)\]\s*", "", stripped, flags=re.IGNORECASE
            ).strip()
            if len(text) > 5:
                issues.append(text.lower())
    return issues


def _extract_verdict(review_text: str) -> str:
    """Extract PASS or FAIL verdict from review text."""
    m = re.search(r"Verdict:\s*(PASS|FAIL)", review_text, re.IGNORECASE)
    return m.group(1).upper() if m else "UNKNOWN"


def _synthesize_reviews(gemini_text: str, gpt_text: str) -> str:
    """Auto-synthesize Gemini (Spec Compliance) and GPT (Edge Case) reviews.

    Compares issue lists programmatically to find:
    - Issues both models agree on (high priority)
    - Issues only Gemini found (spec compliance gaps)
    - Issues only GPT found (edge cases)
    - Verdict contradictions
    Returns a formatted synthesis string.
    """
    gemini_issues = _extract_issues(gemini_text)
    gpt_issues = _extract_issues(gpt_text)

    gemini_verdict = _extract_verdict(gemini_text)
    gpt_verdict = _extract_verdict(gpt_text)

    # Find overlapping issues using keyword similarity
    # Two issues "overlap" if they share 3+ significant words (>3 chars)
    def _significant_words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z\u4e00-\u9fff]+", text) if len(w) > 3}

    both_agree = []
    gemini_only = []
    gpt_only = []
    gpt_matched = set()

    for gi, g_issue in enumerate(gemini_issues):
        g_words = _significant_words(g_issue)
        matched = False
        for gpi, gpt_issue in enumerate(gpt_issues):
            if gpi in gpt_matched:
                continue
            gpt_words = _significant_words(gpt_issue)
            overlap = g_words & gpt_words
            if len(overlap) >= 3 or (len(overlap) >= 2 and len(g_words) <= 5):
                both_agree.append(g_issue)
                gpt_matched.add(gpi)
                matched = True
                break
        if not matched:
            gemini_only.append(g_issue)

    for gpi, gpt_issue in enumerate(gpt_issues):
        if gpi not in gpt_matched:
            gpt_only.append(gpt_issue)

    # Build synthesis
    lines = []
    lines.append("=== SYNTHESIS ===")
    lines.append("")

    # Verdicts
    lines.append(f"Gemini verdict: {gemini_verdict}  |  GPT verdict: {gpt_verdict}")
    lines.append("")

    # Both agree
    lines.append("[HIGH PRIORITY] Both agree:")
    if both_agree:
        for issue in both_agree[:5]:
            lines.append(f"  - {issue}")
    else:
        lines.append("  (no overlapping issues detected)")
    lines.append("")

    # Gemini only
    lines.append("[SPEC COMPLIANCE] Gemini only:")
    if gemini_only:
        for issue in gemini_only[:5]:
            lines.append(f"  - {issue}")
    else:
        lines.append("  (none)")
    lines.append("")

    # GPT only
    lines.append("[EDGE CASES] GPT only:")
    if gpt_only:
        for issue in gpt_only[:5]:
            lines.append(f"  - {issue}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Contradictions
    lines.append("[CONTRADICTIONS]:")
    if (
        gemini_verdict != gpt_verdict
        and gemini_verdict != "UNKNOWN"
        and gpt_verdict != "UNKNOWN"
    ):
        lines.append(
            f"  - Verdict mismatch: Gemini says {gemini_verdict}, GPT says {gpt_verdict}"
        )
    else:
        lines.append("  (none)")
    lines.append("")

    # Recommended action items
    lines.append("[RECOMMENDED ACTION ITEMS]:")
    action_num = 1
    if both_agree:
        lines.append(
            f"  {action_num}. Fix high-priority issues agreed by both reviewers first"
        )
        action_num += 1
    if gemini_verdict == "FAIL":
        lines.append(f"  {action_num}. Address spec compliance gaps flagged by Gemini")
        action_num += 1
    if gpt_only:
        lines.append(
            f"  {action_num}. Add edge case handling for scenarios identified by GPT"
        )
        action_num += 1
    if action_num == 1:
        lines.append("  (both reviewers passed - proceed to user testing)")

    return "\n".join(lines)


def cmd_review(args) -> int:
    """Send current version to Gemini + GPT for parallel dual review.

    Gemini role: Spec Compliance Auditor (checks every spec requirement)
    GPT role: Edge Case Hunter (finds inputs that break the prompt)
    Both run concurrently with 30s timeout per model.
    Results are auto-synthesized after both complete.
    """
    api_key = load_api_key("GEMINI_API_KEY")
    if not api_key:
        print("Error: No Gemini API key configured.")
        print("Run: optimizer.py configure --api-key YOUR_KEY")
        return 1

    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    session_dir = sm.get_session_dir(args.session)

    # Load spec
    spec_path = session_dir / "spec.md"
    if not spec_path.exists():
        print("Error: spec.md not found")
        return 1
    spec_md = spec_path.read_text(encoding="utf-8")

    # Load current prompt version
    vm = VersionManager(session_dir)
    v = vm.latest_version()
    if not v:
        print("Error: No prompt version found. Run add-version first.")
        return 1
    prompt_text = vm.read_version(v)

    # Load test report if provided
    test_report = ""
    if args.test_report:
        test_report = Path(args.test_report).read_text(encoding="utf-8")

    # Get history excerpt for context
    cm = ConversationManager(session_dir)
    history_excerpt = cm.get_history_excerpt()

    # Prepare review kwargs (shared by both models)
    review_kwargs = dict(
        spec_md=spec_md,
        prompt_text=prompt_text,
        test_report=test_report,
        history_excerpt=history_excerpt,
    )

    # Check if GPT is available
    openai_key = load_api_key("OPENAI_API_KEY")
    use_gpt = bool(openai_key) and not args.no_gpt

    # --- Parallel execution ---
    gemini_review_text = ""
    gemini_time = 0.0
    gpt_model_name = ""
    gpt_review_text = ""
    gpt_time = 0.0

    def _run_gemini():
        """Run Gemini review (Spec Compliance Auditor)."""
        client = GeminiClient(api_key=api_key, model=args.model)
        return client.review_prompt(**review_kwargs)

    def _run_gpt():
        """Run GPT review (Edge Case Hunter)."""
        gpt = GPTClient(api_key=openai_key, model=args.gpt_model)
        return gpt.review_prompt(**review_kwargs)

    if use_gpt:
        # Both models available: run in parallel
        print(f"Reviewing v{v} in parallel:")
        print(f"  Gemini ({args.model}) -> Spec Compliance Auditor")
        print(f"  GPT ({args.gpt_model}) -> Edge Case Hunter")
        print(f"  Timeout: {REVIEW_TIMEOUT}s per model")
        print()

        with ThreadPoolExecutor(max_workers=2) as executor:
            gemini_future = executor.submit(_run_gemini)
            gpt_future = executor.submit(_run_gpt)

            # Collect Gemini result
            t0 = time.time()
            try:
                gemini_result = gemini_future.result(timeout=REVIEW_TIMEOUT)
                gemini_time = time.time() - t0
                gemini_review_text = gemini_result.text
                print(f"  [OK] Gemini completed in {gemini_time:.1f}s")
            except TimeoutError:
                gemini_time = REVIEW_TIMEOUT
                print(f"  [TIMEOUT] Gemini timed out after {REVIEW_TIMEOUT}s")
            except Exception as e:
                gemini_time = time.time() - t0
                print(f"  [ERROR] Gemini failed: {e}")

            # Collect GPT result
            t0 = time.time()
            try:
                gpt_result = gpt_future.result(timeout=REVIEW_TIMEOUT)
                gpt_time = time.time() - t0
                gpt_model_name = args.gpt_model
                gpt_review_text = gpt_result.text
                print(f"  [OK] GPT completed in {gpt_time:.1f}s")
            except TimeoutError:
                gpt_time = REVIEW_TIMEOUT
                print(f"  [TIMEOUT] GPT timed out after {REVIEW_TIMEOUT}s")
            except Exception as e:
                gpt_time = time.time() - t0
                print(f"  [ERROR] GPT failed: {e}")
    else:
        # Gemini only
        print(
            f"Reviewing v{v} with Gemini ({args.model}) -> Spec Compliance Auditor..."
        )
        if not openai_key:
            print("  (GPT skipped: no OPENAI_API_KEY configured)")
        elif args.no_gpt:
            print("  (GPT skipped: --no-gpt flag)")
        print()

        t0 = time.time()
        try:
            gemini_result = _run_gemini()
            gemini_time = time.time() - t0
            gemini_review_text = gemini_result.text
            print(f"  [OK] Gemini completed in {gemini_time:.1f}s")
        except Exception as e:
            gemini_time = time.time() - t0
            print(f"  [ERROR] Gemini failed: {e}")

    # --- Auto-synthesize reviews ---
    synthesis_text = ""
    if gemini_review_text and gpt_review_text:
        synthesis_text = _synthesize_reviews(gemini_review_text, gpt_review_text)

    # Save round record
    round_num = cm.next_round()
    cm.save_round(
        RoundRecord(
            round=round_num,
            created_at=time.time(),
            prompt_version=v,
            gemini_model=args.model,
            gemini_review=gemini_review_text,
            test_report=test_report,
            gpt_model=gpt_model_name,
            gpt_review=gpt_review_text,
            synthesis=synthesis_text,
            gemini_time=gemini_time,
            gpt_time=gpt_time,
        )
    )

    # Update session state
    sm.update(args.session, active_round=round_num, status="REVIEWING")

    # Output Gemini review
    if gemini_review_text:
        print("\n" + "=" * 60)
        print(f"GEMINI REVIEW - Spec Compliance Auditor (Round {round_num})")
        print("=" * 60)
        print(gemini_review_text)

    # Output GPT review
    if gpt_review_text:
        print("\n" + "=" * 60)
        print(f"GPT REVIEW - Edge Case Hunter (Round {round_num})")
        print("=" * 60)
        print(gpt_review_text)

    # Output synthesis (only when both models returned results)
    if synthesis_text:
        print("\n" + "=" * 60)
        print(synthesis_text)
        print("=" * 60)

    # Timing summary
    print(f"\nTiming: Gemini {gemini_time:.1f}s", end="")
    if gpt_time:
        print(
            f" | GPT {gpt_time:.1f}s | Total wall-clock ~{max(gemini_time, gpt_time):.1f}s"
        )
    else:
        print()

    if not gemini_review_text and not gpt_review_text:
        print("\nError: No reviews completed successfully.")
        return 1

    return 0


def cmd_feedback(args) -> int:
    """Record user feedback for a review round"""
    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    session_dir = sm.get_session_dir(args.session)
    cm = ConversationManager(session_dir)

    round_num = args.round if args.round else cm.current_round()
    if not round_num:
        print("Error: No review rounds found. Run review first.")
        return 1

    cm.update_round(round_num, user_feedback=args.text)
    print(f"Feedback recorded for round {round_num}")
    return 0


def cmd_diff(args) -> int:
    """Show diff between two versions"""
    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    session_dir = sm.get_session_dir(args.session)
    vm = VersionManager(session_dir)

    v1 = args.v1
    v2 = args.v2 if args.v2 else vm.latest_version()

    if not v2:
        print("Error: No versions to compare")
        return 1

    print(f"Diff: v{v1} -> v{v2}")
    print("-" * 40)
    print(vm.diff(v1, v2))
    return 0


def cmd_finalize(args) -> int:
    """Mark session as completed and show final prompt"""
    sm = SessionManager(data_dir() / "sessions")

    if not sm.session_exists(args.session):
        print(f"Session not found: {args.session}")
        return 1

    session_dir = sm.get_session_dir(args.session)
    vm = VersionManager(session_dir)

    v = vm.latest_version()
    if not v:
        print("Error: No prompt version found")
        return 1

    # Update state
    sm.update(args.session, status="COMPLETED")

    # Output final prompt
    final_prompt = vm.read_version(v)

    print("=" * 60)
    print(f"SESSION COMPLETED - Final Prompt (v{v})")
    print("=" * 60)
    print(final_prompt)
    print("=" * 60)

    # Show changelog
    versions = vm.list_versions()
    if len(versions) > 1:
        print("\nChangelog:")
        for ver in versions:
            notes = ver.get("notes", "") or "(no notes)"
            print(f"  v{ver['version']}: {ver['source']} - {notes}")

    return 0


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        prog="optimizer.py",
        description="Prompt Optimizer - Iterate on prompts with Gemini review",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    # configure
    s = sub.add_parser("configure", help="Configure Gemini API key")
    s.add_argument("--api-key", required=True, help="Gemini API key")

    # status
    sub.add_parser("status", help="Check system status")

    # new
    s = sub.add_parser("new", help="Create new optimization session")
    s.add_argument("--goal", required=True, help="Goal for this prompt")

    # list
    sub.add_parser("list", help="List all sessions")

    # show
    s = sub.add_parser("show", help="Show session details")
    s.add_argument("--session", required=True, help="Session ID")

    # add-version
    s = sub.add_parser("add-version", help="Add a new prompt version")
    s.add_argument("--session", required=True, help="Session ID")
    s.add_argument("--source", default="user", help="Source of this version")
    s.add_argument("--notes", help="Notes about this version")
    s.add_argument("--file", help="Read prompt from file (otherwise stdin)")

    # review
    s = sub.add_parser("review", help="Send to Gemini + GPT for dual review")
    s.add_argument("--session", required=True, help="Session ID")
    s.add_argument("--model", default="gemini-2.5-flash", help="Gemini model")
    s.add_argument("--gpt-model", default="gpt-5.2-chat-latest", help="GPT model")
    s.add_argument("--no-gpt", action="store_true", help="Skip GPT review")
    s.add_argument("--test-report", help="Path to test report file")

    # feedback
    s = sub.add_parser("feedback", help="Record user feedback")
    s.add_argument("--session", required=True, help="Session ID")
    s.add_argument("--round", type=int, help="Round number (default: latest)")
    s.add_argument("--text", required=True, help="Feedback text")

    # diff
    s = sub.add_parser("diff", help="Show diff between versions")
    s.add_argument("--session", required=True, help="Session ID")
    s.add_argument("--v1", type=int, required=True, help="First version")
    s.add_argument("--v2", type=int, help="Second version (default: latest)")

    # finalize
    s = sub.add_parser("finalize", help="Complete session and show final prompt")
    s.add_argument("--session", required=True, help="Session ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch
    commands = {
        "configure": cmd_configure,
        "status": cmd_status,
        "new": cmd_new,
        "list": cmd_list,
        "show": cmd_show,
        "add-version": cmd_add_version,
        "review": cmd_review,
        "feedback": cmd_feedback,
        "diff": cmd_diff,
        "finalize": cmd_finalize,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
