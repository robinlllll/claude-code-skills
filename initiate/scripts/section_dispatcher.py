"""Phase 2: Section Dispatcher — builds prompts and dispatches to AI models.

Triple-model architecture for maximum quality on S1-S3:
  - S1-S3 run on ALL THREE models (Gemini+GPT+Grok) in parallel, then Claude merges
  - Each model gets a differentiated prompt (quantitative/strategic/contrarian)
  - S4-S7 run on single assigned providers
  - Red Team (Grok) critiques all S1-S7
  - S8-S9 synthesis (Claude) incorporates red team findings

Section → Model Assignment:
  Triple (Gemini+GPT+Grok→Claude merge): S1 Market, S2 Competitive, S3 Moat
    Gemini = quantitative anchor (tables, TAM, segment breakdowns)
    GPT    = strategic narrative (first-principles, disruptors, "so what")
    Grok   = contrarian/variant (consensus challenges, structural shifts)
  Single (GPT):    S4 Financials, S5 Management, S7 Risks
  Single (Gemini): S6 Valuation
  Red Team (Grok): Adversarial review of S1-S7
  Synthesis (Claude): S8 Conclusion, S9 Research Gaps

Usage:
    python section_dispatcher.py TICKER [--workspace DIR]
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Sibling imports (scripts/ dir)
sys.path.insert(0, str(Path(__file__).parent))
# Parent imports (initiate/ dir — for prompts package)
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MODELS, RUNS_DIR, ANTHROPIC_API_KEY
from ai_client import call_model, parallel_dispatch
from prompts.section_prompts import (
    s1_market_growth,
    s2_competitive,
    s3_moat,
    s4_company_financials,
    s5_management,
    s6_valuation,
    s7_risks,
    red_team as red_team_prompt,
    s8_conclusion,
    s9_research_gaps,
    dual_model_merge,
)


# Dual-model sections: S1-S3 run on BOTH Gemini and GPT, then Claude merges
DUAL_MODEL_SECTIONS = [
    ("S1_Market_Growth", "1. Market & Growth", s1_market_growth, 16000),
    ("S2_Competitive", "2. Competitive Landscape", s2_competitive, 16000),
    ("S3_Moat", "3. Barriers & Moat", s3_moat, 16000),
]

# Single-model sections: S4-S7 (unchanged)
SINGLE_MODEL_SECTIONS = [
    ("S4_Company_Financials", s4_company_financials, "gpt", 10000),
    ("S5_Management", s5_management, "gpt", 8000),
    ("S6_Valuation", s6_valuation, "gemini", 8000),
    ("S7_Risks", s7_risks, "gpt", 8000),
]


async def dispatch_sections(data_pack: dict, workspace: Path = None) -> dict:
    """Run all sections through AI models.

    Phase A:  S1-S3 triple (Gemini+GPT+Grok) + S4-S7 single — all 13 calls parallel
    Phase A2: Claude merges S1-S3 triple outputs (3 calls parallel)
    Phase B:  Red Team review (Grok) — critiques merged S1-S7
    Phase C:  S8-S9 synthesis (incorporates red team findings)

    Returns:
        {
            "sections": {
                "S1": {"content": str, "provider": str, "model": str, "tokens": dict, "elapsed_s": float},
                ...
                "RT": {"content": str, ...},  # Red Team
            },
            "total_tokens": {"input": int, "output": int},
            "total_elapsed_s": float,
            "errors": [str],
        }
    """
    ticker = data_pack["ticker"]
    company = data_pack["company_name"]

    print(f"\n{'=' * 60}")
    print(f"  Phase 2: Section Analysis for {company} ({ticker})")
    print(f"{'=' * 60}\n")

    t0 = time.time()
    sections = {}
    errors = []
    total_in = 0
    total_out = 0

    # ===== Phase A: S1-S3 triple + S4-S7 single — 13 parallel calls =====
    # S1-S3: Gemini (quantitative) + GPT (strategic) + Grok (contrarian)
    TRIPLE_PROVIDERS = ["gemini", "gpt", "grok"]
    print("  [Phase A] Triple-model dispatch: S1-S3 → Gemini+GPT+Grok, S4-S7 → single\n")

    tasks = []
    task_labels = []  # Track (section_key, provider) for each task

    # S1-S3: dispatch to ALL THREE models with differentiated prompts
    for name, title, prompt_fn, max_tokens in DUAL_MODEL_SECTIONS:
        section_key = name.split("_")[0]  # "S1", "S2", "S3"
        for provider in TRIPLE_PROVIDERS:
            # Each provider gets a differentiated prompt (quantitative/strategic/contrarian)
            system_prompt, user_prompt = prompt_fn(data_pack, provider=provider)
            tasks.append(
                {
                    "provider": provider,
                    "prompt": user_prompt,
                    "system_prompt": system_prompt,
                    "model": MODELS.get(provider),
                    "max_tokens": max_tokens,
                }
            )
            task_labels.append((section_key, provider))
            print(f"    {name} → {provider} ({MODELS.get(provider, '?')})")

    # S4-S7: dispatch to single provider
    for name, prompt_fn, provider, max_tokens in SINGLE_MODEL_SECTIONS:
        system_prompt, user_prompt = prompt_fn(data_pack)
        section_key = name.split("_")[0]
        tasks.append(
            {
                "provider": provider,
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "model": MODELS.get(provider),
                "max_tokens": max_tokens,
            }
        )
        task_labels.append((section_key, provider))
        print(f"    {name} → {provider} ({MODELS.get(provider, '?')})")

    print(f"\n    Total: {len(tasks)} parallel AI calls\n")
    results = await parallel_dispatch(tasks)

    # Collect results — dual sections get two results, single sections get one
    dual_raw = {}  # {section_key: {"gemini": result, "gpt": result}}
    for i, (section_key, provider) in enumerate(task_labels):
        result = results[i]
        if result.get("error"):
            errors.append(f"{section_key}_{provider}: {result['error']}")
            print(f"  FAIL {section_key} ({provider}): {result['error']}")
        else:
            tokens = result.get("tokens", {})
            total_in += tokens.get("input", 0)
            total_out += tokens.get("output", 0)
            content_len = len(result.get("content", ""))
            print(
                f"  OK   {section_key} ({provider}): {content_len:,} chars, "
                f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
                f"{result.get('elapsed_s', 0)}s"
            )

        # Route to dual collector or directly to sections
        if section_key in ("S1", "S2", "S3"):
            dual_raw.setdefault(section_key, {})[provider] = result
        else:
            sections[section_key] = result

    # ===== Phase A2: Claude merges S1-S3 triple outputs =====
    merge_provider = "claude" if ANTHROPIC_API_KEY else "gemini"
    merge_model = MODELS.get("claude_synthesis") if ANTHROPIC_API_KEY else MODELS.get("gemini")
    print(f"\n  [Phase A2] Merging S1-S3 triple outputs with {merge_provider}...\n")

    merge_tasks = []
    merge_keys = []
    for name, title, prompt_fn, _ in DUAL_MODEL_SECTIONS:
        section_key = name.split("_")[0]
        raw = dual_raw.get(section_key, {})
        outputs = {p: raw.get(p, {}) for p in TRIPLE_PROVIDERS}
        texts = {p: outputs[p].get("content", "") for p in TRIPLE_PROVIDERS}
        successful = {p: t for p, t in texts.items() if t}

        if not successful:
            sections[section_key] = {
                "content": "",
                "provider": "none",
                "model": "none",
                "tokens": {"input": 0, "output": 0},
                "elapsed_s": 0,
                "error": "All three models failed for this section",
            }
            errors.append(f"{section_key}_merge: All models failed")
            print(f"  SKIP {section_key} merge: all models failed")
            continue
        elif len(successful) == 1:
            # Only one model succeeded — use it directly
            sole_provider = list(successful.keys())[0]
            sections[section_key] = outputs[sole_provider]
            failed = [p for p in TRIPLE_PROVIDERS if p not in successful]
            print(f"  SKIP {section_key} merge: only {sole_provider} succeeded ({', '.join(failed)} failed)")
            continue

        # 2 or 3 models succeeded — build merge prompt
        sys_merge, usr_merge = dual_model_merge(
            section_name=section_key,
            section_title=title,
            data_pack=data_pack,
            gemini_output=texts.get("gemini", ""),
            gpt_output=texts.get("gpt", ""),
            grok_output=texts.get("grok", ""),
        )
        merge_tasks.append(
            {
                "provider": merge_provider,
                "prompt": usr_merge,
                "system_prompt": sys_merge,
                "model": merge_model,
                "max_tokens": 16000,
            }
        )
        merge_keys.append(section_key)
        n_models = len(successful)
        providers_str = "+".join(successful.keys())
        print(f"    {section_key} merge ({n_models} models: {providers_str}) → {merge_provider}")

    if merge_tasks:
        print()
        merge_results = await parallel_dispatch(merge_tasks)

        for i, section_key in enumerate(merge_keys):
            result = merge_results[i]
            result["provider"] = f"merged({merge_provider})"
            sections[section_key] = result

            if result.get("error"):
                # Merge failed — fall back to best available single output
                fallback_order = ["gemini", "gpt", "grok"]
                for fb in fallback_order:
                    if dual_raw[section_key].get(fb, {}).get("content"):
                        sections[section_key] = dual_raw[section_key][fb]
                        break
                errors.append(f"{section_key}_merge: {result['error']} (fell back to single model)")
                print(f"  FAIL {section_key} merge: {result['error']} → using fallback")
            else:
                tokens = result.get("tokens", {})
                total_in += tokens.get("input", 0)
                total_out += tokens.get("output", 0)
                content_len = len(result.get("content", ""))
                print(
                    f"  OK   {section_key} merged: {content_len:,} chars, "
                    f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
                    f"{result.get('elapsed_s', 0)}s"
                )

    # ===== Phase B: Grok Red Team =====
    prior_sections = _combine_sections(sections)

    print(f"\n  [Phase B] Red Team review (Grok)...\n")
    sys_rt, usr_rt = red_team_prompt(data_pack, prior_sections)
    grok_model = MODELS.get("grok", "grok-4-1-fast-reasoning")
    rt_result = await call_model(
        "grok",
        usr_rt,
        system_prompt=sys_rt,
        model=grok_model,
        max_tokens=6000,
    )
    sections["RT"] = rt_result
    if rt_result.get("error"):
        errors.append(f"Red_Team: {rt_result['error']}")
        print(f"  FAIL Red_Team: {rt_result['error']}")
    else:
        tokens = rt_result.get("tokens", {})
        total_in += tokens.get("input", 0)
        total_out += tokens.get("output", 0)
        print(
            f"  OK   Red_Team (Grok): {len(rt_result.get('content', '')):,} chars, "
            f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
            f"{rt_result.get('elapsed_s', 0)}s"
        )

    # ===== Phase C: S8-S9 synthesis =====
    red_team_content = rt_result.get("content", "")
    if red_team_content:
        prior_sections_with_rt = (
            prior_sections
            + "\n\n---\n\n## RED TEAM REVIEW (by Grok — adversarial analysis)\n\n"
            + red_team_content
        )
    else:
        prior_sections_with_rt = prior_sections

    if ANTHROPIC_API_KEY:
        synth_provider = "claude"
        synth_model_s8 = MODELS.get("claude_synthesis")
        synth_model_s9 = MODELS.get("claude_analysis")
    else:
        synth_provider = "gemini"
        synth_model_s8 = MODELS.get("gemini")
        synth_model_s9 = MODELS.get("gemini")

    print(f"  [Phase C] Synthesizing S8-S9 with {synth_provider}...\n")

    # S8: Investment Conclusion (receives S1-S7 + Red Team findings)
    sys8, usr8 = s8_conclusion(data_pack, prior_sections_with_rt)
    r8 = await call_model(
        synth_provider,
        usr8,
        system_prompt=sys8,
        model=synth_model_s8,
        max_tokens=6000,
    )
    sections["S8"] = r8
    if r8.get("error"):
        errors.append(f"S8_Conclusion: {r8['error']}")
        print(f"  FAIL S8_Conclusion: {r8['error']}")
    else:
        tokens = r8.get("tokens", {})
        total_in += tokens.get("input", 0)
        total_out += tokens.get("output", 0)
        print(
            f"  OK   S8_Conclusion: {len(r8.get('content', '')):,} chars, "
            f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
            f"{r8.get('elapsed_s', 0)}s"
        )

    # S9: Research Gaps (also receives red team findings)
    sys9, usr9 = s9_research_gaps(data_pack, prior_sections_with_rt)
    r9 = await call_model(
        synth_provider,
        usr9,
        system_prompt=sys9,
        model=synth_model_s9,
        max_tokens=4000,
    )
    sections["S9"] = r9
    if r9.get("error"):
        errors.append(f"S9_Research_Gaps: {r9['error']}")
        print(f"  FAIL S9_Research_Gaps: {r9['error']}")
    else:
        tokens = r9.get("tokens", {})
        total_in += tokens.get("input", 0)
        total_out += tokens.get("output", 0)
        print(
            f"  OK   S9_Research_Gaps: {len(r9.get('content', '')):,} chars, "
            f"{tokens.get('input', 0):,}+{tokens.get('output', 0):,} tokens, "
            f"{r9.get('elapsed_s', 0)}s"
        )

    total_elapsed = round(time.time() - t0, 1)

    # Summary — count: S1-S3 merged + S4-S7 + RT + S8 + S9 = 11 entries
    successful = sum(1 for s in sections.values() if not s.get("error"))
    total_sections = len(sections)
    print(f"\n{'=' * 60}")
    print(f"  Phase 2 Complete: {successful}/{total_sections} sections, {total_elapsed}s")
    print(
        f"  Tokens: {total_in:,} input + {total_out:,} output = {total_in + total_out:,} total"
    )
    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors:
            print(f"    - {e}")
    print(f"{'=' * 60}\n")

    result = {
        "sections": sections,
        "total_tokens": {"input": total_in, "output": total_out},
        "total_elapsed_s": total_elapsed,
        "errors": errors,
    }

    # Save to workspace if provided
    if workspace:
        workspace.mkdir(parents=True, exist_ok=True)
        output_path = workspace / "sections.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Saved: {output_path}")

    return result


def _combine_sections(sections: dict) -> str:
    """Combine S1-S7 content for synthesis context."""
    parts = []
    for key in ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]:
        section = sections.get(key, {})
        content = section.get("content", "")
        if content:
            provider = section.get("provider", "unknown")
            parts.append(f"## {key} (by {provider})\n\n{content}")
        else:
            error = section.get("error", "No content")
            parts.append(f"## {key}\n\n[Section unavailable: {error}]")
    return "\n\n---\n\n".join(parts)


# ============ CLI entry point ============


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Coverage Initiation — Phase 2: Section Dispatch"
    )
    parser.add_argument("ticker", help="Stock ticker (must have cached data pack)")
    parser.add_argument("--workspace", help="Output directory", default=None)
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # Load cached data pack
    from data_collector import load_cached

    data_pack = load_cached(ticker)
    if not data_pack:
        print(
            f"  ERROR: No cached data pack for {ticker}. Run data_collector.py first."
        )
        sys.exit(1)

    workspace = (
        Path(args.workspace) if args.workspace else RUNS_DIR / f"{ticker}_sections"
    )
    result = await dispatch_sections(data_pack, workspace)

    if result["errors"]:
        print(f"\n  WARNING: {len(result['errors'])} section(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
