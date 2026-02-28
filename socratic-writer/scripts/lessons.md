# Socratic Writer Lessons

## 2026-02-23: Grok socratic prompt must match input type

**Problem:** When feeding a complete article (~990 lines) to `grok_engine.py socratic`, the original prompt ("你是一个思维教练...5种类型：边界/假设/时间/反面/盲点") generated generic, shallow questions that didn't engage with the article's actual content. The critiques were easily debunked because the article already had mechanisms addressing them.

**Root cause:** The prompt was designed for "initial fuzzy ideas", not for critiquing a finished draft. It told Grok to ask about boundaries/assumptions/blind spots without requiring it to actually read and quote the source material.

**Fix:** Added `GROK_SOCRATIC_REFINE_PROMPT` for article refinement mode. Key constraints:
1. Must quote original text from the article
2. Must find internal contradictions using the article's own examples
3. Must not ignore existing mechanisms (e.g., "反证条件")
4. Must not use external cases the article doesn't discuss

**Auto-detect:** `cmd_socratic` now auto-detects mode based on input length (≥500 chars = refine, <500 = explore). Can be overridden with `--mode explore|refine`.

**Lesson for other skills:** When an AI is asked to critique a document, the prompt must force the AI to ground its critique in the actual text. Generic "what could go wrong" prompts produce hallucinated criticisms that sound smart but don't engage with what was actually written.
