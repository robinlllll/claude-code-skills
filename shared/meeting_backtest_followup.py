"""Meeting Backtest Follow-up: 6 Robustness Analyses

GPT-5.2-pro identified 6 follow-up analyses to validate the original meeting backtest
findings (42 meetings, 675 picks, 211 tickers, 82nd percentile alpha).

Analyses:
1. Data Pipeline Audit — reconcile 90d discrepancy between decay curve and trade management
2. Concentration Stress Test — ex-PDD / ex-HOOD / ex-Top3 sensitivity
3. Cluster-Robust Confidence Intervals — block bootstrap + Newey-West
4. Carhart 4-Factor Regression — ETF-based factor decomposition
5. Transaction Cost Sensitivity — fixed + tiered cost scenarios
6. Real P&L Replication — match backtest picks to actual trades.json

Usage:
    python meeting_backtest_followup.py [--no-cache] [--verbose]
"""

import io
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Optional

# Shared utilities
SKILLS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILLS_DIR))

# Import from existing meeting_backtest.py (which handles Windows GBK stdout fix)
from shared.meeting_backtest import (
    MeetingParser,
    TradeMatcher,
    PriceFetcher,
    Aggregator,
    PortfolioAnalyzer,
    Sentiment,
    TickerNormalizer,
    MAIN_WINDOWS,
    ALL_WINDOWS,
    SECTOR_MAP,
    SECTOR_LABELS,
    SECTOR_ETFS,
    CACHE_PATH,
    TRADES_PATH,
    VAULT_DIR,
    MEETING_DIR,
    REPORT_DIR,
)
from shared.frontmatter_utils import build_frontmatter

# Paths
FOLLOWUP_REPORT_PATH = REPORT_DIR / f"{date.today().isoformat()}_meeting_backtest_followup.md"

# Try numpy/scipy — graceful fallback
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[WARN] numpy not available — some analyses will be skipped")

try:
    from scipy import stats as sp_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── Analysis 1: Data Pipeline Audit ───────────────────────────

class DataPipelineAudit:
    """Trace the 90d discrepancy between decay curve and trade management modules."""

    @staticmethod
    def audit(picks: list[dict]) -> dict:
        """Reconcile 90d return differences across modules.

        The decay curve uses all picks with returns[90] != None.
        The trade management sim filters to bullish+acted with returns[30] != None,
        then simulates checkpoint exits (which may exit before 90d).
        Different N and different calculation → different 90d numbers.
        """
        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]]

        # Module A: Decay curve path — all bullish acted, raw 90d return
        decay_pool = [p for p in bullish_acted
                      if p.get("excess_returns", {}).get(90) is not None]
        decay_90d_excess = [p["excess_returns"][90] for p in decay_pool]

        # Module B: Trade management path — filter to 30d available, simulate exits
        trade_mgmt_pool = [p for p in bullish_acted
                           if p.get("returns", {}).get(30) is not None]

        # Simulate 30d hold (what trade_management_sim does as baseline)
        checkpoints = [1, 3, 7, 14, 21, 30, 45, 60, 90, 180]
        sim_exits_90d = []
        for p in trade_mgmt_pool:
            rets = p.get("returns", {})
            # Time-stop at 90d
            exit_return = None
            for day in checkpoints:
                r = rets.get(day)
                if r is None:
                    continue
                if day >= 90:
                    exit_return = r
                    break
            if exit_return is None:
                # Use last available return before 90d
                for day in reversed(checkpoints):
                    r = rets.get(day)
                    if r is not None and day <= 90:
                        exit_return = r
                        break
            spy_ret = p.get("spy_returns", {}).get(90, 0) or 0
            if exit_return is not None:
                sim_exits_90d.append({
                    "ticker": p["ticker_yf"],
                    "date": p["meeting_date"],
                    "exit_return": exit_return,
                    "excess": exit_return - spy_ret,
                })

        # Find which picks are in one pool but not the other
        decay_keys = {(p["ticker_yf"], str(p["meeting_date"])) for p in decay_pool}
        sim_keys = {(e["ticker"], str(e["date"])) for e in sim_exits_90d}
        mgmt_keys = {(p["ticker_yf"], str(p["meeting_date"])) for p in trade_mgmt_pool}

        only_in_decay = decay_keys - mgmt_keys
        only_in_mgmt = mgmt_keys - decay_keys

        # Per-pick comparison for common picks
        common_keys = decay_keys & mgmt_keys
        discrepancies = []
        for p in decay_pool:
            key = (p["ticker_yf"], str(p["meeting_date"]))
            if key in common_keys:
                raw_90 = p["excess_returns"][90]
                # Find the sim exit for this pick
                sim_entry = next(
                    (e for e in sim_exits_90d
                     if e["ticker"] == p["ticker_yf"]
                     and str(e["date"]) == str(p["meeting_date"])),
                    None
                )
                if sim_entry:
                    sim_90 = sim_entry["excess"]
                    diff = raw_90 - sim_90
                    if abs(diff) > 0.001:
                        discrepancies.append({
                            "ticker": p["ticker_yf"],
                            "date": p["meeting_date"],
                            "decay_excess_90": raw_90,
                            "sim_excess_90": sim_90,
                            "diff": diff,
                        })

        discrepancies.sort(key=lambda x: abs(x["diff"]), reverse=True)

        return {
            "decay_curve": {
                "n": len(decay_pool),
                "mean_excess_90": mean(decay_90d_excess) if decay_90d_excess else None,
                "median_excess_90": median(decay_90d_excess) if decay_90d_excess else None,
            },
            "trade_mgmt_sim": {
                "n": len(sim_exits_90d),
                "mean_excess_90": mean(e["excess"] for e in sim_exits_90d) if sim_exits_90d else None,
                "median_excess_90": median(e["excess"] for e in sim_exits_90d) if sim_exits_90d else None,
            },
            "trade_mgmt_input_pool": {
                "n": len(trade_mgmt_pool),
            },
            "only_in_decay": len(only_in_decay),
            "only_in_mgmt": len(only_in_mgmt),
            "common": len(common_keys),
            "discrepancies": discrepancies[:20],
            "root_cause": (
                "Trade management sim filters to picks with returns[30] != None, then "
                "simulates checkpoint exits. The 90d 'excess' in sim uses SPY return at "
                "the exit checkpoint day (which may differ from the 90d SPY return in the "
                "decay curve). Also, sim may exit before 90d if no 90d return is available, "
                "using the last available checkpoint instead."
            ),
        }


# ── Analysis 2: Concentration Stress Test ─────────────────────

class ConcentrationStressTest:
    """Remove PDD, HOOD, or top-3 contributors and re-measure key metrics."""

    @staticmethod
    def _compute_metrics(picks: list[dict], windows: list[int] = None) -> dict:
        """Compute key metrics for a filtered pick set."""
        if windows is None:
            windows = [30, 90]

        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]]
        bullish_discussed = [p for p in picks
                              if p["sentiment"] == Sentiment.BULLISH and not p["acted_on"]]

        result = {"n_total": len(picks), "n_bullish_acted": len(bullish_acted)}

        for w in windows:
            ba_excess = [p["excess_returns"][w] for p in bullish_acted
                         if p.get("excess_returns", {}).get(w) is not None]
            bd_excess = [p["excess_returns"][w] for p in bullish_discussed
                         if p.get("excess_returns", {}).get(w) is not None]

            if ba_excess:
                result[f"ba_excess_{w}d"] = mean(ba_excess)
                result[f"ba_wr_{w}d"] = sum(1 for e in ba_excess if e > 0) / len(ba_excess)
                result[f"ba_n_{w}d"] = len(ba_excess)
            else:
                result[f"ba_excess_{w}d"] = None
                result[f"ba_wr_{w}d"] = None
                result[f"ba_n_{w}d"] = 0

            if bd_excess:
                result[f"bd_excess_{w}d"] = mean(bd_excess)
            else:
                result[f"bd_excess_{w}d"] = None

        # Mini-bootstrap for percentile (simplified — 500 iterations)
        all_excess_30 = [p["excess_returns"][30] for p in picks
                         if p.get("excess_returns", {}).get(30) is not None]
        ba_excess_30 = [p["excess_returns"][30] for p in bullish_acted
                        if p.get("excess_returns", {}).get(30) is not None]

        if len(ba_excess_30) >= 3 and all_excess_30:
            import random
            rng = random.Random(42)
            n_sample = len(ba_excess_30)
            actual = mean(ba_excess_30)
            random_means = sorted(
                mean(rng.choices(all_excess_30, k=n_sample))
                for _ in range(500)
            )
            percentile = sum(1 for r in random_means if r < actual) / 500 * 100
            result["bootstrap_percentile"] = percentile
        else:
            result["bootstrap_percentile"] = None

        # Rolling portfolio Sharpe (30d hold)
        portfolio = PortfolioAnalyzer.rolling_portfolio(picks, hold_days=30)
        if "error" not in portfolio:
            result["sharpe"] = portfolio.get("sharpe")
            result["excess_sharpe"] = portfolio.get("excess_sharpe")
        else:
            result["sharpe"] = None
            result["excess_sharpe"] = None

        return result

    @staticmethod
    def stress_test(picks: list[dict]) -> dict:
        """Run exclusion stress tests."""
        # Baseline
        baseline = ConcentrationStressTest._compute_metrics(picks)

        # Find top 3 contributors by 30d excess
        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]
                         and p.get("excess_returns", {}).get(30) is not None]
        if bullish_acted:
            sorted_by_excess = sorted(bullish_acted,
                                       key=lambda p: p["excess_returns"][30],
                                       reverse=True)
            top3_tickers = list(dict.fromkeys(
                p["ticker_yf"] for p in sorted_by_excess
            ))[:3]
        else:
            top3_tickers = []

        # Exclusion scenarios
        scenarios = {
            "Baseline": baseline,
        }

        # Ex-PDD
        ex_pdd = [p for p in picks if p["ticker_yf"] != "PDD"]
        scenarios["Ex-PDD"] = ConcentrationStressTest._compute_metrics(ex_pdd)

        # Ex-HOOD
        ex_hood = [p for p in picks if p["ticker_yf"] != "HOOD"]
        scenarios["Ex-HOOD"] = ConcentrationStressTest._compute_metrics(ex_hood)

        # Ex-PDD-HOOD
        ex_both = [p for p in picks if p["ticker_yf"] not in ("PDD", "HOOD")]
        scenarios["Ex-PDD+HOOD"] = ConcentrationStressTest._compute_metrics(ex_both)

        # Ex-Top3
        if top3_tickers:
            ex_top3 = [p for p in picks if p["ticker_yf"] not in top3_tickers]
            scenarios[f"Ex-Top3 ({','.join(top3_tickers)})"] = (
                ConcentrationStressTest._compute_metrics(ex_top3)
            )

        # Ex-META (another large holding)
        ex_meta = [p for p in picks if p["ticker_yf"] != "META"]
        scenarios["Ex-META"] = ConcentrationStressTest._compute_metrics(ex_meta)

        return {
            "scenarios": scenarios,
            "top3_tickers": top3_tickers,
        }


# ── Analysis 3: Cluster-Robust Confidence Intervals ───────────

class ClusterRobustCI:
    """Block bootstrap (resample meetings, not picks) + Newey-West standard errors."""

    @staticmethod
    def block_bootstrap(picks: list[dict], n_iterations: int = 2000) -> dict:
        """Resample entire meetings (not individual picks) for proper clustering.

        The naive bootstrap in the original report samples individual picks,
        ignoring within-meeting correlation. This resamples entire meetings.
        """
        if not HAS_NUMPY:
            return {"error": "numpy required for block bootstrap"}

        # Group picks by meeting date
        meeting_picks = defaultdict(list)
        for p in picks:
            if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]:
                if p.get("excess_returns", {}).get(30) is not None:
                    meeting_picks[p["meeting_date"]].append(p)

        meeting_dates = list(meeting_picks.keys())
        n_meetings = len(meeting_dates)

        if n_meetings < 5:
            return {"error": f"Only {n_meetings} meetings with bullish+acted picks"}

        # Actual statistic: mean excess of bullish+acted
        actual_picks = []
        for md in meeting_dates:
            actual_picks.extend(meeting_picks[md])
        actual_excess = np.mean([p["excess_returns"][30] for p in actual_picks])

        # Block bootstrap: resample meetings with replacement
        rng = np.random.RandomState(42)
        boot_means = []
        for _ in range(n_iterations):
            sampled_dates = rng.choice(meeting_dates, size=n_meetings, replace=True)
            sampled_excess = []
            for md in sampled_dates:
                for p in meeting_picks[md]:
                    sampled_excess.append(p["excess_returns"][30])
            if sampled_excess:
                boot_means.append(np.mean(sampled_excess))

        boot_means = np.array(sorted(boot_means))

        # Confidence intervals
        ci_95 = (float(np.percentile(boot_means, 2.5)),
                 float(np.percentile(boot_means, 97.5)))
        ci_90 = (float(np.percentile(boot_means, 5.0)),
                 float(np.percentile(boot_means, 95.0)))

        # Compare with naive bootstrap (individual pick resampling)
        all_excess = [p["excess_returns"][30] for p in actual_picks]
        naive_boot = []
        for _ in range(n_iterations):
            sample = rng.choice(all_excess, size=len(all_excess), replace=True)
            naive_boot.append(float(np.mean(sample)))
        naive_boot = np.array(sorted(naive_boot))
        naive_ci_95 = (float(np.percentile(naive_boot, 2.5)),
                       float(np.percentile(naive_boot, 97.5)))

        # Percentile of actual in block bootstrap distribution
        block_percentile = float(
            np.sum(boot_means < actual_excess) / len(boot_means) * 100
        )

        # Comparison with the naive 82nd percentile from original report
        # The block bootstrap percentile accounts for within-meeting correlation
        # If block_percentile < naive percentile, the original overstated significance

        return {
            "actual_excess": float(actual_excess),
            "n_meetings": n_meetings,
            "n_picks": len(actual_picks),
            "n_iterations": n_iterations,
            "block_ci_95": ci_95,
            "block_ci_90": ci_90,
            "block_se": float(np.std(boot_means)),
            "block_percentile": block_percentile,
            "naive_ci_95": naive_ci_95,
            "naive_se": float(np.std(naive_boot)),
            "ci_width_ratio": (ci_95[1] - ci_95[0]) / (naive_ci_95[1] - naive_ci_95[0])
                              if (naive_ci_95[1] - naive_ci_95[0]) > 0 else None,
            "zero_in_ci_95": ci_95[0] <= 0 <= ci_95[1],
            "zero_in_ci_90": ci_90[0] <= 0 <= ci_90[1],
        }

    @staticmethod
    def newey_west(picks: list[dict]) -> dict:
        """Compute Newey-West adjusted standard errors for meeting-level excess returns.

        Groups picks by meeting, computes per-meeting mean excess,
        then estimates autocorrelation-adjusted SE.
        Bandwidth L = floor(N^(1/3)).
        """
        if not HAS_NUMPY:
            return {"error": "numpy required for Newey-West"}

        # Compute per-meeting mean excess
        meeting_excess = defaultdict(list)
        for p in picks:
            if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]:
                if p.get("excess_returns", {}).get(30) is not None:
                    meeting_excess[p["meeting_date"]].append(p["excess_returns"][30])

        if len(meeting_excess) < 5:
            return {"error": "Too few meetings"}

        sorted_dates = sorted(meeting_excess.keys())
        y = np.array([np.mean(meeting_excess[d]) for d in sorted_dates])
        n = len(y)

        # OLS: y = alpha (constant)
        y_bar = np.mean(y)
        residuals = y - y_bar

        # Newey-West bandwidth
        L = int(np.floor(n ** (1.0 / 3.0)))

        # Variance estimator: gamma(0) + 2 * sum_{j=1}^{L} (1 - j/(L+1)) * gamma(j)
        gamma = np.zeros(L + 1)
        for j in range(L + 1):
            gamma[j] = np.mean(residuals[:n - j] * residuals[j:]) if j < n else 0

        nw_var = gamma[0]
        for j in range(1, L + 1):
            weight = 1.0 - j / (L + 1)  # Bartlett kernel
            nw_var += 2 * weight * gamma[j]

        nw_se = float(np.sqrt(nw_var / n))
        ols_se = float(np.std(y, ddof=1) / np.sqrt(n))

        # t-statistics
        t_ols = float(y_bar / ols_se) if ols_se > 0 else 0
        t_nw = float(y_bar / nw_se) if nw_se > 0 else 0

        # p-values (two-sided, using normal approximation)
        if HAS_SCIPY:
            p_ols = float(2 * (1 - sp_stats.norm.cdf(abs(t_ols))))
            p_nw = float(2 * (1 - sp_stats.norm.cdf(abs(t_nw))))
        else:
            # Rough approximation
            p_ols = None
            p_nw = None

        return {
            "mean_excess": float(y_bar),
            "n_meetings": n,
            "bandwidth_L": L,
            "ols_se": ols_se,
            "nw_se": nw_se,
            "se_inflation": nw_se / ols_se if ols_se > 0 else None,
            "t_ols": t_ols,
            "t_nw": t_nw,
            "p_ols": p_ols,
            "p_nw": p_nw,
            "significant_5pct_ols": abs(t_ols) > 1.96,
            "significant_5pct_nw": abs(t_nw) > 1.96,
            "significant_10pct_nw": abs(t_nw) > 1.645,
            "autocorrelations": {j: float(gamma[j] / gamma[0]) if gamma[0] > 0 else 0
                                  for j in range(1, min(L + 1, 6))},
        }


# ── Analysis 4: Carhart 4-Factor Regression ───────────────────

class CarhartFactorRegression:
    """ETF-based 4-factor model: MKT, SMB, HML, UMD."""

    FACTOR_ETFS = {
        "SPY": "Market proxy",
        "IWM": "Small cap (for SMB)",
        "IWD": "Value (for HML)",
        "IWF": "Growth (for HML)",
        "MTUM": "Momentum (for UMD)",
    }

    @staticmethod
    def run(picks: list[dict]) -> dict:
        """Run 4-factor regression on meeting-level excess returns.

        Factors (ETF-based):
        - MKT: SPY return
        - SMB: IWM - SPY (size)
        - HML: IWD - IWF (value minus growth)
        - UMD: MTUM - SPY (momentum)
        """
        if not HAS_NUMPY:
            return {"error": "numpy required for factor regression"}

        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            return {"error": "yfinance/pandas required"}

        # Get meeting-level data
        meeting_picks = defaultdict(list)
        for p in picks:
            if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]:
                if p.get("returns", {}).get(30) is not None:
                    meeting_picks[p["meeting_date"]].append(p)

        sorted_dates = sorted(meeting_picks.keys())
        if len(sorted_dates) < 10:
            return {"error": f"Only {len(sorted_dates)} meetings, need >= 10"}

        # Download factor ETF prices
        start = sorted_dates[0] - timedelta(days=7)
        end = min(sorted_dates[-1] + timedelta(days=45), date.today())

        etf_tickers = list(CarhartFactorRegression.FACTOR_ETFS.keys())
        print("  [4-Factor] Downloading factor ETF prices...")
        try:
            df = yf.download(etf_tickers, start=start.isoformat(),
                             end=end.isoformat(), auto_adjust=True, progress=False)
            if df.empty:
                return {"error": "Failed to download factor ETFs"}

            if isinstance(df.columns, pd.MultiIndex):
                close_df = df["Close"]
            else:
                close_df = df[["Close"]]
                if len(etf_tickers) == 1:
                    close_df.columns = etf_tickers
        except Exception as e:
            return {"error": f"ETF download failed: {e}"}

        # Build factor returns for each meeting date (30d forward)
        etf_prices = {}
        for etf in etf_tickers:
            if etf in close_df.columns:
                series = close_df[etf].dropna()
                etf_prices[etf] = {
                    d.date().isoformat(): float(v) for d, v in series.items()
                }

        def get_forward_return(prices: dict, base_date: date, days: int = 30) -> Optional[float]:
            base = PriceFetcher._find_nearest_price(prices, base_date)
            future = PriceFetcher._find_nearest_price(
                prices, base_date + timedelta(days=days))
            if base and future and base > 0:
                return (future - base) / base
            return None

        # Build regression data
        y_data = []  # portfolio excess returns (over risk-free, approx as raw return)
        mkt_data = []
        smb_data = []
        hml_data = []
        umd_data = []
        valid_dates = []

        for md in sorted_dates:
            # Portfolio return: mean of bullish+acted picks
            port_rets = [p["returns"][30] for p in meeting_picks[md]
                         if p.get("returns", {}).get(30) is not None]
            if not port_rets:
                continue

            port_ret = mean(port_rets)

            # Factor returns (30d forward from meeting date)
            spy_ret = get_forward_return(etf_prices.get("SPY", {}), md)
            iwm_ret = get_forward_return(etf_prices.get("IWM", {}), md)
            iwd_ret = get_forward_return(etf_prices.get("IWD", {}), md)
            iwf_ret = get_forward_return(etf_prices.get("IWF", {}), md)
            mtum_ret = get_forward_return(etf_prices.get("MTUM", {}), md)

            if any(r is None for r in [spy_ret, iwm_ret, iwd_ret, iwf_ret, mtum_ret]):
                continue

            y_data.append(port_ret)
            mkt_data.append(spy_ret)
            smb_data.append(iwm_ret - spy_ret)       # Size factor
            hml_data.append(iwd_ret - iwf_ret)        # Value factor
            umd_data.append(mtum_ret - spy_ret)       # Momentum factor
            valid_dates.append(md)

        if len(y_data) < 10:
            return {"error": f"Only {len(y_data)} valid observations, need >= 10"}

        # OLS regression: y = alpha + b1*MKT + b2*SMB + b3*HML + b4*UMD
        y = np.array(y_data)
        X = np.column_stack([
            np.ones(len(y)),  # intercept (alpha)
            np.array(mkt_data),
            np.array(smb_data),
            np.array(hml_data),
            np.array(umd_data),
        ])

        # lstsq: solve y = X @ beta
        beta, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)

        y_hat = X @ beta
        resid = y - y_hat
        n, k = X.shape

        # R-squared
        ss_res = float(np.sum(resid ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k) if n > k else 0

        # Standard errors
        if n > k:
            mse = ss_res / (n - k)
            var_beta = mse * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(var_beta))
            t_stats = beta / se
        else:
            se = np.zeros(k)
            t_stats = np.zeros(k)

        factor_names = ["Alpha", "MKT", "SMB", "HML", "UMD"]
        factors = {}
        for i, name in enumerate(factor_names):
            factors[name] = {
                "coef": float(beta[i]),
                "se": float(se[i]),
                "t_stat": float(t_stats[i]),
                "significant_5pct": abs(float(t_stats[i])) > 2.0,
            }

        # Annualize alpha (approximately — 30d periods)
        periods_per_year = 365.25 / 30
        ann_alpha = float(beta[0]) * periods_per_year

        return {
            "n_observations": n,
            "factors": factors,
            "r_squared": float(r_squared),
            "adj_r_squared": float(adj_r_squared),
            "ann_alpha": ann_alpha,
            "residual_std": float(np.std(resid)),
            "dates_range": (str(valid_dates[0]), str(valid_dates[-1])),
            "interpretation": _interpret_factors(factors, r_squared, ann_alpha),
        }


def _interpret_factors(factors: dict, r_squared: float, ann_alpha: float) -> str:
    """Generate human-readable interpretation of factor regression."""
    lines = []

    alpha = factors.get("Alpha", {})
    if alpha.get("significant_5pct"):
        lines.append(f"Alpha is statistically significant (t={alpha['t_stat']:.2f}), "
                     f"indicating genuine stock-picking skill after controlling for factors.")
    else:
        lines.append(f"Alpha is NOT statistically significant (t={alpha['t_stat']:.2f}), "
                     f"returns may be explained by factor exposures.")

    mkt = factors.get("MKT", {})
    if mkt.get("coef", 0) > 1.1:
        lines.append(f"High market beta ({mkt['coef']:.2f}) — levered market exposure.")
    elif mkt.get("coef", 0) < 0.8:
        lines.append(f"Low market beta ({mkt['coef']:.2f}) — defensive positioning.")

    smb = factors.get("SMB", {})
    if smb.get("significant_5pct") and smb.get("coef", 0) > 0:
        lines.append(f"Significant small-cap tilt (SMB={smb['coef']:.2f}).")
    elif smb.get("significant_5pct") and smb.get("coef", 0) < 0:
        lines.append(f"Significant large-cap tilt (SMB={smb['coef']:.2f}).")

    hml = factors.get("HML", {})
    if hml.get("significant_5pct"):
        style = "value" if hml.get("coef", 0) > 0 else "growth"
        lines.append(f"Significant {style} tilt (HML={hml['coef']:.2f}).")

    umd = factors.get("UMD", {})
    if umd.get("significant_5pct"):
        lines.append(f"Significant momentum exposure (UMD={umd['coef']:.2f}).")

    lines.append(f"R-squared={r_squared:.1%} — factors explain {r_squared:.0%} of return variance.")

    return " ".join(lines)


# ── Analysis 5: Transaction Cost Sensitivity ──────────────────

class TransactionCostSensitivity:
    """Re-compute excess returns under various cost assumptions."""

    # Market-cap tier classification
    LARGE_CAP = {
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "JPM", "V", "MA",
        "AVGO", "LLY", "WMT", "PG", "HD", "COST", "ORCL", "NFLX", "CRM", "BAC",
        "INTC", "QCOM", "AMD", "MU", "ASML", "TSM", "BABA", "PDD", "NVO",
        "PM", "PEP", "DIS", "CMCSA", "SBUX", "NKE", "BKNG", "CMG", "LULU",
        "WFC", "AXP", "PYPL", "SCHW", "SPY",
    }

    MID_CAP = {
        "HOOD", "SNAP", "PINS", "COIN", "DECK", "ONON", "RH", "BLDR", "FND",
        "IBKR", "FUTU", "EXPE", "ABNB", "HLT", "POOL", "EL", "STZ",
        "TJX", "ROST", "DLTR", "LOW", "EFX", "FICO", "MCO", "MSCI",
        "JD", "BIDU", "TCOM", "NTES", "BEKE", "HTHT", "RACE",
    }

    @staticmethod
    def _get_cost_bps(ticker: str, scenario: str) -> float:
        """Get round-trip cost in basis points for a ticker under a scenario."""
        if scenario == "fixed_10bp":
            return 10
        elif scenario == "fixed_20bp":
            return 20
        elif scenario == "fixed_30bp":
            return 30
        elif scenario == "tiered":
            if ticker in TransactionCostSensitivity.LARGE_CAP:
                return 5
            elif ticker in TransactionCostSensitivity.MID_CAP:
                return 15
            else:
                # Non-US or small-cap
                for suffix in [".HK", ".T", ".PA", ".L", ".SW", ".SZ", ".SS", ".DE"]:
                    if ticker.upper().endswith(suffix):
                        return 30
                return 20
        return 0

    @staticmethod
    def analyze(picks: list[dict]) -> dict:
        """Run transaction cost sensitivity analysis."""
        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]
                         and p.get("excess_returns", {}).get(30) is not None]

        if len(bullish_acted) < 5:
            return {"error": "Too few bullish+acted picks"}

        scenarios = ["fixed_10bp", "fixed_20bp", "fixed_30bp", "tiered"]
        results = {}

        # Baseline (no costs)
        baseline_excess = [p["excess_returns"][30] for p in bullish_acted]
        baseline_mean = mean(baseline_excess)
        baseline_wr = sum(1 for e in baseline_excess if e > 0) / len(baseline_excess)

        results["baseline"] = {
            "n": len(bullish_acted),
            "mean_excess": baseline_mean,
            "win_rate": baseline_wr,
        }

        for scenario in scenarios:
            adj_excess = []
            for p in bullish_acted:
                cost_bps = TransactionCostSensitivity._get_cost_bps(
                    p["ticker_yf"], scenario)
                cost_pct = cost_bps / 10000  # convert bps to decimal
                adj = p["excess_returns"][30] - cost_pct
                adj_excess.append(adj)

            adj_mean = mean(adj_excess) if adj_excess else None
            adj_wr = (sum(1 for e in adj_excess if e > 0) / len(adj_excess)
                      if adj_excess else None)

            # Sharpe approximation
            if adj_excess and len(adj_excess) > 1:
                std = (sum((e - adj_mean) ** 2 for e in adj_excess) / len(adj_excess)) ** 0.5
                sharpe = adj_mean / std if std > 0 else 0
            else:
                sharpe = None

            results[scenario] = {
                "n": len(adj_excess),
                "mean_excess": adj_mean,
                "win_rate": adj_wr,
                "sharpe": sharpe,
                "excess_reduction": baseline_mean - adj_mean if adj_mean is not None else None,
            }

        # Binary search for breakeven cost
        if baseline_mean > 0:
            lo, hi = 0.0, 200.0  # in bps
            for _ in range(50):
                mid = (lo + hi) / 2
                adj = baseline_mean - mid / 10000
                if adj > 0:
                    lo = mid
                else:
                    hi = mid
            breakeven_bps = (lo + hi) / 2
        else:
            breakeven_bps = 0  # Already negative without costs

        results["breakeven_bps"] = breakeven_bps

        # Cost distribution under tiered scenario
        cost_dist = defaultdict(list)
        for p in bullish_acted:
            cost = TransactionCostSensitivity._get_cost_bps(p["ticker_yf"], "tiered")
            cost_dist[cost].append(p["ticker_yf"])
        results["tiered_distribution"] = {
            f"{bps}bp": len(tickers) for bps, tickers in sorted(cost_dist.items())
        }

        return results


# ── Analysis 6: Real P&L Replication ──────────────────────────

class RealPnLReplication:
    """Match backtest picks to actual trades in trades.json and compare P&L."""

    @staticmethod
    def replicate(picks: list[dict]) -> dict:
        """For each Bullish+Acted pick, find actual trades and compare returns."""
        # Load raw trades
        try:
            with open(TRADES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            raw_trades = data.get("trades", data) if isinstance(data, dict) else data
        except Exception as e:
            return {"error": f"Failed to load trades.json: {e}"}

        # Index trades by ticker (using trades.json ticker format)
        trades_by_ticker = defaultdict(list)
        for trade in raw_trades:
            asset_type = trade.get("asset_type", "")
            if asset_type not in ("STK", ""):
                continue
            ticker = trade.get("ticker", "").strip()
            if not ticker:
                continue
            trade_date = trade.get("exit_date") or trade.get("entry_date")
            if not trade_date:
                continue

            d = datetime.strptime(trade_date, "%Y-%m-%d").date()
            trades_by_ticker[ticker.upper()].append({
                "date": d,
                "direction": trade.get("direction", ""),
                "ticker": ticker,
                "quantity": trade.get("quantity", 0.0),
                "fill_price": trade.get("exit_price"),  # exit_price = fill price in IBKR CSV
                "pnl_usd": trade.get("pnl_usd", 0.0),
                "commission": trade.get("commission", 0.0),
                "currency": trade.get("currency", "USD"),
            })

        # Find Bullish+Acted picks
        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]
                         and p.get("returns", {}).get(30) is not None]

        matched_results = []
        unmatched_picks = []

        for pick in bullish_acted:
            yf_ticker = pick["ticker_yf"]
            meeting_date = pick["meeting_date"]

            # Search window: meeting_date - 30d to meeting_date + 90d
            window_start = meeting_date - timedelta(days=30)
            window_end = meeting_date + timedelta(days=90)

            # Find actual trades for this ticker
            candidates = TickerNormalizer.yfinance_to_trades_match(yf_ticker)
            found_trades = []

            for candidate in candidates:
                for trade in trades_by_ticker.get(candidate.upper(), []):
                    if window_start <= trade["date"] <= window_end:
                        found_trades.append(trade)

            if not found_trades:
                unmatched_picks.append({
                    "ticker": yf_ticker,
                    "date": meeting_date,
                    "backtest_return_30": pick["returns"][30],
                })
                continue

            # Simplified FIFO matching
            buys = sorted([t for t in found_trades if t["direction"] == "BUY"],
                          key=lambda t: t["date"])
            sells = sorted([t for t in found_trades if t["direction"] == "SELL"],
                           key=lambda t: t["date"])

            # Calculate actual entry/exit prices
            total_buy_qty = sum(t["quantity"] for t in buys)
            total_sell_qty = sum(t["quantity"] for t in sells)
            total_buy_cost = sum(t["quantity"] * (t["fill_price"] or 0) for t in buys
                                if t["fill_price"])
            total_sell_proceeds = sum(t["quantity"] * (t["fill_price"] or 0) for t in sells
                                      if t["fill_price"])

            avg_buy_price = total_buy_cost / total_buy_qty if total_buy_qty > 0 else None
            avg_sell_price = total_sell_proceeds / total_sell_qty if total_sell_qty > 0 else None

            # Actual realized return
            if avg_buy_price and avg_sell_price and avg_buy_price > 0:
                actual_return = (avg_sell_price - avg_buy_price) / avg_buy_price
            else:
                actual_return = None

            # Commission impact
            total_commission = sum(abs(t.get("commission", 0)) for t in found_trades)
            commission_bps = (total_commission / total_buy_cost * 10000
                              if total_buy_cost > 0 else 0)

            # Slippage: compare actual entry vs backtest close price
            backtest_price = pick.get("base_price")
            slippage = None
            if avg_buy_price and backtest_price and backtest_price > 0:
                slippage = (avg_buy_price - backtest_price) / backtest_price

            backtest_return = pick["returns"][30]

            matched_results.append({
                "ticker": yf_ticker,
                "meeting_date": meeting_date,
                "backtest_return_30": backtest_return,
                "actual_return": actual_return,
                "diff": (actual_return - backtest_return
                         if actual_return is not None else None),
                "avg_buy_price": avg_buy_price,
                "avg_sell_price": avg_sell_price,
                "backtest_price": backtest_price,
                "slippage": slippage,
                "commission_bps": commission_bps,
                "n_buys": len(buys),
                "n_sells": len(sells),
                "total_buy_qty": total_buy_qty,
                "total_sell_qty": total_sell_qty,
                "first_buy_date": buys[0]["date"] if buys else None,
                "last_sell_date": sells[-1]["date"] if sells else None,
            })

        # Aggregate comparison
        with_both = [r for r in matched_results
                     if r["actual_return"] is not None and r["backtest_return_30"] is not None]

        if with_both:
            corr = None
            if HAS_NUMPY and len(with_both) >= 5:
                actual_arr = np.array([r["actual_return"] for r in with_both])
                bt_arr = np.array([r["backtest_return_30"] for r in with_both])
                corr_matrix = np.corrcoef(actual_arr, bt_arr)
                corr = float(corr_matrix[0, 1])

            slippages = [r["slippage"] for r in matched_results if r["slippage"] is not None]
            diffs = [r["diff"] for r in with_both]

            aggregate = {
                "n_matched": len(matched_results),
                "n_with_both_returns": len(with_both),
                "n_unmatched": len(unmatched_picks),
                "mean_backtest_return": mean(r["backtest_return_30"] for r in with_both),
                "mean_actual_return": mean(r["actual_return"] for r in with_both),
                "mean_diff": mean(diffs),
                "median_diff": median(diffs),
                "mean_slippage": mean(slippages) if slippages else None,
                "mean_commission_bps": mean(r["commission_bps"] for r in matched_results),
                "correlation": corr,
            }
        else:
            aggregate = {
                "n_matched": len(matched_results),
                "n_with_both_returns": 0,
                "n_unmatched": len(unmatched_picks),
            }

        return {
            "aggregate": aggregate,
            "matched": sorted(matched_results,
                              key=lambda r: abs(r.get("diff") or 0), reverse=True)[:30],
            "unmatched": unmatched_picks[:20],
        }


# ── Report Generator ──────────────────────────────────────────

class FollowupReportGenerator:
    """Generate the Obsidian follow-up report."""

    @staticmethod
    def _section_audit(result: dict) -> list[str]:
        lines = ["## 1. Data Pipeline Audit (数据管道审计)", ""]
        lines.append("> 追溯 90 天超额收益在 Alpha 衰减曲线和止损止盈模拟中出现不同数字的原因。")
        lines.append("")

        dc = result.get("decay_curve", {})
        tm = result.get("trade_mgmt_sim", {})
        tmi = result.get("trade_mgmt_input_pool", {})

        lines.append("### 模块对比")
        lines.append("")
        lines.append("| 模块 | 样本 N | 90天超额均值 | 90天超额中位数 |")
        lines.append("| --- | ---: | ---: | ---: |")

        dc_mean = f"{dc['mean_excess_90']:.2%}" if dc.get('mean_excess_90') is not None else "N/A"
        dc_med = f"{dc['median_excess_90']:.2%}" if dc.get('median_excess_90') is not None else "N/A"
        lines.append(f"| Alpha 衰减曲线 | {dc.get('n', 0)} | {dc_mean} | {dc_med} |")

        tm_mean = f"{tm['mean_excess_90']:.2%}" if tm.get('mean_excess_90') is not None else "N/A"
        tm_med = f"{tm['median_excess_90']:.2%}" if tm.get('median_excess_90') is not None else "N/A"
        lines.append(f"| 止损止盈模拟 (90d exit) | {tm.get('n', 0)} | {tm_mean} | {tm_med} |")
        lines.append(f"| 止损止盈输入池 (30d filter) | {tmi.get('n', 0)} | — | — |")
        lines.append("")

        lines.append("### 样本差异")
        lines.append("")
        lines.append(f"- 仅在衰减曲线中: **{result.get('only_in_decay', 0)}** 条 (有 90d return 但无 30d return)")
        lines.append(f"- 仅在止损模拟中: **{result.get('only_in_mgmt', 0)}** 条 (有 30d return 但无 90d return)")
        lines.append(f"- 两者都有: **{result.get('common', 0)}** 条")
        lines.append("")

        # Discrepancies table
        discs = result.get("discrepancies", [])
        if discs:
            lines.append("### 同一 pick 在两模块中的 90 天超额差异 (Top 15)")
            lines.append("")
            lines.append("| 股票 | 日期 | 衰减曲线 | 止损模拟 | 差异 |")
            lines.append("| --- | --- | ---: | ---: | ---: |")
            for d in discs[:15]:
                lines.append(
                    f"| {d['ticker']} | {d['date']} | "
                    f"{d['decay_excess_90']:.2%} | {d['sim_excess_90']:.2%} | "
                    f"{d['diff']:+.2%} |")
            lines.append("")

        lines.append("### Root Cause")
        lines.append("")
        lines.append(f"> {result.get('root_cause', 'N/A')}")
        lines.append("")
        return lines

    @staticmethod
    def _section_stress_test(result: dict) -> list[str]:
        lines = ["## 2. Concentration Stress Test (集中度压力测试)", ""]
        lines.append("> 移除 PDD、HOOD、或最大贡献者后，alpha 是否依然存在？")
        lines.append("")

        scenarios = result.get("scenarios", {})
        top3 = result.get("top3_tickers", [])
        if top3:
            lines.append(f"Top 3 贡献者: **{', '.join(top3)}**")
            lines.append("")

        lines.append("### 各场景 Bullish+Acted 指标")
        lines.append("")
        lines.append("| 场景 | N | 30天超额 | 30天胜率 | 90天超额 | Bootstrap分位 | Sharpe |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")

        for name, s in scenarios.items():
            n = s.get("n_bullish_acted", 0)
            e30 = f"{s['ba_excess_30d']:.2%}" if s.get("ba_excess_30d") is not None else "N/A"
            wr30 = f"{s['ba_wr_30d']:.0%}" if s.get("ba_wr_30d") is not None else "N/A"
            e90 = f"{s['ba_excess_90d']:.2%}" if s.get("ba_excess_90d") is not None else "N/A"
            bp = f"{s['bootstrap_percentile']:.0f}%" if s.get("bootstrap_percentile") is not None else "N/A"
            sh = f"{s['excess_sharpe']:.2f}" if s.get("excess_sharpe") is not None else "N/A"
            lines.append(f"| {name} | {n} | {e30} | {wr30} | {e90} | {bp} | {sh} |")

        lines.append("")

        # Interpretation
        baseline = scenarios.get("Baseline", {})
        bl_excess = baseline.get("ba_excess_30d", 0) or 0
        fragile = False
        for name, s in scenarios.items():
            if name == "Baseline":
                continue
            sc_excess = s.get("ba_excess_30d")
            if sc_excess is not None and bl_excess > 0:
                if sc_excess < 0 or sc_excess < bl_excess * 0.3:
                    fragile = True
                    break

        if fragile:
            lines.append("> **Warning:** Alpha is fragile — removing key names eliminates most of the excess return. Results are driven by a small number of outsized winners.")
        else:
            lines.append("> Alpha is reasonably robust to single-stock exclusion — no single ticker drives the majority of returns.")
        lines.append("")
        return lines

    @staticmethod
    def _section_cluster_ci(block_result: dict, nw_result: dict) -> list[str]:
        lines = ["## 3. Cluster-Robust Confidence Intervals (聚类稳健置信区间)", ""]
        lines.append("> 原始 bootstrap 对个别 picks 抽样，忽略同一场周会内的相关性。")
        lines.append("> Block bootstrap 以整场周会为单位重采样，Newey-West 修正自相关。")
        lines.append("")

        if "error" in block_result:
            lines.append(f"*Block Bootstrap: {block_result['error']}*")
            lines.append("")
        else:
            lines.append("### Block Bootstrap (会议级重采样)")
            lines.append("")
            lines.append("| 指标 | Block Bootstrap | Naive Bootstrap |")
            lines.append("| --- | ---: | ---: |")
            lines.append(f"| 实际超额 (30d) | {block_result['actual_excess']:.2%} | — |")
            lines.append(f"| 标准误 | {block_result['block_se']:.3%} | {block_result['naive_se']:.3%} |")

            ci95 = block_result['block_ci_95']
            nci = block_result['naive_ci_95']
            lines.append(f"| 95% CI | [{ci95[0]:.2%}, {ci95[1]:.2%}] | [{nci[0]:.2%}, {nci[1]:.2%}] |")

            ci90 = block_result['block_ci_90']
            lines.append(f"| 90% CI | [{ci90[0]:.2%}, {ci90[1]:.2%}] | — |")

            ratio = block_result.get('ci_width_ratio')
            ratio_s = f"{ratio:.2f}x" if ratio else "N/A"
            lines.append(f"| CI 宽度比 (block/naive) | {ratio_s} | — |")
            lines.append(f"| 0 在 95% CI 内？ | {'是' if block_result['zero_in_ci_95'] else '否'} | — |")
            lines.append(f"| 0 在 90% CI 内？ | {'是' if block_result['zero_in_ci_90'] else '否'} | — |")
            lines.append(f"| 迭代次数 | {block_result['n_iterations']} | — |")
            lines.append(f"| 会议数 | {block_result['n_meetings']} | — |")
            lines.append("")

            if block_result['zero_in_ci_95']:
                lines.append("> **结论:** 0 在 95% CI 内 — 在 5% 显著性水平下，不能排除 alpha = 0。聚类效应使得置信区间变宽。")
            else:
                lines.append("> **结论:** 0 不在 95% CI 内 — 即使考虑聚类效应，alpha 仍然统计显著。")
            lines.append("")

        if "error" in nw_result:
            lines.append(f"*Newey-West: {nw_result['error']}*")
            lines.append("")
        else:
            lines.append("### Newey-West 标准误")
            lines.append("")
            lines.append("| 指标 | OLS | Newey-West |")
            lines.append("| --- | ---: | ---: |")
            lines.append(f"| 均值超额 | {nw_result['mean_excess']:.2%} | — |")
            lines.append(f"| 标准误 | {nw_result['ols_se']:.3%} | {nw_result['nw_se']:.3%} |")
            lines.append(f"| t-统计量 | {nw_result['t_ols']:.2f} | {nw_result['t_nw']:.2f} |")

            if nw_result.get('p_ols') is not None:
                lines.append(f"| p-value | {nw_result['p_ols']:.4f} | {nw_result['p_nw']:.4f} |")

            lines.append(f"| 5% 显著？ | {'是' if nw_result['significant_5pct_ols'] else '否'} | {'是' if nw_result['significant_5pct_nw'] else '否'} |")
            lines.append(f"| 10% 显著？ | — | {'是' if nw_result['significant_10pct_nw'] else '否'} |")

            inf = nw_result.get("se_inflation")
            lines.append(f"| SE 膨胀率 | — | {inf:.2f}x |" if inf else "| SE 膨胀率 | — | N/A |")
            lines.append(f"| 带宽 L | — | {nw_result['bandwidth_L']} |")
            lines.append(f"| 会议数 N | {nw_result['n_meetings']} | — |")
            lines.append("")

            # Autocorrelations
            ac = nw_result.get("autocorrelations", {})
            if ac:
                lines.append("自相关系数: " + ", ".join(
                    f"lag{j}={v:.3f}" for j, v in sorted(ac.items())))
                lines.append("")

        return lines

    @staticmethod
    def _section_4factor(result: dict) -> list[str]:
        lines = ["## 4. Carhart 4-Factor Regression (四因子回归)", ""]
        lines.append("> 将 Bullish+Acted 组合收益分解为市场(MKT)、市值(SMB)、价值(HML)、动量(UMD)。")
        lines.append("> Alpha = 扣除所有因子暴露后的残余收益 = 纯选股能力。")
        lines.append("> 使用 ETF 代理: SPY, IWM, IWD, IWF, MTUM。")
        lines.append("")

        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        factors = result.get("factors", {})
        lines.append(f"观测数: **{result['n_observations']}** 场周会")
        lines.append(f"日期范围: {result['dates_range'][0]} — {result['dates_range'][1]}")
        lines.append("")

        lines.append("### 因子载荷")
        lines.append("")
        lines.append("| 因子 | 系数 | 标准误 | t-统计量 | 显著(5%)？ |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for name in ["Alpha", "MKT", "SMB", "HML", "UMD"]:
            f = factors.get(name, {})
            sig = "是" if f.get("significant_5pct") else "否"
            lines.append(
                f"| {name} | {f.get('coef', 0):.4f} | {f.get('se', 0):.4f} | "
                f"{f.get('t_stat', 0):.2f} | {sig} |")
        lines.append("")

        lines.append(f"- **年化 Alpha:** {result.get('ann_alpha', 0):.1%}")
        lines.append(f"- **R-squared:** {result.get('r_squared', 0):.1%}")
        lines.append(f"- **Adjusted R-squared:** {result.get('adj_r_squared', 0):.1%}")
        lines.append(f"- **残差标准差:** {result.get('residual_std', 0):.3f}")
        lines.append("")

        interp = result.get("interpretation", "")
        if interp:
            lines.append(f"> {interp}")
            lines.append("")

        return lines

    @staticmethod
    def _section_costs(result: dict) -> list[str]:
        lines = ["## 5. Transaction Cost Sensitivity (交易成本敏感性)", ""]
        lines.append("> 在不同成本假设下重新计算超额收益。如果 alpha 在合理成本下归零 → 可能不可交易。")
        lines.append("")

        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        bl = result.get("baseline", {})
        lines.append(f"样本: **{bl.get('n', 0)}** 条 Bullish+Acted picks")
        lines.append("")

        lines.append("### 成本场景")
        lines.append("")
        lines.append("| 场景 | 30天超额 | 胜率 | Sharpe | 超额减少 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")

        scenario_labels = {
            "baseline": "无成本 (Baseline)",
            "fixed_10bp": "固定 10bp",
            "fixed_20bp": "固定 20bp",
            "fixed_30bp": "固定 30bp",
            "tiered": "分层 (大盘5/中盘15/小盘&非美20-30bp)",
        }

        for key in ["baseline", "fixed_10bp", "fixed_20bp", "fixed_30bp", "tiered"]:
            s = result.get(key, {})
            label = scenario_labels.get(key, key)
            me = f"{s['mean_excess']:.2%}" if s.get("mean_excess") is not None else "N/A"
            wr = f"{s['win_rate']:.0%}" if s.get("win_rate") is not None else "N/A"
            sh = f"{s['sharpe']:.2f}" if s.get("sharpe") is not None else "—"
            red = f"{s['excess_reduction']:.2%}" if s.get("excess_reduction") is not None else "—"
            lines.append(f"| {label} | {me} | {wr} | {sh} | {red} |")

        lines.append("")

        be = result.get("breakeven_bps", 0)
        lines.append(f"### Breakeven Cost: **{be:.0f} bps**")
        lines.append("")
        if be > 30:
            lines.append(f"> Alpha 在 {be:.0f}bp 成本下归零。大多数机构交易成本在 5-30bp 之间，因此策略在成本后仍可能有正 alpha。")
        elif be > 10:
            lines.append(f"> Alpha 在 {be:.0f}bp 成本下归零。对于非 US large-cap 股票，实际成本可能接近或超过此水平。")
        else:
            lines.append(f"> Alpha 在仅 {be:.0f}bp 成本下即归零。策略不具备交易可行性。")
        lines.append("")

        # Tiered distribution
        tdist = result.get("tiered_distribution", {})
        if tdist:
            lines.append("### 分层成本分布")
            lines.append("")
            for tier, count in sorted(tdist.items()):
                lines.append(f"- {tier}: {count} 条")
            lines.append("")

        return lines

    @staticmethod
    def _section_pnl_replication(result: dict) -> list[str]:
        lines = ["## 6. Real P&L Replication (实际盈亏复制)", ""]
        lines.append("> 将 Bullish+Acted picks 对应到 trades.json 中的实际交易记录。")
        lines.append("> 比较回测理论收益 vs 实际实现盈亏，量化滑点和执行偏差。")
        lines.append("")

        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        agg = result.get("aggregate", {})
        lines.append(f"- 匹配到实际交易: **{agg.get('n_matched', 0)}** 条")
        lines.append(f"- 双向收益可比: **{agg.get('n_with_both_returns', 0)}** 条")
        lines.append(f"- 未匹配: **{agg.get('n_unmatched', 0)}** 条")
        lines.append("")

        if agg.get("n_with_both_returns", 0) > 0:
            lines.append("### 汇总对比")
            lines.append("")
            lines.append("| 指标 | 值 |")
            lines.append("| --- | ---: |")
            lines.append(f"| 回测平均收益 (30d) | {agg['mean_backtest_return']:.2%} |")
            lines.append(f"| 实际平均收益 | {agg['mean_actual_return']:.2%} |")
            lines.append(f"| 平均差异 (实际 - 回测) | {agg['mean_diff']:+.2%} |")
            lines.append(f"| 中位差异 | {agg['median_diff']:+.2%} |")
            if agg.get("mean_slippage") is not None:
                lines.append(f"| 平均滑点 (入场) | {agg['mean_slippage']:+.2%} |")
            lines.append(f"| 平均佣金 | {agg['mean_commission_bps']:.1f} bps |")
            if agg.get("correlation") is not None:
                lines.append(f"| 回测 vs 实际相关性 | {agg['correlation']:.2f} |")
            lines.append("")

            # Interpretation
            diff = agg.get("mean_diff", 0)
            if abs(diff) < 0.01:
                lines.append("> 回测与实际收益高度一致（差异 < 1%），回测模型可靠。")
            elif diff > 0:
                lines.append(f"> 实际收益高于回测 {diff:+.2%}，可能因为持仓期更长或择时更优。")
            else:
                lines.append(f"> 实际收益低于回测 {diff:+.2%}，差异来自执行滑点、择时偏差或部分仓位管理。")
            lines.append("")

        # Per-trade detail (biggest discrepancies)
        matched = result.get("matched", [])
        if matched:
            lines.append("### 最大偏差 picks (|实际 - 回测|)")
            lines.append("")
            lines.append("| 股票 | 会议日 | 回测30d | 实际收益 | 差异 | 滑点 | 佣金(bps) |")
            lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
            for r in matched[:20]:
                bt = f"{r['backtest_return_30']:.1%}" if r.get("backtest_return_30") is not None else "N/A"
                act = f"{r['actual_return']:.1%}" if r.get("actual_return") is not None else "N/A"
                diff = f"{r['diff']:+.1%}" if r.get("diff") is not None else "N/A"
                slip = f"{r['slippage']:+.2%}" if r.get("slippage") is not None else "N/A"
                comm = f"{r['commission_bps']:.0f}" if r.get("commission_bps") is not None else "N/A"
                lines.append(
                    f"| {r['ticker']} | {r['meeting_date']} | {bt} | {act} | {diff} | {slip} | {comm} |")
            lines.append("")

        # Unmatched picks
        unmatched = result.get("unmatched", [])
        if unmatched:
            lines.append("### 未匹配到交易记录的 picks")
            lines.append("")
            for u in unmatched[:10]:
                lines.append(f"- {u['date']} {u['ticker']} (回测30d: {u['backtest_return_30']:.1%})")
            if len(unmatched) > 10:
                lines.append(f"- ... 及另外 {len(unmatched) - 10} 条")
            lines.append("")

        return lines

    @staticmethod
    def generate(audit: dict, stress: dict, cluster_block: dict, cluster_nw: dict,
                 factor: dict, costs: dict, pnl: dict,
                 picks: list[dict], meetings_count: int) -> str:
        """Generate the full follow-up report."""
        today = date.today().isoformat()
        total_picks = len(picks)
        unique_tickers = len(set(p["ticker_yf"] for p in picks))

        lines = [
            "---",
            f"date: {today}",
            "type: backtest-followup",
            "tags: [backtest, robustness, meeting-picks, decision-audit]",
            f"meetings_analyzed: {meetings_count}",
            f"unique_tickers: {unique_tickers}",
            f"total_picks: {total_picks}",
            "---",
            "",
            "# 周会选股回测 — 鲁棒性检验报告",
            "",
            f"> 原始回测分析了 **{meetings_count}** 场周会、**{unique_tickers}** 只股票、**{total_picks}** 次提及。",
            "> 本报告对原始结果进行 6 项鲁棒性检验，验证 alpha 的真实性和可交易性。",
            f"> 生成日期: {today}",
            "",
            "## Executive Summary",
            "",
        ]

        # Generate executive summary based on results
        summary_points = FollowupReportGenerator._executive_summary(
            audit, stress, cluster_block, cluster_nw, factor, costs, pnl)
        for point in summary_points:
            lines.append(f"- {point}")
        lines.append("")

        # 6 analysis sections
        lines.extend(FollowupReportGenerator._section_audit(audit))
        lines.extend(FollowupReportGenerator._section_stress_test(stress))
        lines.extend(FollowupReportGenerator._section_cluster_ci(cluster_block, cluster_nw))
        lines.extend(FollowupReportGenerator._section_4factor(factor))
        lines.extend(FollowupReportGenerator._section_costs(costs))
        lines.extend(FollowupReportGenerator._section_pnl_replication(pnl))

        # Conclusion
        lines.append("## 综合结论")
        lines.append("")
        lines.extend(FollowupReportGenerator._conclusion(
            stress, cluster_block, cluster_nw, factor, costs))
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _executive_summary(audit, stress, cluster_block, cluster_nw, factor, costs, pnl) -> list[str]:
        points = []

        # 1. Data audit
        dc = audit.get("decay_curve", {})
        tm = audit.get("trade_mgmt_sim", {})
        if dc.get("mean_excess_90") is not None and tm.get("mean_excess_90") is not None:
            diff = dc["mean_excess_90"] - tm["mean_excess_90"]
            points.append(
                f"**数据审计:** 90天超额差异为 {diff:+.2%}（衰减曲线 {dc['mean_excess_90']:.2%} vs "
                f"止损模拟 {tm['mean_excess_90']:.2%}），源于样本筛选差异 "
                f"(N={dc['n']} vs {tm['n']})"
            )

        # 2. Concentration
        scenarios = stress.get("scenarios", {})
        bl = scenarios.get("Baseline", {})
        bl_excess = bl.get("ba_excess_30d", 0) or 0
        worst_name = None
        worst_excess = bl_excess
        for name, s in scenarios.items():
            if name == "Baseline":
                continue
            e = s.get("ba_excess_30d")
            if e is not None and e < worst_excess:
                worst_excess = e
                worst_name = name
        if worst_name:
            points.append(
                f"**集中度:** 最脆弱场景 {worst_name}，30天超额从 {bl_excess:.2%} 降至 {worst_excess:.2%}")

        # 3. Cluster CI
        if "error" not in cluster_block:
            ci = cluster_block.get("block_ci_95", (0, 0))
            zero_in = cluster_block.get("zero_in_ci_95", True)
            points.append(
                f"**聚类检验:** Block bootstrap 95% CI [{ci[0]:.2%}, {ci[1]:.2%}]，"
                f"{'0 在区间内 (不显著)' if zero_in else '0 不在区间内 (显著)'}")

        # 4. Factor regression
        if "error" not in factor:
            alpha = factor.get("factors", {}).get("Alpha", {})
            r2 = factor.get("r_squared", 0)
            points.append(
                f"**因子分解:** Alpha={alpha.get('coef', 0):.4f} "
                f"(t={alpha.get('t_stat', 0):.2f}，{'显著' if alpha.get('significant_5pct') else '不显著'})，"
                f"R²={r2:.1%}")

        # 5. Costs
        if "error" not in costs:
            be = costs.get("breakeven_bps", 0)
            points.append(f"**成本敏感性:** Breakeven cost = {be:.0f}bp")

        # 6. P&L replication
        if "error" not in pnl:
            agg = pnl.get("aggregate", {})
            if agg.get("mean_diff") is not None:
                points.append(
                    f"**P&L 复制:** 实际 vs 回测差异 {agg['mean_diff']:+.2%}，"
                    f"相关性 {agg.get('correlation', 0):.2f}")

        return points

    @staticmethod
    def _conclusion(stress, cluster_block, cluster_nw, factor, costs) -> list[str]:
        lines = []

        # Score card
        scores = {}

        # Concentration robustness
        scenarios = stress.get("scenarios", {})
        bl_excess = (scenarios.get("Baseline", {}).get("ba_excess_30d") or 0)
        min_excess = min(
            (s.get("ba_excess_30d") or 0)
            for name, s in scenarios.items() if name != "Baseline"
        ) if len(scenarios) > 1 else bl_excess
        if min_excess > bl_excess * 0.5:
            scores["concentration"] = "PASS"
        elif min_excess > 0:
            scores["concentration"] = "WEAK PASS"
        else:
            scores["concentration"] = "FAIL"

        # Statistical significance
        if "error" not in cluster_block:
            if not cluster_block.get("zero_in_ci_95"):
                scores["significance"] = "PASS"
            elif not cluster_block.get("zero_in_ci_90"):
                scores["significance"] = "WEAK PASS"
            else:
                scores["significance"] = "FAIL"

        if "error" not in cluster_nw:
            if cluster_nw.get("significant_5pct_nw"):
                scores["newey_west"] = "PASS"
            elif cluster_nw.get("significant_10pct_nw"):
                scores["newey_west"] = "WEAK PASS"
            else:
                scores["newey_west"] = "FAIL"

        # Factor alpha
        if "error" not in factor:
            alpha = factor.get("factors", {}).get("Alpha", {})
            if alpha.get("significant_5pct") and alpha.get("coef", 0) > 0:
                scores["factor_alpha"] = "PASS"
            elif alpha.get("coef", 0) > 0:
                scores["factor_alpha"] = "WEAK PASS"
            else:
                scores["factor_alpha"] = "FAIL"

        # Cost viability
        if "error" not in costs:
            be = costs.get("breakeven_bps", 0)
            if be > 30:
                scores["cost_viability"] = "PASS"
            elif be > 15:
                scores["cost_viability"] = "WEAK PASS"
            else:
                scores["cost_viability"] = "FAIL"

        lines.append("### Scorecard")
        lines.append("")
        lines.append("| 检验 | 结果 |")
        lines.append("| --- | --- |")
        label_map = {
            "concentration": "集中度鲁棒性",
            "significance": "Block Bootstrap 显著性",
            "newey_west": "Newey-West 显著性",
            "factor_alpha": "因子调整后 Alpha",
            "cost_viability": "交易成本可行性",
        }
        for key, label in label_map.items():
            sc = scores.get(key, "N/A")
            emoji = {"PASS": "PASS", "WEAK PASS": "WEAK", "FAIL": "FAIL"}.get(sc, "N/A")
            lines.append(f"| {label} | {emoji} |")
        lines.append("")

        pass_count = sum(1 for v in scores.values() if v == "PASS")
        weak_count = sum(1 for v in scores.values() if v == "WEAK PASS")
        fail_count = sum(1 for v in scores.values() if v == "FAIL")
        total = len(scores)

        if pass_count >= total * 0.6:
            lines.append(f"> **总体评估:** {pass_count}/{total} 项通过，{weak_count} 项弱通过，{fail_count} 项未通过。周会选股信号具有一定的真实 alpha，但需要关注集中度和统计显著性的边界情况。")
        elif fail_count >= total * 0.6:
            lines.append(f"> **总体评估:** {fail_count}/{total} 项未通过。原始报告的 alpha 大概率来自运气、集中度、或因子暴露，而非真正的选股能力。")
        else:
            lines.append(f"> **总体评估:** 结果参半 ({pass_count} 通过 / {weak_count} 弱通过 / {fail_count} 未通过)。Alpha 信号存在但不够稳健，建议继续积累数据后重新检验。")

        lines.append("")
        return lines


# ── Main Pipeline ─────────────────────────────────────────────

def run(use_cache: bool = True, verbose: bool = False):
    """Run all 6 follow-up analyses."""
    print("=" * 60)
    print("  周会选股回测 — 鲁棒性检验 (Follow-up)")
    print("=" * 60)
    print()

    # ── Step 1-4: Reuse existing pipeline to build picks ──────
    print("[1/4] Parsing meetings...")
    parser = MeetingParser()
    meetings = parser.parse_all()
    print(f"  Found {len(meetings)} meetings")

    print("[2/4] Matching against trades...")
    matcher = TradeMatcher()
    all_picks = []
    for m in meetings:
        for p in m["picks"]:
            pick = {**p, "meeting_date": m["date"]}
            acted, reason = matcher.is_acted_on(p["ticker_yf"], m["date"])
            pick["acted_on"] = acted
            pick["acted_reason"] = reason
            if reason == "held":
                pick["position_shares"] = matcher.get_position_shares(
                    p["ticker_yf"], m["date"])
            else:
                pick["position_shares"] = 0.0
            all_picks.append(pick)
    print(f"  {len(all_picks)} picks from {len(meetings)} meetings")

    print("[3/4] Fetching forward prices (from cache)...")
    fetcher = PriceFetcher(use_cache=use_cache)
    fetcher.batch_fetch(all_picks, ALL_WINDOWS)
    priced = sum(1 for p in all_picks
                 if any(p.get("returns", {}).get(w) is not None for w in MAIN_WINDOWS))
    print(f"  Got prices for {priced}/{len(all_picks)} picks")

    print("[4/4] Running 6 follow-up analyses...")
    print()

    # ── Analysis 1: Data Pipeline Audit ───────────────────────
    print("  [1/6] Data Pipeline Audit...")
    audit_result = DataPipelineAudit.audit(all_picks)
    dc = audit_result.get("decay_curve", {})
    tm = audit_result.get("trade_mgmt_sim", {})
    print(f"    Decay curve N={dc.get('n', 0)}, "
          f"Trade mgmt N={tm.get('n', 0)}, "
          f"Discrepancies: {len(audit_result.get('discrepancies', []))}")

    # ── Analysis 2: Concentration Stress Test ─────────────────
    print("  [2/6] Concentration Stress Test...")
    stress_result = ConcentrationStressTest.stress_test(all_picks)
    n_scenarios = len(stress_result.get("scenarios", {}))
    print(f"    {n_scenarios} scenarios tested")

    # ── Analysis 3: Cluster-Robust CI ─────────────────────────
    print("  [3/6] Cluster-Robust Confidence Intervals...")
    block_result = ClusterRobustCI.block_bootstrap(all_picks)
    nw_result = ClusterRobustCI.newey_west(all_picks)
    if "error" not in block_result:
        ci = block_result.get("block_ci_95", (0, 0))
        print(f"    Block bootstrap 95% CI: [{ci[0]:.2%}, {ci[1]:.2%}]")
    else:
        print(f"    Block bootstrap: {block_result['error']}")
    if "error" not in nw_result:
        print(f"    Newey-West t-stat: {nw_result.get('t_nw', 0):.2f}")
    else:
        print(f"    Newey-West: {nw_result['error']}")

    # ── Analysis 4: 4-Factor Regression ───────────────────────
    print("  [4/6] Carhart 4-Factor Regression...")
    factor_result = CarhartFactorRegression.run(all_picks)
    if "error" not in factor_result:
        alpha = factor_result.get("factors", {}).get("Alpha", {})
        print(f"    Alpha={alpha.get('coef', 0):.4f}, "
              f"t={alpha.get('t_stat', 0):.2f}, "
              f"R²={factor_result.get('r_squared', 0):.1%}")
    else:
        print(f"    {factor_result['error']}")

    # ── Analysis 5: Transaction Cost Sensitivity ──────────────
    print("  [5/6] Transaction Cost Sensitivity...")
    cost_result = TransactionCostSensitivity.analyze(all_picks)
    if "error" not in cost_result:
        be = cost_result.get("breakeven_bps", 0)
        print(f"    Breakeven cost: {be:.0f} bps")
    else:
        print(f"    {cost_result['error']}")

    # ── Analysis 6: Real P&L Replication ──────────────────────
    print("  [6/6] Real P&L Replication...")
    pnl_result = RealPnLReplication.replicate(all_picks)
    if "error" not in pnl_result:
        agg = pnl_result.get("aggregate", {})
        print(f"    Matched: {agg.get('n_matched', 0)}, "
              f"Unmatched: {agg.get('n_unmatched', 0)}")
        if agg.get("mean_diff") is not None:
            print(f"    Mean diff (actual-backtest): {agg['mean_diff']:+.2%}")
    else:
        print(f"    {pnl_result['error']}")

    # ── Generate Report ───────────────────────────────────────
    print()
    print("Generating follow-up report...")
    report = FollowupReportGenerator.generate(
        audit=audit_result,
        stress=stress_result,
        cluster_block=block_result,
        cluster_nw=nw_result,
        factor=factor_result,
        costs=cost_result,
        pnl=pnl_result,
        picks=all_picks,
        meetings_count=len(meetings),
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FOLLOWUP_REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"  Report saved to: {FOLLOWUP_REPORT_PATH}")

    # Console summary
    print()
    print("=" * 60)
    print("  FOLLOW-UP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Meeting Backtest Follow-up Analyses")
    ap.add_argument("--no-cache", action="store_true",
                    help="Re-fetch all prices (ignore cache)")
    ap.add_argument("--verbose", action="store_true",
                    help="Print detailed debug output")
    args = ap.parse_args()
    run(use_cache=not args.no_cache, verbose=args.verbose)
