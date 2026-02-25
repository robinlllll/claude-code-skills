# Example Session

```
User: Help me optimize an earnings analysis prompt

Claude: Creating optimization session...
[Creates session, fills spec.md]
[Generates initial prompt v1]
Running parallel multi-AI review...

Reviewing v1 in parallel:
  Gemini (gemini-3-pro-preview) -> Spec Compliance Auditor
  GPT (gpt-5.2-chat-latest) -> Edge Case Hunter
  Timeout: 30s per model

  [OK] Gemini completed in 8.2s
  [OK] GPT completed in 12.1s

============================================================
GEMINI REVIEW - Spec Compliance Auditor (Round 1)
============================================================
Spec Compliance Checklist:
[FAIL] Output table format - not specified in prompt
[PASS] Revenue extraction - covered
[FAIL] R&D expense tracking - missing
...

============================================================
GPT REVIEW - Edge Case Hunter (Round 1)
============================================================
Edge Case Test Cases:
1. Input: Empty/corrupted PDF
   Expected: Error message
   Likely actual: Hallucinated numbers
   Risk: HIGH
...

============================================================
=== SYNTHESIS ===

Gemini verdict: FAIL  |  GPT verdict: FAIL

[HIGH PRIORITY] Both agree:
  - output format underspecified
  - missing error handling for malformed input

[SPEC COMPLIANCE] Gemini only:
  - r&d expense not mentioned in extraction list
  - quarterly comparison not addressed

[EDGE CASES] GPT only:
  - non-english earnings reports cause garbled output
  - very short filings (<1 page) produce empty tables

[CONTRADICTIONS]:
  (none)

[RECOMMENDED ACTION ITEMS]:
  1. Fix high-priority issues agreed by both reviewers first
  2. Address spec compliance gaps flagged by Gemini
  3. Add edge case handling for scenarios identified by GPT
============================================================

Timing: Gemini 8.2s | GPT 12.1s | Total wall-clock ~12.1s

Claude: Based on synthesis, modifying prompt -> saved as v2.
Please test with real earnings data.

User: Tested with Tencent 2024Q3, looks good now.

Claude: [finalize session]
Final prompt is v3, after 2 rounds of iteration.
```
