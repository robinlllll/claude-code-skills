# Lessons Learned

## 2026-02-09 | openai module was missing from the .venv despite being in requirements.txt. Always check venv packages if subprocess calls fail with import errors. Fix: pip install openai in the venv directly.

## 2026-02-09 | Review timeout of 30s is too short for complex prompts. 90s works well. Gemini typically takes 45-90s for spec compliance audits.

## 2026-02-12 | Grok fallback added: when GPT is unavailable, optimizer auto-falls back to Grok (xAI) for edge case review. Requires XAI_API_KEY in env. Also: 90s timeout confirmed appropriate for complex specs.

## 2026-02-12 | Anti-hallucination is the #1 prompt quality issue for knowledge-dependent tasks. Key pattern: concrete filled example + schema defaults table + explicit Rule 12 (accuracy>completeness) + UNVERIFIED PROFILE flag for unknown inputs. Tested on Gator Capital — eliminated hallucinated TMT tags.
