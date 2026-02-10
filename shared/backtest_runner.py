"""Backtesting framework — Tier 1 scenarios using daily OHLC data.

Reads trade data from IBKR CSV cache (ibkr_sync.py) or from a provided
DataFrame.  Uses yfinance for price data and benchmarks.

Tier 1 scenarios (daily OHLC):
  A. Holding period analysis — 30/60/90 days vs actual
  B. Position sizing — equal weight vs actual
  C. DCA vs lump sum
  D. Alpha vs Beta decomposition (vs SPY)

Reports are saved to Documents/Obsidian Vault/Backtests/.

Attempts to use VectorBT for performance analytics.  Falls back to pure
pandas calculations if VectorBT is not installed.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ── Paths ────────────────────────────────────────────────────

SHARED_DIR = Path(__file__).parent
CACHE_DIR = SHARED_DIR / "data" / "ibkr_cache"
TRADES_CSV = CACHE_DIR / "trades.csv"
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
BACKTEST_DIR = VAULT_DIR / "Backtests"

# ── Dependency checks ────────────────────────────────────────

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required.  Install with:  pip install pandas")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy is required.  Install with:  pip install numpy")
    sys.exit(1)

HAS_VBT = False
try:
    import vectorbt as vbt  # type: ignore

    HAS_VBT = True
except ImportError:
    pass  # We handle the fallback silently per-scenario

HAS_YFINANCE = False
try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    pass

# Suppress yfinance FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)


# ── Price data ───────────────────────────────────────────────


def load_price_data(
    tickers: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Download daily OHLC data from Yahoo Finance for given tickers.

    Args:
        tickers: List of ticker symbols (e.g. ["AAPL", "MSFT"]).
        start_date: YYYY-MM-DD start.
        end_date: YYYY-MM-DD end.

    Returns:
        DataFrame with MultiIndex columns (field, ticker) or flat columns
        for a single ticker.  Uses adjusted close.
    """
    if not HAS_YFINANCE:
        print("ERROR: yfinance is required for price data.")
        print("       pip install yfinance")
        return pd.DataFrame()

    if not tickers:
        return pd.DataFrame()

    # Extend end_date by 1 day so the end date is inclusive
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    print(
        f"Downloading price data for {len(tickers)} tickers "
        f"({start_date} to {end_date})..."
    )

    try:
        data = yf.download(
            tickers,
            start=start_date,
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        print(f"  yfinance download failed: {exc}")
        return pd.DataFrame()

    if data.empty:
        print("  No price data returned.")
        return data

    # Forward-fill NaN (weekends already excluded, but gaps happen)
    data = data.ffill()
    print(f"  Got {len(data)} trading days.")
    return data


def load_benchmark(
    benchmark: str = "SPY",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load benchmark price data.

    Args:
        benchmark: Ticker symbol for benchmark (default SPY).
        start_date: YYYY-MM-DD (defaults to 2 years ago).
        end_date: YYYY-MM-DD (defaults to today).

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume].
    """
    if start_date is None:
        start_date = (date.today() - timedelta(days=730)).isoformat()
    if end_date is None:
        end_date = date.today().isoformat()

    data = load_price_data([benchmark], start_date, end_date)
    # yfinance returns MultiIndex for single ticker too sometimes
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


# ── Trade data loader ────────────────────────────────────────


def _load_trades_from_cache() -> pd.DataFrame:
    """Load trades from IBKR cache CSV."""
    if not TRADES_CSV.is_file():
        print(f"No trade cache found at {TRADES_CSV}")
        print("Run `ibkr_sync.py sync` first, or pass a DataFrame directly.")
        return pd.DataFrame()
    return pd.read_csv(TRADES_CSV, encoding="utf-8")


def _normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure trade DataFrame has the columns we need with consistent types.

    Expected minimum columns: symbol, tradeDate, quantity, tradePrice, buySell.
    """
    if df.empty:
        return df

    required = {"symbol", "tradeDate", "quantity", "tradePrice"}
    missing = required - set(df.columns)
    if missing:
        print(f"WARNING: Trade data missing columns: {missing}")
        print(f"         Available: {list(df.columns)}")
        return pd.DataFrame()

    df = df.copy()
    df["tradeDate"] = pd.to_datetime(df["tradeDate"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["tradePrice"] = pd.to_numeric(df["tradePrice"], errors="coerce").fillna(0)

    # Derive side if missing
    if "buySell" not in df.columns:
        df["buySell"] = df["quantity"].apply(lambda q: "BUY" if q > 0 else "SELL")

    # notional
    df["notional"] = (df["quantity"].abs() * df["tradePrice"]).round(2)

    return (
        df.dropna(subset=["tradeDate"]).sort_values("tradeDate").reset_index(drop=True)
    )


def _generate_sample_trades() -> pd.DataFrame:
    """Generate sample trade data for demo/testing purposes."""
    print("Generating sample trade data for demonstration...")
    today = date.today()
    rows = [
        {
            "symbol": "AAPL",
            "tradeDate": (today - timedelta(days=120)).isoformat(),
            "quantity": 50,
            "tradePrice": 178.50,
            "buySell": "BUY",
        },
        {
            "symbol": "AAPL",
            "tradeDate": (today - timedelta(days=30)).isoformat(),
            "quantity": -50,
            "tradePrice": 195.20,
            "buySell": "SELL",
        },
        {
            "symbol": "MSFT",
            "tradeDate": (today - timedelta(days=90)).isoformat(),
            "quantity": 30,
            "tradePrice": 380.00,
            "buySell": "BUY",
        },
        {
            "symbol": "MSFT",
            "tradeDate": (today - timedelta(days=15)).isoformat(),
            "quantity": -30,
            "tradePrice": 415.00,
            "buySell": "SELL",
        },
        {
            "symbol": "GOOGL",
            "tradeDate": (today - timedelta(days=60)).isoformat(),
            "quantity": 40,
            "tradePrice": 142.00,
            "buySell": "BUY",
        },
        {
            "symbol": "GOOGL",
            "tradeDate": (today - timedelta(days=10)).isoformat(),
            "quantity": -40,
            "tradePrice": 165.30,
            "buySell": "SELL",
        },
        {
            "symbol": "NVDA",
            "tradeDate": (today - timedelta(days=180)).isoformat(),
            "quantity": 25,
            "tradePrice": 480.00,
            "buySell": "BUY",
        },
        {
            "symbol": "NVDA",
            "tradeDate": (today - timedelta(days=45)).isoformat(),
            "quantity": -25,
            "tradePrice": 720.00,
            "buySell": "SELL",
        },
        {
            "symbol": "META",
            "tradeDate": (today - timedelta(days=75)).isoformat(),
            "quantity": 35,
            "tradePrice": 510.00,
            "buySell": "BUY",
        },
        # META still open (no sell) — will be used as open position
    ]
    return pd.DataFrame(rows)


# ── Utility ──────────────────────────────────────────────────


def _pct(val: float) -> str:
    """Format a decimal as percentage string."""
    return f"{val * 100:+.2f}%"


def _dollar(val: float) -> str:
    """Format as dollar amount."""
    return f"${val:,.2f}"


def _returns_series(prices: pd.Series) -> pd.Series:
    """Daily returns from a price series."""
    return prices.pct_change().dropna()


# ── Scenario A: Holding Period Analysis ──────────────────────


def scenario_holding_period(trades_df: pd.DataFrame) -> dict:
    """Compare actual holding periods to 30/60/90-day alternatives.

    For each round-trip (BUY then SELL of the same symbol), compute:
    - Actual return over the actual holding period
    - What the return would have been at 30, 60, 90 days

    Returns:
        {"metrics": {...}, "report_md": str}
    """
    df = _normalize_trades(trades_df)
    if df.empty:
        return {"metrics": {}, "report_md": "No trade data available."}

    # Pair buys with sells per symbol
    symbols = df["symbol"].unique()
    alt_periods = [30, 60, 90]
    results: list[dict] = []

    all_tickers = list(symbols)
    start = df["tradeDate"].min() - timedelta(days=10)
    end = date.today()
    prices = load_price_data(
        all_tickers, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    )

    if prices.empty:
        return {
            "metrics": {},
            "report_md": "Could not download price data from Yahoo Finance.",
        }

    for sym in symbols:
        sym_trades = df[df["symbol"] == sym].copy()
        buys = sym_trades[sym_trades["quantity"] > 0]
        sells = sym_trades[sym_trades["quantity"] < 0]

        if buys.empty:
            continue

        # Get close prices for this symbol
        try:
            if isinstance(prices.columns, pd.MultiIndex):
                close = prices["Close"][sym].dropna()
            else:
                close = prices["Close"].dropna()
        except (KeyError, TypeError):
            continue

        if close.empty:
            continue

        for _, buy in buys.iterrows():
            entry_date = buy["tradeDate"]
            entry_price = buy["tradePrice"]

            # Actual exit
            matching_sells = sells[sells["tradeDate"] > entry_date]
            if not matching_sells.empty:
                exit_row = matching_sells.iloc[0]
                actual_days = (exit_row["tradeDate"] - entry_date).days
                actual_return = (exit_row["tradePrice"] - entry_price) / entry_price
            else:
                # Still open — use latest price
                actual_days = (pd.Timestamp(date.today()) - entry_date).days
                actual_return = (
                    (close.iloc[-1] - entry_price) / entry_price
                    if len(close) > 0
                    else 0
                )

            row: dict[str, Any] = {
                "symbol": sym,
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": entry_price,
                "actual_days": actual_days,
                "actual_return": round(actual_return, 4),
            }

            # Alternative holding periods
            for days in alt_periods:
                alt_exit = entry_date + timedelta(days=days)
                # Find closest trading day
                mask = close.index >= pd.Timestamp(alt_exit)
                if mask.any():
                    alt_price = close[mask].iloc[0]
                elif len(close) > 0:
                    alt_price = close.iloc[-1]
                else:
                    alt_price = entry_price
                alt_ret = (alt_price - entry_price) / entry_price
                row[f"return_{days}d"] = round(alt_ret, 4)

            results.append(row)

    if not results:
        return {"metrics": {}, "report_md": "No paired trades found for analysis."}

    res_df = pd.DataFrame(results)

    # Aggregate metrics
    metrics = {
        "trade_count": len(res_df),
        "avg_actual_days": round(res_df["actual_days"].mean(), 1),
        "avg_actual_return": round(res_df["actual_return"].mean(), 4),
    }
    for days in alt_periods:
        col = f"return_{days}d"
        if col in res_df.columns:
            metrics[f"avg_return_{days}d"] = round(res_df[col].mean(), 4)

    # Markdown report
    today_str = date.today().isoformat()
    table_rows = []
    for _, r in res_df.iterrows():
        table_rows.append(
            f"| {r['symbol']} | {r['entry_date']} | {r['actual_days']}d | "
            f"{_pct(r['actual_return'])} | "
            f"{_pct(r.get('return_30d', 0))} | "
            f"{_pct(r.get('return_60d', 0))} | "
            f"{_pct(r.get('return_90d', 0))} |"
        )

    report_md = f"""---
type: backtest
date: {today_str}
scenario: holding_period
data_granularity: daily_ohlc
tags: [backtest, tier-1, holding-period]
---
# Backtest: Holding Period Analysis

## Data & Limitations
- **Granularity:** Daily OHLC (Yahoo Finance adjusted close)
- **Limitation:** Does not account for intraday entry/exit timing, dividends during holding, or transaction costs. Alternative exit prices use next available trading day if the target day falls on a weekend/holiday.

## Results

### Per-Trade Comparison

| Symbol | Entry Date | Actual Hold | Actual Return | 30d Return | 60d Return | 90d Return |
|--------|-----------|-------------|---------------|------------|------------|------------|
{chr(10).join(table_rows)}

### Summary

| Metric | Value |
|--------|-------|
| Trades analyzed | {metrics["trade_count"]} |
| Avg holding period | {metrics["avg_actual_days"]} days |
| Avg actual return | {_pct(metrics["avg_actual_return"])} |
| Avg 30-day return | {_pct(metrics.get("avg_return_30d", 0))} |
| Avg 60-day return | {_pct(metrics.get("avg_return_60d", 0))} |
| Avg 90-day return | {_pct(metrics.get("avg_return_90d", 0))} |

## Actionable Takeaway
{"Your actual holding periods outperform the standard alternatives on average -- your exit timing is adding value." if metrics["avg_actual_return"] >= max(metrics.get("avg_return_30d", 0), metrics.get("avg_return_60d", 0), metrics.get("avg_return_90d", 0)) else "Consider whether a systematic holding period (e.g., " + ("30" if metrics.get("avg_return_30d", 0) >= metrics.get("avg_return_90d", 0) else "90") + " days) would have improved returns vs. your discretionary exits."}
"""
    return {"metrics": metrics, "report_md": report_md}


# ── Scenario B: Position Sizing (Equal Weight vs Actual) ─────


def scenario_position_sizing(
    trades_df: pd.DataFrame,
    portfolio_value: float = 100_000.0,
) -> dict:
    """Compare actual position sizes to equal-weight allocation.

    For each BUY trade, compute:
    - Actual weight = notional / portfolio_value
    - Equal weight = 1 / N (where N = number of unique symbols traded)
    - Return contribution of each under both schemes

    Returns:
        {"metrics": {...}, "report_md": str}
    """
    df = _normalize_trades(trades_df)
    if df.empty:
        return {"metrics": {}, "report_md": "No trade data available."}

    buys = df[df["quantity"] > 0].copy()
    if buys.empty:
        return {"metrics": {}, "report_md": "No BUY trades found."}

    unique_symbols = buys["symbol"].unique()
    n_positions = len(unique_symbols)
    equal_weight = 1.0 / n_positions

    # Get latest prices for return calculation
    end_date = date.today().isoformat()
    start_date = buys["tradeDate"].min().strftime("%Y-%m-%d")
    prices = load_price_data(list(unique_symbols), start_date, end_date)

    rows: list[dict] = []
    total_actual_contrib = 0.0
    total_equal_contrib = 0.0

    for sym in unique_symbols:
        sym_buys = buys[buys["symbol"] == sym]
        total_notional = sym_buys["notional"].sum()
        avg_entry = (sym_buys["notional"].sum()) / sym_buys["quantity"].abs().sum()
        actual_weight = total_notional / portfolio_value

        # Current / exit price
        try:
            if isinstance(prices.columns, pd.MultiIndex):
                current_price = prices["Close"][sym].dropna().iloc[-1]
            else:
                current_price = prices["Close"].dropna().iloc[-1]
        except (KeyError, IndexError):
            current_price = avg_entry  # fallback: assume flat

        sym_return = (current_price - avg_entry) / avg_entry if avg_entry > 0 else 0

        actual_contrib = actual_weight * sym_return
        equal_contrib = equal_weight * sym_return
        total_actual_contrib += actual_contrib
        total_equal_contrib += equal_contrib

        rows.append(
            {
                "symbol": sym,
                "avg_entry": round(avg_entry, 2),
                "current_price": round(current_price, 2),
                "return": round(sym_return, 4),
                "actual_weight": round(actual_weight, 4),
                "equal_weight": round(equal_weight, 4),
                "actual_contrib": round(actual_contrib, 4),
                "equal_contrib": round(equal_contrib, 4),
            }
        )

    metrics = {
        "n_positions": n_positions,
        "portfolio_value": portfolio_value,
        "actual_portfolio_return": round(total_actual_contrib, 4),
        "equal_weight_return": round(total_equal_contrib, 4),
        "sizing_alpha": round(total_actual_contrib - total_equal_contrib, 4),
    }

    today_str = date.today().isoformat()
    table_rows = []
    for r in rows:
        table_rows.append(
            f"| {r['symbol']} | {_dollar(r['avg_entry'])} | {_dollar(r['current_price'])} | "
            f"{_pct(r['return'])} | {_pct(r['actual_weight'])} | {_pct(r['equal_weight'])} | "
            f"{_pct(r['actual_contrib'])} | {_pct(r['equal_contrib'])} |"
        )

    sizing_verdict = (
        "Your position sizing added value -- you allocated more to winners."
        if metrics["sizing_alpha"] > 0
        else "Equal-weight allocation would have outperformed your actual sizing. "
        "Consider whether conviction-weighted sizing is truly adding value."
    )

    report_md = f"""---
type: backtest
date: {today_str}
scenario: position_sizing
data_granularity: daily_ohlc
tags: [backtest, tier-1, position-sizing]
---
# Backtest: Position Sizing (Equal Weight vs Actual)

## Data & Limitations
- **Granularity:** Daily OHLC (Yahoo Finance adjusted close)
- **Limitation:** Assumes static weights at entry (no rebalancing). Does not account for partial exits, margin, or position adds. Portfolio value is estimated at {_dollar(portfolio_value)}.

## Results

### Per-Symbol Comparison

| Symbol | Avg Entry | Current | Return | Actual Wt | Equal Wt | Actual Contrib | Equal Contrib |
|--------|-----------|---------|--------|-----------|----------|----------------|---------------|
{chr(10).join(table_rows)}

### Summary

| Metric | Value |
|--------|-------|
| Positions | {metrics["n_positions"]} |
| Portfolio value (assumed) | {_dollar(metrics["portfolio_value"])} |
| Actual portfolio return | {_pct(metrics["actual_portfolio_return"])} |
| Equal-weight return | {_pct(metrics["equal_weight_return"])} |
| **Sizing alpha** | **{_pct(metrics["sizing_alpha"])}** |

## Actionable Takeaway
{sizing_verdict}
"""
    return {"metrics": metrics, "report_md": report_md}


# ── Scenario C: DCA vs Lump Sum ─────────────────────────────


def scenario_dca_vs_lump(trades_df: pd.DataFrame) -> dict:
    """Compare DCA (dollar-cost averaging) vs lump-sum for each symbol.

    For each symbol with BUY trades:
    - Lump sum: invest total notional on first trade date
    - DCA: spread the same total across weekly purchases over the holding period

    Returns:
        {"metrics": {...}, "report_md": str}
    """
    df = _normalize_trades(trades_df)
    if df.empty:
        return {"metrics": {}, "report_md": "No trade data available."}

    buys = df[df["quantity"] > 0].copy()
    if buys.empty:
        return {"metrics": {}, "report_md": "No BUY trades found."}

    symbols = buys["symbol"].unique()
    start_date = buys["tradeDate"].min().strftime("%Y-%m-%d")
    end_date = date.today().isoformat()
    prices = load_price_data(list(symbols), start_date, end_date)

    if prices.empty:
        return {"metrics": {}, "report_md": "Could not download price data."}

    results: list[dict] = []

    for sym in symbols:
        sym_buys = buys[buys["symbol"] == sym]
        total_investment = sym_buys["notional"].sum()
        first_date = sym_buys["tradeDate"].min()

        try:
            if isinstance(prices.columns, pd.MultiIndex):
                close = prices["Close"][sym].dropna()
            else:
                close = prices["Close"].dropna()
        except (KeyError, TypeError):
            continue

        if len(close) < 2:
            continue

        # Lump sum: buy everything on first trade date
        mask = close.index >= pd.Timestamp(first_date)
        if not mask.any():
            continue
        lump_price = close[mask].iloc[0]
        lump_shares = total_investment / lump_price
        current_price = close.iloc[-1]
        lump_value = lump_shares * current_price
        lump_return = (lump_value - total_investment) / total_investment

        # DCA: weekly purchases from first_date to today
        dca_dates = pd.date_range(start=first_date, end=date.today(), freq="W-MON")
        if len(dca_dates) == 0:
            dca_dates = pd.DatetimeIndex([first_date])

        weekly_amount = total_investment / len(dca_dates)
        dca_shares = 0.0
        dca_invested = 0.0

        for dca_date in dca_dates:
            mask = close.index >= dca_date
            if mask.any():
                buy_price = close[mask].iloc[0]
                dca_shares += weekly_amount / buy_price
                dca_invested += weekly_amount

        dca_value = dca_shares * current_price
        dca_return = (
            (dca_value - dca_invested) / dca_invested if dca_invested > 0 else 0
        )

        results.append(
            {
                "symbol": sym,
                "total_invested": round(total_investment, 2),
                "weeks": len(dca_dates),
                "lump_return": round(lump_return, 4),
                "dca_return": round(dca_return, 4),
                "lump_value": round(lump_value, 2),
                "dca_value": round(dca_value, 2),
                "winner": "Lump Sum" if lump_return >= dca_return else "DCA",
            }
        )

    if not results:
        return {"metrics": {}, "report_md": "No symbols with sufficient data."}

    lump_wins = sum(1 for r in results if r["winner"] == "Lump Sum")
    dca_wins = len(results) - lump_wins
    avg_lump = np.mean([r["lump_return"] for r in results])
    avg_dca = np.mean([r["dca_return"] for r in results])

    metrics = {
        "symbols_analyzed": len(results),
        "lump_sum_wins": lump_wins,
        "dca_wins": dca_wins,
        "avg_lump_return": round(avg_lump, 4),
        "avg_dca_return": round(avg_dca, 4),
    }

    today_str = date.today().isoformat()
    table_rows = []
    for r in results:
        table_rows.append(
            f"| {r['symbol']} | {_dollar(r['total_invested'])} | {r['weeks']}w | "
            f"{_pct(r['lump_return'])} | {_pct(r['dca_return'])} | "
            f"{_dollar(r['lump_value'])} | {_dollar(r['dca_value'])} | "
            f"**{r['winner']}** |"
        )

    overall_winner = "Lump Sum" if lump_wins >= dca_wins else "DCA"
    report_md = f"""---
type: backtest
date: {today_str}
scenario: dca_vs_lump
data_granularity: daily_ohlc
tags: [backtest, tier-1, dca]
---
# Backtest: DCA vs Lump Sum

## Data & Limitations
- **Granularity:** Daily OHLC (Yahoo Finance adjusted close)
- **Limitation:** DCA simulation uses weekly Monday purchases. Lump sum buys at the close price on first trade date. Does not account for transaction costs, slippage, or the opportunity cost of holding cash during DCA.

## Results

### Per-Symbol Comparison

| Symbol | Total Invested | DCA Period | Lump Return | DCA Return | Lump Value | DCA Value | Winner |
|--------|---------------|------------|-------------|------------|------------|-----------|--------|
{chr(10).join(table_rows)}

### Summary

| Metric | Value |
|--------|-------|
| Symbols analyzed | {metrics["symbols_analyzed"]} |
| Lump Sum wins | {metrics["lump_sum_wins"]} |
| DCA wins | {metrics["dca_wins"]} |
| Avg lump sum return | {_pct(metrics["avg_lump_return"])} |
| Avg DCA return | {_pct(metrics["avg_dca_return"])} |

## Actionable Takeaway
{overall_winner} outperformed in the majority of your positions. {"In trending markets, deploying capital immediately tends to win. Reserve DCA for high-volatility entries where timing risk is elevated." if overall_winner == "Lump Sum" else "DCA reduced timing risk and improved average entry prices. For high-conviction positions, consider deploying over 4-6 weeks instead of going all-in."}
"""
    return {"metrics": metrics, "report_md": report_md}


# ── Scenario D: Alpha vs Beta Decomposition ─────────────────


def scenario_alpha_beta(
    trades_df: pd.DataFrame,
    benchmark_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Decompose portfolio returns into alpha and beta components vs SPY.

    Uses simple OLS regression of portfolio daily returns against benchmark
    daily returns to estimate alpha (intercept) and beta (slope).

    Returns:
        {"metrics": {...}, "report_md": str}
    """
    df = _normalize_trades(trades_df)
    if df.empty:
        return {"metrics": {}, "report_md": "No trade data available."}

    buys = df[df["quantity"] > 0]
    if buys.empty:
        return {"metrics": {}, "report_md": "No BUY trades found."}

    symbols = list(buys["symbol"].unique())
    start_date = buys["tradeDate"].min().strftime("%Y-%m-%d")
    end_date = date.today().isoformat()

    # Load benchmark
    if benchmark_df is None or benchmark_df.empty:
        benchmark_df = load_benchmark("SPY", start_date, end_date)

    if benchmark_df.empty:
        return {"metrics": {}, "report_md": "Could not load benchmark data."}

    # Load portfolio prices
    prices = load_price_data(symbols, start_date, end_date)
    if prices.empty:
        return {"metrics": {}, "report_md": "Could not load portfolio price data."}

    # Build equal-weight portfolio daily returns
    daily_returns_list = []
    for sym in symbols:
        try:
            if isinstance(prices.columns, pd.MultiIndex):
                close = prices["Close"][sym].dropna()
            else:
                close = prices["Close"].dropna()
        except (KeyError, TypeError):
            continue
        ret = close.pct_change().dropna()
        ret.name = sym
        daily_returns_list.append(ret)

    if not daily_returns_list:
        return {"metrics": {}, "report_md": "No return data computed."}

    portfolio_returns = pd.concat(daily_returns_list, axis=1).mean(axis=1)
    portfolio_returns.name = "portfolio"

    # Benchmark returns
    bench_close = (
        benchmark_df["Close"]
        if "Close" in benchmark_df.columns
        else benchmark_df.iloc[:, 0]
    )
    bench_returns = bench_close.pct_change().dropna()
    bench_returns.name = "benchmark"

    # Align dates
    aligned = pd.concat([portfolio_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 10:
        return {
            "metrics": {},
            "report_md": "Insufficient overlapping data for regression.",
        }

    port_ret = aligned["portfolio"].values
    bench_ret = aligned["benchmark"].values

    # Simple OLS: port = alpha + beta * bench + epsilon
    # Using numpy polyfit (degree 1) as OLS
    beta, alpha_total = np.polyfit(bench_ret, port_ret, 1)

    # Annualize (252 trading days)
    alpha_annual = alpha_total * 252
    portfolio_annual = port_ret.mean() * 252
    benchmark_annual = bench_ret.mean() * 252

    # Correlation and R-squared
    correlation = np.corrcoef(port_ret, bench_ret)[0, 1]
    r_squared = correlation**2

    # Sharpe ratio (assume 5% risk-free for simplicity)
    rf_daily = 0.05 / 252
    port_excess = port_ret - rf_daily
    sharpe = (
        (port_excess.mean() / port_excess.std()) * np.sqrt(252)
        if port_excess.std() > 0
        else 0
    )

    # Information ratio
    tracking_error = (port_ret - bench_ret).std() * np.sqrt(252)
    info_ratio = (
        (portfolio_annual - benchmark_annual) / tracking_error
        if tracking_error > 0
        else 0
    )

    metrics = {
        "beta": round(float(beta), 3),
        "alpha_daily": round(float(alpha_total), 6),
        "alpha_annual": round(float(alpha_annual), 4),
        "r_squared": round(float(r_squared), 4),
        "correlation": round(float(correlation), 4),
        "portfolio_annual_return": round(float(portfolio_annual), 4),
        "benchmark_annual_return": round(float(benchmark_annual), 4),
        "sharpe_ratio": round(float(sharpe), 3),
        "information_ratio": round(float(info_ratio), 3),
        "tracking_error": round(float(tracking_error), 4),
        "trading_days": len(aligned),
    }

    today_str = date.today().isoformat()

    # Interpret beta
    if beta > 1.2:
        beta_note = "Your portfolio is significantly more volatile than the market (aggressive)."
    elif beta > 0.8:
        beta_note = "Your portfolio has market-like sensitivity."
    else:
        beta_note = "Your portfolio is defensive / low-beta relative to SPY."

    # Per-symbol beta
    sym_betas = []
    for sym in symbols:
        try:
            if isinstance(prices.columns, pd.MultiIndex):
                sym_ret = prices["Close"][sym].pct_change().dropna()
            else:
                sym_ret = prices["Close"].pct_change().dropna()
            sym_aligned = pd.concat([sym_ret, bench_returns], axis=1).dropna()
            if len(sym_aligned) < 10:
                continue
            s_beta, s_alpha = np.polyfit(
                sym_aligned.iloc[:, 1].values,
                sym_aligned.iloc[:, 0].values,
                1,
            )
            sym_betas.append(
                {
                    "symbol": sym,
                    "beta": round(float(s_beta), 3),
                    "alpha_annual": round(float(s_alpha * 252), 4),
                }
            )
        except Exception:
            continue

    sym_table = ""
    if sym_betas:
        sym_rows = []
        for sb in sorted(sym_betas, key=lambda x: x["alpha_annual"], reverse=True):
            sym_rows.append(
                f"| {sb['symbol']} | {sb['beta']:.3f} | {_pct(sb['alpha_annual'])} |"
            )
        sym_table = f"""
### Per-Symbol Decomposition

| Symbol | Beta | Alpha (annualized) |
|--------|------|--------------------|
{chr(10).join(sym_rows)}
"""

    report_md = f"""---
type: backtest
date: {today_str}
scenario: alpha_beta
data_granularity: daily_ohlc
tags: [backtest, tier-1, alpha-beta, risk]
---
# Backtest: Alpha vs Beta Decomposition

## Data & Limitations
- **Granularity:** Daily OHLC (Yahoo Finance adjusted close)
- **Benchmark:** SPY (S&P 500 ETF)
- **Limitation:** Uses equal-weight portfolio returns (not actual capital-weighted). Alpha from simple OLS regression -- does not account for factor exposures (size, value, momentum). Risk-free rate assumed at 5% for Sharpe calculation. Period: {start_date} to {end_date} ({metrics["trading_days"]} trading days).

## Results

### Portfolio vs Benchmark

| Metric | Value |
|--------|-------|
| **Beta** | {metrics["beta"]:.3f} |
| **Alpha (annualized)** | {_pct(metrics["alpha_annual"])} |
| R-squared | {metrics["r_squared"]:.4f} |
| Correlation | {metrics["correlation"]:.4f} |
| Portfolio return (ann.) | {_pct(metrics["portfolio_annual_return"])} |
| Benchmark return (ann.) | {_pct(metrics["benchmark_annual_return"])} |
| Sharpe ratio | {metrics["sharpe_ratio"]:.3f} |
| Information ratio | {metrics["information_ratio"]:.3f} |
| Tracking error (ann.) | {_pct(metrics["tracking_error"])} |
{sym_table}

### Interpretation

- **Beta = {metrics["beta"]:.3f}:** {beta_note}
- **Alpha = {_pct(metrics["alpha_annual"])} annualized:** {"Positive alpha suggests stock selection is adding value beyond market exposure." if metrics["alpha_annual"] > 0 else "Negative alpha suggests returns are lagging after adjusting for market exposure. Review stock selection process."}
- **R-squared = {metrics["r_squared"]:.2f}:** {"High -- most of your returns are explained by market movements." if metrics["r_squared"] > 0.7 else "Low -- your portfolio has significant idiosyncratic exposure (good for a stock picker)."}

## Actionable Takeaway
{"Your positive alpha indicates stock selection skill. Focus on maintaining the quality of your research process." if metrics["alpha_annual"] > 0.02 else "Consider whether the portfolio's risk-adjusted returns justify the effort vs. a passive SPY allocation." if metrics["alpha_annual"] < -0.02 else "Alpha is close to zero -- your returns are largely explained by market beta. To generate alpha, increase conviction concentration or improve entry timing."}
"""
    return {"metrics": metrics, "report_md": report_md}


# ── Run All Scenarios ────────────────────────────────────────


def run_all_scenarios(
    trades_df: pd.DataFrame,
    portfolio_value: float = 100_000.0,
) -> list[dict]:
    """Run all Tier 1 scenarios and return results.

    Args:
        trades_df: DataFrame of trades (from IBKR cache or provided).
        portfolio_value: Estimated portfolio value for sizing scenario.

    Returns:
        List of dicts, each with {scenario, metrics, report_md}.
    """
    scenarios = [
        ("holding_period", lambda: scenario_holding_period(trades_df)),
        (
            "position_sizing",
            lambda: scenario_position_sizing(trades_df, portfolio_value),
        ),
        ("dca_vs_lump", lambda: scenario_dca_vs_lump(trades_df)),
        ("alpha_beta", lambda: scenario_alpha_beta(trades_df)),
    ]

    results = []
    for name, fn in scenarios:
        print(f"\n{'=' * 60}")
        print(f"Running scenario: {name}")
        print("=" * 60)
        try:
            result = fn()
            result["scenario"] = name
            results.append(result)
            print(f"  Done. Metrics: {json.dumps(result.get('metrics', {}), indent=2)}")
        except Exception as exc:
            print(f"  ERROR in {name}: {exc}")
            results.append(
                {
                    "scenario": name,
                    "metrics": {"error": str(exc)},
                    "report_md": f"Scenario {name} failed: {exc}",
                }
            )

    return results


# ── Save to Obsidian ─────────────────────────────────────────


def save_report_to_obsidian(scenario_name: str, report_md: str) -> Path:
    """Save a backtest report to the Obsidian Vault.

    Args:
        scenario_name: Short name (e.g. "holding_period").
        report_md: Full markdown content including frontmatter.

    Returns:
        Path to the saved file.
    """
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    filename = f"{today_str} - {scenario_name}.md"
    filepath = BACKTEST_DIR / filename
    filepath.write_text(report_md, encoding="utf-8")
    print(f"Saved: {filepath}")
    return filepath


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtesting framework — Tier 1 scenarios (daily OHLC)."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=[
            "all",
            "holding_period",
            "position_sizing",
            "dca_vs_lump",
            "alpha_beta",
        ],
        default="all",
        help="Which scenario to run (default: all).",
    )
    parser.add_argument(
        "--trades-csv",
        type=Path,
        default=None,
        help="Path to trades CSV. Defaults to IBKR cache.",
    )
    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=100_000.0,
        help="Estimated portfolio value for sizing scenario (default: 100000).",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample trade data (for testing without IBKR sync).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save reports to Obsidian Vault.",
    )
    parser.add_argument(
        "--no-vbt",
        action="store_true",
        help="Force pure-pandas mode even if VectorBT is available.",
    )

    args = parser.parse_args()

    global HAS_VBT
    if args.no_vbt:
        HAS_VBT = False
        print("VectorBT disabled (--no-vbt). Using pure pandas.")
    elif not HAS_VBT:
        print("VectorBT not installed. Using pure pandas fallback.")
        print("  (Optional: pip install vectorbt for enhanced analytics)")

    # Load trade data
    if args.sample:
        trades_df = _generate_sample_trades()
    elif args.trades_csv:
        if not args.trades_csv.is_file():
            print(f"ERROR: Trades CSV not found: {args.trades_csv}")
            sys.exit(1)
        trades_df = pd.read_csv(args.trades_csv, encoding="utf-8")
    else:
        trades_df = _load_trades_from_cache()

    if trades_df.empty:
        print("\nNo trade data available. Options:")
        print("  1. Run `ibkr_sync.py sync` to download from IBKR")
        print("  2. Pass --trades-csv <path> to use a custom CSV")
        print("  3. Pass --sample to use demo data")
        sys.exit(1)

    print(f"\nLoaded {len(trades_df)} trades.")
    trades_df = _normalize_trades(trades_df)
    if trades_df.empty:
        print("ERROR: Trade data could not be normalized. Check column names.")
        sys.exit(1)

    # Run scenarios
    scenario_map = {
        "holding_period": lambda: scenario_holding_period(trades_df),
        "position_sizing": lambda: scenario_position_sizing(
            trades_df, args.portfolio_value
        ),
        "dca_vs_lump": lambda: scenario_dca_vs_lump(trades_df),
        "alpha_beta": lambda: scenario_alpha_beta(trades_df),
    }

    if args.scenario == "all":
        results = run_all_scenarios(trades_df, args.portfolio_value)
    else:
        result = scenario_map[args.scenario]()
        result["scenario"] = args.scenario
        results = [result]

    # Save to Obsidian if requested
    if args.save:
        print(f"\nSaving reports to {BACKTEST_DIR}...")
        for r in results:
            if r.get("report_md"):
                save_report_to_obsidian(r["scenario"], r["report_md"])

    # Print summary
    print("\n" + "=" * 60)
    print("BACKTEST SUMMARY")
    print("=" * 60)
    for r in results:
        scenario = r.get("scenario", "unknown")
        m = r.get("metrics", {})
        if "error" in m:
            print(f"  {scenario}: FAILED - {m['error']}")
        else:
            key_metric = ""
            if scenario == "holding_period":
                key_metric = f"avg return: {_pct(m.get('avg_actual_return', 0))}"
            elif scenario == "position_sizing":
                key_metric = f"sizing alpha: {_pct(m.get('sizing_alpha', 0))}"
            elif scenario == "dca_vs_lump":
                key_metric = f"lump wins: {m.get('lump_sum_wins', 0)}, DCA wins: {m.get('dca_wins', 0)}"
            elif scenario == "alpha_beta":
                key_metric = f"alpha: {_pct(m.get('alpha_annual', 0))}, beta: {m.get('beta', 0):.3f}"
            print(f"  {scenario}: {key_metric}")


if __name__ == "__main__":
    main()
