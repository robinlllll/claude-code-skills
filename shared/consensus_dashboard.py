"""Consensus Dashboard Generator.

Reads JSONL history per ticker and generates a self-contained HTML dashboard
with EPS consensus trend charts, revenue estimates, surprise history,
relative valuation, and downgrade alerts.

Usage:
    python consensus_dashboard.py GOOG              # single ticker
    python consensus_dashboard.py GOOG AAPL NKE     # multi-ticker
    python consensus_dashboard.py --portfolio       # all portfolio tickers with history
    python consensus_dashboard.py GOOG --open       # generate and open in browser
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SKILLS_DIR = str(Path(__file__).resolve().parent.parent)
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)

from shared.consensus_data import (
    get_consensus,
    load_history,
    detect_changes,
    HISTORY_DIR,
)

OUTPUT_DIR = (
    Path.home() / "Documents" / "Obsidian Vault" / "归档" / "Consensus Dashboard"
)


def _safe(v):
    """Convert NaN/None to None for JSON serialization."""
    if v is None:
        return None
    try:
        if math.isnan(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def build_ticker_data(ticker: str, *, live: bool = True) -> dict:
    """Build complete dashboard data for a single ticker.

    Args:
        ticker: Ticker symbol.
        live: If True (default), fetch live data from YFinance/Finnhub.
              If False, use the latest JSONL history snapshot as "current"
              (much faster — no API calls).
    """
    if live:
        current = get_consensus(ticker)
    else:
        # Fast path: use latest history snapshot as current
        history = load_history(ticker)
        if not history:
            raise ValueError(f"No history for {ticker}")
        current = history[-1]

    # History
    history = load_history(ticker)
    # Also add current if not already today
    today = datetime.now().strftime("%Y-%m-%d")
    has_today = any(s.get("timestamp", "")[:10] == today for s in history)
    if not has_today:
        history.append(current)

    # Alert status
    prev = None
    for snap in reversed(history[:-1]) if len(history) > 1 else []:
        snap_date = snap.get("timestamp", "")[:10]
        if snap_date < today:
            prev = snap
            break
    alert = detect_changes(current, prev)

    # ── Build EPS Consensus Trend time series ──
    # For each snapshot, extract EPS estimates by period
    eps_trend_series = {}  # {period: [{date, value}, ...]}
    for snap in history:
        date = snap.get("timestamp", "")[:10]
        for e in snap.get("estimates", {}).get("eps", []):
            period = e.get("period", "")
            avg = _safe(e.get("eps_avg"))
            if avg is not None and period:
                eps_trend_series.setdefault(period, []).append(
                    {"date": date, "value": avg}
                )

    # Also use eps_trend (built-in 7d/30d/60d/90d) for more data points
    # Convert to approximate dates for richer initial chart
    today_dt = datetime.now()
    for t in current.get("eps_trend", []):
        period = t.get("period", "")
        if not period:
            continue
        for key, days_ago in [
            ("90d_ago", 90),
            ("60d_ago", 60),
            ("30d_ago", 30),
            ("7d_ago", 7),
        ]:
            val = _safe(t.get(key))
            if val is not None:
                from datetime import timedelta

                approx_date = (today_dt - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                series = eps_trend_series.setdefault(period, [])
                # Only add if we don't have a snapshot near that date
                existing_dates = {p["date"] for p in series}
                if approx_date not in existing_dates:
                    series.append({"date": approx_date, "value": val})

    # Sort each series by date and deduplicate
    for period in eps_trend_series:
        eps_trend_series[period].sort(key=lambda x: x["date"])

    # ── Revenue trend series ──
    rev_trend_series = {}
    for snap in history:
        date = snap.get("timestamp", "")[:10]
        for e in snap.get("estimates", {}).get("revenue", []):
            period = e.get("period", "")
            avg = _safe(e.get("rev_avg"))
            if avg is not None and period and avg > 0:
                rev_trend_series.setdefault(period, []).append(
                    {"date": date, "value": avg}
                )
    for period in rev_trend_series:
        rev_trend_series[period].sort(key=lambda x: x["date"])

    # ── Price target trend ──
    pt_series = []
    for snap in history:
        date = snap.get("timestamp", "")[:10]
        pt = snap.get("price_target", {})
        mean = _safe(pt.get("yf_mean"))
        cur = _safe(pt.get("yf_current"))
        if mean is not None:
            pt_series.append({"date": date, "mean": mean, "current": cur})

    # ── NTM P/E series (price / forward EPS) ──
    pe_series = []
    for snap in history:
        date = snap.get("timestamp", "")[:10]
        price = _safe(snap.get("price_target", {}).get("yf_current"))
        # Use +1y EPS as NTM proxy
        fwd_eps = None
        for e in snap.get("estimates", {}).get("eps", []):
            if e.get("period") == "+1y":
                fwd_eps = _safe(e.get("eps_avg"))
                break
        if not fwd_eps:
            for e in snap.get("estimates", {}).get("eps", []):
                if e.get("period") == "0y":
                    fwd_eps = _safe(e.get("eps_avg"))
                    break
        if price and fwd_eps and fwd_eps > 0:
            pe_series.append({"date": date, "pe": round(price / fwd_eps, 2)})

    # ── Surprise history ──
    surprises = []
    for s in current.get("surprises", []):
        actual = _safe(s.get("actual"))
        estimate = _safe(s.get("estimate"))
        surp_pct = _safe(s.get("surprise_pct"))
        if actual is not None:
            surprises.append(
                {
                    "period": s.get("period", ""),
                    "actual": actual,
                    "estimate": estimate,
                    "surprise_pct": surp_pct,
                }
            )

    # ── EPS revisions (7d/30d % change for summary table) ──
    revisions = {}
    for t in current.get("eps_trend", []):
        period = t.get("period", "")
        current_val = _safe(t.get("current"))
        d7 = _safe(t.get("7d_ago"))
        d30 = _safe(t.get("30d_ago"))
        d60 = _safe(t.get("60d_ago"))
        d90 = _safe(t.get("90d_ago"))
        if current_val is not None and period:
            rev = {}
            if d7 is not None and abs(d7) > 0.0001:
                rev["7d"] = round((current_val - d7) / abs(d7) * 100, 2)
            if d30 is not None and abs(d30) > 0.0001:
                rev["30d"] = round((current_val - d30) / abs(d30) * 100, 2)
            if d60 is not None and abs(d60) > 0.0001:
                rev["60d"] = round((current_val - d60) / abs(d60) * 100, 2)
            if d90 is not None and abs(d90) > 0.0001:
                rev["90d"] = round((current_val - d90) / abs(d90) * 100, 2)
            if rev:
                revisions[period] = rev

    # ── Current estimates table ──
    eps_table = []
    for e in current.get("estimates", {}).get("eps", []):
        avg = _safe(e.get("eps_avg"))
        if avg is not None:
            eps_table.append(
                {
                    "period": e["period"],
                    "avg": avg,
                    "low": _safe(e.get("eps_low")),
                    "high": _safe(e.get("eps_high")),
                    "yoy": _safe(e.get("growth")),
                    "analysts": _safe(e.get("num_analysts")),
                }
            )

    rev_table = []
    for e in current.get("estimates", {}).get("revenue", []):
        avg = _safe(e.get("rev_avg"))
        if avg is not None and avg > 0:
            rev_table.append(
                {
                    "period": e["period"],
                    "avg": avg,
                    "low": _safe(e.get("rev_low")),
                    "high": _safe(e.get("rev_high")),
                    "yoy": _safe(e.get("growth")),
                    "analysts": _safe(e.get("num_analysts")),
                }
            )

    # ── Ratings ──
    ratings = current.get("ratings", {})

    return {
        "ticker": ticker.upper(),
        "timestamp": current["timestamp"],
        "price": _safe(current.get("price_target", {}).get("yf_current")),
        "snapshot_count": len(history),
        "alert": {
            "severity": alert["severity"],
            "signals": [
                {
                    "detail": s["detail"],
                    "severity": s["severity"],
                    "direction": s.get("direction", ""),
                }
                for s in alert["signals"]
            ],
        },
        "eps_trend_series": eps_trend_series,
        "rev_trend_series": rev_trend_series,
        "pt_series": pt_series,
        "pe_series": pe_series,
        "surprises": surprises,
        "eps_table": eps_table,
        "rev_table": rev_table,
        "ratings": {
            "recommendation": ratings.get("recommendation", ""),
            "num_analysts": ratings.get("num_analysts"),
            "fh_strong_buy": ratings.get("fh_strong_buy", 0),
            "fh_buy": ratings.get("fh_buy", 0),
            "fh_hold": ratings.get("fh_hold", 0),
            "fh_sell": ratings.get("fh_sell", 0),
            "fh_strong_sell": ratings.get("fh_strong_sell", 0),
        },
        "price_target": {
            "current": _safe(current.get("price_target", {}).get("yf_current")),
            "mean": _safe(current.get("price_target", {}).get("yf_mean")),
            "median": _safe(current.get("price_target", {}).get("yf_median")),
            "high": _safe(current.get("price_target", {}).get("yf_high")),
            "low": _safe(current.get("price_target", {}).get("yf_low")),
        },
        "revisions": revisions,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Consensus Dashboard — {{GENERATED_AT}}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<style>
  :root {
    --bg: #0a0c10; --surface: #12151c; --card: #1a1d27; --border: #252836;
    --text: #e4e7f0; --muted: #7c8098; --accent: #4f8ff7;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6;
    --teal: #14b8a6; --purple: #a78bfa;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif; }

  /* ── Top Nav Bar ── */
  .topbar {
    position: sticky; top: 0; z-index: 100;
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 12px 24px; display: flex; align-items: center; gap: 16px;
    backdrop-filter: blur(12px);
  }
  .topbar-brand {
    font-size: 14px; font-weight: 700; color: var(--accent);
    white-space: nowrap; letter-spacing: -0.3px;
  }
  .search-box {
    position: relative; width: 240px; flex-shrink: 0;
  }
  .search-box input {
    width: 100%; padding: 7px 12px 7px 32px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text); font-size: 13px; outline: none;
    transition: border-color 0.2s;
  }
  .search-box input:focus { border-color: var(--accent); }
  .search-box svg {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    width: 14px; height: 14px; color: var(--muted);
  }
  .ticker-tabs {
    display: flex; gap: 4px; flex-wrap: wrap; flex: 1; overflow-x: auto;
    scrollbar-width: none;
  }
  .ticker-tabs::-webkit-scrollbar { display: none; }
  .ticker-tab {
    padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
    cursor: pointer; border: 1px solid transparent; white-space: nowrap;
    transition: all 0.15s; user-select: none;
    background: var(--bg); color: var(--muted);
  }
  .ticker-tab:hover { color: var(--text); border-color: var(--border); }
  .ticker-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .ticker-tab.sev-critical { border-left: 3px solid var(--red); }
  .ticker-tab.sev-warning { border-left: 3px solid var(--yellow); }
  .ticker-tab.sev-watch { border-left: 3px solid var(--blue); }
  .ticker-tab.active.sev-critical,
  .ticker-tab.active.sev-warning,
  .ticker-tab.active.sev-watch { border-left-color: transparent; }
  .ticker-tab .tab-dot {
    display: inline-block; width: 6px; height: 6px; border-radius: 50%;
    margin-right: 4px; vertical-align: middle;
  }
  .tab-dot.dot-critical { background: var(--red); }
  .tab-dot.dot-warning { background: var(--yellow); }
  .tab-dot.dot-watch { background: var(--blue); }
  .nav-summary {
    font-size: 11px; color: var(--muted); white-space: nowrap; flex-shrink: 0;
  }

  /* ── Main Content ── */
  .main { padding: 20px 24px 40px; max-width: 1400px; margin: 0 auto; }

  /* ── Stock Page Header ── */
  .stock-header {
    display: flex; align-items: baseline; gap: 16px; margin-bottom: 24px;
    padding-bottom: 16px; border-bottom: 1px solid var(--border);
  }
  .stock-ticker { font-size: 36px; font-weight: 800; letter-spacing: -1px; }
  .stock-price { font-size: 28px; font-weight: 600; color: var(--muted); }
  .badge {
    padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .badge-critical { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge-warning { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .badge-watch { background: rgba(59,130,246,0.15); color: var(--blue); }
  .badge-clean { background: rgba(34,197,94,0.12); color: var(--green); }
  .stock-meta { font-size: 12px; color: var(--muted); margin-left: auto; }
  .stock-nav {
    display: flex; gap: 6px; margin-left: 16px;
  }
  .stock-nav button {
    padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
    cursor: pointer; border: 1px solid var(--border); background: var(--bg);
    color: var(--muted); transition: all 0.15s;
  }
  .stock-nav button:hover { color: var(--text); border-color: var(--accent); }

  /* ── KPI Cards Row ── */
  .kpi-row {
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
    margin-bottom: 20px;
  }
  .kpi-card {
    background: var(--card); border-radius: 10px; padding: 14px 16px;
    border: 1px solid var(--border);
  }
  .kpi-label { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .kpi-value { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .kpi-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

  /* ── Chart Panels ── */
  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .chart-panel {
    background: var(--card); border-radius: 10px; padding: 16px 20px;
    border: 1px solid var(--border);
  }
  .chart-panel.full-width { grid-column: 1 / -1; }
  .chart-panel h3 {
    font-size: 13px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
  }
  .chart-box { position: relative; height: 320px; }
  .chart-box.short { height: 240px; }

  /* ── Data Tables ── */
  .tables-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .table-panel {
    background: var(--card); border-radius: 10px; padding: 16px 20px;
    border: 1px solid var(--border);
  }
  .table-panel h3 {
    font-size: 13px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
  }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; }
  td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .pos { color: var(--green); }
  .neg { color: var(--red); }

  /* ── Bottom Row: Alerts + Ratings + PT ── */
  .bottom-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .info-panel {
    background: var(--card); border-radius: 10px; padding: 16px 20px;
    border: 1px solid var(--border);
  }
  .info-panel h3 {
    font-size: 13px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
  }
  .alert-list { list-style: none; font-size: 13px; }
  .alert-list li { padding: 6px 0; display: flex; align-items: flex-start; gap: 8px; }
  .alert-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
  .alert-dot.critical { background: var(--red); }
  .alert-dot.warning { background: var(--yellow); }
  .alert-dot.watch { background: var(--blue); }
  .ratings-bar { display: flex; height: 28px; border-radius: 6px; overflow: hidden; margin-top: 8px; }
  .ratings-bar span { display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: #fff; }
  .rb-sbuy { background: #16a34a; }
  .rb-buy { background: #4ade80; color: #064e3b !important; }
  .rb-hold { background: #fbbf24; color: #78350f !important; }
  .rb-sell { background: #f97316; }
  .rb-ssell { background: #dc2626; }
  .ratings-legend { display: flex; gap: 12px; margin-top: 8px; font-size: 11px; color: var(--muted); flex-wrap: wrap; }
  .ratings-legend span::before { content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; vertical-align: middle; background: var(--c); }
  .pt-visual { margin-top: 12px; position: relative; height: 40px; }
  .pt-range-bar {
    position: absolute; top: 16px; height: 6px; border-radius: 3px;
    background: linear-gradient(90deg, var(--red), var(--yellow), var(--green));
    opacity: 0.3;
  }
  .pt-marker {
    position: absolute; top: 8px; width: 2px; height: 22px; border-radius: 1px;
  }
  .pt-label { position: absolute; top: 32px; font-size: 10px; color: var(--muted); transform: translateX(-50%); white-space: nowrap; }

  /* ── Footer ── */
  .meta { font-size: 11px; color: var(--muted); text-align: right; padding: 0 24px 20px; }

  /* ── Hidden pages ── */
  .stock-page { display: none; }
  .stock-page.active { display: block; }

  /* ── Keyboard hint ── */
  .kbd-hint { font-size: 11px; color: var(--muted); margin-left: 8px; }
  kbd { background: var(--bg); border: 1px solid var(--border); border-radius: 3px; padding: 1px 5px; font-size: 10px; font-family: inherit; }

  @media (max-width: 1000px) {
    .kpi-row { grid-template-columns: repeat(3, 1fr); }
    .charts-grid, .tables-grid { grid-template-columns: 1fr; }
    .bottom-grid { grid-template-columns: 1fr; }
  }
  @media (max-width: 700px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    .topbar { flex-wrap: wrap; }
    .search-box { width: 100%; order: 10; }
  }
</style>
</head>
<body>

<!-- Top Navigation Bar -->
<div class="topbar">
  <span class="topbar-brand">CONSENSUS</span>
  <div class="search-box">
    <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>
    <input type="text" id="searchInput" placeholder="Search ticker... (/ to focus)" autocomplete="off">
  </div>
  <div class="ticker-tabs" id="tickerTabs"></div>
  <div class="nav-summary" id="navSummary"></div>
  <span class="kbd-hint"><kbd>&larr;</kbd> <kbd>&rarr;</kbd> navigate</span>
</div>

<!-- Stock Pages Container -->
<div class="main" id="app"></div>

<p class="meta">Generated {{GENERATED_AT}} &mdash; Data: YFinance + Finnhub &mdash; Robin's Analysis Pipeline</p>

<script>
const DATA = {{DATA_JSON}};

const PERIOD_COLORS = {
  '0q': '#4f8ff7', '+1q': '#22c55e', '0y': '#f59e0b', '+1y': '#ef4444',
  '-1y': '#a78bfa', '-4q': '#8b5cf6', '+2y': '#ec4899',
  'fh_eps': '#06b6d4', 'fh_revenue': '#ec4899',
};
const PERIOD_NAMES = {
  '0q': 'Current Q', '+1q': 'Next Q', '0y': 'Current FY', '+1y': 'Next FY',
  '-1y': 'Last FY', '-4q': 'Last Q', '+2y': 'FY+2',
};

let activeTicker = null;
let charts = {};

// ── Utility functions ──
function fmtNum(n, dec=2) {
  if (n == null) return '-';
  if (Math.abs(n) >= 1e12) return '$' + (n/1e12).toFixed(dec) + 'T';
  if (Math.abs(n) >= 1e9) return '$' + (n/1e9).toFixed(dec) + 'B';
  if (Math.abs(n) >= 1e6) return '$' + (n/1e6).toFixed(dec) + 'M';
  return '$' + n.toFixed(dec);
}
function fmtPct(n) {
  if (n == null) return '-';
  const pct = (Math.abs(n) < 10 ? n * 100 : n).toFixed(1);
  return (n >= 0 ? '+' : '') + pct + '%';
}
function pctClass(n) { return n == null ? '' : n >= 0 ? 'pos' : 'neg'; }

// ── Build Navigation ──
function buildNav() {
  const tabs = document.getElementById('tickerTabs');
  const summary = document.getElementById('navSummary');
  let crit = 0, warn = 0, watch = 0, clean = 0;

  // Summary tab (always first)
  const summaryTab = document.createElement('div');
  summaryTab.className = 'ticker-tab';
  summaryTab.dataset.ticker = 'SUMMARY';
  summaryTab.innerHTML = '◉ SUMMARY';
  summaryTab.style.fontWeight = '700';
  summaryTab.style.letterSpacing = '0.5px';
  summaryTab.addEventListener('click', () => selectTicker('SUMMARY'));
  tabs.appendChild(summaryTab);

  DATA.forEach(d => {
    const sev = d.alert.severity;
    if (sev === 'CRITICAL') crit++;
    else if (sev === 'WARNING') warn++;
    else if (sev === 'WATCH') watch++;
    else clean++;

    const tab = document.createElement('div');
    tab.className = 'ticker-tab' + (sev ? ' sev-' + sev.toLowerCase() : '');
    tab.dataset.ticker = d.ticker;

    let dot = '';
    if (sev === 'CRITICAL') dot = '<span class="tab-dot dot-critical"></span>';
    else if (sev === 'WARNING') dot = '<span class="tab-dot dot-warning"></span>';
    else if (sev === 'WATCH') dot = '<span class="tab-dot dot-watch"></span>';
    tab.innerHTML = dot + d.ticker;

    tab.addEventListener('click', () => selectTicker(d.ticker));
    tabs.appendChild(tab);
  });

  const parts = [];
  parts.push(DATA.length + ' tickers');
  if (crit) parts.push(crit + ' critical');
  if (warn) parts.push(warn + ' warning');
  summary.textContent = parts.join(' | ');
}

// ── Build a Stock Page ──
function buildStockPage(d) {
  const page = document.createElement('div');
  page.className = 'stock-page';
  page.id = 'page-' + d.ticker;

  const sev = d.alert.severity;
  const sevClass = sev ? 'badge-' + sev.toLowerCase() : 'badge-clean';
  const sevText = sev || 'CLEAN';
  const priceStr = d.price ? '$' + d.price.toFixed(2) : '';

  // Find index for prev/next
  const idx = DATA.findIndex(x => x.ticker === d.ticker);

  let html = '';

  // ── Header ──
  html += `<div class="stock-header">
    <span class="stock-ticker">${d.ticker}</span>
    <span class="stock-price">${priceStr}</span>
    <span class="badge ${sevClass}">${sevText}</span>
    <span class="stock-meta">${d.snapshot_count} snapshot${d.snapshot_count > 1 ? 's' : ''} &middot; Updated ${d.timestamp.slice(0,16).replace('T',' ')}</span>
    <div class="stock-nav">
      ${idx > 0 ? '<button onclick="selectTicker(DATA['+(idx-1)+'].ticker)">&larr; '+DATA[idx-1].ticker+'</button>' : '<button onclick="selectTicker(\'SUMMARY\')">&larr; SUMMARY</button>'}
      ${idx < DATA.length-1 ? '<button onclick="selectTicker(DATA['+(idx+1)+'].ticker)">'+DATA[idx+1].ticker+' &rarr;</button>' : ''}
    </div>
  </div>`;

  // ── KPI Cards ──
  const pt = d.price_target;
  const upside = (pt.mean && pt.current && pt.current > 0)
    ? ((pt.mean - pt.current) / pt.current * 100) : null;
  const r = d.ratings;
  const totalRatings = (r.fh_strong_buy||0)+(r.fh_buy||0)+(r.fh_hold||0)+(r.fh_sell||0)+(r.fh_strong_sell||0);
  // Forward EPS from table
  const fwdEps = d.eps_table.find(e => e.period === '+1y') || d.eps_table.find(e => e.period === '0y');
  const fwdPE = (d.price && fwdEps && fwdEps.avg > 0) ? (d.price / fwdEps.avg) : null;
  // Latest surprise
  const lastSurp = d.surprises.length > 0 ? d.surprises[0] : null;

  html += '<div class="kpi-row">';
  // Price Target
  html += `<div class="kpi-card">
    <div class="kpi-label">Mean Price Target</div>
    <div class="kpi-value">${pt.mean ? '$'+pt.mean.toFixed(2) : '-'}</div>
    <div class="kpi-sub ${upside!=null?pctClass(upside):''}">${upside!=null?(upside>=0?'+':'')+upside.toFixed(1)+'% implied upside':pt.low&&pt.high?'$'+pt.low.toFixed(0)+' — $'+pt.high.toFixed(0):''}</div>
  </div>`;
  // Forward P/E
  html += `<div class="kpi-card">
    <div class="kpi-label">Forward P/E (NTM)</div>
    <div class="kpi-value">${fwdPE ? fwdPE.toFixed(1)+'x' : '-'}</div>
    <div class="kpi-sub">${fwdEps ? 'FY EPS $'+fwdEps.avg.toFixed(2) : ''}</div>
  </div>`;
  // Consensus Rating
  html += `<div class="kpi-card">
    <div class="kpi-label">Consensus Rating</div>
    <div class="kpi-value">${r.recommendation ? r.recommendation.replace('_',' ').toUpperCase() : '-'}</div>
    <div class="kpi-sub">${totalRatings} analysts</div>
  </div>`;
  // Alert Signals
  const nSignals = d.alert.signals.length;
  html += `<div class="kpi-card">
    <div class="kpi-label">Change Signals</div>
    <div class="kpi-value ${nSignals>0?'neg':''}">${nSignals}</div>
    <div class="kpi-sub">${sev || 'Clean'}</div>
  </div>`;
  // Last Surprise
  html += `<div class="kpi-card">
    <div class="kpi-label">Last EPS Surprise</div>
    <div class="kpi-value ${lastSurp&&lastSurp.surprise_pct!=null?pctClass(lastSurp.surprise_pct):''}">${lastSurp&&lastSurp.surprise_pct!=null?(lastSurp.surprise_pct>=0?'+':'')+lastSurp.surprise_pct.toFixed(1)+'%':'-'}</div>
    <div class="kpi-sub">${lastSurp?lastSurp.period:''}</div>
  </div>`;
  html += '</div>';

  // ── Pre-check data availability for charts ──
  const hasEpsTrend = Object.values(d.eps_trend_series).some(pts => pts.length >= 2);
  const hasRevTrend = Object.values(d.rev_trend_series).some(pts => pts.length >= 2);
  const hasPtTrend = d.pt_series.length >= 2;
  const hasPeTrend = d.pe_series.length >= 2;
  const hasSurprises = d.surprises.length > 0;

  // ── EPS Trend (always show — star chart) ──
  html += '<div class="charts-grid">';
  html += `<div class="chart-panel full-width">
    <h3>EPS Consensus Trend</h3>
    <div class="chart-box"><canvas id="chart-eps-${d.ticker}"></canvas></div>
  </div>`;
  html += '</div>';

  // ── Secondary charts: only show rows that have data ──
  const row2panels = [];
  if (hasRevTrend) row2panels.push(`<div class="chart-panel">
    <h3>Revenue Consensus Trend</h3>
    <div class="chart-box short"><canvas id="chart-rev-${d.ticker}"></canvas></div>
  </div>`);
  if (hasPtTrend) row2panels.push(`<div class="chart-panel">
    <h3>Price Target vs Price</h3>
    <div class="chart-box short"><canvas id="chart-pt-${d.ticker}"></canvas></div>
  </div>`);
  if (hasPeTrend) row2panels.push(`<div class="chart-panel">
    <h3>NTM P/E Ratio</h3>
    <div class="chart-box short"><canvas id="chart-pe-${d.ticker}"></canvas></div>
  </div>`);
  if (hasSurprises) row2panels.push(`<div class="chart-panel">
    <h3>EPS Surprise History</h3>
    <div class="chart-box short"><canvas id="chart-surp-${d.ticker}"></canvas></div>
  </div>`);

  if (row2panels.length > 0) {
    // If only 1 panel, make it full width
    if (row2panels.length === 1) {
      html += '<div class="charts-grid">' + row2panels[0].replace('class="chart-panel"', 'class="chart-panel full-width"') + '</div>';
    } else {
      // Group into rows of 2
      for (let i = 0; i < row2panels.length; i += 2) {
        html += '<div class="charts-grid">';
        html += row2panels[i];
        if (i + 1 < row2panels.length) html += row2panels[i + 1];
        html += '</div>';
      }
    }
  }

  // ── Data Tables: EPS Estimates + Revenue Estimates ──
  html += '<div class="tables-grid">';
  // EPS Table
  if (d.eps_table.length > 0) {
    html += '<div class="table-panel"><h3>EPS Estimates</h3><table>';
    html += '<tr><th>Period</th><th class="num">Consensus</th><th class="num">Low</th><th class="num">High</th><th class="num">YoY Growth</th><th class="num">Analysts</th></tr>';
    d.eps_table.forEach(e => {
      const yoyStr = e.yoy != null ? fmtPct(e.yoy) : '-';
      const yoyC = e.yoy != null ? pctClass(e.yoy) : '';
      html += `<tr><td><strong>${PERIOD_NAMES[e.period]||e.period}</strong></td><td class="num"><strong>$${e.avg.toFixed(2)}</strong></td><td class="num">$${e.low?.toFixed(2)||'-'}</td><td class="num">$${e.high?.toFixed(2)||'-'}</td><td class="num ${yoyC}">${yoyStr}</td><td class="num">${e.analysts?.toFixed(0)||'-'}</td></tr>`;
    });
    html += '</table></div>';
  }
  // Revenue Table
  if (d.rev_table.length > 0) {
    html += '<div class="table-panel"><h3>Revenue Estimates</h3><table>';
    html += '<tr><th>Period</th><th class="num">Consensus</th><th class="num">Low</th><th class="num">High</th><th class="num">YoY Growth</th><th class="num">Analysts</th></tr>';
    d.rev_table.forEach(e => {
      const yoyStr = e.yoy != null ? fmtPct(e.yoy) : '-';
      const yoyC = e.yoy != null ? pctClass(e.yoy) : '';
      html += `<tr><td><strong>${PERIOD_NAMES[e.period]||e.period}</strong></td><td class="num"><strong>${fmtNum(e.avg)}</strong></td><td class="num">${fmtNum(e.low)}</td><td class="num">${fmtNum(e.high)}</td><td class="num ${yoyC}">${yoyStr}</td><td class="num">${e.analysts?.toFixed(0)||'-'}</td></tr>`;
    });
    html += '</table></div>';
  }
  html += '</div>';

  // ── Bottom Row: Alerts + Ratings + Price Target Detail ──
  html += '<div class="bottom-grid">';
  // Alerts
  html += '<div class="info-panel"><h3>Consensus Changes</h3>';
  if (d.alert.signals.length > 0) {
    html += '<ul class="alert-list">';
    d.alert.signals.forEach(s => {
      const arrow = s.direction === 'UP' ? '⬆ ' : s.direction === 'DOWN' ? '⬇ ' : '';
      html += `<li><span class="alert-dot ${s.severity.toLowerCase()}"></span><span>${arrow}${s.detail}</span></li>`;
    });
    html += '</ul>';
  } else {
    html += '<p style="color:var(--green);font-size:14px;padding:12px 0">No material changes detected</p>';
  }
  html += '</div>';

  // Ratings
  html += '<div class="info-panel"><h3>Analyst Ratings</h3>';
  if (totalRatings > 0) {
    html += '<div class="ratings-bar">';
    if (r.fh_strong_buy) html += `<span class="rb-sbuy" style="flex:${r.fh_strong_buy}">${r.fh_strong_buy}</span>`;
    if (r.fh_buy) html += `<span class="rb-buy" style="flex:${r.fh_buy}">${r.fh_buy}</span>`;
    if (r.fh_hold) html += `<span class="rb-hold" style="flex:${r.fh_hold}">${r.fh_hold}</span>`;
    if (r.fh_sell) html += `<span class="rb-sell" style="flex:${r.fh_sell}">${r.fh_sell}</span>`;
    if (r.fh_strong_sell) html += `<span class="rb-ssell" style="flex:${r.fh_strong_sell}">${r.fh_strong_sell}</span>`;
    html += '</div>';
    html += '<div class="ratings-legend">';
    html += `<span style="--c:#16a34a">Strong Buy ${r.fh_strong_buy||0}</span>`;
    html += `<span style="--c:#4ade80">Buy ${r.fh_buy||0}</span>`;
    html += `<span style="--c:#fbbf24">Hold ${r.fh_hold||0}</span>`;
    html += `<span style="--c:#f97316">Sell ${r.fh_sell||0}</span>`;
    html += `<span style="--c:#dc2626">Strong Sell ${r.fh_strong_sell||0}</span>`;
    html += '</div>';
    if (r.recommendation) html += `<p style="margin-top:8px;font-size:13px">Consensus: <strong>${r.recommendation.replace('_',' ').toUpperCase()}</strong></p>`;
  } else {
    html += '<p style="color:var(--muted)">No rating data available</p>';
  }
  html += '</div>';

  // Price Target Detail
  html += '<div class="info-panel"><h3>Price Target Range</h3>';
  if (pt.mean) {
    html += '<table>';
    html += `<tr><td>Current Price</td><td class="num"><strong>$${pt.current?.toFixed(2)||'-'}</strong></td></tr>`;
    html += `<tr><td>Mean Target</td><td class="num"><strong>$${pt.mean.toFixed(2)}</strong></td></tr>`;
    html += `<tr><td>Median Target</td><td class="num">$${pt.median?.toFixed(2)||'-'}</td></tr>`;
    html += `<tr><td>High Target</td><td class="num" style="color:var(--green)">$${pt.high?.toFixed(2)||'-'}</td></tr>`;
    html += `<tr><td>Low Target</td><td class="num" style="color:var(--red)">$${pt.low?.toFixed(2)||'-'}</td></tr>`;
    if (upside != null) html += `<tr><td>Implied Upside</td><td class="num ${pctClass(upside)}"><strong>${(upside>=0?'+':'')+upside.toFixed(1)}%</strong></td></tr>`;
    html += '</table>';
  } else {
    html += '<p style="color:var(--muted)">No price target data available</p>';
  }
  html += '</div>';
  html += '</div>';

  // ── Surprise History Table ──
  if (d.surprises.length > 0) {
    html += '<div class="tables-grid"><div class="table-panel" style="grid-column:1/-1"><h3>EPS Surprise History</h3><table>';
    html += '<tr><th>Period</th><th class="num">Actual EPS</th><th class="num">Consensus Est.</th><th class="num">Surprise</th><th class="num">Surprise %</th></tr>';
    d.surprises.forEach(s => {
      const surpVal = (s.actual != null && s.estimate != null) ? (s.actual - s.estimate) : null;
      const surpStr = s.surprise_pct != null ? (s.surprise_pct >= 0 ? '+' : '') + s.surprise_pct.toFixed(1) + '%' : '-';
      const surpC = s.surprise_pct != null ? pctClass(s.surprise_pct) : '';
      html += `<tr><td>${s.period}</td><td class="num"><strong>$${s.actual.toFixed(2)}</strong></td><td class="num">$${s.estimate!=null?s.estimate.toFixed(2):'-'}</td><td class="num ${surpC}">${surpVal!=null?(surpVal>=0?'+':'')+surpVal.toFixed(2):'-'}</td><td class="num ${surpC}"><strong>${surpStr}</strong></td></tr>`;
    });
    html += '</table></div></div>';
  }

  page.innerHTML = html;
  return page;
}

// ── Build Summary Page ──
function buildSummaryPage() {
  const page = document.createElement('div');
  page.className = 'stock-page';
  page.id = 'page-SUMMARY';

  const allSignals = [];
  DATA.forEach(d => {
    d.alert.signals.forEach(s => {
      allSignals.push({ ticker: d.ticker, price: d.price, ...s });
    });
  });

  const ups = allSignals.filter(s => s.direction === 'UP').length;
  const downs = allSignals.filter(s => s.direction === 'DOWN').length;
  const criticals = allSignals.filter(s => s.severity === 'CRITICAL').length;
  const warnings = allSignals.filter(s => s.severity === 'WARNING').length;
  const watches = allSignals.filter(s => s.severity === 'WATCH').length;
  const changedTickers = new Set(allSignals.map(s => s.ticker));

  let html = '';
  html += `<div class="stock-header">
    <span class="stock-ticker">CHANGES SUMMARY</span>
    <span class="stock-price">${DATA.length} tickers monitored</span>
    <span class="stock-meta">${changedTickers.size} with changes</span>
  </div>`;

  html += '<div class="kpi-row">';
  html += `<div class="kpi-card"><div class="kpi-label">Total Changes</div><div class="kpi-value">${allSignals.length}</div><div class="kpi-sub">${changedTickers.size} tickers</div></div>`;
  html += `<div class="kpi-card"><div class="kpi-label">Upgrades</div><div class="kpi-value pos">${ups}</div><div class="kpi-sub">estimates raised</div></div>`;
  html += `<div class="kpi-card"><div class="kpi-label">Downgrades</div><div class="kpi-value neg">${downs}</div><div class="kpi-sub">estimates cut</div></div>`;
  html += `<div class="kpi-card"><div class="kpi-label">Critical</div><div class="kpi-value" style="color:var(--red)">${criticals}</div><div class="kpi-sub">&gt;5% revision</div></div>`;
  html += `<div class="kpi-card"><div class="kpi-label">Warning</div><div class="kpi-value" style="color:var(--yellow)">${warnings}</div><div class="kpi-sub">2-5% revision</div></div>`;
  html += '</div>';

  if (allSignals.length > 0) {
    const sevOrder = {'CRITICAL': 0, 'WARNING': 1, 'WATCH': 2};
    allSignals.sort((a, b) => (sevOrder[a.severity] ?? 3) - (sevOrder[b.severity] ?? 3) || a.ticker.localeCompare(b.ticker));
    html += '<div class="table-panel" style="margin-bottom:20px"><h3>All Consensus Changes</h3><table>';
    html += '<tr><th>Ticker</th><th class="num">Price</th><th>Direction</th><th>Severity</th><th style="width:55%">Detail</th></tr>';
    allSignals.forEach(s => {
      const arrow = s.direction === 'UP' ? '<span class="pos">⬆ UP</span>' : s.direction === 'DOWN' ? '<span class="neg">⬇ DOWN</span>' : '';
      const sevBadge = `<span class="badge badge-${s.severity.toLowerCase()}" style="font-size:10px;padding:2px 8px">${s.severity}</span>`;
      const priceStr = s.price ? '$' + s.price.toFixed(2) : '-';
      html += `<tr><td><strong style="cursor:pointer;color:var(--accent)" onclick="selectTicker('${s.ticker}')">${s.ticker}</strong></td><td class="num">${priceStr}</td><td>${arrow}</td><td>${sevBadge}</td><td>${s.detail}</td></tr>`;
    });
    html += '</table></div>';
  } else {
    html += '<div class="info-panel" style="text-align:center;padding:40px"><p style="color:var(--green);font-size:18px">No material changes detected</p><p style="color:var(--muted);margin-top:8px">All consensus estimates stable</p></div>';
  }

  const cleanTickers = DATA.filter(d => !changedTickers.has(d.ticker)).map(d => d.ticker);
  if (cleanTickers.length > 0) {
    html += `<div class="info-panel"><h3>No Changes (${cleanTickers.length})</h3><p style="color:var(--muted);line-height:1.8">${cleanTickers.map(t => '<span style="cursor:pointer;color:var(--accent)" onclick="selectTicker(\''+t+'\')">'+t+'</span>').join(' &middot; ')}</p></div>`;
  }

  page.innerHTML = html;
  return page;
}

// ── Chart Rendering ──
function destroyCharts() {
  Object.values(charts).forEach(c => { try { c.destroy(); } catch(e){} });
  charts = {};
}

function chartOpts(yCallback, unit='week') {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: { type: 'time', time: { unit, tooltipFormat: 'yyyy-MM-dd' }, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#7c8098', font: { size: 11 } } },
      y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#7c8098', font: { size: 11 }, callback: yCallback } },
    },
    plugins: {
      legend: { labels: { color: '#e4e7f0', usePointStyle: true, font: { size: 11 } } },
    },
  };
}

function renderCharts(d) {
  destroyCharts();

  // 1. EPS Consensus Trend (star chart)
  const epsCtx = document.getElementById('chart-eps-' + d.ticker);
  if (epsCtx) {
    const datasets = [];
    for (const [period, points] of Object.entries(d.eps_trend_series)) {
      if (points.length < 2) continue;
      datasets.push({
        label: PERIOD_NAMES[period] || period,
        data: points.map(p => ({x: p.date, y: p.value})),
        borderColor: PERIOD_COLORS[period] || '#888',
        backgroundColor: (PERIOD_COLORS[period] || '#888') + '18',
        borderWidth: 2.5, pointRadius: points.length < 30 ? 4 : 2,
        pointHoverRadius: 6, tension: 0.3, fill: false,
      });
    }
    if (datasets.length > 0) {
      const opts = chartOpts(v => '$' + v.toFixed(2));
      opts.plugins.tooltip = { callbacks: { label: ctx => ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(3) } };
      charts.eps = new Chart(epsCtx, { type: 'line', data: { datasets }, options: opts });
    } else {
      epsCtx.parentElement.innerHTML = '<p style="color:var(--muted);text-align:center;padding-top:120px">Not enough history yet. Run daily collector to accumulate data points.</p>';
    }
  }

  // 2. Revenue Trend (only if canvas exists — panels are conditionally rendered)
  const revCtx = document.getElementById('chart-rev-' + d.ticker);
  if (revCtx) {
    const datasets = [];
    for (const [period, points] of Object.entries(d.rev_trend_series)) {
      if (points.length < 2) continue;
      datasets.push({
        label: PERIOD_NAMES[period] || period,
        data: points.map(p => ({x: p.date, y: p.value})),
        borderColor: PERIOD_COLORS[period] || '#888',
        borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false,
      });
    }
    if (datasets.length > 0) {
      charts.rev = new Chart(revCtx, { type: 'line', data: { datasets }, options: chartOpts(v => {
        if (v >= 1e12) return '$' + (v/1e12).toFixed(1) + 'T';
        if (v >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
        if (v >= 1e6) return '$' + (v/1e6).toFixed(0) + 'M';
        return '$' + v.toFixed(0);
      })});
    }
  }

  // 3. Price Target vs Price
  const ptCtx = document.getElementById('chart-pt-' + d.ticker);
  if (ptCtx) {
    const ds = [
      { label: 'Mean Target', data: d.pt_series.map(p => ({x: p.date, y: p.mean})), borderColor: var_green, borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false, borderDash: [6,3] },
      { label: 'Current Price', data: d.pt_series.filter(p=>p.current).map(p => ({x: p.date, y: p.current})), borderColor: var_accent, borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false },
    ];
    charts.pt = new Chart(ptCtx, { type: 'line', data: { datasets: ds }, options: chartOpts(v => '$' + v.toFixed(0)) });
  }

  // 4. NTM P/E
  const peCtx = document.getElementById('chart-pe-' + d.ticker);
  if (peCtx) {
    const ds = [{ label: 'NTM P/E', data: d.pe_series.map(p => ({x: p.date, y: p.pe})), borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.1)', borderWidth: 2, pointRadius: 3, tension: 0.3, fill: true }];
    charts.pe = new Chart(peCtx, { type: 'line', data: { datasets: ds }, options: chartOpts(v => v.toFixed(1) + 'x') });
  }

  // 5. Surprise History (bar chart)
  const surpCtx = document.getElementById('chart-surp-' + d.ticker);
  if (surpCtx) {
    const labels = d.surprises.map(s => s.period).reverse();
    const values = d.surprises.map(s => s.surprise_pct).reverse();
    const colors = values.map(v => v >= 0 ? '#22c55e' : '#ef4444');
    charts.surp = new Chart(surpCtx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ label: 'Surprise %', data: values, backgroundColor: colors, borderRadius: 4, barPercentage: 0.6 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false }, ticks: { color: '#7c8098', font: { size: 10 } } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#7c8098', callback: v => v.toFixed(0) + '%' } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y.toFixed(1) + '%' } },
        },
      },
    });
  }
}

// Color variables for chart use
const var_green = '#22c55e';
const var_accent = '#4f8ff7';

// ── Page Selection ──
function selectTicker(ticker) {
  if (activeTicker === ticker) return;
  activeTicker = ticker;

  // Update tabs
  document.querySelectorAll('.ticker-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.ticker === ticker);
  });
  // Scroll active tab into view
  const activeTab = document.querySelector('.ticker-tab.active');
  if (activeTab) activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });

  // Show page
  document.querySelectorAll('.stock-page').forEach(p => {
    p.classList.toggle('active', p.id === 'page-' + ticker);
  });

  // Render charts for this ticker (skip for summary page)
  if (ticker !== 'SUMMARY') {
    const d = DATA.find(x => x.ticker === ticker);
    if (d) setTimeout(() => renderCharts(d), 30);
  } else {
    destroyCharts();
  }

  // Update URL hash
  history.replaceState(null, '', '#' + ticker);
}

// ── Search ──
const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('input', () => {
  const q = searchInput.value.toUpperCase().trim();
  document.querySelectorAll('.ticker-tab').forEach(t => {
    const match = !q || t.dataset.ticker.includes(q);
    t.style.display = match ? '' : 'none';
  });
});

// ── Keyboard Navigation ──
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && document.activeElement !== searchInput) {
    e.preventDefault();
    searchInput.focus();
    return;
  }
  if (e.key === 'Escape') {
    searchInput.blur();
    searchInput.value = '';
    searchInput.dispatchEvent(new Event('input'));
    return;
  }
  if (document.activeElement === searchInput) return;

  if (activeTicker === 'SUMMARY') {
    if (e.key === 'ArrowRight' && DATA.length > 0) selectTicker(DATA[0].ticker);
    return;
  }
  const idx = DATA.findIndex(x => x.ticker === activeTicker);
  if (e.key === 'ArrowLeft') {
    selectTicker(idx > 0 ? DATA[idx - 1].ticker : 'SUMMARY');
  } else if (e.key === 'ArrowRight' && idx < DATA.length - 1) {
    selectTicker(DATA[idx + 1].ticker);
  }
});

// ── Initialize ──
const app = document.getElementById('app');
app.appendChild(buildSummaryPage());
DATA.forEach(d => app.appendChild(buildStockPage(d)));
buildNav();

// Select initial ticker from hash, default to SUMMARY
const hashTicker = location.hash.slice(1).toUpperCase();
if (hashTicker && hashTicker !== 'SUMMARY') {
  const initial = DATA.find(d => d.ticker === hashTicker);
  selectTicker(initial ? initial.ticker : 'SUMMARY');
} else {
  selectTicker('SUMMARY');
}
</script>
</body>
</html>"""


def generate_dashboard(tickers: list[str], output_path: Path | None = None) -> Path:
    """Generate the full HTML dashboard for given tickers."""
    all_data = []
    for ticker in tickers:
        try:
            d = build_ticker_data(ticker)
            all_data.append(d)
        except Exception as e:
            print(f"  [ERR] {ticker}: {e}")

    if not all_data:
        print("No data to display.")
        return None

    # Sort: alerts first, then alphabetical
    sev_order = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2, "": 3}
    all_data.sort(key=lambda d: (sev_order.get(d["alert"]["severity"], 3), d["ticker"]))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    data_json = json.dumps(all_data, ensure_ascii=False, default=str)

    html = HTML_TEMPLATE.replace("{{GENERATED_AT}}", generated_at).replace(
        "{{DATA_JSON}}", data_json
    )

    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / "consensus-dashboard.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Dashboard: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Consensus dashboard generator")
    parser.add_argument("tickers", nargs="*", help="Ticker symbol(s)")
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Use all portfolio tickers with history",
    )
    parser.add_argument("--output", type=str, help="Custom output path")
    parser.add_argument(
        "--open", action="store_true", help="Open in browser after generating"
    )
    args = parser.parse_args()

    if args.portfolio:
        # All tickers that have history files
        tickers = []
        if HISTORY_DIR.exists():
            for f in sorted(HISTORY_DIR.glob("*.jsonl")):
                if not f.name.startswith("_"):
                    tickers.append(f.stem)
        if not tickers:
            print("No history files found. Run consensus_collector.py first.")
            return
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        parser.print_help()
        return

    output_path = Path(args.output) if args.output else None
    path = generate_dashboard(tickers, output_path)

    if path and args.open:
        webbrowser.open(str(path))


if __name__ == "__main__":
    main()
