---
name: memory-cycle
description: Track NAND/DRAM prices across multiple sources to identify memory cycle inflection points
---

# Memory Cycle Tracker

Cross-validate NAND and DRAM price signals from 5 independent data sources to identify memory cycle inflection points. Investment-actionable for MU, WDC, Samsung (005930.KS), SK Hynix (000660.KS).

## Project Location

`C:\Users\thisi\.claude\skills\memory-cycle\`

## When to Use This Skill

- User mentions memory cycle, DRAM/NAND prices, memory semiconductor tracking
- User asks about MU, WDC, Samsung, SK Hynix cycle positioning
- User wants to check memory spot prices or Korean export data
- User asks "where are we in the memory cycle?"
- User wants memory cycle dashboard or alerts

## Commands

### /memory-cycle collect

Collect latest data from all sources and update the database.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/.claude/skills/memory-cycle/scripts/collect_all.py
```

### /memory-cycle collect --daily

Run daily-frequency collectors only (yfinance, spot pricing) + intra-month alert checks.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/.claude/skills/memory-cycle/scripts/collect_all.py --daily
```

### /memory-cycle dashboard

Generate the HTML dashboard with all 6 panels.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/.claude/skills/memory-cycle/scripts/generate_dashboard.py
```

### /memory-cycle status

Show current cycle phase, latest signals, and any active alerts.

```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe C:/Users/thisi/.claude/skills/memory-cycle/scripts/collect_all.py --status
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/memory_db.py` | SQLite schema: price_signals, fundamental_signals, composite_scores, fetch_log |
| `scripts/base_collector.py` | CollectorResult dataclass + common interface |
| `scripts/collect_yfinance.py` | MU, WDC, Samsung, Hynix, SOXX + KRW/USD FX |
| `scripts/collect_sec_xbrl.py` | MU + WDC: segment revenue, gross margin, inventory days, capex |
| `scripts/collect_korea_exports.py` | Korean memory exports (HS 854232) value + volume |
| `scripts/collect_spot_pricing.py` | DXI spot prices + PCPartPicker fallback |
| `scripts/collect_all.py` | Orchestrator: run all, compute scores, export CSV |
| `scripts/cross_validation.py` | Z-score engine + Group A vs B divergence |
| `scripts/cycle_classifier.py` | Phase classifier (early/mid/peak/contraction) |
| `scripts/generate_dashboard.py` | HTML dashboard with 6 panels |

## Architecture

```
5 Data Sources (free, scrapable)
  -> Collectors (one script each, common interface)
    -> SQLite DB (normalized time-series)
      -> Cross-Validation Engine (z-score, 2 signal groups)
        -> Cycle Phase Classifier (early/mid/peak/contraction)
          -> Dashboard (HTML) + CSV + Email alerts
```

**Signal Groups (avoid circularity):**
- Group A (Price Momentum): stock prices, retail DRAM/SSD prices, spot prices
- Group B (Fundamentals): Korean exports (1.5x weight), Micron revenue/margin, capex, inventory days
- Primary signal = divergence between Group A and Group B

**3 Sub-Cycles:**
- HBM: AI demand driven, can mask commodity weakness
- Commodity DRAM: Traditional cycle, inventory-driven
- NAND: Often lags DRAM, WDC is cleaner pure-play

## Dependencies

- yfinance
- requests
- beautifulsoup4
- pandas
- numpy
- scipy (statsmodels for Granger test)
- python-dotenv

## Output

- SQLite DB: `scripts/data/memory_cycle.db`
- CSV: `Documents/Obsidian Vault/研究/研究笔记/memory-cycle-tracker.csv`
- Dashboard: `Documents/Obsidian Vault/研究/研究笔记/memory-cycle-dashboard.html`
- Email alerts on phase transitions or significant divergence
