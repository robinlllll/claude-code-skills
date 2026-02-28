"""Cycle Phase Classifier for Memory Cycle Tracker.

From Grok review: Memory cycles are reflexive. Must know WHERE in the cycle.

Phases:
- Early Recovery: Korean exports YoY turning positive, stocks still down, GM <25%
- Mid Expansion: Exports accelerating, prices rising, margins expanding
- Late Cycle / Peak: Exports +30%+ YoY, capex guidance rising >20%, GM >40%
- Contraction: Exports decelerating, capex still high (reflexive lag), prices rolling

Uses: Korean export YoY trajectory + Micron gross margin + capex guidance delta + inventory days.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import memory_db as db

PHASES = ["early_recovery", "mid_expansion", "late_cycle", "contraction"]

PHASE_LABELS = {
    "early_recovery": "Early Recovery",
    "mid_expansion": "Mid Expansion",
    "late_cycle": "Late Cycle / Peak",
    "contraction": "Contraction",
}

PHASE_INVESTMENT = {
    "early_recovery": "Best risk/reward -- get long",
    "mid_expansion": "Hold, add on dips",
    "late_cycle": "Trim, tighten stops",
    "contraction": "Avoid or short",
}


def classify_phase(
    export_yoy: float | None = None,
    export_acceleration: float | None = None,
    gross_margin: float | None = None,
    capex_ratio: float | None = None,
    capex_delta: float | None = None,
    inventory_days: float | None = None,
    inventory_delta: float | None = None,
    group_a_zscore: float | None = None,
    group_b_zscore: float | None = None,
) -> tuple[str, float, dict]:
    """Classify the current memory cycle phase.

    Returns: (phase, confidence, evidence_dict)

    Evidence-based scoring: each condition adds/subtracts points for each phase.
    Phase with highest score wins.
    """
    scores = {p: 0.0 for p in PHASES}
    evidence = {}

    # --- Korean Exports YoY ---
    if export_yoy is not None:
        evidence["export_yoy"] = f"{export_yoy:+.1%}"
        if export_yoy < -0.10:
            scores["contraction"] += 3
            scores["early_recovery"] += 1  # Could be bottoming
        elif -0.10 <= export_yoy < 0.05:
            scores["early_recovery"] += 3
            scores["contraction"] += 1
        elif 0.05 <= export_yoy < 0.30:
            scores["mid_expansion"] += 3
            scores["early_recovery"] += 1
        else:  # >= 30%
            scores["late_cycle"] += 3
            scores["mid_expansion"] += 1

    # --- Export Acceleration (2nd derivative) ---
    if export_acceleration is not None:
        evidence["export_accel"] = f"{export_acceleration:+.2f}"
        if export_acceleration > 0.05:
            scores["early_recovery"] += 2
            scores["mid_expansion"] += 2
        elif export_acceleration < -0.05:
            scores["late_cycle"] += 1
            scores["contraction"] += 2

    # --- Gross Margin ---
    if gross_margin is not None:
        evidence["gross_margin"] = f"{gross_margin:.1%}"
        if gross_margin < 0.15:
            scores["contraction"] += 2
            scores["early_recovery"] += 2
        elif 0.15 <= gross_margin < 0.25:
            scores["early_recovery"] += 3
        elif 0.25 <= gross_margin < 0.40:
            scores["mid_expansion"] += 3
        else:  # >= 40%
            scores["late_cycle"] += 3

    # --- Capex/Revenue Ratio ---
    if capex_ratio is not None:
        evidence["capex_ratio"] = f"{capex_ratio:.1%}"
        if capex_ratio > 0.40:
            scores["late_cycle"] += 2
            scores["contraction"] += 1  # Reflexive lag
        elif capex_ratio < 0.20:
            scores["early_recovery"] += 1
            scores["contraction"] += 1

    # --- Capex Delta (QoQ change in capex ratio) ---
    if capex_delta is not None:
        evidence["capex_delta"] = f"{capex_delta:+.2f}"
        if capex_delta > 0.20:
            scores["late_cycle"] += 3  # Capex rising >20% in bull = peak warning
        elif capex_delta < -0.10:
            scores["contraction"] += 1
            scores["early_recovery"] += 1

    # --- Inventory Days ---
    if inventory_days is not None:
        evidence["inventory_days"] = f"{inventory_days:.0f}"
        if inventory_days > 150:
            scores["contraction"] += 2
        elif inventory_days > 120:
            scores["contraction"] += 1
            scores["late_cycle"] += 1
        elif inventory_days < 90:
            scores["mid_expansion"] += 2
        elif inventory_days < 110:
            scores["early_recovery"] += 1

    # --- Inventory Delta (declining = recovery signal) ---
    if inventory_delta is not None:
        evidence["inventory_delta"] = f"{inventory_delta:+.1f} days"
        if inventory_delta < -10:
            scores["early_recovery"] += 2
        elif inventory_delta > 10:
            scores["contraction"] += 1
            scores["late_cycle"] += 1

    # --- Price signals vs Fundamentals divergence ---
    if group_a_zscore is not None and group_b_zscore is not None:
        evidence["group_a_z"] = f"{group_a_zscore:+.2f}"
        evidence["group_b_z"] = f"{group_b_zscore:+.2f}"
        # Stocks up but fundamentals weak = late cycle optimism
        if group_a_zscore > 1.0 and group_b_zscore < 0:
            scores["late_cycle"] += 2
        # Stocks down but fundamentals improving = early recovery
        elif group_a_zscore < 0 and group_b_zscore > 0:
            scores["early_recovery"] += 2

    # Determine winner
    max_score = max(scores.values())
    if max_score == 0:
        return "unknown", 0.0, evidence

    phase = max(scores, key=scores.get)
    total_score = sum(scores.values())
    confidence = max_score / total_score if total_score > 0 else 0.0

    evidence["scores"] = {k: round(v, 1) for k, v in scores.items()}

    return phase, round(confidence, 3), evidence


def classify_from_db() -> tuple[str, float, dict]:
    """Classify cycle phase using latest data from the database."""
    # Get latest Micron fundamentals
    latest = db.get_latest_signals_by_metric()

    # Korean export YoY
    export_yoy = None
    export_accel = None
    export_signals = db.get_signals(metric="korea_memory_export_value", limit=24)
    if len(export_signals) >= 13:
        current = export_signals[-1]["value"]
        year_ago = export_signals[-13]["value"]
        if year_ago > 0:
            export_yoy = (current - year_ago) / year_ago

        # Acceleration: compare this month's YoY with 3 months ago YoY
        if len(export_signals) >= 16:
            prev_current = export_signals[-4]["value"]
            prev_year_ago = export_signals[-16]["value"]
            if prev_year_ago > 0:
                prev_yoy = (prev_current - prev_year_ago) / prev_year_ago
                export_accel = export_yoy - prev_yoy if export_yoy is not None else None

    # Gross margin (latest MU)
    gm = latest.get("mu_gross_margin", {}).get("value")

    # Capex ratio and delta
    capex_ratio = latest.get("mu_capex_ratio", {}).get("value")
    capex_signals = db.get_signals(metric="mu_capex_ratio", limit=8)
    capex_delta = None
    if len(capex_signals) >= 2:
        capex_delta = (
            (capex_signals[-1]["value"] - capex_signals[-2]["value"])
            / capex_signals[-2]["value"]
            if capex_signals[-2]["value"] > 0
            else None
        )

    # Inventory days and delta
    inv_days = latest.get("mu_inventory_days", {}).get("value")
    inv_signals = db.get_signals(metric="mu_inventory_days", limit=8)
    inv_delta = None
    if len(inv_signals) >= 2:
        inv_delta = inv_signals[-1]["value"] - inv_signals[-2]["value"]

    # Group z-scores
    composites = db.get_composites(limit=1)
    group_a_z = None
    group_b_z = None
    if composites:
        latest_comp = composites[-1] if isinstance(composites, list) else composites
        # Get the latest composite
        all_composites = db.get_composites()
        if all_composites:
            latest_comp = all_composites[-1]
            group_a_z = latest_comp.get("group_a_zscore")
            group_b_z = latest_comp.get("group_b_zscore")

    phase, confidence, evidence = classify_phase(
        export_yoy=export_yoy,
        export_acceleration=export_accel,
        gross_margin=gm,
        capex_ratio=capex_ratio,
        capex_delta=capex_delta,
        inventory_days=inv_days,
        inventory_delta=inv_delta,
        group_a_zscore=group_a_z,
        group_b_zscore=group_b_z,
    )

    # Save phase to latest composite
    all_composites = db.get_composites()
    if all_composites:
        latest_date = all_composites[-1]["date"]
        db.upsert_composite(
            latest_date,
            cycle_phase=phase,
            phase_confidence=confidence,
            korean_export_yoy=export_yoy,
            gross_margin=gm,
            inventory_days=inv_days,
            capex_ratio=capex_ratio,
        )

    return phase, confidence, evidence


def get_phase_summary() -> dict:
    """Get current cycle phase with investment implication."""
    phase, confidence, evidence = classify_from_db()
    return {
        "phase": phase,
        "label": PHASE_LABELS.get(phase, "Unknown"),
        "confidence": confidence,
        "implication": PHASE_INVESTMENT.get(phase, "Insufficient data"),
        "evidence": evidence,
    }


def run() -> dict:
    """Run cycle classification. Returns phase summary."""
    print("  [Classifier] Running cycle phase classification...")
    summary = get_phase_summary()
    print(
        f"  [Classifier] Phase: {summary['label']} (confidence: {summary['confidence']:.0%})"
    )
    print(f"  [Classifier] Implication: {summary['implication']}")
    return summary


if __name__ == "__main__":
    summary = run()
    print(f"\n{'=' * 50}")
    print(f"MEMORY CYCLE PHASE: {summary['label']}")
    print(f"Confidence: {summary['confidence']:.0%}")
    print(f"Investment: {summary['implication']}")
    print("\nEvidence:")
    for k, v in summary["evidence"].items():
        if k != "scores":
            print(f"  {k}: {v}")
    if "scores" in summary["evidence"]:
        print("\nPhase scores:")
        for k, v in summary["evidence"]["scores"].items():
            label = PHASE_LABELS.get(k, k)
            print(f"  {label}: {v}")
