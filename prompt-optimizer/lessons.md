# Lessons Learned

## 2026-02-09 | openai module was missing from the .venv despite being in requirements.txt. Always check venv packages if subprocess calls fail with import errors. Fix: pip install openai in the venv directly.

## 2026-02-09 | Review timeout of 30s is too short for complex prompts. 90s works well. Gemini typically takes 45-90s for spec compliance audits.
