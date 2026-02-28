---
name: self-heal
description: "Self-healing validation and auto-fix for portfolio monitor. Runs layered checks, diagnoses failures, applies fixes with git safety. Use when user says 'self-heal', 'validate', 'health check pm', or '/self-heal'."
allowed-tools: "Bash Read Write Edit Glob Grep"
metadata:
  version: 1.0.0
---

# Self-Heal: Portfolio Monitor Validation & Auto-Fix

## Accepted Pipelines

`/self-heal [pipeline]` where pipeline is one of:
- `factor` — factor regression, betas, R², attribution
- `ctr` — CTR sign consistency, attribution schema
- `positions` — portfolio positions, count drift
- `exposure` — sector weights, top holdings
- `risk` — Sharpe, Sortino, max drawdown
- `all` — everything (default)
- `earnings` — earnings pipeline preflight (separate flow)

## Flow

### Step 1: Setup

```bash
cd C:\Users\thisi\PORTFOLIO\portfolio_monitor
```

### Step 2: Layer 0 — Syntax Check

```bash
python -m compileall -q .
```

If syntax error → read the file mentioned in the error → fix immediately → re-run.

### Step 3: Check Server

```bash
# Check if server is running
curl -s http://localhost:8000/api/health
```

If not running → start it:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 &
# Wait 3 seconds for startup
```

### Step 4: Git Safety Branch

**CRITICAL: Always create a safety branch before making any fixes.**

```bash
git stash
git checkout -b auto/heal-$(date +%Y%m%d-%H%M%S)
```

### Step 5: Run Validation

```bash
python scripts/validate_all.py --pipeline {pipeline} --json
```

Parse the JSON output. If `all_ok: true` → skip to Step 8 (cleanup).

### Step 6: Diagnose and Fix (max 5 attempts per failure)

For each failure in the JSON output:

1. Read the source file mapped to the failing check (see table below)
2. Match against known fix patterns (see table below)
3. Apply fix via Edit tool
4. Re-run `python scripts/validate_all.py --json`
5. If same check still fails → increment attempt counter
6. **If attempt > 5 → STOP and escalate to user**

### Step 7: Escalation (if stuck)

```bash
git checkout main
git stash pop
```

Report to user:
- Which checks failed
- What was attempted
- What the likely root cause is

### Step 8: Cleanup (success path)

If `all_ok: true`:

```bash
# If on a heal branch with fixes applied:
git add -A
git commit -m "auto/heal: fix {list of fixed checks}"
git checkout main
git merge auto/heal-{timestamp}
git branch -d auto/heal-{timestamp}
git stash pop  # restore any stashed work
```

If no fixes were needed:
```bash
git checkout main
git branch -d auto/heal-{timestamp}
git stash pop
```

Report: "All checks pass."

## Check → Source File Mapping

| Check | Source files to read |
|-------|---------------------|
| `test_index_v2_served_in_root_route` | `app.py` (root route ~line 1394) |
| `test_route_ordering` | `app.py` (search for `@app.get`) |
| `test_ctr_sign_consistency` | `services/performance_engine.py` (~line 1270, `get_position_attribution`) |
| `test_all_six_betas_present` | `services/factor_service.py` (`get_factor_exposure`) |
| `test_r_squared_in_bounds` | `services/factor_service.py` (`get_factor_exposure`) |
| `test_factor_attribution_residual` | `services/factor_service.py` (`get_factor_attribution`) |
| `test_positions_non_empty` | `app.py` (`/api/portfolio` route) |
| `test_sector_weights_sum` | `services/exposure_service.py` |
| `test_risk_metrics_present_and_finite` | `services/risk_service.py` |
| `test_api_keys_loadable` | `~/.claude/skills/shared/preflight.py`, `~/Screenshots/.env` |

## Known Fix Patterns

| Pattern | Detection | Fix |
|---------|-----------|-----|
| Sign inversion | positive P&L + negative CTR | Check `pnl / nav_start * 10000` in performance_engine.py — look for missing negative sign or wrong NAV denominator |
| Wrong HTML file | `index.html` in root route instead of `index_v2.html` | Edit app.py root route: change filename to `index_v2.html` |
| Route shadowing | specific route defined after parameterized route | Move the specific route block above the parameterized one |
| Empty response | API returns `[]` or `{}` | Check DB has data for date range; check date param parsing |
| Missing factor data | factor endpoint returns error | Run `POST /api/factor/refresh-data` first, then retry |
| Missing API keys | preflight reports no keys | Check `~/Screenshots/.env` has GEMINI_API_KEY, OPENAI_API_KEY, XAI_API_KEY |

## Earnings Pipeline (`/self-heal earnings`)

Special flow — no auto-fix (content quality issues):

1. Run `shared/preflight.py` → validate Gemini/GPT/Grok keys
2. Find most recent analysis: `~/Documents/Obsidian Vault/研究/财报分析/`
3. Run `earnings-pipeline/scripts/validate_analysis.py --content-file {path}`
4. Report pass/fail — do NOT auto-fix

```bash
# Step 1: API key check
python -c "
import sys; sys.path.insert(0, r'C:\Users\thisi\.claude\skills')
from shared.preflight import validate_api_keys
results = validate_api_keys(verbose=True)
if not all(results.values()):
    print('FAIL: Missing API keys'); sys.exit(1)
print('All API keys present')
"

# Step 2: Find latest analysis
ls -t ~/Documents/Obsidian\ Vault/研究/财报分析/*.md | head -1

# Step 3: Validate (if validator exists)
python earnings-pipeline/scripts/validate_analysis.py --content-file {path}
```

## Key Paths

- **Test suite:** `tests/test_self_heal.py`
- **Validator:** `scripts/validate_all.py`
- **Fixtures:** `tests/fixtures/` (JSON baselines + tolerances.yaml)
- **Capture:** `scripts/capture_fixtures.py`
- **Preflight:** `~/.claude/skills/shared/preflight.py`
