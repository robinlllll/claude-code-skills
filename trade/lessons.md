# Lessons Learned

## 2026-02-27: Refactored from instruction-driven to script-driven (v2.0)

**Problem:** v1.0 was 100% instruction-driven (7-step SKILL.md). Claude interpreted each step ad-hoc, leading to:
- Inconsistent execution across runs
- investments.db never reliably created (Step 5.5 was too complex for ad-hoc interpretation)
- thesis.md vs thesis.yaml confusion
- Only 2 trade logs ever created in months of use → high friction

**Solution:** Created `scripts/trade_logger.py` — a single deterministic Python script that handles the entire workflow. SKILL.md simplified to 3 steps: parse input → run script → present results.

**Key design choices:**
- Trade .md file is the primary record; SQLite/thesis/task are all best-effort
- Portfolio API failure is graceful (fields show "N/A", trade still logged)
- Script outputs JSON to stdout for Claude to parse and present
- `argparse` for strict input validation
- Thesis.yaml auto-transition: BUY/ADD → active, full SELL/COVER → past, TRIM → no change

**Import pattern:** `sys.path.insert(0, str(SHARED_DIR))` where `SHARED_DIR = Path(r'C:\Users\thisi\.claude\skills\shared')` — then `from schemas import DecisionRecord` etc.
