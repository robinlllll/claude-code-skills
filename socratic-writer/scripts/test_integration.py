#!/usr/bin/env python3
"""Quick integration test for the M3MAD upgrade + Devil's Advocate 4th role.

Tests import chains, session creation, and verifies the 4-way parallel
architecture is correctly wired without actually calling external APIs.
"""
import sys
import os
import json
import tempfile
import shutil

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

errors = []
passes = []

# ─── Test 1: Import all modules ───────────────────────────────────
try:
    from debate import (
        cmd_debate_parallel, cmd_full_debate, cmd_rebuttal,
        _call_grok_devils_advocate, _display_grok_advocate_result,
        GROK_DEVILS_ADVOCATE_PROMPT,
    )
    passes.append("debate.py imports (including 4th role functions)")
except Exception as e:
    errors.append(f"debate.py import: {e}")

try:
    from grok_engine import (
        cmd_synthesize, _detect_collective_delusion, _load_challenge_text,
        GROK_SYNTHESIS_PROMPT,
    )
    passes.append("grok_engine.py imports")
except Exception as e:
    errors.append(f"grok_engine.py import: {e}")

try:
    from arbitrate import (
        load_all_ai_opinions, detect_conflicts, cmd_compare,
    )
    passes.append("arbitrate.py imports")
except Exception as e:
    errors.append(f"arbitrate.py import: {e}")

try:
    from session import cmd_new, cmd_add_dialogue, load_session
    passes.append("session.py imports")
except Exception as e:
    errors.append(f"session.py import: {e}")

# ─── Test 2: Verify prompt has advocate section ────────────────────
try:
    assert "{advocate_challenge}" in GROK_SYNTHESIS_PROMPT, \
        "GROK_SYNTHESIS_PROMPT missing {advocate_challenge} placeholder"
    assert "魔鬼代言人" in GROK_SYNTHESIS_PROMPT, \
        "GROK_SYNTHESIS_PROMPT missing Devil's Advocate label"
    passes.append("GROK_SYNTHESIS_PROMPT has advocate placeholder")
except Exception as e:
    errors.append(f"Prompt check: {e}")

# ─── Test 3: Verify Devil's Advocate prompt exists and is well-formed ──
try:
    assert len(GROK_DEVILS_ADVOCATE_PROMPT) > 200, "Prompt too short"
    assert "{topic}" in GROK_DEVILS_ADVOCATE_PROMPT, "Missing {topic}"
    assert "{content}" in GROK_DEVILS_ADVOCATE_PROMPT, "Missing {content}"
    assert "反论点" in GROK_DEVILS_ADVOCATE_PROMPT, "Missing 反论点"
    assert "抗压评分" in GROK_DEVILS_ADVOCATE_PROMPT, "Missing 抗压评分"
    passes.append("GROK_DEVILS_ADVOCATE_PROMPT well-formed")
except Exception as e:
    errors.append(f"Advocate prompt: {e}")

# ─── Test 4: Collective delusion detection with 4 sources ──────────
try:
    test_challenges = {
        "Gemini": "The evidence suggests causality between pricing and demand. Time horizon is critical. Stakeholder incentives align with growth assumptions.",
        "GPT": "Alternative frameworks show constraint on execution. Second-order effects of pricing changes affect incentive structures.",
        "Grok": "Hidden assumptions about evidence quality. Execution risk from stakeholder misalignment. Time-dependent constraints.",
        "Advocate": "The entire causality chain is assumption-heavy. Alternative scenarios undermine the evidence base. Incentive structures may reverse.",
    }
    result = _detect_collective_delusion(test_challenges)
    assert "convergence_pct" in result, "Missing convergence_pct"
    assert "themes_by_ai" in result, "Missing themes_by_ai"
    assert "Advocate" in result["themes_by_ai"], "Advocate not in themes_by_ai"
    assert len(result["themes_by_ai"]) == 4, f"Expected 4 AIs, got {len(result['themes_by_ai'])}"
    passes.append(f"Collective delusion detection: 4 sources, convergence={result['convergence_pct']}%")
except Exception as e:
    errors.append(f"Delusion detection: {e}")

# ─── Test 5: Create session and verify structure ───────────────────
try:
    # Use a temp data dir
    original_data = os.environ.get("SKILL_DATA_DIR")
    tmp_dir = tempfile.mkdtemp(prefix="socratic_test_")
    os.environ["SKILL_DATA_DIR"] = tmp_dir

    # Reload session module to pick up new data dir
    import importlib
    import session as session_mod
    importlib.reload(session_mod)

    # Create session
    session_id = session_mod.cmd_new("Test: AI will replace knowledge workers")
    assert session_id, "No session ID returned"

    session_path = os.path.join(tmp_dir, "sessions", session_id)
    assert os.path.exists(session_path), f"Session dir not created: {session_path}"

    # Add dialogue
    session_mod.cmd_add_dialogue(session_id, "What jobs first?", "Routine analytical tasks", "边界")
    session_mod.cmd_add_dialogue(session_id, "Timeline evidence?", "Exponential improvement pace", "时间")

    # Verify dialogue
    dialogue_path = os.path.join(session_path, "dialogue.json")
    with open(dialogue_path, "r", encoding="utf-8") as f:
        dialogue = json.load(f)
    assert len(dialogue.get("exchanges", [])) == 2, f"Expected 2 exchanges, got {len(dialogue.get('exchanges', []))}"

    # Create fake challenge files to test arbitrate loading
    challenges_dir = os.path.join(session_path, "challenges")
    os.makedirs(challenges_dir, exist_ok=True)

    fake_gemini = {"timestamp": "2026-02-24T12:00:00", "result": {"assumption_map": [{"claim": "test", "layer": "核心", "confidence": 0.8, "is_load_bearing": True}], "verification_score": 7}}
    fake_gpt = {"timestamp": "2026-02-24T12:00:00", "response": "Framework analysis: related to X theory"}
    fake_grok = {"timestamp": "2026-02-24T12:00:00", "response": "Blind spots: missing stakeholder Y"}
    fake_advocate = {"timestamp": "2026-02-24T12:00:00", "response": "Counter-argument: the thesis fails because Z"}

    for name, data in [("gemini.json", fake_gemini), ("gpt.json", fake_gpt), ("grok.json", fake_grok), ("grok_advocate.json", fake_advocate)]:
        with open(os.path.join(challenges_dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    passes.append(f"Session created: {session_id}, 2 dialogues, 4 fake challenge files")

    # Restore
    if original_data:
        os.environ["SKILL_DATA_DIR"] = original_data
    else:
        del os.environ["SKILL_DATA_DIR"]

except Exception as e:
    errors.append(f"Session creation: {e}")
    tmp_dir = None

# ─── Test 6: Arbitrate loads all 5 opinions ────────────────────────
try:
    if tmp_dir and session_id:
        # Temporarily point to test data
        os.environ["SKILL_DATA_DIR"] = tmp_dir
        importlib.reload(session_mod)

        # Also need to reload arbitrate
        import arbitrate as arb_mod
        importlib.reload(arb_mod)

        opinions = arb_mod.load_all_ai_opinions(session_id)
        loaded = [k for k, v in opinions.items() if v is not None]
        assert "gemini" in loaded, "Gemini not loaded"
        assert "gpt" in loaded, "GPT not loaded"
        assert "grok" in loaded, "Grok (blind spots) not loaded"
        assert "grok_advocate" in loaded, "Grok advocate not loaded"
        assert "claude" in loaded, "Claude not loaded"

        assert opinions["grok_advocate"]["source"] == "Grok (魔鬼代言人)", \
            f"Wrong source: {opinions['grok_advocate']['source']}"
        assert opinions["grok"]["source"] == "Grok (盲点扫描仪)", \
            f"Wrong source: {opinions['grok']['source']}"

        passes.append(f"Arbitrate loaded {len(loaded)} opinions: {loaded}")

        # Restore
        if original_data:
            os.environ["SKILL_DATA_DIR"] = original_data
        else:
            del os.environ["SKILL_DATA_DIR"]
except Exception as e:
    errors.append(f"Arbitrate loading: {e}")

# ─── Test 7: Detect conflicts with all opinions ───────────────────
try:
    if tmp_dir and session_id:
        os.environ["SKILL_DATA_DIR"] = tmp_dir
        importlib.reload(session_mod)
        importlib.reload(arb_mod)

        opinions = arb_mod.load_all_ai_opinions(session_id)
        result = arb_mod.detect_conflicts(opinions)
        assert result.get("convergence") is not None, "No convergence data"
        passes.append(f"Convergence analysis: {result['convergence'].get('convergence_pct', '?')}%")

        if original_data:
            os.environ["SKILL_DATA_DIR"] = original_data
        else:
            del os.environ["SKILL_DATA_DIR"]
except Exception as e:
    errors.append(f"Detect conflicts: {e}")

# ─── Cleanup ───────────────────────────────────────────────────────
if tmp_dir and os.path.exists(tmp_dir):
    shutil.rmtree(tmp_dir)

# ─── Report ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("INTEGRATION TEST REPORT")
print("=" * 60)
print(f"\nPassed: {len(passes)}")
for p in passes:
    print(f"  ✓ {p}")

if errors:
    print(f"\nFailed: {len(errors)}")
    for e in errors:
        print(f"  ✗ {e}")
else:
    print("\n  All tests passed!")

print(f"\nTotal: {len(passes)} passed, {len(errors)} failed")
sys.exit(1 if errors else 0)
