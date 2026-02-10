---
name: prompt-optimizer
description: Iteratively optimize a prompt using PromptSpec + tests + versioning + multi-AI review (Gemini + GPT). Use only when the user explicitly wants prompt iteration with tracked versions and test feedback.
---

# Prompt Optimizer

Iteratively optimize prompts through:
- **PromptSpec**: Define requirements, constraints, and evaluation criteria
- **TestSuite**: Test cases with expected output characteristics
- **Versioning**: Track all prompt iterations
- **Multi-AI Review**: Parallel dual review with differentiated roles + auto-synthesis
  - **Gemini** = Spec Compliance Auditor (checks every spec requirement)
  - **GPT** = Edge Case Hunter (finds inputs that break the prompt)
- **User Testing**: User-driven testing is MANDATORY before each iteration

## Multi-AI Review Architecture

```
                    ┌──────────────┐
                    │  review cmd  │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │    PARALLEL (30s timeout) │
              ├─────────┐   ┌───────────┤
              ▼         │   │           ▼
   ┌──────────────┐     │   │    ┌──────────────┐
   │    Gemini    │     │   │    │     GPT      │
   │  Spec Audit  │     │   │    │  Edge Cases  │
   └──────┬───────┘     │   │    └──────┬───────┘
          │             │   │           │
          └─────────────┴───┴───────────┘
                        │
               ┌────────┴────────┐
               │  Auto-Synthesis │
               │  (no AI call)   │
               └────────┬────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ Unified Summary  │
              │ + Action Items   │
              └──────────────────┘
```

**Reviewer Roles:**

| Model | Role | Focus | Output |
|-------|------|-------|--------|
| Gemini | Spec Compliance Auditor | Does the prompt satisfy EVERY spec requirement? | Checklist with PASS/FAIL per requirement |
| GPT | Edge Case Hunter | What inputs would break this prompt? | Problematic test cases with expected vs actual |

**Synthesis Output (auto-generated, no AI call):**
- **Both agree** (high priority): Issues found by both models
- **Gemini only** (spec compliance): Missing constraints, ambiguous instructions
- **GPT only** (edge cases): Adversarial inputs, boundary conditions
- **Contradictions**: Where models disagree (e.g., verdict mismatch)
- **Recommended action items**: Prioritized fix list

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Create Session  ->  2. Fill Spec  ->  3. Claude generates v1 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │  4. Parallel Multi-AI Review  │
               │  Gemini (spec) + GPT (edge)  │
               │  -> Auto-synthesis            │
               └──────────────┬───────────────┘
                              │
                              ▼
              ┌──────────────────────────────┐
              │  5. User Testing (REQUIRED)   │
              │  -> Test with real data       │
              │  -> Record results + issues   │
              └──────────────┬───────────────┘
                             │
                             ▼
                      ┌────────────┐
                      │  Satisfied? │
                      └─────┬──────┘
                            │
                 ┌──────────┴──────────┐
                 │                     │
                YES                    NO
                 │                     │
                 ▼                     ▼
          ┌───────────┐    ┌─────────────────────┐
          │ 6. Done   │    │ 6. Record feedback   │
          │ Finalize  │    │ -> back to step 4    │
          └───────────┘    └─────────────────────┘
```

**Core principle: User testing > AI review**
- AI review is "theoretical" checking (format, logic, constraints, edge cases)
- User testing is "practical" validation (real data, actual results)
- Only the user can say "good enough" -- AI PASS is just a reference

## Step-by-Step

### 1. Create Session
```bash
python ~/.claude/skills/prompt-optimizer/scripts/run.py optimizer.py new --goal "USER'S GOAL"
```

### 2. Fill PromptSpec
Edit `data/sessions/{id}/spec.md` to define:
- Task description (one sentence)
- Input/output format
- Hard constraints (must satisfy)
- Soft constraints (try to satisfy)
- Things to avoid
- Evaluation criteria

### 3. Create Initial Prompt (Claude)
```bash
echo "PROMPT_TEXT" | python ~/.claude/skills/prompt-optimizer/scripts/run.py optimizer.py add-version --session ID --source claude
```

### 4. Multi-AI Review (parallel)
```bash
python ~/.claude/skills/prompt-optimizer/scripts/run.py optimizer.py review --session ID
```

Both models run **in parallel** (30s timeout each):

**Gemini (Spec Compliance Auditor) returns:**
- **Spec Compliance Checklist**: Every spec requirement with PASS/FAIL
- **Verdict**: PASS / FAIL
- **Top 5 Issues**: Missing constraints, ambiguous instructions, underspecified format
- **Minimal Patch**: Replace/add/delete instructions
- **Regression Risks**: Potential new issues

**GPT (Edge Case Hunter) returns:**
- **Edge Case Test Cases**: 5-8 problematic inputs with expected vs actual behavior
- **Verdict**: PASS / FAIL
- **Top 5 Issues**: Adversarial inputs, boundary conditions, model confusion risks
- **Minimal Patch**: Replace/add/delete instructions
- **Regression Risks**: Potential new issues

**Auto-Synthesis (shown after both reviews):**
- Issues both agree on (fix first)
- Issues only one model found (categorized by role)
- Verdict contradictions
- Prioritized action items

**Flags:**
- `--no-gpt`: Skip GPT review (Gemini only)
- `--model MODEL`: Override Gemini model (default: gemini-2.5-flash)
- `--gpt-model MODEL`: Override GPT model (default: gpt-5.2-chat-latest)

### 5. User Testing (REQUIRED)

**This is the most critical step. User must:**
1. Test the current prompt version with real data
2. Observe actual output
3. Record issues and improvement suggestions

```bash
python ~/.claude/skills/prompt-optimizer/scripts/run.py optimizer.py feedback --session ID --text "USER'S FEEDBACK"
```

**Feedback should include:**
- What data did you test with?
- What was the actual output?
- Where did it not meet expectations?
- What changes are needed?

### 6. Iterate or Finalize

**If not satisfied:**
1. Claude modifies prompt based on user feedback + AI review synthesis
2. Save new version
3. Back to step 4

**If satisfied:**
```bash
python ~/.claude/skills/prompt-optimizer/scripts/run.py optimizer.py finalize --session ID
```

## Commands

| Command | Description |
|---------|-------------|
| `configure --api-key KEY` | Set Gemini API key |
| `status` | Check API keys (Gemini + GPT) and session stats |
| `new --goal "..."` | Create new session |
| `list` | List all sessions |
| `show --session ID` | Show session details |
| `add-version --session ID` | Add prompt version |
| `review --session ID` | Parallel Gemini + GPT review with synthesis |
| `review --session ID --no-gpt` | Gemini-only review |
| `feedback --session ID --text "..."` | **Record user test feedback (REQUIRED)** |
| `diff --session ID --v1 N` | Compare versions |
| `finalize --session ID` | Complete session |

## API Keys

| Key | Required | Source |
|-----|----------|--------|
| `GEMINI_API_KEY` | Yes | env var or `configure --api-key` |
| `OPENAI_API_KEY` | Optional | env var (enables GPT Edge Case Hunter) |

## Data Structure

```
data/sessions/{session_id}/
├── state.json           # Session metadata
├── spec.md              # PromptSpec (requirements)
├── tests/               # Test cases
│   ├── case_001.md
│   └── ...
├── versions/            # Prompt versions
│   ├── manifest.json
│   ├── v1.md
│   └── v2.md
└── conversations/       # Review rounds + user feedback
    ├── round_001.json   # gemini_review + gpt_review + synthesis + user_feedback
    └── ...
```

**Round record fields:** `round`, `created_at`, `prompt_version`, `gemini_model`, `gemini_review`, `gpt_model`, `gpt_review`, `synthesis`, `gemini_time`, `gpt_time`, `user_feedback`, `test_report`, `notes`

## Example Session

```
User: Help me optimize an earnings analysis prompt

Claude: Creating optimization session...
[Creates session, fills spec.md]
[Generates initial prompt v1]
Running parallel multi-AI review...

Reviewing v1 in parallel:
  Gemini (gemini-2.5-flash) -> Spec Compliance Auditor
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

## Notes

- **User feedback has highest priority** - AI review is advisory, user decides
- Parallel execution reduces review time (wall-clock = slowest model, not sum)
- 30s timeout per model: if one times out, the other's result still shows
- Synthesis is programmatic (keyword matching), not another AI call
- GPT review is optional: works fine with Gemini-only if no OpenAI key
- Round records store all data: individual reviews, synthesis, timing, feedback
