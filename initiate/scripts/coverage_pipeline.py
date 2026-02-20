"""Coverage Initiation Pipeline — Main orchestrator.

Runs the complete multi-phase pipeline:
  Phase 0: Preflight check (API keys, dependencies)
  Phase 1: Data Collection (Perplexity + SEC EDGAR + yfinance + Local Vault)
  Phase 2: Section Analysis (S1-S3 triple Gemini+GPT+Grok→Claude merge, S4-S7 single, Grok red team)
  Phase 3: Report Assembly (merge, format, save to Obsidian)
  Phase 4: Notification (optional email)

Usage:
    python coverage_pipeline.py TICKER [--refresh] [--fast] [--no-email] [--review]
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Script dir on sys.path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    RUNS_DIR,
    OUTPUT_DIR,
    preflight_check,
    MODELS,
)


async def run_pipeline(
    ticker: str,
    refresh: bool = False,
    fast: bool = False,
    send_email: bool = True,
    review: bool = False,
) -> dict:
    """Run the complete coverage initiation pipeline.

    Args:
        ticker: Stock ticker symbol
        refresh: Force re-fetch data (ignore cache)
        fast: Skip cross-validation step
        send_email: Send email notification when done
        review: Pause after analysis for user review

    Returns:
        Pipeline result dict with report path and metadata
    """
    ticker = ticker.upper()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    workspace = RUNS_DIR / f"{ticker}_{timestamp}"
    workspace.mkdir(parents=True, exist_ok=True)

    pipeline_t0 = time.time()

    print(f"\n{'#' * 60}")
    print(f"  COVERAGE INITIATION: {ticker}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Workspace: {workspace}")
    print(f"{'#' * 60}")

    # ===== Phase 0: Preflight =====
    print("\n--- Phase 0: Preflight ---\n")
    keys = preflight_check()

    print("  API Keys:")
    print(f"    Perplexity: {'OK' if keys['perplexity'] else 'MISSING'}")
    print(f"    OpenAI:     {'OK' if keys['openai'] else 'MISSING'}")
    print(f"    Gemini:     {'OK' if keys['gemini'] else 'MISSING'}")
    print(f"    xAI (Grok): {'OK' if keys['xai'] else 'MISSING'}")
    print(f"    Anthropic:  {'OK' if keys['anthropic'] else 'MISSING'}")

    if not keys["ready"]:
        print("\n  ABORT: Minimum API keys not available.")
        print("  Required: Perplexity + (OpenAI or Gemini)")
        return {"error": "Preflight failed: missing API keys"}

    print("\n  Models:")
    print(f"    Triple S1-S3: {MODELS['gemini']} + {MODELS['gpt']} + {MODELS.get('grok', 'grok-4-1-fast-reasoning')} → Claude merge")
    print(f"    Single:     {MODELS['gpt']} (S4,S5,S7) / {MODELS['gemini']} (S6)")
    print(f"    Red Team:   {MODELS.get('grok', 'grok-4-1-fast-reasoning')}")
    print(f"    Synthesis:  {MODELS['claude_synthesis']} (S8, S9)")

    # ===== Phase 1: Data Collection =====
    print("\n--- Phase 1: Data Collection ---\n")

    from data_collector import collect_all

    data_pack = await collect_all(ticker, refresh=refresh)

    # Save data pack to workspace
    dp_path = workspace / "data_pack.json"
    with open(dp_path, "w", encoding="utf-8") as f:
        json.dump(data_pack, f, indent=2, ensure_ascii=False, default=str)

    company_name = data_pack.get("company_name", ticker)

    # ===== Phase 2: Section Analysis =====
    print("\n--- Phase 2: Section Analysis ---\n")

    from section_dispatcher import dispatch_sections

    dispatch_result = await dispatch_sections(data_pack, workspace)

    if review:
        print("\n  [REVIEW MODE] Pipeline paused. Section outputs saved to workspace.")
        print(f"  Workspace: {workspace}")
        print("  Re-run without --review to continue to report assembly.")
        return {
            "status": "paused_for_review",
            "workspace": str(workspace),
            "sections_completed": sum(
                1 for s in dispatch_result["sections"].values() if not s.get("error")
            ),
        }

    # ===== Phase 3: Report Assembly =====
    print("\n--- Phase 3: Report Assembly ---\n")

    from report_assembler import assemble_report

    report = assemble_report(
        ticker=ticker,
        company_name=company_name,
        sections=dispatch_result["sections"],
        data_pack=data_pack,
        total_tokens=dispatch_result["total_tokens"],
        total_elapsed_s=round(time.time() - pipeline_t0, 1),
        workspace=workspace,
    )

    total_elapsed = round(time.time() - pipeline_t0, 1)
    report_path = (
        OUTPUT_DIR
        / ticker
        / f"{datetime.now().strftime('%Y-%m-%d %H%M')} {ticker} Coverage Initiation.md"
    )

    # ===== Phase 4: Notification =====
    if send_email:
        print("\n--- Phase 4: Email Notification ---\n")
        try:
            _send_email(
                ticker, company_name, report_path, total_elapsed, dispatch_result
            )
        except Exception as e:
            print(f"  Email failed: {e}")

    # ===== Summary =====
    tokens = dispatch_result["total_tokens"]
    total_tokens = tokens["input"] + tokens["output"]

    print(f"\n{'#' * 60}")
    print(f"  PIPELINE COMPLETE: {company_name} ({ticker})")
    print(f"  Time: {total_elapsed}s")
    print(
        f"  Tokens: {total_tokens:,} ({tokens['input']:,} in + {tokens['output']:,} out)"
    )
    print(
        f"  Sections: {sum(1 for s in dispatch_result['sections'].values() if not s.get('error'))}/9 OK"
    )
    print(f"  Report: {report_path}")
    print(f"{'#' * 60}\n")

    return {
        "status": "complete",
        "ticker": ticker,
        "company_name": company_name,
        "report_path": str(report_path),
        "workspace": str(workspace),
        "total_elapsed_s": total_elapsed,
        "total_tokens": total_tokens,
        "sections_completed": sum(
            1 for s in dispatch_result["sections"].values() if not s.get("error")
        ),
        "errors": dispatch_result["errors"],
    }


def _send_email(
    ticker: str,
    company_name: str,
    report_path: Path,
    elapsed: float,
    dispatch_result: dict,
):
    """Send email notification with report summary."""
    try:
        sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
        from shared.email_notify import send_email

        tokens = dispatch_result["total_tokens"]
        sections_ok = sum(
            1 for s in dispatch_result["sections"].values() if not s.get("error")
        )

        subject = f"Coverage Initiation Complete: {company_name} ({ticker})"
        body = f"""Coverage initiation report generated for {company_name} ({ticker}).

Pipeline Summary:
- Sections: {sections_ok}/9 completed
- Total time: {elapsed:.0f}s
- Tokens: {tokens["input"] + tokens["output"]:,}

Report saved to: {report_path}

Models used:
- Triple: Gemini + GPT + Grok → Claude merge (S1, S2, S3)
- Single: GPT (S4, S5, S7), Gemini (S6)
- Red Team: Grok
- Synthesis: Claude (S8, S9)
"""
        if dispatch_result["errors"]:
            body += "\nErrors:\n"
            for e in dispatch_result["errors"]:
                body += f"  - {e}\n"

        send_email(subject, body)
        print("  Email sent to thisisrobin66@gmail.com")

    except Exception as e:
        print(f"  Email notification failed: {e}")


# ============ CLI entry point ============


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Coverage Initiation Engine — Multi-AI Equity Research Pipeline"
    )
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument(
        "--refresh", action="store_true", help="Force re-fetch data (ignore cache)"
    )
    parser.add_argument("--fast", action="store_true", help="Skip cross-validation")
    parser.add_argument(
        "--no-email", action="store_true", help="Skip email notification"
    )
    parser.add_argument(
        "--review", action="store_true", help="Pause after analysis for review"
    )
    args = parser.parse_args()

    result = await run_pipeline(
        ticker=args.ticker,
        refresh=args.refresh,
        fast=args.fast,
        send_email=not args.no_email,
        review=args.review,
    )

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
