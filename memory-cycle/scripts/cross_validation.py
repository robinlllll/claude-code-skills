"""Cross-Validation Engine for Memory Cycle Tracker.

Scoring: Rolling Z-Scores (not categorical buckets, per Gemini review).
- Each metric: 12-month rolling z-score
- Group A score = average z-score of price signals
- Group B score = weighted average z-score of fundamental signals (Korean exports 1.5x)
- Divergence = Group A z-score minus Group B z-score (>1.0 or <-1.0 = significant)

3 Sub-Cycle scores: HBM, Commodity DRAM, NAND
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import memory_db as db

# Lookback window for z-scores
ZSCORE_WINDOW = 12  # months

# Signal group membership and weights
GROUP_A_METRICS = {
    # Stock prices (monthly returns computed)
    "price_MU": 1.0,
    "price_WDC": 0.8,
    "price_005930_KS": 0.8,
    "price_000660_KS": 0.8,
    "mu_vs_soxx_relative": 1.2,  # Higher weight - 2nd derivative signal
    # Spot/retail prices
    "dxi_ddr5_spot_price": 1.0,
    "dxi_ddr4_spot_price": 0.8,
    "dxi_nand_spot_price": 1.0,
    "pcpp_ddr5_median_price": 0.7,
    "pcpp_ssd_median_price": 0.7,
    "ddr5_spot_price": 1.0,
    "ddr4_spot_price": 0.8,
    "nand_spot_price": 1.0,
}

GROUP_B_METRICS = {
    # Korean exports (1.5x weight - leading indicator)
    "korea_memory_export_value": 1.5,
    "korea_memory_export_volume": 1.2,
    "korea_memory_value_volume_ratio": 1.5,
    # Micron fundamentals
    "mu_revenue": 1.0,
    "mu_gross_margin": 1.2,
    "mu_inventory_days": -1.0,  # Negative: high inventory = bearish
    "mu_capex_ratio": -0.8,  # Negative: high capex = late cycle
    # WDC fundamentals
    "wdc_revenue": 0.8,
    "wdc_gross_margin": 1.0,
    "wdc_inventory_days": -0.8,
    "wdc_capex_ratio": -0.6,
}

# Sub-cycle metric mapping
SUBCYCLE_METRICS = {
    "HBM": [
        "korea_memory_value_volume_ratio",  # Rising = HBM mix improving
        "price_000660_KS",  # Hynix = HBM leader
    ],
    "DRAM": [
        "dxi_ddr5_spot_price",
        "dxi_ddr4_spot_price",
        "ddr5_spot_price",
        "pcpp_ddr5_median_price",
        "korea_memory_export_volume",
        "mu_inventory_days",
    ],
    "NAND": [
        "dxi_nand_spot_price",
        "nand_spot_price",
        "pcpp_ssd_median_price",
        "wdc_revenue",
        "wdc_gross_margin",
        "price_WDC",
    ],
}


def compute_zscore(values: list[float], window: int = ZSCORE_WINDOW) -> list[float]:
    """Compute rolling z-scores for a series of values."""
    zscores = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start : i + 1]
        if len(window_vals) < 3:
            zscores.append(0.0)
            continue
        mean = sum(window_vals) / len(window_vals)
        variance = sum((x - mean) ** 2 for x in window_vals) / len(window_vals)
        std = variance**0.5
        if std < 1e-10:
            zscores.append(0.0)
        else:
            zscores.append((values[i] - mean) / std)
    return zscores


def get_monthly_series(metric: str, start_date: str = None) -> dict[str, float]:
    """Get a metric's values as {YYYY-MM: value} dict, taking last value per month."""
    signals = db.get_signals(metric=metric, start_date=start_date)
    monthly = {}
    for s in signals:
        month = s["date"][:7]  # YYYY-MM
        monthly[month] = s["value"]
    return monthly


def compute_group_scores(start_date: str = None) -> dict:
    """Compute Group A and Group B z-scores for each month.

    Returns: {
        'months': [YYYY-MM, ...],
        'group_a': [z-score, ...],
        'group_b': [z-score, ...],
        'divergence': [z-score, ...],
        'metric_zscores': {metric: {month: z-score, ...}, ...},
    }
    """
    # Collect all monthly series
    all_series = {}
    all_months = set()

    for metric in list(GROUP_A_METRICS.keys()) + list(GROUP_B_METRICS.keys()):
        series = get_monthly_series(metric, start_date)
        if series:
            all_series[metric] = series
            all_months.update(series.keys())

    if not all_months:
        return {
            "months": [],
            "group_a": [],
            "group_b": [],
            "divergence": [],
            "metric_zscores": {},
        }

    months = sorted(all_months)

    # Compute z-scores for each metric
    metric_zscores = {}
    for metric, series in all_series.items():
        values = [series.get(m, None) for m in months]
        # Forward-fill missing values
        filled = _forward_fill(values)
        zscores = compute_zscore(filled)
        metric_zscores[metric] = {m: z for m, z in zip(months, zscores)}

    # Compute group scores per month
    group_a_scores = []
    group_b_scores = []
    divergences = []

    for month in months:
        # Group A: weighted average z-score
        a_sum, a_weight = 0.0, 0.0
        for metric, weight in GROUP_A_METRICS.items():
            if metric in metric_zscores and month in metric_zscores[metric]:
                z = metric_zscores[metric][month]
                a_sum += z * abs(weight)
                a_weight += abs(weight)

        # Group B: weighted average z-score
        b_sum, b_weight = 0.0, 0.0
        for metric, weight in GROUP_B_METRICS.items():
            if metric in metric_zscores and month in metric_zscores[metric]:
                z = metric_zscores[metric][month]
                # For negative-weighted metrics (inventory, capex), flip the z-score
                effective_z = z * (1 if weight > 0 else -1)
                b_sum += effective_z * abs(weight)
                b_weight += abs(weight)

        a_score = a_sum / a_weight if a_weight > 0 else 0.0
        b_score = b_sum / b_weight if b_weight > 0 else 0.0
        divergence = a_score - b_score

        group_a_scores.append(round(a_score, 3))
        group_b_scores.append(round(b_score, 3))
        divergences.append(round(divergence, 3))

    return {
        "months": months,
        "group_a": group_a_scores,
        "group_b": group_b_scores,
        "divergence": divergences,
        "metric_zscores": metric_zscores,
    }


def compute_subcycle_scores(metric_zscores: dict, months: list[str]) -> dict:
    """Compute sub-cycle health scores for HBM, Commodity DRAM, NAND.

    Returns: {sub_cycle: {month: score, ...}, ...}
    """
    scores = {}
    for sub_cycle, metrics in SUBCYCLE_METRICS.items():
        monthly_scores = {}
        for month in months:
            total, count = 0.0, 0
            for metric in metrics:
                if metric in metric_zscores and month in metric_zscores[metric]:
                    total += metric_zscores[metric][month]
                    count += 1
            monthly_scores[month] = round(total / count, 3) if count > 0 else 0.0
        scores[sub_cycle] = monthly_scores
    return scores


def detect_divergences(
    group_a: list[float],
    group_b: list[float],
    months: list[str],
    threshold: float = 1.0,
) -> list[dict]:
    """Detect significant divergences between Group A and Group B.

    Returns list of {month, divergence, direction, severity} dicts.
    """
    alerts = []
    for i, month in enumerate(months):
        div = group_a[i] - group_b[i]
        if abs(div) >= threshold:
            direction = "A_leads" if div > 0 else "B_leads"
            severity = "high" if abs(div) >= 2.0 else "moderate"
            alerts.append(
                {
                    "month": month,
                    "divergence": round(div, 3),
                    "direction": direction,
                    "severity": severity,
                    "group_a": group_a[i],
                    "group_b": group_b[i],
                }
            )
    return alerts


def check_intramonth_alerts(start_date: str = None) -> list[dict]:
    """Check for intra-month threshold alerts (for --daily mode).

    Alerts:
    - DRAM spot price moves >10% within 4 weeks
    - MU underperforms SOXX by >5% in 2 weeks
    """
    alerts = []

    # Check spot price moves
    for metric in ["dxi_ddr5_spot_price", "ddr5_spot_price", "dxi_nand_spot_price"]:
        signals = db.get_signals(metric=metric, limit=30)
        if len(signals) >= 2:
            recent = signals[-1]["value"]
            baseline = (
                signals[-5]["value"] if len(signals) >= 5 else signals[0]["value"]
            )
            if baseline > 0:
                pct_change = (recent - baseline) / baseline
                if abs(pct_change) >= 0.10:
                    alerts.append(
                        {
                            "type": "spot_price_move",
                            "metric": metric,
                            "change_pct": round(pct_change * 100, 1),
                            "direction": "up" if pct_change > 0 else "down",
                            "current": recent,
                            "baseline": baseline,
                        }
                    )

    # Check MU vs SOXX divergence
    mu_signals = db.get_signals(metric="price_MU", limit=15)
    soxx_signals = db.get_signals(metric="price_SOXX", limit=15)
    if len(mu_signals) >= 3 and len(soxx_signals) >= 3:
        mu_ret = (mu_signals[-1]["value"] - mu_signals[-3]["value"]) / mu_signals[-3][
            "value"
        ]
        soxx_ret = (
            soxx_signals[-1]["value"] - soxx_signals[-3]["value"]
        ) / soxx_signals[-3]["value"]
        rel_perf = mu_ret - soxx_ret
        if abs(rel_perf) >= 0.05:
            alerts.append(
                {
                    "type": "mu_soxx_divergence",
                    "mu_return": round(mu_ret * 100, 1),
                    "soxx_return": round(soxx_ret * 100, 1),
                    "relative": round(rel_perf * 100, 1),
                }
            )

    return alerts


def save_composite_scores(scores: dict, subcycle_scores: dict):
    """Save computed scores to the composite_scores table."""
    months = scores["months"]
    for i, month in enumerate(months):
        date = f"{month}-01"  # First of month

        kwargs = {
            "group_a_zscore": scores["group_a"][i],
            "group_b_zscore": scores["group_b"][i],
            "divergence": scores["divergence"][i],
        }

        # Add sub-cycle scores
        for sub in ["HBM", "DRAM", "NAND"]:
            key = f"{sub.lower()}_score"
            if sub in subcycle_scores and month in subcycle_scores[sub]:
                kwargs[key] = subcycle_scores[sub][month]

        db.upsert_composite(date, **kwargs)


def _forward_fill(values: list) -> list[float]:
    """Forward-fill None values in a list."""
    result = []
    last_valid = 0.0
    for v in values:
        if v is not None:
            last_valid = float(v)
        result.append(last_valid)
    return result


def run(start_date: str = None) -> dict:
    """Run full cross-validation. Returns scores dict."""
    print("  [CrossVal] Computing z-scores and group scores...")
    scores = compute_group_scores(start_date)

    if not scores["months"]:
        print("  [CrossVal] No data available for scoring")
        return scores

    print(f"  [CrossVal] {len(scores['months'])} months scored")

    subcycle_scores = compute_subcycle_scores(
        scores["metric_zscores"], scores["months"]
    )
    print("  [CrossVal] Sub-cycle scores: HBM/DRAM/NAND computed")

    divergences = detect_divergences(
        scores["group_a"], scores["group_b"], scores["months"]
    )
    if divergences:
        print(f"  [CrossVal] {len(divergences)} significant divergences detected")

    save_composite_scores(scores, subcycle_scores)
    print("  [CrossVal] Saved composite scores to DB")

    scores["subcycle_scores"] = subcycle_scores
    scores["divergence_alerts"] = divergences
    return scores


if __name__ == "__main__":
    result = run()
    if result["months"]:
        latest = result["months"][-1]
        print(f"\nLatest month: {latest}")
        print(f"  Group A: {result['group_a'][-1]}")
        print(f"  Group B: {result['group_b'][-1]}")
        print(f"  Divergence: {result['divergence'][-1]}")
        if result.get("divergence_alerts"):
            print("\nDivergence alerts:")
            for a in result["divergence_alerts"][-3:]:
                print(
                    f"  {a['month']}: {a['divergence']} ({a['direction']}, {a['severity']})"
                )
