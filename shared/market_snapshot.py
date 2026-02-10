"""Market Data Snapshot — yfinance wrapper for /research skill.

Pulls price, financials, analyst consensus, insider activity, and
institutional holders for a given ticker.  Outputs a structured markdown
block that slots directly into research reports.

Usage:
    python market_snapshot.py TICKER              # full snapshot
    python market_snapshot.py TICKER --section price
    python market_snapshot.py TICKER --section financials
    python market_snapshot.py TICKER --section analysts
    python market_snapshot.py TICKER --section insiders
    python market_snapshot.py TICKER --section institutions
    python market_snapshot.py TICKER --json       # machine-readable
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Encoding fix for Windows GBK console ──
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance is required.  pip install yfinance", file=sys.stderr)
    sys.exit(1)


# ── Helpers ──────────────────────────────────────────────────

def _fmt_num(n, decimals=2) -> str:
    """Format number with magnitude suffix (B/M/K)."""
    if n is None:
        return "N/A"
    if abs(n) >= 1e9:
        return f"{n / 1e9:,.{decimals}f}B"
    if abs(n) >= 1e6:
        return f"{n / 1e6:,.{decimals}f}M"
    if abs(n) >= 1e3:
        return f"{n / 1e3:,.{decimals}f}K"
    return f"{n:,.{decimals}f}"


def _fmt_pct(n) -> str:
    if n is None:
        return "N/A"
    return f"{n * 100:.1f}%"


def _safe(info: dict, key: str, default=None):
    """Get value from info dict, treating 0 as valid."""
    v = info.get(key, default)
    if v is None:
        return default
    return v


# ── Data Collection ──────────────────────────────────────────

def get_snapshot(ticker_str: str) -> dict:
    """Collect all market data for a ticker. Returns structured dict."""
    t = yf.Ticker(ticker_str)
    info = {}
    try:
        info = t.info or {}
    except Exception as e:
        print(f"Warning: could not fetch info: {e}", file=sys.stderr)

    result = {
        "ticker": ticker_str.upper(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "price": _collect_price(info),
        "financials": _collect_financials(info),
        "analysts": _collect_analysts(info, t),
        "insiders": _collect_insiders(t),
        "institutions": _collect_institutions(t),
        "profile": _collect_profile(info),
    }
    return result


def _collect_price(info: dict) -> dict:
    return {
        "current": _safe(info, "currentPrice") or _safe(info, "regularMarketPrice"),
        "previous_close": _safe(info, "previousClose") or _safe(info, "regularMarketPreviousClose"),
        "open": _safe(info, "open") or _safe(info, "regularMarketOpen"),
        "day_high": _safe(info, "dayHigh") or _safe(info, "regularMarketDayHigh"),
        "day_low": _safe(info, "dayLow") or _safe(info, "regularMarketDayLow"),
        "52w_high": _safe(info, "fiftyTwoWeekHigh"),
        "52w_low": _safe(info, "fiftyTwoWeekLow"),
        "50d_ma": _safe(info, "fiftyDayAverage"),
        "200d_ma": _safe(info, "twoHundredDayAverage"),
        "market_cap": _safe(info, "marketCap"),
        "volume": _safe(info, "volume") or _safe(info, "regularMarketVolume"),
        "avg_volume": _safe(info, "averageVolume"),
        "currency": _safe(info, "currency", "USD"),
        "exchange": _safe(info, "exchange"),
    }


def _collect_financials(info: dict) -> dict:
    return {
        "pe_trailing": _safe(info, "trailingPE"),
        "pe_forward": _safe(info, "forwardPE"),
        "peg": _safe(info, "pegRatio"),
        "pb": _safe(info, "priceToBook"),
        "ps": _safe(info, "priceToSalesTrailing12Months"),
        "ev_ebitda": _safe(info, "enterpriseToEbitda"),
        "eps_trailing": _safe(info, "trailingEps"),
        "eps_forward": _safe(info, "forwardEps"),
        "revenue": _safe(info, "totalRevenue"),
        "revenue_growth": _safe(info, "revenueGrowth"),
        "gross_margin": _safe(info, "grossMargins"),
        "operating_margin": _safe(info, "operatingMargins"),
        "profit_margin": _safe(info, "profitMargins"),
        "roe": _safe(info, "returnOnEquity"),
        "roa": _safe(info, "returnOnAssets"),
        "debt_to_equity": _safe(info, "debtToEquity"),
        "current_ratio": _safe(info, "currentRatio"),
        "free_cashflow": _safe(info, "freeCashflow"),
        "dividend_yield": _safe(info, "dividendYield"),
        "payout_ratio": _safe(info, "payoutRatio"),
        "beta": _safe(info, "beta"),
    }


def _collect_analysts(info: dict, ticker_obj) -> dict:
    result = {
        "target_high": _safe(info, "targetHighPrice"),
        "target_low": _safe(info, "targetLowPrice"),
        "target_mean": _safe(info, "targetMeanPrice"),
        "target_median": _safe(info, "targetMedianPrice"),
        "recommendation": _safe(info, "recommendationKey"),
        "num_analysts": _safe(info, "numberOfAnalystOpinions"),
        "ratings_breakdown": {},
    }
    try:
        rec = ticker_obj.recommendations
        if rec is not None and not rec.empty:
            # Get the most recent period's breakdown
            latest = rec.iloc[-1] if len(rec) > 0 else None
            if latest is not None:
                for col in rec.columns:
                    val = latest.get(col)
                    if val is not None and col.lower() != "period":
                        try:
                            result["ratings_breakdown"][col] = int(val)
                        except (ValueError, TypeError):
                            pass
    except Exception:
        pass
    return result


def _collect_insiders(ticker_obj) -> list:
    rows = []
    try:
        txns = ticker_obj.insider_transactions
        if txns is not None and not txns.empty:
            for _, row in txns.head(10).iterrows():
                rows.append({
                    "name": str(row.get("Insider", row.get("insider", ""))),
                    "relation": str(row.get("Position", row.get("position", ""))),
                    "transaction": str(row.get("Transaction", row.get("transaction", ""))),
                    "date": str(row.get("Start Date", row.get("startDate", ""))),
                    "shares": row.get("Shares", row.get("shares")),
                    "value": row.get("Value", row.get("value")),
                })
    except Exception:
        pass
    return rows


def _collect_institutions(ticker_obj) -> list:
    rows = []
    try:
        holders = ticker_obj.institutional_holders
        if holders is not None and not holders.empty:
            for _, row in holders.head(10).iterrows():
                rows.append({
                    "holder": str(row.get("Holder", "")),
                    "shares": row.get("Shares", row.get("shares")),
                    "value": row.get("Value", row.get("value")),
                    "pct_out": row.get("pctHeld", row.get("% Out")),
                    "date": str(row.get("Date Reported", "")),
                })
    except Exception:
        pass
    return rows


def _collect_profile(info: dict) -> dict:
    return {
        "name": _safe(info, "longName") or _safe(info, "shortName", ""),
        "sector": _safe(info, "sector", ""),
        "industry": _safe(info, "industry", ""),
        "country": _safe(info, "country", ""),
        "employees": _safe(info, "fullTimeEmployees"),
        "summary": _safe(info, "longBusinessSummary", ""),
        "website": _safe(info, "website", ""),
    }


# ── Markdown Rendering ───────────────────────────────────────

def render_markdown(data: dict, sections: list[str] | None = None) -> str:
    """Render snapshot as markdown. If sections given, only those."""
    all_sections = ["price", "financials", "analysts", "insiders", "institutions"]
    if sections:
        active = [s for s in all_sections if s in sections]
    else:
        active = all_sections

    lines = [f"## 📊 市场数据快照 — {data['ticker']}"]
    lines.append(f"*{data['profile']['name']}* | {data['profile']['sector']} > {data['profile']['industry']} | {data['profile']['country']}")
    lines.append(f"数据时间: {data['timestamp']}")
    lines.append("")

    if "price" in active:
        lines.extend(_render_price(data["price"]))
    if "financials" in active:
        lines.extend(_render_financials(data["financials"]))
    if "analysts" in active:
        lines.extend(_render_analysts(data["analysts"], data["price"]))
    if "insiders" in active:
        lines.extend(_render_insiders(data["insiders"]))
    if "institutions" in active:
        lines.extend(_render_institutions(data["institutions"]))

    return "\n".join(lines)


def _render_price(p: dict) -> list[str]:
    cur = p.get("currency", "USD")
    current = p.get("current")
    prev = p.get("previous_close")
    chg = ""
    if current and prev:
        diff = current - prev
        pct = diff / prev * 100
        arrow = "+" if diff >= 0 else ""
        chg = f" ({arrow}{diff:.2f}, {arrow}{pct:.2f}%)"

    lines = ["### 价格与交易"]
    lines.append(f"| 指标 | 值 ({cur}) |")
    lines.append("|------|------|")
    lines.append(f"| 现价 | **{_fmt_num(current, 2)}**{chg} |")
    lines.append(f"| 今日区间 | {_fmt_num(p.get('day_low'), 2)} — {_fmt_num(p.get('day_high'), 2)} |")
    lines.append(f"| 52 周区间 | {_fmt_num(p.get('52w_low'), 2)} — {_fmt_num(p.get('52w_high'), 2)} |")
    lines.append(f"| 50 日均线 | {_fmt_num(p.get('50d_ma'), 2)} |")
    lines.append(f"| 200 日均线 | {_fmt_num(p.get('200d_ma'), 2)} |")
    lines.append(f"| 总市值 | {_fmt_num(p.get('market_cap'))} |")
    lines.append(f"| 成交量 / 均量 | {_fmt_num(p.get('volume'), 0)} / {_fmt_num(p.get('avg_volume'), 0)} |")

    # Position vs 52w range
    high = p.get("52w_high")
    low = p.get("52w_low")
    if current and high and low and high != low:
        pct_range = (current - low) / (high - low) * 100
        lines.append(f"| 52 周位置 | {pct_range:.0f}% (0%=最低, 100%=最高) |")

    lines.append("")
    return lines


def _render_financials(f: dict) -> list[str]:
    lines = ["### 关键财务指标"]
    lines.append("| 估值 | 值 | 盈利能力 | 值 |")
    lines.append("|------|------|----------|------|")
    lines.append(f"| P/E (TTM) | {_fmt_num(f.get('pe_trailing'))} | 毛利率 | {_fmt_pct(f.get('gross_margin'))} |")
    lines.append(f"| P/E (Fwd) | {_fmt_num(f.get('pe_forward'))} | 营业利润率 | {_fmt_pct(f.get('operating_margin'))} |")
    lines.append(f"| PEG | {_fmt_num(f.get('peg'))} | 净利率 | {_fmt_pct(f.get('profit_margin'))} |")
    lines.append(f"| P/B | {_fmt_num(f.get('pb'))} | ROE | {_fmt_pct(f.get('roe'))} |")
    lines.append(f"| EV/EBITDA | {_fmt_num(f.get('ev_ebitda'))} | ROA | {_fmt_pct(f.get('roa'))} |")
    lines.append("")

    lines.append("| 增长与现金流 | 值 | 风险 | 值 |")
    lines.append("|------------|------|------|------|")
    lines.append(f"| 营收 | {_fmt_num(f.get('revenue'))} | Beta | {_fmt_num(f.get('beta'))} |")
    lines.append(f"| 营收增速 | {_fmt_pct(f.get('revenue_growth'))} | D/E | {_fmt_num(f.get('debt_to_equity'))} |")
    lines.append(f"| EPS (TTM) | {_fmt_num(f.get('eps_trailing'))} | 流动比率 | {_fmt_num(f.get('current_ratio'))} |")
    lines.append(f"| EPS (Fwd) | {_fmt_num(f.get('eps_forward'))} | 股息率 | {_fmt_pct(f.get('dividend_yield'))} |")
    lines.append(f"| 自由现金流 | {_fmt_num(f.get('free_cashflow'))} | 派息比率 | {_fmt_pct(f.get('payout_ratio'))} |")
    lines.append("")
    return lines


def _render_analysts(a: dict, price: dict) -> list[str]:
    lines = ["### 分析师共识"]
    rec = a.get("recommendation", "N/A")
    num = a.get("num_analysts")
    num_str = f" ({num} 位分析师)" if num else ""

    lines.append(f"**共识评级: {rec.upper() if isinstance(rec, str) else rec}**{num_str}")
    lines.append("")

    target_mean = a.get("target_mean")
    current = price.get("current")
    upside = ""
    if target_mean and current and current > 0:
        pct = (target_mean - current) / current * 100
        upside = f" ({'↑' if pct >= 0 else '↓'}{abs(pct):.1f}%)"

    lines.append(f"| 目标价 | 值 |")
    lines.append("|--------|------|")
    lines.append(f"| 最高 | {_fmt_num(a.get('target_high'), 2)} |")
    lines.append(f"| 均值 | **{_fmt_num(target_mean, 2)}**{upside} |")
    lines.append(f"| 中位数 | {_fmt_num(a.get('target_median'), 2)} |")
    lines.append(f"| 最低 | {_fmt_num(a.get('target_low'), 2)} |")
    lines.append("")

    bd = a.get("ratings_breakdown", {})
    if bd:
        lines.append("评级分布:")
        for k, v in bd.items():
            lines.append(f"  - {k}: {v}")
        lines.append("")
    return lines


def _render_insiders(insiders: list) -> list[str]:
    lines = ["### 内部人交易 (近期)"]
    if not insiders:
        lines.append("*无近期内部人交易数据*")
        lines.append("")
        return lines

    lines.append("| 日期 | 姓名 | 职位 | 交易类型 | 股数 | 金额 |")
    lines.append("|------|------|------|----------|------|------|")
    for row in insiders:
        date_str = str(row.get("date", ""))[:10]
        name = row.get("name", "")[:20]
        rel = row.get("relation", "")[:15]
        txn = row.get("transaction", "")
        shares = _fmt_num(row.get("shares"), 0) if row.get("shares") else "N/A"
        val = _fmt_num(row.get("value"), 0) if row.get("value") else "N/A"
        lines.append(f"| {date_str} | {name} | {rel} | {txn} | {shares} | {val} |")
    lines.append("")
    return lines


def _render_institutions(institutions: list) -> list[str]:
    lines = ["### 机构持仓 Top 10"]
    if not institutions:
        lines.append("*无机构持仓数据*")
        lines.append("")
        return lines

    lines.append("| 机构 | 持股数 | 持仓市值 | 占比 |")
    lines.append("|------|--------|----------|------|")
    for row in institutions:
        holder = row.get("holder", "")[:30]
        shares = _fmt_num(row.get("shares"), 0) if row.get("shares") else "N/A"
        val = _fmt_num(row.get("value"), 0) if row.get("value") else "N/A"
        pct = _fmt_pct(row.get("pct_out")) if row.get("pct_out") else "N/A"
        lines.append(f"| {holder} | {shares} | {val} | {pct} |")
    lines.append("")
    return lines


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Market Data Snapshot (yfinance)")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. PM, NVDA)")
    parser.add_argument("--section", "-s", choices=["price", "financials", "analysts", "insiders", "institutions"],
                        action="append", help="Only show specific section(s)")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON instead of markdown")
    args = parser.parse_args()

    data = get_snapshot(args.ticker)

    if args.json:
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    else:
        print(render_markdown(data, args.section))


if __name__ == "__main__":
    main()
