#!/usr/bin/env python3
"""
Research Questions Router — Parse [?] questions from earnings analysis,
assemble context, send to ChatGPT, write answers back to the original file.

Usage:
    python research_questions.py TICKER [--dry-run] [--file PATH] [--model MODEL]
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ────────────────────────────────────────────────────

OBSIDIAN_VAULT = Path.home() / "Documents" / "Obsidian Vault"
EARNINGS_FOLDER = OBSIDIAN_VAULT / "研究" / "财报分析"
PORTFOLIO_DIR = Path.home() / "PORTFOLIO" / "research" / "companies"

CHATGPT_SCRIPTS = Path.home() / ".claude" / "skills" / "chatgpt" / "scripts"

# ── Constants ────────────────────────────────────────────────

MAX_CONTEXT_CHARS = 6000
MAX_THESIS_CHARS = 2000
FALLBACK_CHARS = 8000


# ── Parse ────────────────────────────────────────────────────


def find_latest_analysis(ticker: str, file_path: str = None) -> Path | None:
    """Find the latest analysis file for a ticker. Returns None if not found."""
    if file_path:
        p = Path(file_path)
        if p.exists():
            return p
        print(f"Error: Specified file not found: {file_path}", file=sys.stderr)
        return None

    folder = EARNINGS_FOLDER / ticker.upper()
    if not folder.exists():
        print(f"Error: No analysis folder for {ticker}: {folder}", file=sys.stderr)
        return None

    # Find analysis files (skip _ prefixed notes files)
    analyses = sorted(
        [f for f in folder.glob("*.md") if not f.name.startswith("_")],
        key=lambda f: f.name,
        reverse=True,
    )
    if not analyses:
        print(f"Error: No analysis files found in {folder}", file=sys.stderr)
        return None

    return analyses[0]


def parse_research_questions(filepath: Path) -> list[dict]:
    """
    Parse [?] research questions from a file.
    Returns list of {question, line_number, raw_line}. Skips [x] lines.
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    questions = []
    in_rq_section = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect section boundaries
        if stripped.startswith("## Research Questions"):
            in_rq_section = True
            continue
        if in_rq_section and stripped.startswith("## "):
            break  # Hit next section

        if not in_rq_section:
            continue

        # Match - [?] question pattern
        m = re.match(r"^- \[\?\]\s+(.+)$", stripped)
        if m:
            questions.append(
                {
                    "question": m.group(1).strip(),
                    "line_number": i,  # 0-indexed
                    "raw_line": line,
                }
            )

    return questions


# ── Context Assembly ─────────────────────────────────────────


def _extract_section(text: str, header_pattern: str, max_chars: int) -> str:
    """Extract content under a markdown header matching the pattern."""
    lines = text.split("\n")
    collecting = False
    collected = []
    chars = 0

    for line in lines:
        if re.match(header_pattern, line.strip()):
            collecting = True
            continue
        if collecting:
            # Stop at next same-level or higher header
            if re.match(r"^#{1,4}\s", line.strip()) and collected:
                break
            collected.append(line)
            chars += len(line)
            if chars >= max_chars:
                break

    return "\n".join(collected).strip()


def _extract_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter fields."""
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("---", 3)
    if end == -1:
        return fm
    block = text[3:end]
    for line in block.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def assemble_context(ticker: str, analysis_path: Path) -> dict:
    """
    Assemble context from analysis file + thesis.
    Returns {analysis_summary, performance_snapshot, thesis_summary, company, quarters}.
    """
    text = analysis_path.read_text(encoding="utf-8")
    fm = _extract_frontmatter(text)

    company = fm.get("company", ticker.upper())
    quarters = fm.get("quarters", "")

    # Section 1: 综合评估 (~4k chars)
    section1 = _extract_section(
        text, r"^#{1,5}\s*1\.\s*综合评估", MAX_CONTEXT_CHARS
    )

    # Section 2: 业绩概览 (~2k chars)
    section2 = _extract_section(text, r"^#{1,5}\s*2\.\s*业绩概览", 2000)

    # Fallback: if Section 1 not found, use first 8k chars of AI Analysis
    if not section1:
        ai_section = _extract_section(text, r"^##\s*AI Analysis", FALLBACK_CHARS)
        section1 = ai_section[:FALLBACK_CHARS] if ai_section else text[:FALLBACK_CHARS]

    # Thesis summary
    thesis_summary = ""
    thesis_path = PORTFOLIO_DIR / ticker.upper() / "thesis.md"
    if thesis_path.exists():
        thesis_text = thesis_path.read_text(encoding="utf-8")
        # Extract Bull Case + Bear Case + Core Thesis
        core = _extract_section(thesis_text, r"^##\s*Core Thesis", 500)
        bull = _extract_section(thesis_text, r"^##\s*Bull Case", 800)
        bear = _extract_section(thesis_text, r"^##\s*Bear Case", 800)
        parts = []
        if core:
            parts.append(f"**Core Thesis:** {core}")
        if bull:
            parts.append(f"**Bull Case:** {bull}")
        if bear:
            parts.append(f"**Bear Case:** {bear}")
        thesis_summary = "\n\n".join(parts)[:MAX_THESIS_CHARS]

    return {
        "analysis_summary": section1,
        "performance_snapshot": section2,
        "thesis_summary": thesis_summary or "暂无 thesis 记录",
        "company": company,
        "quarters": quarters,
    }


# ── Prompt ───────────────────────────────────────────────────

PROMPT_TEMPLATE = """## 背景
{company} ({ticker}) {quarters} 财报分析。

## 核心发现
{analysis_summary}

## 业绩数据
{performance_snapshot}

## 投资论点
{thesis_summary}

---

## 问题
{question}

## 回答格式
- 一句话结论 + 多头/空头信号
- 关键论据（引用页码，如 p.10）
- 信息不足处标注"需额外数据"
- 中文，200字以内，不用emoji，不用分隔线"""


def build_prompt(question: str, context: dict) -> str:
    """Build the full prompt for ChatGPT."""
    return PROMPT_TEMPLATE.format(
        company=context["company"],
        ticker=context.get("ticker", ""),
        quarters=context["quarters"],
        analysis_summary=context["analysis_summary"] or "（无）",
        performance_snapshot=context["performance_snapshot"] or "（无）",
        thesis_summary=context["thesis_summary"],
        question=question,
    )


# ── ChatGPT ─────────────────────────────────────────────────


def send_to_chatgpt(question: str, context: dict, model: str = None) -> str:
    """Send a single question to ChatGPT with assembled context. Returns answer text."""
    sys.path.insert(0, str(CHATGPT_SCRIPTS))
    from chatgpt_api import ask_chatgpt

    prompt = build_prompt(question, context)
    system_msg = (
        "你是资深股票分析师。回答简洁精准：一句话结论 + 关键论据 + 页码引用。"
        "中文，200字以内。不用emoji，不用分隔线，不用标题格式。直接回答问题。"
    )

    kwargs = {"system": system_msg, "no_history": False}
    if model:
        kwargs["model"] = model

    return ask_chatgpt(prompt, **kwargs)


# ── Write Back ───────────────────────────────────────────────


def write_answers_to_file(filepath: Path, qa_pairs: list[dict]) -> None:
    """
    Write answers back to the original file.
    For each pair: [?] → [x], insert blockquote answer below.
    Re-reads file before each write to handle concurrent edits.
    """
    for pair in qa_pairs:
        # Re-read file for each question (safety against concurrent edits)
        text = filepath.read_text(encoding="utf-8")
        lines = text.split("\n")

        question_text = pair["question"]
        answer = pair["answer"]
        model = pair.get("model", "GPT-5.2")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Find the matching [?] line
        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^- \[\?\]\s+", line.strip()) and question_text in line:
                target_idx = i
                break

        if target_idx is None:
            print(f"  Warning: Could not find [?] line for: {question_text[:50]}...")
            continue

        # Replace [?] with [x]
        lines[target_idx] = lines[target_idx].replace("- [?]", "- [x]", 1)

        # Format answer as indented blockquote
        answer_lines = answer.strip().split("\n")
        formatted = [f"  > **{model} | {now_str}**", "  >"]
        for aline in answer_lines:
            formatted.append(f"  > {aline}")
        formatted.append("")  # blank line after blockquote

        # Insert after the [x] line
        insert_pos = target_idx + 1
        # Skip any existing blockquote content from a previous run (shouldn't happen but be safe)
        while insert_pos < len(lines) and lines[insert_pos].strip().startswith(">"):
            insert_pos += 1

        for j, fline in enumerate(formatted):
            lines.insert(insert_pos + j, fline)

        filepath.write_text("\n".join(lines), encoding="utf-8")
        print(f"  ✓ Wrote answer for: {question_text[:60]}...")


# ── Main ─────────────────────────────────────────────────────


def run(ticker: str, dry_run: bool = False, file_path: str = None, model: str = None):
    """Main entry point."""
    ticker = ticker.upper()
    print(f"\n{'=' * 60}")
    print(f"Research Questions Router — {ticker}")
    print(f"{'=' * 60}\n")

    # 1. Find analysis file
    analysis_path = find_latest_analysis(ticker, file_path)
    if not analysis_path:
        return
    print(f"Analysis: {analysis_path.name}")

    # 2. Parse questions
    questions = parse_research_questions(analysis_path)
    if not questions:
        print("\n✓ 无待研究问题（所有问题已标记 [x] 或未添加 [?] 问题）")
        return

    print(f"Found {len(questions)} pending question(s):\n")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q['question'][:80]}")

    # 3. Assemble context
    print(f"\nAssembling context...")
    context = assemble_context(ticker, analysis_path)
    context["ticker"] = ticker
    print(f"  Company: {context['company']}")
    print(f"  Quarters: {context['quarters']}")
    print(f"  Analysis context: {len(context['analysis_summary'])} chars")
    print(f"  Performance data: {len(context['performance_snapshot'])} chars")
    print(f"  Thesis: {'loaded' if 'thesis' not in context['thesis_summary'] else 'none'}")

    # 4. Dry run: show prompts and exit
    if dry_run:
        print(f"\n{'─' * 40}")
        print("DRY RUN — Prompts preview:\n")
        for i, q in enumerate(questions, 1):
            prompt = build_prompt(q["question"], context)
            print(f"── Question {i}/{len(questions)} ──")
            print(f"Q: {q['question']}")
            print(f"\nPrompt ({len(prompt)} chars):")
            print(prompt[:2000])
            if len(prompt) > 2000:
                print(f"  ... ({len(prompt) - 2000} more chars)")
            print()
        return

    # 5. Send each question to ChatGPT
    qa_pairs = []
    model_name = model or "gpt-5.2-chat-latest"
    model_display = model or "GPT-5.2"

    for i, q in enumerate(questions, 1):
        print(f"\n── Sending question {i}/{len(questions)} to {model_display} ──")
        print(f"  Q: {q['question'][:80]}")

        try:
            answer = send_to_chatgpt(q["question"], context, model=model)
            qa_pairs.append(
                {
                    "question": q["question"],
                    "answer": answer,
                    "model": model_display,
                }
            )
            print(f"  ✓ Got answer ({len(answer)} chars)")
        except Exception as e:
            # Retry once
            print(f"  ⚠ Error: {e}. Retrying...")
            try:
                answer = send_to_chatgpt(q["question"], context, model=model)
                qa_pairs.append(
                    {
                        "question": q["question"],
                        "answer": answer,
                        "model": model_display,
                    }
                )
                print(f"  ✓ Got answer on retry ({len(answer)} chars)")
            except Exception as e2:
                print(f"  ✗ Failed after retry: {e2}")
                continue

    if not qa_pairs:
        print("\n✗ No answers received. All questions remain [?].")
        return

    # 6. Write answers back to file
    print(f"\nWriting {len(qa_pairs)} answer(s) to {analysis_path.name}...")
    write_answers_to_file(analysis_path, qa_pairs)

    answered = len(qa_pairs)
    remaining = len(questions) - answered
    print(f"\n{'=' * 60}")
    print(f"Done! {answered} answered, {remaining} remaining.")
    if remaining > 0:
        print(f"Run again to retry failed questions.")
    print(f"{'=' * 60}\n")


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Research Questions Router — Send [?] questions to ChatGPT"
    )
    parser.add_argument("ticker", help="Ticker symbol (e.g., SHOP-CA)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview prompts without sending to ChatGPT",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Specific analysis file path (default: latest)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="ChatGPT model (default: gpt-5.2-chat-latest). Options: o3, o4-mini, gpt-4o",
    )
    args = parser.parse_args()
    run(args.ticker, dry_run=args.dry_run, file_path=args.file, model=args.model)
