---
name: consensus-dashboard
description: "Generate and view a FactSet-style consensus estimates dashboard for portfolio tickers. Tracks EPS revisions, revenue estimates, price targets, analyst ratings. Use when user says 'consensus', 'EPS revisions', 'analyst estimates', 'consensus dashboard', 'estimate changes', or asks about earnings forecast trends. NOT for individual earnings transcript analysis (use /transcript-analyzer)."
---

# /consensus — Consensus Estimates Dashboard

Generate and view a FactSet-style consensus estimates dashboard for portfolio tickers. Tracks EPS revisions, revenue estimates, price targets, analyst ratings, and downgrade alerts over time.

## When to Use

Trigger when user:
- Says "consensus", "consensus dashboard", "EPS revision", "estimate changes"
- Wants to see analyst consensus data for tickers
- Asks about earnings estimate trends
- Uses `/consensus` command

## Commands

```bash
# Generate dashboard for all tickers with history
/consensus

# Specific tickers
/consensus GOOG NVDA AAPL

# Collect fresh data + generate
/consensus --collect

# Collect data for portfolio tickers (no dashboard)
/consensus collect

# View alerts only
/consensus alerts

# Open in browser
/consensus --open
```

## Execution Steps

### Default: Generate + Open Dashboard

```bash
cd ~/.claude/skills

# If --collect flag or 'collect' subcommand:
python shared/consensus_collector.py --portfolio

# Generate dashboard
python shared/consensus_dashboard.py --portfolio --open
```

### Specific Tickers

```bash
cd ~/.claude/skills

# Collect data for specific tickers first
python shared/consensus_collector.py --tickers GOOG NVDA

# Generate dashboard
python shared/consensus_dashboard.py GOOG NVDA --open
```

### Alerts Only

```bash
cd ~/.claude/skills
python shared/consensus_data.py --alert GOOG NVDA AAPL
```

## Architecture

```
consensus_data.py          — Core module: YFinance + Finnhub data fetch, JSONL history, downgrade detection
consensus_collector.py     — Daily batch collector (scheduled task candidate)
consensus_dashboard.py     — HTML dashboard generator (self-contained, Chart.js)
```

### Data Flow

```
YFinance API + Finnhub API
    ↓ get_consensus(ticker)
JSONL snapshots (~/.claude/data/consensus_history/{TICKER}.jsonl)
    ↓ build_ticker_data(ticker)
Self-contained HTML dashboard (Chart.js, dark theme)
    ↓
Portfolio Monitor at /consensus (served via FastAPI)
```

### Data Sources

| Source | Data |
|--------|------|
| YFinance | EPS/Revenue estimates (quarterly+annual), EPS revision trend (7d/30d/60d/90d), growth estimates, price targets, recommendation |
| Finnhub | Analyst rating distribution (Strong Buy/Buy/Hold/Sell/Strong Sell), earnings surprises |

### Downgrade Detection

| Severity | Threshold | Example |
|----------|-----------|---------|
| CRITICAL | >5% cut | EPS 0q revised -8.3% over 30d |
| WARNING | 2-5% | Revenue +1y revised -3.1% cross-snapshot |
| WATCH | 0.5-2% | EPS 0y revised -1.2% over 7d |

## Integration Points

| System | How |
|--------|-----|
| Portfolio Monitor | `/consensus` route serves dashboard HTML |
| Morning Brief | §7 scans top 10 tickers for downgrades |
| Telegram | `shared/telegram_notify.py` pushes CRITICAL/WARNING alerts |
| Daily Schedule | `consensus_collector.py --notify` runs daily |

## Key Files

- `shared/consensus_data.py` — Core data module
- `shared/consensus_collector.py` — Batch collector
- `shared/consensus_dashboard.py` — Dashboard generator
- `~/.claude/data/consensus_history/` — JSONL snapshot storage
- `~/Documents/Obsidian Vault/归档/Consensus Dashboard/consensus-dashboard.html` — Output

## Dashboard Features

- **Search + Tab navigation** — Filter and switch between tickers
- **KPI cards** — Price target, forward P/E, consensus rating, downgrade signals, last surprise
- **EPS Consensus Trend chart** — The star feature, shows estimate revisions over time by period
- **Revenue Trend chart** — Revenue estimate evolution
- **Price Target vs Price chart** — Mean target vs current price
- **NTM P/E chart** — Forward P/E evolution
- **Surprise History bar chart** — Beat/miss history
- **Estimates tables** — Current EPS + Revenue estimates with YoY growth
- **Ratings bar** — Visual distribution of Strong Buy → Strong Sell
- **Alert detail** — Specific downgrade signals with severity

## Python Path

Always use full Python path:
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe
```
