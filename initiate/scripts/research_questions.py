"""Research Questions for Coverage Initiation Reports.

Reads [?] questions from a coverage initiation report, sends them to
dual-AI (GPT o3 + Grok) in parallel, and writes answers back to the file.

Supports multiple rounds: re-run after adding new [?] questions.

Usage:
    python research_questions.py TICKER [--dry-run] [--file PATH] [--model MODEL] [--gpt-only]
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    OPENAI_API_KEY,
    XAI_API_KEY,
    OUTPUT_DIR,
)

# ============ Question Detection ============


def _normalize_question_markers(filepath: Path) -> int:
    """Normalize informal question markers to standard [?] format.

    Converts:
      - ? question  →  - [?] question
      - ？question  →  - [?] question
      - [ ] ?question → - [?] question
      * ?question   →  - [?] question
      N. ?question  →  - [?] question

    Returns number of markers normalized.
    """
    text = filepath.read_text(encoding="utf-8")
    original = text

    # Pattern: bullet + optional checkbox + ? or ？ + question
    patterns = [
        (r"^(\s*)-\s*\[\s*\]\s*[?？]\s*", r"\1- [?] "),  # - [ ] ?q
        (r"^(\s*)-\s*[?？]\s*", r"\1- [?] "),  # - ?q
        (r"^(\s*)\*\s*[?？]\s*", r"\1- [?] "),  # * ?q
        (r"^(\s*)\d+\.\s*[?？]\s*", r"\1- [?] "),  # 1. ?q
        (r"^(\s*)[?？]\s+", r"\1- [?] "),  # ?q at line start
    ]

    count = 0
    for pat, repl in patterns:
        text, n = re.subn(pat, repl, text, flags=re.MULTILINE)
        count += n

    if text != original:
        filepath.write_text(text, encoding="utf-8")

    return count


def parse_questions(filepath: Path) -> list[dict]:
    """Find all pending [?] questions in the report.

    Returns list of dicts with: question, line_number, raw_line, section, local_context
    """
    lines = filepath.read_text(encoding="utf-8").splitlines()
    questions = []
    current_section = "Unknown"

    for i, line in enumerate(lines):
        # Track which section we're in
        heading_match = re.match(r"^#{1,3}\s+(.+)", line)
        if heading_match:
            current_section = heading_match.group(1).strip()

        # Find [?] questions
        q_match = re.match(r"^\s*-\s*\[\?\]\s+(.+)$", line)
        if q_match:
            questions.append(
                {
                    "question": q_match.group(1).strip(),
                    "line_number": i,
                    "raw_line": line,
                    "section": current_section,
                    "local_context": _extract_local_context(lines, i),
                }
            )

    return questions


def _extract_local_context(
    lines: list[str], question_line: int, window: int = 20
) -> str:
    """Extract surrounding context (20 lines above) for a question."""
    start = max(0, question_line - window)
    context_lines = []
    for line in lines[start:question_line]:
        # Skip other questions and blank lines
        if re.match(r"^\s*-\s*\[\?\]", line):
            continue
        if line.strip():
            context_lines.append(line)
    return "\n".join(context_lines[-15:])  # Last 15 non-empty lines


# ============ Context Assembly ============


def assemble_context(filepath: Path, max_chars: int = 12000) -> str:
    """Extract report context for the AI prompt.

    Pulls: Quick Facts + key section summaries (first ~500 chars each).
    """
    text = filepath.read_text(encoding="utf-8")
    parts = []

    # Extract Quick Facts table
    qf_match = re.search(r"## Quick Facts\n(.*?)(?=\n##|\n---)", text, re.DOTALL)
    if qf_match:
        parts.append(f"## Quick Facts\n{qf_match.group(1).strip()}")

    # Extract first ~600 chars of each major section
    section_pattern = re.compile(r"^# (\d+\..+?)$", re.MULTILINE)
    for match in section_pattern.finditer(text):
        section_title = match.group(1)
        section_start = match.end()
        # Find next section or end
        next_match = section_pattern.search(text, section_start)
        section_end = next_match.start() if next_match else len(text)
        section_text = text[section_start:section_end].strip()
        # Take first 600 chars as summary
        summary = section_text[:600]
        if len(section_text) > 600:
            # Cut at last complete sentence
            last_period = summary.rfind(".")
            if last_period > 300:
                summary = summary[: last_period + 1]
        parts.append(f"### {section_title}\n{summary}")

    # Extract Red Team section summary
    rt_match = re.search(
        r"# Red Team Review.*?\n(.*?)(?=\n---\n|\n# \d)", text, re.DOTALL
    )
    if rt_match:
        rt_text = rt_match.group(1).strip()[:800]
        parts.append(f"### Red Team Review (Grok)\n{rt_text}")

    context = "\n\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars]
    return context


# ============ Prompt Building ============


def build_prompt(
    ticker: str,
    company_name: str,
    questions: list[dict],
    report_context: str,
) -> str:
    """Build the batch prompt for dual-AI answering."""
    n = len(questions)

    # Build questions block
    q_block = []
    for i, q in enumerate(questions, 1):
        q_block.append(f"### Q{i}. {q['question']}")
        q_block.append(f"> Section: {q['section']}")
        if q["local_context"]:
            ctx = q["local_context"][:500]
            q_block.append(f"> Context excerpt:\n> {ctx}")
        q_block.append("")

    questions_text = "\n".join(q_block)

    prompt = f"""## Background
Coverage Initiation Report for {company_name} ({ticker}).
This is a 9-section CFA-level equity research report produced by a multi-AI pipeline (Gemini + GPT + Grok).
The user (a portfolio manager) has read the report and marked questions that need deeper investigation.

## Report Summary
{report_context}

---

## Research Questions ({n} questions)

{questions_text}

## Answer Requirements
1. Number each answer to match the question (Q1, Q2, etc.)
2. **Incremental value first** — industry cross-comparisons, historical trend analysis, external data verification, independent judgment
3. Each answer should be comprehensive and thorough — no word limit
4. Structure: One-sentence conclusion → Key evidence → Mark uncertainties as "needs additional data"
5. Write in English
6. For each question, consider: what does the report say, what does it miss, and what's the independent view?

## Data Integrity Requirements (CRITICAL)
- NEVER fabricate external data, market figures, or statistics
- Tag all external data with source: [SEC/IR], [Industry Report], [News], [Personal Estimate], [No Reliable Data]
- If citing news or industry reports, include the source name and approximate date
- "I don't know" is 100x more valuable than fabricated data
- If the report's claim is questionable, say so explicitly and explain why
"""
    return prompt


SYSTEM_PROMPT = """You are a senior buy-side equity analyst reviewing a coverage initiation report.
Your job is to answer the portfolio manager's follow-up questions with INCREMENTAL insight —
do not merely repeat what the report already says.

Focus on:
- Cross-industry comparisons and historical analogs
- Data verification and source quality assessment
- Contrarian perspectives and risk factors the report may underweight
- Specific, actionable next steps for further research

Be direct, specific, and honest about uncertainty. Never fabricate data."""


# ============ AI Dispatch ============


def send_to_gpt(prompt: str, api_key: str, model: str = "o3") -> str:
    """Send prompt to GPT and return answer text."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # o3 and o-series don't support temperature
    kwargs = {"model": model, "messages": messages}
    if model.startswith("o"):
        kwargs["max_completion_tokens"] = 10000
    else:
        kwargs["max_completion_tokens"] = 10000

    try:
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        print(f"  GPT attempt 1 failed: {e}. Retrying...")
        time.sleep(3)
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


def send_to_grok(prompt: str, api_key: str) -> str:
    """Send prompt to Grok and return answer text."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    response = client.chat.completions.create(
        model="grok-4-1-fast-reasoning",
        messages=messages,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ============ File Writing ============


def _count_existing_rounds(lines: list[str]) -> int:
    """Count how many answer rounds already exist in the file."""
    count = 0
    for line in lines:
        if re.match(r"^## Research Questions — Round \d+", line):
            count += 1
        # Also count legacy single-round header as round 1
        if line.startswith("## Research Questions — AI Answers"):
            count += 1
    return count


def write_answers_to_top(
    filepath: Path,
    questions: list[dict],
    gpt_answer: str | None,
    grok_answer: str | None,
    gpt_model: str = "o3",
) -> None:
    """Write AI answers to top of file and mark [?] → [x].

    Multi-round support: each round gets its own numbered section.
    Previous rounds are preserved — new round is inserted above them.
    """
    lines = filepath.read_text(encoding="utf-8").splitlines()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = len(questions)

    # Determine round number
    round_num = _count_existing_rounds(lines) + 1

    # Build answer block for this round
    q_summary = ", ".join(f"Q{i + 1}" for i in range(n))
    answer_parts = [
        f"## Research Questions — Round {round_num}",
        "",
        f"> {n} questions ({q_summary}) | {now}",
        "",
    ]

    if gpt_answer:
        answer_parts.append(f"### {gpt_model}")
        answer_parts.append("")
        answer_parts.append(gpt_answer.strip())
        answer_parts.append("")

    if grok_answer:
        answer_parts.append("### Grok")
        answer_parts.append("")
        answer_parts.append(grok_answer.strip())
        answer_parts.append("")

    answer_parts.append("---")
    answer_parts.append("")

    answer_block = "\n".join(answer_parts)

    # Find insertion point: after frontmatter, before first heading or existing round
    insert_at = 0
    in_frontmatter = False
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == "---":
            in_frontmatter = False
            insert_at = i + 1
            continue
        if not in_frontmatter and (
            line.startswith("#") or line.startswith("## Research Questions")
        ):
            insert_at = i
            break

    # Insert new round at top (above previous rounds)
    answer_lines = answer_block.splitlines()
    for j, al in enumerate(answer_lines):
        lines.insert(insert_at + j, al)

    # Mark [?] → [x] only for THIS round's questions
    final_text = "\n".join(lines)
    for q in questions:
        # Escape the question text for regex and replace its specific [?]
        escaped = re.escape(q["question"])
        final_text = re.sub(
            rf"- \[\?\] {escaped}",
            f"- [x] {q['question']}",
            final_text,
            count=1,
        )

    filepath.write_text(final_text, encoding="utf-8")
    print(f"  Round {round_num} answers written to: {filepath}")
    print(f"  {n} questions marked [?] → [x]")


# ============ Report Finding ============


def find_latest_report(ticker: str) -> Path | None:
    """Find the latest coverage initiation report for a ticker."""
    report_dir = OUTPUT_DIR / ticker.upper()
    if not report_dir.exists():
        return None

    reports = sorted(report_dir.glob("*.md"), reverse=True)
    if not reports:
        return None

    return reports[0]


def extract_company_name(filepath: Path) -> str:
    """Extract company name from report frontmatter or title."""
    text = filepath.read_text(encoding="utf-8")

    # Try frontmatter title
    title_match = re.search(r'^title:\s*"(.+?)\s*\(', text, re.MULTILINE)
    if title_match:
        return title_match.group(1).strip()

    # Try first heading
    h1_match = re.search(r"^#\s+(.+?)\s*\(", text, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    return "Unknown Company"


# ============ Main ============


def main():
    parser = argparse.ArgumentParser(
        description="Coverage Initiation — Research Questions (dual-AI)"
    )
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview prompt, don't send"
    )
    parser.add_argument("--file", help="Specific report file path")
    parser.add_argument("--model", default="o3", help="GPT model (default: o3)")
    parser.add_argument("--gpt-only", action="store_true", help="Skip Grok, GPT only")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # Find report
    if args.file:
        filepath = Path(args.file)
    else:
        filepath = find_latest_report(ticker)

    if not filepath or not filepath.exists():
        print(f"  ERROR: No report found for {ticker}")
        print(f"  Searched: {OUTPUT_DIR / ticker}")
        sys.exit(1)

    print(f"  Report: {filepath.name}")

    # Normalize markers
    normalized = _normalize_question_markers(filepath)
    if normalized:
        print(f"  Normalized {normalized} question markers")

    # Parse questions
    questions = parse_questions(filepath)
    if not questions:
        print("  No [?] questions found in the report.")
        print("  Add questions by editing the report: - [?] Your question here")
        sys.exit(0)

    print(f"  Found {len(questions)} questions:")
    for i, q in enumerate(questions, 1):
        print(f"    Q{i}. {q['question'][:80]}...")
        print(f"        Section: {q['section']}")

    # Assemble context
    company = extract_company_name(filepath)
    context = assemble_context(filepath)
    prompt = build_prompt(ticker, company, questions, context)

    print(f"\n  Prompt: {len(prompt):,} chars")

    if args.dry_run:
        print(f"\n{'=' * 60}")
        print("  DRY RUN — Prompt preview (first 4000 chars):")
        print(f"{'=' * 60}\n")
        print(prompt[:4000])
        if len(prompt) > 4000:
            print(f"\n  ... [{len(prompt) - 4000:,} more chars]")
        sys.exit(0)

    # Check API keys
    if not OPENAI_API_KEY:
        print("  ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    # Dispatch to AI
    gpt_answer = None
    grok_answer = None

    if args.gpt_only or not XAI_API_KEY:
        if not XAI_API_KEY and not args.gpt_only:
            print("  WARNING: XAI_API_KEY not set, running GPT only")
        print(f"\n  Sending to GPT ({args.model})...")
        t0 = time.time()
        gpt_answer = send_to_gpt(prompt, OPENAI_API_KEY, args.model)
        elapsed = time.time() - t0
        print(f"  GPT done: {len(gpt_answer):,} chars, {elapsed:.1f}s")
    else:
        print(f"\n  Sending to GPT ({args.model}) + Grok in parallel...")
        t0 = time.time()

        with ThreadPoolExecutor(max_workers=2) as ex:
            gpt_future = ex.submit(send_to_gpt, prompt, OPENAI_API_KEY, args.model)
            grok_future = ex.submit(send_to_grok, prompt, XAI_API_KEY)

            try:
                gpt_answer = gpt_future.result()
                print(f"  GPT done: {len(gpt_answer):,} chars")
            except Exception as e:
                print(f"  GPT FAILED: {e}")

            try:
                grok_answer = grok_future.result()
                print(f"  Grok done: {len(grok_answer):,} chars")
            except Exception as e:
                print(f"  Grok FAILED: {e}")

        elapsed = time.time() - t0
        print(f"  Total: {elapsed:.1f}s")

    if not gpt_answer and not grok_answer:
        print("  ERROR: Both models failed. No answers to write.")
        sys.exit(1)

    # Write answers
    write_answers_to_top(filepath, questions, gpt_answer, grok_answer, args.model)
    print("\n  Done. Re-run after adding new [?] questions for another round.")


if __name__ == "__main__":
    main()
