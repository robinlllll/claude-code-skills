"""
Multi-AI Plan Review Script
Sends a plan to Gemini, Grok, and ChatGPT in parallel with role-specific prompts.
Saves individual reviews as markdown files.

Usage:
    python review.py <plan-file-path> [--output-dir <dir>] [--models gemini,grok,chatgpt]
"""

import sys
import os
import argparse
import threading
import time
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

# Load API keys from both .env locations
load_dotenv(Path.home() / "Screenshots" / ".env")
load_dotenv(Path.home() / "13F-CLAUDE" / ".env")

# ── Role-specific prompt templates ──

GEMINI_PROMPT = """You are a senior software architect reviewing an implementation plan.

Please review this plan critically and provide:

1. **Architecture Assessment** — Is the overall design sound? Any anti-patterns or over-engineering?
2. **Data Model Review** — Is any schema/data model well-designed? Missing fields? Indexing issues?
3. **API/Integration Risks** — External dependency risks, data quality concerns, coverage gaps.
4. **What's Missing** — Important features, edge cases, or scenarios not covered?
5. **Implementation Order Critique** — Is the proposed sequence optimal? Would you reorder?
6. **Alternative Approaches** — Would you consider different tools, storage, or architectures?
7. **Concrete Improvement Suggestions** — Top 5 specific, actionable changes you'd make.

Be specific, critical, and constructive. Don't be polite — be useful.

Here is the plan:

{plan_content}"""

GROK_PROMPT = """You are a contrarian technical reviewer. Your job is to find flaws, risks, and blind spots that the plan author missed. You have a production-ops mindset — think about what happens when this system runs in production for 12 months.

Review this implementation plan and provide:

1. **Kill Shots** — What could make this plan fail entirely? Single points of failure, deal-breakers.
2. **Data Quality Traps** — Specific data issues that could lead to wrong decisions or signals.
3. **Operational Risks** — What happens when things fail? Cron jobs, API changes, DB corruption, scaling.
4. **Over-Engineering Check** — What parts are unnecessary complexity? What should be simpler?
5. **Under-Engineering Check** — What parts are too naive and will cause problems at scale?
6. **Missing Edge Cases** — Scenarios that would break this system.
7. **Alternative Approaches** — Better tools, data sources, or architectures?
8. **Top 5 Changes** — Your highest-priority concrete changes.

Be blunt. This is for someone making real decisions based on this system.

Here is the plan:

{plan_content}"""

CHATGPT_PROMPT = """You are an expert technology advisor reviewing an implementation plan. Focus on whether this system will actually deliver value to the end user, not just whether it's technically correct.

Review this plan and provide:

1. **Value Assessment** — Will the proposed system actually produce useful output? What's the evidence?
2. **Architecture Fitness** — Is the tech stack appropriate for the scale and use case?
3. **Coverage Analysis** — What's well-covered vs poorly covered? Any blind spots?
4. **Design Review** — Schema, API, data model — are they fit for purpose?
5. **Gap Analysis** — What capabilities are missing that the user will need within 6 months?
6. **Integration Complexity** — Is the integration surface too large? Risk of breakage?
7. **Cost-Benefit Analysis** — Is the investment (time, money, maintenance) worth the output?
8. **Top 5 Improvements** — Your highest-priority specific, actionable changes.

Focus on utility, not just technical correctness. The goal is better decisions, not a prettier codebase.

Here is the plan:

{plan_content}"""


def call_gemini(plan_content: str) -> str:
    """Send plan to Gemini and return response text."""
    import google.genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "ERROR: GEMINI_API_KEY not found in .env files"

    client = google.genai.Client(api_key=api_key)
    prompt = GEMINI_PROMPT.format(plan_content=plan_content)

    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=prompt,
    )
    return response.text


def call_grok(plan_content: str) -> str:
    """Send plan to Grok and return response text."""
    from openai import OpenAI

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return "ERROR: XAI_API_KEY not found in .env files"

    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    prompt = GROK_PROMPT.format(plan_content=plan_content)

    response = client.chat.completions.create(
        model="grok-4-1-fast-reasoning",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content


def call_chatgpt(plan_content: str) -> str:
    """Send plan to ChatGPT and return response text."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "ERROR: OPENAI_API_KEY not found in .env files"

    client = OpenAI(api_key=api_key)
    prompt = CHATGPT_PROMPT.format(plan_content=plan_content)

    response = client.chat.completions.create(
        model="o3",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=16000,
    )
    return response.choices[0].message.content


def save_review(
    output_dir: Path, plan_name: str, model: str, content: str, tags: list[str]
):
    """Save a review as a markdown file with YAML frontmatter."""
    today = date.today().isoformat()
    tags_str = ", ".join(tags)

    md = f"""---
tags: [{tags_str}]
date: {today}
model: {model}
source: {plan_name}.md
type: ai-review
---

# {model.title()} Review: {plan_name}

*Model: {model} | Date: {today}*

{content}
"""

    filepath = output_dir / f"{plan_name}-review-{model}.md"
    filepath.write_text(md, encoding="utf-8")
    print(f"  Saved: {filepath.name}")
    return filepath


def run_review(
    plan_path: str, output_dir: str = None, models: str = "gemini,grok,chatgpt"
):
    """Main entry point for plan review."""
    plan_file = Path(plan_path)
    if not plan_file.exists():
        print(f"ERROR: Plan file not found: {plan_path}")
        sys.exit(1)

    plan_content = plan_file.read_text(encoding="utf-8")
    plan_name = plan_file.stem  # e.g., "plan-consensus-tracker"

    if output_dir:
        out = Path(output_dir)
    else:
        out = plan_file.parent
    out.mkdir(parents=True, exist_ok=True)

    # Determine which models to use
    model_list = [m.strip().lower() for m in models.split(",")]

    model_funcs = {
        "gemini": call_gemini,
        "grok": call_grok,
        "chatgpt": call_chatgpt,
    }

    # Extract domain tags from plan name
    domain_tags = plan_name.replace("plan-", "").split("-")
    base_tags = ["plan-review"] + domain_tags[:2]

    print(f"Plan Review: {plan_name}")
    print(f"Models: {', '.join(model_list)}")
    print(f"Output: {out}")
    print(f"Plan length: {len(plan_content):,} chars")
    print()

    # Run all models in parallel
    results = {}
    errors = {}

    def run_model(name):
        try:
            print(f"  [{name}] Starting...")
            t0 = time.time()
            result = model_funcs[name](plan_content)
            elapsed = time.time() - t0
            results[name] = result
            print(f"  [{name}] Done ({elapsed:.1f}s, {len(result):,} chars)")
        except Exception as e:
            errors[name] = str(e)
            print(f"  [{name}] ERROR: {e}")

    threads = []
    for model in model_list:
        if model in model_funcs:
            t = threading.Thread(target=run_model, args=(model,))
            threads.append(t)
            t.start()
        else:
            print(f"  WARNING: Unknown model '{model}', skipping")

    for t in threads:
        t.join()

    print()

    # Save individual reviews
    saved_files = []
    for model in model_list:
        if model in results:
            tags = base_tags + [model]
            f = save_review(out, plan_name, model, results[model], tags)
            saved_files.append(f)

    # Report errors
    if errors:
        print()
        print("Errors:")
        for model, err in errors.items():
            print(f"  {model}: {err}")

    print()
    print(f"Reviews saved: {len(saved_files)}/{len(model_list)}")
    for f in saved_files:
        print(f"  {f}")

    return saved_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-AI Plan Review")
    parser.add_argument("plan_path", help="Path to the plan markdown file")
    parser.add_argument(
        "--output-dir", help="Directory to save reviews (default: same as plan)"
    )
    parser.add_argument(
        "--models",
        default="gemini,grok,chatgpt",
        help="Comma-separated models to use (default: gemini,grok,chatgpt)",
    )

    args = parser.parse_args()
    run_review(args.plan_path, args.output_dir, args.models)
