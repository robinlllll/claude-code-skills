"""Test S1-S3 v2 prompts — run all 3 sections on all 3 models for comparison.

Usage:
    python test_s1s3_compare.py TICKER
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MODELS, RUNS_DIR
from ai_client import call_model, parallel_dispatch
from prompts.section_prompts import s1_market_growth, s2_competitive, s3_moat


SECTIONS = [
    ("S1_Market_Growth", "1. Market & Growth", s1_market_growth),
    ("S2_Competitive", "2. Competitive Landscape", s2_competitive),
    ("S3_Moat", "3. Barriers & Moat", s3_moat),
]
PROVIDERS = ["gemini", "gpt", "grok"]


async def run_test(ticker: str):
    # Load cached data pack
    cache_path = RUNS_DIR / "_cache" / f"{ticker}_data_pack.json"
    if not cache_path.exists():
        print(f"ERROR: No cached data for {ticker}. Run data_collector.py first.")
        sys.exit(1)

    with open(cache_path, "r", encoding="utf-8") as f:
        data_pack = json.load(f)

    company = data_pack.get("company_name", ticker)
    print(f"\n{'=' * 70}")
    print(f"  S1-S3 V2 Prompt Comparison Test: {company} ({ticker})")
    print(f"  Models: {', '.join(f'{p}={MODELS[p]}' for p in PROVIDERS)}")
    print(f"{'=' * 70}\n")

    # Build all 9 tasks (3 sections × 3 providers)
    tasks = []
    task_labels = []
    for name, title, prompt_fn in SECTIONS:
        for provider in PROVIDERS:
            sys_prompt, usr_prompt = prompt_fn(data_pack, provider=provider)
            tasks.append({
                "provider": provider,
                "prompt": usr_prompt,
                "system_prompt": sys_prompt,
                "model": MODELS[provider],
                "max_tokens": 16000,
            })
            task_labels.append((name, provider))
            # Print prompt length for comparison
            total_chars = len(sys_prompt) + len(usr_prompt)
            print(f"  {name} → {provider}: prompt {total_chars:,} chars")

    print(f"\n  Dispatching {len(tasks)} parallel calls...\n")
    t0 = time.time()
    results = await parallel_dispatch(tasks)
    elapsed = time.time() - t0

    # Save results
    output_dir = RUNS_DIR / f"{ticker}_s1s3_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for i, (label, provider) in enumerate(task_labels):
        result = results[i]
        section_key = label.split("_")[0]  # "S1", "S2", "S3"
        content = result.get("content", "")
        tokens = result.get("tokens", {})
        error = result.get("error")

        status = "FAIL" if error else "OK"
        print(
            f"  {status}  {section_key} ({provider}): "
            f"{len(content):,} chars, "
            f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
            f"{result.get('elapsed_s', 0)}s"
            + (f" ERROR: {error}" if error else "")
        )

        # Save individual output
        filename = f"{section_key}_{provider}.md"
        with open(output_dir / filename, "w", encoding="utf-8") as f:
            f.write(f"# {label} — {provider.upper()} ({MODELS[provider]})\n\n")
            if error:
                f.write(f"**ERROR:** {error}\n")
            else:
                f.write(content)

        summary.append({
            "section": section_key,
            "provider": provider,
            "model": MODELS[provider],
            "chars": len(content),
            "input_tokens": tokens.get("input", 0),
            "output_tokens": tokens.get("output", 0),
            "elapsed_s": result.get("elapsed_s", 0),
            "error": error,
        })

    # Save summary
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Print comparison table
    print(f"\n{'=' * 70}")
    print(f"  Results saved to: {output_dir}")
    print(f"  Total wall-clock: {elapsed:.1f}s")
    print(f"{'=' * 70}")
    print(f"\n  {'Section':<6} {'Provider':<8} {'Chars':>8} {'Out Tok':>8} {'Time':>6}")
    print(f"  {'-'*6:<6} {'-'*8:<8} {'-'*8:>8} {'-'*8:>8} {'-'*6:>6}")
    for s in summary:
        print(
            f"  {s['section']:<6} {s['provider']:<8} "
            f"{s['chars']:>8,} {s['output_tokens']:>8,} "
            f"{s['elapsed_s']:>5.1f}s"
        )

    print(f"\n  Files:")
    for p in sorted(output_dir.glob("*.md")):
        print(f"    {p.name}")
    print()

    return output_dir


if __name__ == "__main__":
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "SITM"
    asyncio.run(run_test(ticker))
