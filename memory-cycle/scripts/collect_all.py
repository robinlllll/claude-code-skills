"""Orchestrator for Memory Cycle Tracker.

Modes:
- Default (monthly): Run all collectors, compute scores, export CSV
- --daily: Run daily-frequency collectors only + intra-month alerts
- --status: Show current cycle phase and latest signals
"""

import sys
import csv
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import memory_db as db

VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
CSV_PATH = VAULT_DIR / "研究" / "研究笔记" / "memory-cycle-tracker.csv"
DASHBOARD_PATH = VAULT_DIR / "研究" / "研究笔记" / "memory-cycle-dashboard.html"


def run_all_collectors() -> list:
    """Run all 4 collectors and return results."""
    results = []

    # Import and run each collector
    print("=" * 60)
    print("MEMORY CYCLE TRACKER - Full Collection Run")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. yfinance (stocks + FX)
    print("\n[1/4] Stock Prices + FX (yfinance)")
    try:
        import collect_yfinance
        r = collect_yfinance.run()
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    # 2. SEC XBRL (MU + WDC fundamentals)
    print("\n[2/4] SEC XBRL Fundamentals")
    try:
        import collect_sec_xbrl
        r = collect_sec_xbrl.run()
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    # 3. Korean Exports
    print("\n[3/4] Korean Memory Exports")
    try:
        import collect_korea_exports
        r = collect_korea_exports.run()
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    # 4. Spot Pricing
    print("\n[4/4] Spot/Retail Pricing")
    try:
        import collect_spot_pricing
        r = collect_spot_pricing.run()
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    return results


def run_daily_collectors() -> list:
    """Run daily-frequency collectors only."""
    results = []

    print("=" * 60)
    print("MEMORY CYCLE TRACKER - Daily Check")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Only yfinance and spot pricing run daily
    print("\n[1/2] Stock Prices (yfinance)")
    try:
        import collect_yfinance
        r = collect_yfinance.run(period='1mo')
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    print("\n[2/2] Spot Pricing")
    try:
        import collect_spot_pricing
        r = collect_spot_pricing.run()
        results.append(r)
        print(f"  -> {r.status}: {r.rows_added} signals")
    except Exception as e:
        print(f"  -> FAILED: {e}")

    return results


def compute_scores():
    """Run cross-validation and cycle classification."""
    print("\n" + "=" * 60)
    print("SCORING & CLASSIFICATION")
    print("=" * 60)

    # Cross-validation
    print("\n[Score] Cross-Validation Engine")
    import cross_validation
    scores = cross_validation.run()

    # Cycle classification
    print("\n[Phase] Cycle Phase Classifier")
    import cycle_classifier
    phase = cycle_classifier.run()

    return scores, phase


def check_alerts(daily: bool = False):
    """Check for alerts and optionally send email."""
    import cross_validation

    alerts = []

    if daily:
        # Intra-month alerts
        intra = cross_validation.check_intramonth_alerts()
        if intra:
            alerts.extend(intra)
            print(f"\n[ALERT] {len(intra)} intra-month alerts detected!")
            for a in intra:
                if a['type'] == 'spot_price_move':
                    print(f"  -> {a['metric']}: {a['change_pct']:+.1f}% ({a['direction']})")
                elif a['type'] == 'mu_soxx_divergence':
                    print(f"  -> MU vs SOXX: {a['relative']:+.1f}% "
                          f"(MU: {a['mu_return']:+.1f}%, SOXX: {a['soxx_return']:+.1f}%)")

    # Check for phase transitions
    composites = db.get_composites()
    if len(composites) >= 2:
        prev_phase = composites[-2].get('cycle_phase')
        curr_phase = composites[-1].get('cycle_phase')
        if prev_phase and curr_phase and prev_phase != curr_phase:
            alerts.append({
                'type': 'phase_transition',
                'from': prev_phase,
                'to': curr_phase,
            })
            print(f"\n[ALERT] Phase transition: {prev_phase} -> {curr_phase}")

    # Check for divergence
    if composites:
        latest = composites[-1]
        div = latest.get('divergence')
        if div is not None and abs(div) >= 1.5:
            alerts.append({
                'type': 'divergence',
                'value': div,
                'direction': 'A_leads' if div > 0 else 'B_leads',
            })
            direction = "prices leading fundamentals" if div > 0 else "fundamentals leading prices"
            print(f"\n[ALERT] Significant divergence: {div:.2f} ({direction})")

    if alerts:
        _send_alert_email(alerts)

    return alerts


def _send_alert_email(alerts: list):
    """Send alert email if significant signals detected."""
    try:
        sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
        from shared.email_notify import send_email

        # Build alert summary
        lines = ["# Memory Cycle Alert\n"]
        for a in alerts:
            if a['type'] == 'phase_transition':
                lines.append(f"## Phase Transition: {a['from']} -> {a['to']}\n")
            elif a['type'] == 'divergence':
                lines.append(f"## Divergence Alert: {a['value']:.2f} ({a['direction']})\n")
            elif a['type'] == 'spot_price_move':
                lines.append(f"- **{a['metric']}**: {a['change_pct']:+.1f}% {a['direction']}\n")
            elif a['type'] == 'mu_soxx_divergence':
                lines.append(f"- **MU vs SOXX**: {a['relative']:+.1f}%\n")

        # Get current phase
        import cycle_classifier
        summary = cycle_classifier.get_phase_summary()
        lines.append(f"\n**Current Phase:** {summary['label']}")
        lines.append(f"**Confidence:** {summary['confidence']:.0%}")
        lines.append(f"**Implication:** {summary['implication']}")

        send_email(
            subject=f"[Memory Cycle] {alerts[0]['type'].replace('_', ' ').title()}",
            md_content='\n'.join(lines),
        )
        print("  [Email] Alert sent successfully")
    except Exception as e:
        print(f"  [Email] Failed to send alert: {e}")


def export_csv():
    """Export composite scores to CSV for Obsidian."""
    composites = db.get_composites()
    if not composites:
        print("\n[CSV] No composite data to export")
        return

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'date', 'group_a_zscore', 'group_b_zscore', 'divergence',
        'hbm_score', 'dram_score', 'nand_score',
        'cycle_phase', 'phase_confidence',
        'korean_export_yoy', 'gross_margin', 'inventory_days', 'capex_ratio',
    ]

    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in composites:
            writer.writerow(row)

    print(f"\n[CSV] Exported {len(composites)} rows to {CSV_PATH}")


def show_status():
    """Show current cycle status summary."""
    print("=" * 60)
    print("MEMORY CYCLE STATUS")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # DB stats
    stats = db.get_stats()
    print(f"\nDatabase: {stats['total_signals']} signals, {stats['total_composites']} composites")
    if stats['date_range']:
        print(f"Date range: {stats['date_range']['min']} to {stats['date_range']['max']}")

    # Latest signals
    latest = db.get_latest_signals_by_metric()
    if latest:
        print(f"\nLatest signals ({len(latest)} metrics):")
        key_metrics = ['price_MU', 'mu_gross_margin', 'mu_inventory_days',
                       'korea_memory_export_value', 'mu_vs_soxx_relative']
        for m in key_metrics:
            if m in latest:
                s = latest[m]
                print(f"  {m}: {s['value']:.2f} ({s['date']})")

    # Current phase
    composite = db.get_latest_composite()
    if composite:
        print(f"\nCycle Phase: {composite.get('cycle_phase', 'N/A')}")
        print(f"Confidence: {composite.get('phase_confidence', 0):.0%}")
        print(f"Group A z-score: {composite.get('group_a_zscore', 'N/A')}")
        print(f"Group B z-score: {composite.get('group_b_zscore', 'N/A')}")
        print(f"Divergence: {composite.get('divergence', 'N/A')}")
        print(f"Sub-cycles: HBM={composite.get('hbm_score', 'N/A')}, "
              f"DRAM={composite.get('dram_score', 'N/A')}, "
              f"NAND={composite.get('nand_score', 'N/A')}")

    # Recent fetch log
    fetches = db.get_fetch_history(limit=8)
    if fetches:
        print(f"\nRecent fetches:")
        for f_entry in fetches:
            print(f"  {f_entry['source']}: {f_entry['status']} "
                  f"({f_entry['rows_added']} rows, {f_entry['fetch_date']})")


def main():
    parser = argparse.ArgumentParser(description='Memory Cycle Tracker Orchestrator')
    parser.add_argument('--daily', action='store_true',
                        help='Run daily-frequency collectors only')
    parser.add_argument('--status', action='store_true',
                        help='Show current cycle status')
    parser.add_argument('--no-dashboard', action='store_true',
                        help='Skip dashboard generation')
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # Run collectors
    if args.daily:
        results = run_daily_collectors()
    else:
        results = run_all_collectors()

    # Always compute scores
    scores, phase = compute_scores()

    # Check alerts
    check_alerts(daily=args.daily)

    # Export CSV
    export_csv()

    # Generate dashboard
    if not args.no_dashboard:
        try:
            import generate_dashboard
            generate_dashboard.run()
        except Exception as e:
            print(f"\n[Dashboard] Generation failed: {e}")

    # Summary
    total_signals = sum(r.rows_added for r in results)
    failed = sum(1 for r in results if r.status == 'failed')
    print(f"\n{'=' * 60}")
    print(f"COMPLETE: {total_signals} total signals from {len(results)} sources")
    if failed:
        print(f"WARNING: {failed} source(s) failed")
    print(f"Phase: {phase.get('label', 'Unknown')} ({phase.get('confidence', 0):.0%})")
    print(f"CSV: {CSV_PATH}")
    print(f"Dashboard: {DASHBOARD_PATH}")
    print("=" * 60)


if __name__ == '__main__':
    main()
