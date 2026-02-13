"""Vault-Intel Coordinator — 3-Stage Pipeline Orchestrator.

Stage 1: Hygiene (sequential — vault writes, must finish before others)
Stage 2: Intelligence — Linker + Kill Criteria + 13F Delta (parallel)
Stage 3: Briefing (sequential — needs all outputs)

Entry points:
  - As skill: Claude calls via SKILL.md instructions
  - As scheduled task: vault_intel_nightly.py wrapper
  - Manual: python coordinator.py --dry-run
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from importlib import import_module
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SKILLS_DIR = r"C:\Users\thisi\.claude\skills"
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)
from config import load_config, get_run_dir, LOCK_FILE, DATA_DIR


def acquire_lock(config: dict) -> bool:
    """Acquire lock file to prevent double execution.
    Returns True if lock acquired, False if another run is active.
    """
    if not config.get("safety", {}).get("lock_file", True):
        return True

    timeout_hours = config.get("safety", {}).get("lock_timeout_hours", 2)

    if LOCK_FILE.exists():
        try:
            lock_data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
            lock_time = datetime.fromisoformat(lock_data["started_at"])
            if datetime.now(timezone.utc) - lock_time < timedelta(hours=timeout_hours):
                return False  # Lock is still valid
            # Lock expired — clean it up
            print(f"  Stale lock detected (>{timeout_hours}h old), overriding")
        except Exception:
            pass  # Corrupted lock file, override it

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_data = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    LOCK_FILE.write_text(json.dumps(lock_data), encoding="utf-8")
    return True


def release_lock():
    """Release the lock file."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def run_agent(
    agent_name: str, config: dict, dry_run: bool, agent_results: dict = None
) -> dict:
    """Run a single agent by name, returning its result dict."""
    agent_map = {
        "hygiene": "agent_hygiene",
        "linker": "agent_linker",
        "killcriteria": "agent_killcriteria",
        "13f_delta": "agent_13f_delta",
        "briefing": "agent_briefing",
    }

    module_name = agent_map.get(agent_name)
    if not module_name:
        return {
            "agent": agent_name,
            "status": "failed",
            "errors": [f"Unknown agent: {agent_name}"],
        }

    try:
        module = import_module(module_name)
        kwargs = {"config": config, "dry_run": dry_run}
        if agent_results is not None:
            kwargs["agent_results"] = agent_results
        return module.run(**kwargs)
    except Exception as e:
        return {
            "agent": agent_name,
            "status": "failed",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {},
            "issues": [],
            "actions_taken": [],
            "errors": [f"{type(e).__name__}: {e}"],
        }


def save_results(run_id: str, results: dict):
    """Save all agent results to a run-specific directory."""
    run_dir = get_run_dir(run_id)
    for agent_name, result in results.items():
        out_path = run_dir / f"{agent_name}_result.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    # Also save to flat data/ for standalone agent use
    for agent_name, result in results.items():
        out_path = DATA_DIR / f"{agent_name}_result.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)


def print_summary(results: dict):
    """Print a compact summary of all agent results."""
    print("\n" + "=" * 60)
    print("VAULT-INTEL RUN SUMMARY")
    print("=" * 60)
    for name, result in results.items():
        status = result.get("status", "unknown")
        metrics = result.get("metrics", {})
        errors = result.get("errors", [])
        issues = result.get("issues", [])

        status_icon = {"success": "+", "partial": "~", "failed": "!"}
        icon = status_icon.get(status, "?")
        print(f"  [{icon}] {name}: {status}")

        # Key metrics per agent
        if name == "hygiene":
            print(
                f"      Scanned: {metrics.get('files_scanned', 0)}, "
                f"Issues: {metrics.get('issues_found', 0)}, "
                f"Fixed: {metrics.get('auto_fixed', 0)}"
            )
        elif name == "killcriteria":
            print(
                f"      P1: {metrics.get('p1_violations', 0)}, "
                f"Stale: {metrics.get('stale_kc', 0)}, "
                f"Drawdowns: {metrics.get('drawdown_alerts', 0)}"
            )
        elif name == "13f_delta":
            print(
                f"      New: {metrics.get('new_positions', 0)}, "
                f"Exits: {metrics.get('exits', 0)}, "
                f"Overlaps: {metrics.get('portfolio_overlaps', 0)}"
            )
        elif name == "linker":
            print(
                f"      Links: {metrics.get('links_added', 0)}, "
                f"Narratives: {metrics.get('narrative_changes', 0)}"
            )
        elif name == "briefing":
            print(
                f"      Health: {metrics.get('health_score', '?')}/100, "
                f"P1: {metrics.get('p1_count', 0)}"
            )

        if errors:
            for err in errors[:2]:
                print(f"      ERROR: {err}")
    print("=" * 60)


def send_notification(results: dict, dry_run: bool):
    """Send Telegram notification with briefing summary."""
    if dry_run:
        print("  [DRY RUN] Telegram notification skipped")
        return

    briefing = results.get("briefing", {})
    summary = briefing.get("telegram_summary", "Vault Intel completed (no summary)")

    try:
        from shared.telegram_notify import notify

        notify(summary)
        print(f"  Telegram notification sent: {summary}")
    except Exception as e:
        print(f"  Telegram notification failed: {e}")


def main(args: list[str] = None):
    """Main entry point for the vault-intel coordinator."""
    import argparse

    parser = argparse.ArgumentParser(description="Vault-Intel Coordinator")
    parser.add_argument(
        "--dry-run", action="store_true", help="Scan everything but don't modify vault"
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Run a single agent only (hygiene|linker|killcriteria|13f_delta|briefing)",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="interactive",
        help="Run mode: interactive (default) or nightly",
    )
    parsed = parser.parse_args(args)

    config = load_config()
    dry_run = parsed.dry_run
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    print(f"=== Vault-Intel {'[DRY RUN] ' if dry_run else ''}=== {run_id}")

    # Single agent mode
    if parsed.agent:
        print(f"Running single agent: {parsed.agent}")
        result = run_agent(parsed.agent, config, dry_run)
        save_results(run_id, {parsed.agent: result})
        print_summary({parsed.agent: result})
        return

    # Full pipeline
    if not acquire_lock(config):
        print("Another vault-intel run is active. Aborting.")
        return

    try:
        results = {}

        # STAGE 1: HYGIENE (sequential — vault writes must finish first)
        print(f"\n>>> Stage 1: Hygiene [{run_id}]")
        results["hygiene"] = run_agent("hygiene", config, dry_run)
        print(f"    Done: {results['hygiene'].get('status', 'unknown')}")

        # STAGE 2: INTELLIGENCE (parallel — vault is now stable)
        print("\n>>> Stage 2: Intelligence Agents (parallel)")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(run_agent, "linker", config, dry_run): "linker",
                pool.submit(run_agent, "killcriteria", config, dry_run): "killcriteria",
                pool.submit(run_agent, "13f_delta", config, dry_run): "13f_delta",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=300)
                    print(f"    {name}: {results[name].get('status', 'unknown')}")
                except Exception as e:
                    results[name] = {
                        "agent": name,
                        "status": "failed",
                        "metrics": {},
                        "issues": [],
                        "actions_taken": [],
                        "errors": [str(e)],
                    }
                    print(f"    {name}: FAILED — {e}")

        # STAGE 3: BRIEFING (sequential — needs all outputs)
        print("\n>>> Stage 3: Daily Briefing")
        results["briefing"] = run_agent(
            "briefing", config, dry_run, agent_results=results
        )
        print(f"    Done: {results['briefing'].get('status', 'unknown')}")

        # Save and report
        save_results(run_id, results)
        print_summary(results)
        send_notification(results, dry_run)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
