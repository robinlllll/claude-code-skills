"""Consensus estimates aggregator — YFinance + Finnhub.

Pulls forward EPS/revenue estimates, earnings surprises, analyst ratings,
price targets, and EPS revision trends. Merges both sources into a single
structured dict or markdown report.

Usage as module:
    from consensus_data import get_consensus, render_consensus_md

Usage as CLI:
    python consensus_data.py GOOG
    python consensus_data.py GOOG --json
    python consensus_data.py GOOG --section estimates
    python consensus_data.py GOOG AAPL META          # multi-ticker
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── Encoding fix for Windows GBK console ──
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import requests as _requests
except ImportError:
    _requests = None

# ── Config ──
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
if not FINNHUB_API_KEY:
    _env_path = Path.home() / "Screenshots" / ".env"
    if _env_path.exists():
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("FINNHUB_API_KEY="):
                FINNHUB_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")

FINNHUB_BASE = "https://finnhub.io/api/v1"


# ── Helpers ──
def _fmt_num(n, decimals=2) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 1e12:
        return f"${n / 1e12:,.{decimals}f}T"
    if abs(n) >= 1e9:
        return f"${n / 1e9:,.{decimals}f}B"
    if abs(n) >= 1e6:
        return f"${n / 1e6:,.{decimals}f}M"
    return f"${n:,.{decimals}f}"


def _fmt_pct(n) -> str:
    if n is None:
        return "N/A"
    return f"{n * 100:+.1f}%" if abs(n) < 10 else f"{n:+.1f}%"


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _finnhub_get(endpoint: str, params: dict) -> Optional[dict]:
    """Call Finnhub API. Returns None on failure."""
    if not _requests or not FINNHUB_API_KEY:
        return None
    params["token"] = FINNHUB_API_KEY
    try:
        r = _requests.get(f"{FINNHUB_BASE}/{endpoint}", params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and "error" in data:
                return None
            return data
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  Data Collection
# ═══════════════════════════════════════════════════════════════


def get_consensus(ticker: str) -> dict:
    """Collect consensus data from YFinance + Finnhub. Returns structured dict."""
    result = {
        "ticker": ticker.upper(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": {"yfinance": False, "finnhub": False},
        "estimates": {},
        "surprises": [],
        "ratings": {},
        "price_target": {},
        "eps_trend": {},
        "growth": {},
    }

    _collect_yfinance(ticker, result)
    _collect_finnhub(ticker, result)

    return result


def _collect_yfinance(ticker: str, result: dict):
    """Populate result dict with YFinance consensus data."""
    if yf is None:
        return
    try:
        t = yf.Ticker(ticker)
    except Exception:
        return

    result["source"]["yfinance"] = True

    # ── EPS estimates ──
    try:
        ee = t.earnings_estimate
        if ee is not None and not ee.empty:
            eps_rows = []
            for period in ee.index:
                row = ee.loc[period]
                eps_rows.append(
                    {
                        "period": str(period),
                        "eps_avg": _safe_float(row.get("avg")),
                        "eps_low": _safe_float(row.get("low")),
                        "eps_high": _safe_float(row.get("high")),
                        "eps_year_ago": _safe_float(row.get("yearAgoEps")),
                        "num_analysts": _safe_float(row.get("numberOfAnalysts")),
                        "growth": _safe_float(row.get("growth")),
                    }
                )
            result["estimates"]["eps"] = eps_rows
    except Exception:
        pass

    # ── Revenue estimates ──
    try:
        re_ = t.revenue_estimate
        if re_ is not None and not re_.empty:
            rev_rows = []
            for period in re_.index:
                row = re_.loc[period]
                rev_rows.append(
                    {
                        "period": str(period),
                        "rev_avg": _safe_float(row.get("avg")),
                        "rev_low": _safe_float(row.get("low")),
                        "rev_high": _safe_float(row.get("high")),
                        "rev_year_ago": _safe_float(row.get("yearAgoRevenue")),
                        "num_analysts": _safe_float(row.get("numberOfAnalysts")),
                        "growth": _safe_float(row.get("growth")),
                    }
                )
            result["estimates"]["revenue"] = rev_rows
    except Exception:
        pass

    # ── EPS trend (revision tracking) ──
    try:
        et = t.eps_trend
        if et is not None and not et.empty:
            trend_rows = []
            for period in et.index:
                row = et.loc[period]
                trend_rows.append(
                    {
                        "period": str(period),
                        "current": _safe_float(row.get("current")),
                        "7d_ago": _safe_float(row.get("7daysAgo")),
                        "30d_ago": _safe_float(row.get("30daysAgo")),
                        "60d_ago": _safe_float(row.get("60daysAgo")),
                        "90d_ago": _safe_float(row.get("90daysAgo")),
                    }
                )
            result["eps_trend"] = trend_rows
    except Exception:
        pass

    # ── Growth estimates ──
    try:
        ge = t.growth_estimates
        if ge is not None and not ge.empty:
            growth_rows = []
            for period in ge.index:
                row = ge.loc[period]
                growth_rows.append(
                    {
                        "period": str(period),
                        "stock": _safe_float(row.get("stockTrend")),
                        "index": _safe_float(row.get("indexTrend")),
                    }
                )
            result["growth"] = growth_rows
    except Exception:
        pass

    # ── Analyst price targets ──
    try:
        pt = t.analyst_price_targets
        if pt is not None:
            result["price_target"]["yf_current"] = _safe_float(pt.get("current"))
            result["price_target"]["yf_high"] = _safe_float(pt.get("high"))
            result["price_target"]["yf_low"] = _safe_float(pt.get("low"))
            result["price_target"]["yf_mean"] = _safe_float(pt.get("mean"))
            result["price_target"]["yf_median"] = _safe_float(pt.get("median"))
    except Exception:
        pass

    # ── Analyst ratings ──
    try:
        info = t.info or {}
        result["ratings"]["recommendation"] = info.get("recommendationKey", "")
        result["ratings"]["num_analysts"] = info.get("numberOfAnalystOpinions")

        rec = t.recommendations
        if rec is not None and not rec.empty:
            latest = rec.iloc[-1]
            breakdown = {}
            for col in rec.columns:
                if col.lower() != "period":
                    try:
                        breakdown[col] = int(latest[col])
                    except (ValueError, TypeError):
                        pass
            result["ratings"]["breakdown"] = breakdown
            result["ratings"]["period"] = str(latest.get("period", ""))
    except Exception:
        pass


def _collect_finnhub(ticker: str, result: dict):
    """Populate result dict with Finnhub data (complements YFinance)."""
    if not FINNHUB_API_KEY or not _requests:
        return

    result["source"]["finnhub"] = True
    symbol = ticker.upper()

    # ── Earnings surprises (Finnhub free tier) ──
    data = _finnhub_get("stock/earnings", {"symbol": symbol})
    if data and isinstance(data, list):
        surprises = []
        for e in data[:8]:
            surprises.append(
                {
                    "period": e.get("period", ""),
                    "actual": _safe_float(e.get("actual")),
                    "estimate": _safe_float(e.get("estimate")),
                    "surprise_pct": _safe_float(e.get("surprisePercent")),
                }
            )
        result["surprises"] = surprises

    # ── Analyst recommendations (Finnhub free tier) ──
    data = _finnhub_get("stock/recommendation", {"symbol": symbol})
    if data and isinstance(data, list) and len(data) > 0:
        latest = data[0]
        result["ratings"]["fh_period"] = latest.get("period", "")
        result["ratings"]["fh_strong_buy"] = latest.get("strongBuy", 0)
        result["ratings"]["fh_buy"] = latest.get("buy", 0)
        result["ratings"]["fh_hold"] = latest.get("hold", 0)
        result["ratings"]["fh_sell"] = latest.get("sell", 0)
        result["ratings"]["fh_strong_sell"] = latest.get("strongSell", 0)

        # Rating history for trend (last 3 months)
        if len(data) >= 3:
            result["ratings"]["fh_history"] = [
                {
                    "period": d.get("period", ""),
                    "strong_buy": d.get("strongBuy", 0),
                    "buy": d.get("buy", 0),
                    "hold": d.get("hold", 0),
                    "sell": d.get("sell", 0),
                    "strong_sell": d.get("strongSell", 0),
                }
                for d in data[:3]
            ]

    # ── Company news (last 7 days, top 5) ──
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    data = _finnhub_get(
        "company-news", {"symbol": symbol, "from": week_ago, "to": today}
    )
    if data and isinstance(data, list):
        result["news"] = [
            {
                "headline": n.get("headline", ""),
                "source": n.get("source", ""),
                "url": n.get("url", ""),
                "datetime": n.get("datetime", 0),
            }
            for n in data[:5]
        ]

    # ── EPS/Revenue estimates (may fail on free tier) ──
    for endpoint, key in [
        ("stock/eps-estimate", "fh_eps"),
        ("stock/revenue-estimate", "fh_revenue"),
    ]:
        data = _finnhub_get(endpoint, {"symbol": symbol})
        if data and isinstance(data, dict) and data.get("data"):
            rows = []
            for e in data["data"][:4]:
                rows.append(
                    {
                        "period": e.get("period", ""),
                        "avg": _safe_float(e.get("epsAvg") or e.get("revenueAvg")),
                        "high": _safe_float(e.get("epsHigh") or e.get("revenueHigh")),
                        "low": _safe_float(e.get("epsLow") or e.get("revenueLow")),
                        "num_analysts": _safe_float(e.get("numberAnalysts")),
                    }
                )
            result["estimates"][key] = rows


# ═══════════════════════════════════════════════════════════════
#  Markdown Rendering
# ═══════════════════════════════════════════════════════════════


def render_consensus_md(data: dict, sections: Optional[list[str]] = None) -> str:
    """Render consensus data as markdown. Sections: estimates, surprises, ratings, target, trend, growth, news."""
    all_sections = [
        "estimates",
        "surprises",
        "ratings",
        "target",
        "trend",
        "growth",
        "news",
    ]
    active = [s for s in all_sections if s in sections] if sections else all_sections

    lines = [f"## Consensus Data — {data['ticker']}"]
    sources = []
    if data["source"].get("yfinance"):
        sources.append("YFinance")
    if data["source"].get("finnhub"):
        sources.append("Finnhub")
    lines.append(f"Sources: {', '.join(sources)} | {data['timestamp']}")
    lines.append("")

    if "estimates" in active:
        lines.extend(_render_estimates(data))
    if "trend" in active:
        lines.extend(_render_eps_trend(data))
    if "surprises" in active:
        lines.extend(_render_surprises(data))
    if "ratings" in active:
        lines.extend(_render_ratings(data))
    if "target" in active:
        lines.extend(_render_price_target(data))
    if "growth" in active:
        lines.extend(_render_growth(data))
    if "news" in active:
        lines.extend(_render_news(data))

    return "\n".join(lines)


def _render_estimates(data: dict) -> list[str]:
    lines = ["### EPS Consensus"]
    eps = data["estimates"].get("eps", [])
    if eps:
        lines.append("")
        lines.append("| Period | EPS Est | Low | High | YoY | #Analysts |")
        lines.append("|--------|---------|-----|------|-----|-----------|")
        for e in eps:
            growth = _fmt_pct(e["growth"]) if e["growth"] is not None else "N/A"
            avg = f"${e['eps_avg']:.2f}" if e.get("eps_avg") is not None else "N/A"
            low = f"${e['eps_low']:.2f}" if e.get("eps_low") is not None else "N/A"
            high = f"${e['eps_high']:.2f}" if e.get("eps_high") is not None else "N/A"
            na = int(e["num_analysts"]) if e.get("num_analysts") else "N/A"
            lines.append(
                f"| {e['period']} | {avg} | {low} | {high} | {growth} | {na} |"
            )
    else:
        lines.append("No EPS estimate data available.")
    lines.append("")

    lines.append("### Revenue Consensus")
    rev = data["estimates"].get("revenue", [])
    if rev:
        lines.append("")
        lines.append("| Period | Rev Est | Low | High | YoY | #Analysts |")
        lines.append("|--------|---------|-----|------|-----|-----------|")
        for e in rev:
            growth = _fmt_pct(e["growth"]) if e["growth"] is not None else "N/A"
            avg = _fmt_num(e["rev_avg"]) if e["rev_avg"] else "N/A"
            low = _fmt_num(e["rev_low"]) if e["rev_low"] else "N/A"
            high = _fmt_num(e["rev_high"]) if e["rev_high"] else "N/A"
            lines.append(
                f"| {e['period']} | {avg} | {low} | {high} | {growth} "
                f"| {int(e['num_analysts']) if e['num_analysts'] else 'N/A'} |"
            )
    else:
        lines.append("No revenue estimate data available.")
    lines.append("")
    return lines


def _render_eps_trend(data: dict) -> list[str]:
    trend = data.get("eps_trend", [])
    if not trend:
        return []
    lines = ["### EPS Revision Trend"]
    lines.append("")
    lines.append(
        "| Period | Current | 7d Ago | 30d Ago | 60d Ago | 90d Ago | 90d Chg |"
    )
    lines.append(
        "|--------|---------|--------|---------|---------|---------|---------|"
    )
    for t in trend:
        cur = t.get("current")
        a90 = t.get("90d_ago")
        if cur is not None and a90 is not None and a90 != 0:
            chg_str = _fmt_pct((cur - a90) / abs(a90))
        else:
            chg_str = "N/A"
        vals = []
        vals.append(f"| {t['period']}")
        for key in ["current", "7d_ago", "30d_ago", "60d_ago", "90d_ago"]:
            v = t.get(key)
            vals.append(f"${v:.3f}" if v is not None else "N/A")
        vals.append(chg_str)
        lines.append(" | ".join(vals) + " |")
    lines.append("")
    return lines


def _render_surprises(data: dict) -> list[str]:
    surprises = data.get("surprises", [])
    if not surprises:
        return []
    lines = ["### Earnings Surprises (Finnhub)"]
    lines.append("")
    lines.append("| Quarter | Actual | Estimate | Surprise |")
    lines.append("|---------|--------|----------|----------|")
    for s in surprises:
        actual = f"${s['actual']:.2f}" if s["actual"] is not None else "N/A"
        est = f"${s['estimate']:.2f}" if s["estimate"] is not None else "N/A"
        surp = f"{s['surprise_pct']:+.1f}%" if s["surprise_pct"] is not None else "N/A"
        lines.append(f"| {s['period']} | {actual} | {est} | {surp} |")
    lines.append("")
    return lines


def _render_ratings(data: dict) -> list[str]:
    ratings = data.get("ratings", {})
    if not ratings:
        return []
    lines = ["### Analyst Ratings"]
    lines.append("")

    rec = ratings.get("recommendation", "")
    num = ratings.get("num_analysts", "N/A")
    lines.append(
        f"**Recommendation:** {rec.upper() if rec else 'N/A'} ({num} analysts)"
    )
    lines.append("")

    # Finnhub breakdown (more granular)
    if ratings.get("fh_strong_buy") is not None:
        total = sum(
            [
                ratings.get("fh_strong_buy", 0),
                ratings.get("fh_buy", 0),
                ratings.get("fh_hold", 0),
                ratings.get("fh_sell", 0),
                ratings.get("fh_strong_sell", 0),
            ]
        )
        lines.append("| Rating | Count | % |")
        lines.append("|--------|-------|---|")
        for label, key in [
            ("Strong Buy", "fh_strong_buy"),
            ("Buy", "fh_buy"),
            ("Hold", "fh_hold"),
            ("Sell", "fh_sell"),
            ("Strong Sell", "fh_strong_sell"),
        ]:
            cnt = ratings.get(key, 0)
            pct = f"{cnt / total * 100:.0f}%" if total > 0 else "N/A"
            lines.append(f"| {label} | {cnt} | {pct} |")
        lines.append(f"| **Total** | **{total}** | |")
        if ratings.get("fh_period"):
            lines.append(f"\n_Period: {ratings['fh_period']}_")
    elif ratings.get("breakdown"):
        bd = ratings["breakdown"]
        lines.append("| Rating | Count |")
        lines.append("|--------|-------|")
        for k, v in bd.items():
            lines.append(f"| {k} | {v} |")

    lines.append("")
    return lines


def _render_price_target(data: dict) -> list[str]:
    pt = data.get("price_target", {})
    if not pt:
        return []
    lines = ["### Price Target Consensus"]
    lines.append("")
    current = pt.get("yf_current")
    mean = pt.get("yf_mean")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(
        f"| Current Price | ${current:.2f} |" if current else "| Current Price | N/A |"
    )
    lines.append(f"| Mean Target | ${mean:.2f} |" if mean else "| Mean Target | N/A |")
    lines.append(
        f"| Median Target | ${pt.get('yf_median', 0):.2f} |"
        if pt.get("yf_median")
        else "| Median Target | N/A |"
    )
    lines.append(
        f"| High | ${pt.get('yf_high', 0):.2f} |"
        if pt.get("yf_high")
        else "| High | N/A |"
    )
    lines.append(
        f"| Low | ${pt.get('yf_low', 0):.2f} |" if pt.get("yf_low") else "| Low | N/A |"
    )
    if current and mean:
        upside = (mean - current) / current
        lines.append(f"| **Implied Upside** | **{_fmt_pct(upside)}** |")
    lines.append("")
    return lines


def _render_growth(data: dict) -> list[str]:
    growth = data.get("growth", [])
    if not growth:
        return []
    lines = ["### Growth Estimates"]
    lines.append("")
    lines.append("| Period | Stock | Index | vs Index |")
    lines.append("|--------|-------|-------|----------|")
    for g in growth:
        stock = _fmt_pct(g["stock"]) if g["stock"] is not None else "N/A"
        index = _fmt_pct(g["index"]) if g["index"] is not None else "N/A"
        if g["stock"] is not None and g["index"] is not None:
            diff = g["stock"] - g["index"]
            vs = _fmt_pct(diff)
        else:
            vs = "N/A"
        lines.append(f"| {g['period']} | {stock} | {index} | {vs} |")
    lines.append("")
    return lines


def _render_news(data: dict) -> list[str]:
    news = data.get("news", [])
    if not news:
        return []
    lines = ["### Recent News (Finnhub)"]
    lines.append("")
    for n in news:
        lines.append(f"- [{n['source']}] {n['headline']}")
    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
#  Consensus History Tracking
# ═══════════════════════════════════════════════════════════════

HISTORY_DIR = Path.home() / ".claude" / "data" / "consensus_history"


def save_snapshot(data: dict) -> Path:
    """Save consensus snapshot to JSONL history file. One file per ticker."""
    from jsonl_utils import safe_jsonl_append

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ticker = data["ticker"].upper()
    path = HISTORY_DIR / f"{ticker}.jsonl"
    safe_jsonl_append(path, data)
    return path


def load_history(ticker: str) -> list[dict]:
    """Load all snapshots for a ticker, sorted by timestamp."""
    path = HISTORY_DIR / f"{ticker.upper()}.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: r.get("timestamp", ""))
    return rows


def get_consensus_with_history(ticker: str) -> tuple[dict, Optional[dict]]:
    """Fetch current consensus, save it, and return (current, previous_snapshot)."""
    current = get_consensus(ticker)
    history = load_history(ticker)
    save_snapshot(current)

    # Find previous snapshot (at least 1 day older)
    prev = None
    cur_date = current["timestamp"][:10]
    for snap in reversed(history):
        snap_date = snap.get("timestamp", "")[:10]
        if snap_date < cur_date:
            prev = snap
            break

    return current, prev


def diff_consensus(current: dict, previous: dict) -> dict:
    """Compare two consensus snapshots and return changes."""
    changes = {
        "ticker": current["ticker"],
        "current_date": current["timestamp"][:10],
        "previous_date": previous["timestamp"][:10],
        "eps_changes": [],
        "revenue_changes": [],
        "rating_change": None,
        "pt_change": None,
    }

    # ── EPS estimate changes ──
    cur_eps = {e["period"]: e for e in current.get("estimates", {}).get("eps", [])}
    prev_eps = {e["period"]: e for e in previous.get("estimates", {}).get("eps", [])}
    for period in cur_eps:
        if period in prev_eps:
            c_avg = cur_eps[period].get("eps_avg")
            p_avg = prev_eps[period].get("eps_avg")
            if c_avg is not None and p_avg is not None and p_avg != 0:
                chg = c_avg - p_avg
                chg_pct = chg / abs(p_avg)
                if abs(chg_pct) > 0.001:  # >0.1% change
                    changes["eps_changes"].append(
                        {
                            "period": period,
                            "prev": p_avg,
                            "curr": c_avg,
                            "delta": chg,
                            "delta_pct": chg_pct,
                        }
                    )

    # ── Revenue estimate changes ──
    cur_rev = {e["period"]: e for e in current.get("estimates", {}).get("revenue", [])}
    prev_rev = {
        e["period"]: e for e in previous.get("estimates", {}).get("revenue", [])
    }
    for period in cur_rev:
        if period in prev_rev:
            c_avg = cur_rev[period].get("rev_avg")
            p_avg = prev_rev[period].get("rev_avg")
            if c_avg is not None and p_avg is not None and p_avg != 0:
                chg = c_avg - p_avg
                chg_pct = chg / abs(p_avg)
                if abs(chg_pct) > 0.001:
                    changes["revenue_changes"].append(
                        {
                            "period": period,
                            "prev": p_avg,
                            "curr": c_avg,
                            "delta": chg,
                            "delta_pct": chg_pct,
                        }
                    )

    # ── Rating change ──
    cur_rec = current.get("ratings", {}).get("recommendation", "")
    prev_rec = previous.get("ratings", {}).get("recommendation", "")
    if cur_rec and prev_rec and cur_rec != prev_rec:
        changes["rating_change"] = {"prev": prev_rec, "curr": cur_rec}

    # ── Price target change ──
    cur_pt = current.get("price_target", {}).get("yf_mean")
    prev_pt = previous.get("price_target", {}).get("yf_mean")
    if cur_pt and prev_pt and cur_pt != prev_pt:
        changes["pt_change"] = {
            "prev": prev_pt,
            "curr": cur_pt,
            "delta": cur_pt - prev_pt,
            "delta_pct": (cur_pt - prev_pt) / prev_pt,
        }

    return changes


def render_diff_md(changes: dict) -> str:
    """Render consensus diff as markdown."""
    lines = [f"### Consensus Changes — {changes['ticker']}"]
    lines.append(f"_{changes['previous_date']} → {changes['current_date']}_")
    lines.append("")

    has_changes = False

    # EPS
    if changes["eps_changes"]:
        has_changes = True
        lines.append("**EPS Estimate Revisions:**")
        lines.append("| Period | Previous | Current | Change |")
        lines.append("|--------|----------|---------|--------|")
        for c in changes["eps_changes"]:
            direction = "UP" if c["delta"] > 0 else "DOWN"
            lines.append(
                f"| {c['period']} | ${c['prev']:.2f} | ${c['curr']:.2f} "
                f"| {_fmt_pct(c['delta_pct'])} {direction} |"
            )
        lines.append("")

    # Revenue
    if changes["revenue_changes"]:
        has_changes = True
        lines.append("**Revenue Estimate Revisions:**")
        lines.append("| Period | Previous | Current | Change |")
        lines.append("|--------|----------|---------|--------|")
        for c in changes["revenue_changes"]:
            direction = "UP" if c["delta"] > 0 else "DOWN"
            lines.append(
                f"| {c['period']} | {_fmt_num(c['prev'])} | {_fmt_num(c['curr'])} "
                f"| {_fmt_pct(c['delta_pct'])} {direction} |"
            )
        lines.append("")

    # Rating
    if changes["rating_change"]:
        has_changes = True
        rc = changes["rating_change"]
        lines.append(f"**Rating Change:** {rc['prev']} → **{rc['curr']}**")
        lines.append("")

    # Price target
    if changes["pt_change"]:
        has_changes = True
        pt = changes["pt_change"]
        lines.append(
            f"**Mean Price Target:** ${pt['prev']:.2f} → ${pt['curr']:.2f} "
            f"({_fmt_pct(pt['delta_pct'])})"
        )
        lines.append("")

    if not has_changes:
        lines.append("_No material changes since last snapshot._")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Downgrade Detection & Alerts
# ═══════════════════════════════════════════════════════════════

# Severity thresholds (absolute % change)
_THRESH_CRITICAL = 0.15  # >15% revision
_THRESH_WARNING = 0.07   # >7% revision
_THRESH_WATCH = 0.03     # >3% revision

# Rating hierarchy (lower = more bearish)
_RATING_RANK = {
    "strong_buy": 5,
    "strongbuy": 5,
    "buy": 4,
    "overweight": 3.5,
    "outperform": 3.5,
    "hold": 3,
    "neutral": 3,
    "underweight": 2.5,
    "underperform": 2.5,
    "sell": 2,
    "strong_sell": 1,
    "strongsell": 1,
}


def _classify_severity(pct_change: float) -> str:
    """Classify negative revision severity. pct_change should be negative."""
    mag = abs(pct_change)
    if mag >= _THRESH_CRITICAL:
        return "CRITICAL"
    if mag >= _THRESH_WARNING:
        return "WARNING"
    if mag >= _THRESH_WATCH:
        return "WATCH"
    return ""


def detect_changes(data: dict, prev: Optional[dict] = None) -> dict:
    """Detect material consensus changes (upgrades and downgrades).

    Returns:
        {
            "ticker": str,
            "severity": str,  # worst severity across all signals
            "signals": [
                {
                    "type": str,  # eps_trend, eps_revision, rev_revision, pt_change, rating_change
                    "period": str,
                    "detail": str,
                    "severity": str,
                    "magnitude": float,  # negative = downgrade, positive = upgrade
                    "direction": str,  # "UP" or "DOWN"
                },
                ...
            ],
        }
    """
    ticker = data["ticker"]
    signals = []

    # ── 1. EPS Trend (single-snapshot — YFinance embeds 7d/30d/60d/90d) ──
    for t in data.get("eps_trend", []):
        cur = t.get("current")
        for lookback, label in [
            ("30d_ago", "30d"),
            ("60d_ago", "60d"),
            ("90d_ago", "90d"),
        ]:
            ago = t.get(lookback)
            if cur is not None and ago is not None and ago != 0:
                chg_pct = (cur - ago) / abs(ago)
                if abs(chg_pct) > _THRESH_WATCH:
                    sev = _classify_severity(chg_pct)
                    if sev:
                        direction = "UP" if chg_pct > 0 else "DOWN"
                        cur_str = f"${cur:.3f}"
                        ago_str = f"${ago:.3f}"
                        signals.append(
                            {
                                "type": "eps_trend",
                                "period": t["period"],
                                "detail": f"EPS {t['period']} revised {chg_pct * 100:+.1f}% over {label} ({ago_str} → {cur_str})",
                                "severity": sev,
                                "magnitude": chg_pct,
                                "direction": direction,
                            }
                        )
                    break  # only report longest significant lookback per period

    # ── 2. Cross-snapshot diffs (if previous available) ──
    if prev:
        diff = diff_consensus(data, prev)
        days_gap = diff["current_date"], diff["previous_date"]

        # EPS revisions
        for c in diff.get("eps_changes", []):
            if abs(c["delta_pct"]) > _THRESH_WATCH:
                sev = _classify_severity(c["delta_pct"])
                if sev:
                    direction = "UP" if c["delta_pct"] > 0 else "DOWN"
                    signals.append(
                        {
                            "type": "eps_revision",
                            "period": c["period"],
                            "detail": f"EPS {c['period']} consensus {direction}: ${c['prev']:.2f} → ${c['curr']:.2f} ({c['delta_pct'] * 100:+.1f}%)",
                            "severity": sev,
                            "magnitude": c["delta_pct"],
                            "direction": direction,
                        }
                    )

        # Revenue revisions
        for c in diff.get("revenue_changes", []):
            if abs(c["delta_pct"]) > _THRESH_WATCH:
                sev = _classify_severity(c["delta_pct"])
                if sev:
                    direction = "UP" if c["delta_pct"] > 0 else "DOWN"
                    signals.append(
                        {
                            "type": "rev_revision",
                            "period": c["period"],
                            "detail": f"Revenue {c['period']} consensus {direction}: {_fmt_num(c['prev'])} → {_fmt_num(c['curr'])} ({c['delta_pct'] * 100:+.1f}%)",
                            "severity": sev,
                            "magnitude": c["delta_pct"],
                            "direction": direction,
                        }
                    )

        # Price target change
        pt = diff.get("pt_change")
        if pt and abs(pt["delta_pct"]) > _THRESH_WATCH:
            sev = _classify_severity(pt["delta_pct"])
            if sev:
                direction = "UP" if pt["delta_pct"] > 0 else "DOWN"
                signals.append(
                    {
                        "type": "pt_change",
                        "period": "",
                        "detail": f"Mean PT {direction}: ${pt['prev']:.0f} → ${pt['curr']:.0f} ({pt['delta_pct'] * 100:+.1f}%)",
                        "severity": sev,
                        "magnitude": pt["delta_pct"],
                        "direction": direction,
                    }
                )

        # Rating change
        rc = diff.get("rating_change")
        if rc:
            prev_rank = _RATING_RANK.get(rc["prev"].lower(), 3)
            curr_rank = _RATING_RANK.get(rc["curr"].lower(), 3)
            if curr_rank != prev_rank:
                direction = "UP" if curr_rank > prev_rank else "DOWN"
                signals.append(
                    {
                        "type": "rating_change",
                        "period": "",
                        "detail": f"Rating {direction}: {rc['prev']} → {rc['curr']}",
                        "severity": "WARNING",
                        "magnitude": curr_rank - prev_rank,
                        "direction": direction,
                    }
                )

    # Deduplicate: prefer cross-snapshot over trend for same period
    seen_periods = set()
    deduped = []
    # Cross-snapshot signals first (more precise)
    for s in signals:
        if s["type"] in ("eps_revision", "rev_revision", "pt_change", "rating_change"):
            key = (s["type"], s["period"])
            seen_periods.add(key)
            deduped.append(s)
    for s in signals:
        if s["type"] == "eps_trend":
            key = ("eps_revision", s["period"])
            if key not in seen_periods:
                deduped.append(s)

    # Determine worst severity
    severity_order = {"CRITICAL": 3, "WARNING": 2, "WATCH": 1, "": 0}
    worst = max((severity_order.get(s["severity"], 0) for s in deduped), default=0)
    worst_label = {3: "CRITICAL", 2: "WARNING", 1: "WATCH", 0: ""}[worst]

    return {
        "ticker": ticker,
        "severity": worst_label,
        "signals": sorted(
            deduped, key=lambda s: severity_order.get(s["severity"], 0), reverse=True
        ),
    }


# Backward compatibility alias
detect_downgrades = detect_changes


def scan_portfolio_changes(
    tickers: list[str],
    track: bool = True,
) -> list[dict]:
    """Scan multiple tickers for material consensus changes.

    Args:
        tickers: List of ticker symbols
        track: If True, save snapshots and diff vs previous

    Returns:
        List of alert dicts (only tickers WITH downgrades), sorted by severity.
    """
    alerts = []
    for ticker in tickers:
        try:
            if track:
                current, prev = get_consensus_with_history(ticker)
            else:
                current = get_consensus(ticker)
                prev = None

            result = detect_changes(current, prev)
            if result["signals"]:
                alerts.append(result)
        except Exception:
            continue

    severity_order = {"CRITICAL": 3, "WARNING": 2, "WATCH": 1, "": 0}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 0), reverse=True)
    return alerts


# Backward compatibility alias
scan_portfolio_downgrades = scan_portfolio_changes


def render_alerts_md(alerts: list[dict]) -> str:
    """Render consensus change alerts as attention-grabbing markdown."""
    if not alerts:
        return ""

    severity_icon = {"CRITICAL": "🔴", "WARNING": "🟡", "WATCH": "🔵"}
    lines = ["## ⚠️ Consensus 变动预警\n"]

    for alert in alerts:
        icon = severity_icon.get(alert["severity"], "")
        lines.append(f"### {icon} {alert['ticker']} — {alert['severity']}")
        lines.append("")
        for s in alert["signals"]:
            arrow = "⬆" if s.get("direction") == "UP" else "⬇" if s.get("direction") == "DOWN" else ""
            s_icon = severity_icon.get(s["severity"], "")
            lines.append(f"- {s_icon} {arrow} {s['detail']}")
        lines.append("")

    # Summary line
    crit = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    warn = sum(1 for a in alerts if a["severity"] == "WARNING")
    watch = sum(1 for a in alerts if a["severity"] == "WATCH")
    parts = []
    if crit:
        parts.append(f"🔴 {crit} CRITICAL")
    if warn:
        parts.append(f"🟡 {warn} WARNING")
    if watch:
        parts.append(f"🔵 {watch} WATCH")
    lines.append(f"**Summary:** {' | '.join(parts)}")
    lines.append("")

    return "\n".join(lines)


def _notify_alerts(alerts: list[dict]) -> bool:
    """Push consensus change alerts to Telegram if CRITICAL or WARNING found. Best-effort."""
    serious = [a for a in alerts if a["severity"] in ("CRITICAL", "WARNING")]
    if not serious:
        return False
    try:
        from shared.telegram_notify import notify

        icons = {"CRITICAL": "🔴", "WARNING": "🟡", "WATCH": "🔵"}
        lines = ["⚠️ *Consensus 变动预警*\n"]
        for a in serious:
            lines.append(
                f"{icons.get(a['severity'], '')} *{a['ticker']}* — {a['severity']}"
            )
            for s in a["signals"]:
                arrow = "⬆" if s.get("direction") == "UP" else "⬇" if s.get("direction") == "DOWN" else ""
                lines.append(f"  {arrow} {s['detail']}")
            lines.append("")

        crit = sum(1 for a in serious if a["severity"] == "CRITICAL")
        warn = sum(1 for a in serious if a["severity"] == "WARNING")
        parts = []
        if crit:
            parts.append(f"🔴 {crit} CRITICAL")
        if warn:
            parts.append(f"🟡 {warn} WARNING")
        lines.append(" | ".join(parts))

        ok = notify("\n".join(lines))
        if ok:
            print("Telegram notification sent.")
        return ok
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Consensus estimates aggregator")
    parser.add_argument("tickers", nargs="+", help="Ticker symbol(s)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument(
        "--section",
        nargs="*",
        choices=[
            "estimates",
            "surprises",
            "ratings",
            "target",
            "trend",
            "growth",
            "news",
        ],
        help="Only show specific sections",
    )
    parser.add_argument(
        "--track", action="store_true", help="Save snapshot and show changes vs last"
    )
    parser.add_argument(
        "--history", action="store_true", help="Show all saved snapshots for ticker"
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Only show change alerts (skip full report)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Telegram alert if any CRITICAL/WARNING found",
    )
    args = parser.parse_args()

    # ── Alert-only mode: scan for downgrades ──
    if args.alert:
        alerts = scan_portfolio_downgrades(args.tickers, track=args.track)
        if alerts:
            md = render_alerts_md(alerts)
            print(md)
            if args.notify:
                _notify_alerts(alerts)
        else:
            print(
                f"No consensus changes detected for {', '.join(t.upper() for t in args.tickers)}"
            )
        return

    for ticker in args.tickers:
        if args.history:
            hist = load_history(ticker)
            if not hist:
                print(f"No history for {ticker.upper()}")
            else:
                print(f"## {ticker.upper()} — {len(hist)} snapshots")
                print("| Date | EPS (0q) | EPS (0y) | Rev (0y) | PT Mean | Rating |")
                print("|------|----------|----------|----------|---------|--------|")
                for snap in hist:
                    date = snap["timestamp"][:10]
                    eps_0q = "N/A"
                    eps_0y = "N/A"
                    rev_0y = "N/A"
                    for e in snap.get("estimates", {}).get("eps", []):
                        if e["period"] == "0q":
                            eps_0q = (
                                f"${e['eps_avg']:.2f}" if e.get("eps_avg") else "N/A"
                            )
                        if e["period"] == "0y":
                            eps_0y = (
                                f"${e['eps_avg']:.2f}" if e.get("eps_avg") else "N/A"
                            )
                    for e in snap.get("estimates", {}).get("revenue", []):
                        if e["period"] == "0y":
                            rev_0y = (
                                _fmt_num(e["rev_avg"]) if e.get("rev_avg") else "N/A"
                            )
                    pt = snap.get("price_target", {})
                    pt_mean = f"${pt['yf_mean']:.0f}" if pt.get("yf_mean") else "N/A"
                    rating = snap.get("ratings", {}).get("recommendation", "N/A")
                    print(
                        f"| {date} | {eps_0q} | {eps_0y} | {rev_0y} | {pt_mean} | {rating} |"
                    )
            continue

        if args.track:
            current, prev = get_consensus_with_history(ticker)
            md = render_consensus_md(current, sections=args.section)
            print(md)
            if prev:
                diff = diff_consensus(current, prev)
                print(render_diff_md(diff))
            else:
                print("_First snapshot saved. Run again later to see changes._")
            # Always check for downgrades
            alert = detect_changes(current, prev)
            if alert["signals"]:
                print(render_alerts_md([alert]))
        elif args.json:
            data = get_consensus(ticker)
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        else:
            data = get_consensus(ticker)
            md = render_consensus_md(data, sections=args.section)
            print(md)

        if len(args.tickers) > 1:
            print("\n---\n")


if __name__ == "__main__":
    main()
