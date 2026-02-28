---
name: portfolio
description: "Portfolio Monitor - Open the portfolio dashboard, check positions, trades, and holdings. Use when user says 'portfolio', 'positions', 'P&L', '持仓', 'dashboard', or asks to check holdings."
allowed-tools: "Bash Read Write Edit Glob Grep"
metadata:
  version: 1.0.0
---

# Portfolio Monitor

Quick access to the Portfolio Monitor web dashboard.

## Project Location

`C:\Users\thisi\PORTFOLIO\portfolio_monitor`

## When to Use This Skill

- User runs `/portfolio`
- User wants to open the portfolio site
- User asks to check portfolio, positions, trades, or holdings

## CRITICAL: File Targeting

The portfolio monitor frontend is served from `static/index_v2.html`, NOT `index.html`.
Before ANY frontend edit:
1. Verify the served file: `grep -r "index_v2" app.py` or check the static mount
2. Always edit `index_v2.html` for the main dashboard
3. CSS lives in `static/css/main.css`, JS modules in `static/js/`
4. `index.html` is legacy/unused — never edit it

## Workflow

### 1. Check if Server is Running

```bash
curl -s --connect-timeout 2 http://localhost:8000/api/thesis-options
```

### 2. Start Server if Not Running

If the curl fails or returns empty, start the server:

```bash
cd "C:/Users/thisi/PORTFOLIO/portfolio_monitor" && cmd //c "start /b python -m uvicorn app:app --host 0.0.0.0 --port 8000"
```

Wait 3 seconds for server to start.

### 3. Open the Site

```bash
start http://localhost:8000
```

### 4. Confirm to User

Display a brief confirmation:
```
✅ Portfolio Monitor opened at http://localhost:8000
```

## Optional Arguments

| Argument | Action |
|----------|--------|
| (none) | Open dashboard |
| `refresh` | Open + refresh data from IBKR |
| `trades` | Open to trades analysis tab |
| `holdings` | Open to current holdings tab |

## If "refresh" Argument

After opening the site, call the refresh endpoint:

```bash
curl -s -X POST http://localhost:8000/api/refresh
```

Then report result: positions count, last update time.

## If "trades" or "holdings" Argument

Just open the site - user can navigate to the specific tab. No special handling needed.
