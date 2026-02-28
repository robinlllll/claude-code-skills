#!/usr/bin/env python3
"""
Research Questions Router — Parse [?] questions from earnings analysis,
assemble context (global + per-question local), send to GPT + Grok in parallel,
write dual-AI answers at top of file.

Usage:
    python research_questions.py TICKER [--dry-run] [--file PATH] [--model MODEL] [--gpt-only]
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ────────────────────────────────────────────────────

OBSIDIAN_VAULT = Path.home() / "Documents" / "Obsidian Vault"
EARNINGS_FOLDER = OBSIDIAN_VAULT / "研究" / "财报分析"
PORTFOLIO_DIR = Path.home() / "PORTFOLIO" / "research" / "companies"

CHATGPT_CONFIG = Path.home() / ".claude" / "skills" / "chatgpt" / "data" / "config.json"
GROK_CONFIG = Path.home() / ".claude" / "skills" / "socratic-writer" / "data" / "config.json"

# ── Constants ────────────────────────────────────────────────

MAX_CONTEXT_CHARS = 6000
MAX_THESIS_CHARS = 2000
FALLBACK_CHARS = 8000
LOCAL_CONTEXT_WINDOW = 20  # lines above/below each question
MAX_PRIOR_ANSWERS_CHARS = 6000  # cap prior answers in followup context


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
        # Try with common suffixes: FND -> FND-US, BABA -> BABA-HK, etc.
        for suffix in ("-US", "-CA", "-HK", "-UK", "-EU"):
            candidate = EARNINGS_FOLDER / f"{ticker.upper()}{suffix}"
            if candidate.exists():
                folder = candidate
                break
        else:
            print(f"Error: No analysis folder for {ticker}: {folder}", file=sys.stderr)
            return None

    # Find analysis files (skip _ prefixed notes files)
    analyses = sorted(
        [f for f in folder.glob("*.md") if not f.name.startswith("_")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not analyses:
        print(f"Error: No analysis files found in {folder}", file=sys.stderr)
        return None

    return analyses[0]


def _normalize_question_markers(filepath: Path) -> int:
    """
    Auto-convert informal question markers to standard `- [?]` format.
    Supports: `- ?`, `- ？`, `- [ ] ？`, `* ？`, `？` at line start, numbered `N. ？`.
    Returns count of lines converted.
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    converted = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip hint line, answered questions, and frontmatter
        if "提问语法" in stripped or stripped.startswith("- [x]"):
            continue

        new_line = None

        # Pattern: `- ?question` or `- ？question`
        m = re.match(r"^- [?？]\s*(.+)$", stripped)
        if m:
            new_line = f"- [?] {m.group(1).strip()}"

        # Pattern: `- [ ] ？question` or `- [ ] ?question` (checkbox)
        if not new_line:
            m = re.match(r"^- \[ \]\s*[?？]\s*(.+)$", stripped)
            if m:
                new_line = f"- [?] {m.group(1).strip()}"

        # Pattern: `* ？question` or `* ?question` (asterisk bullet)
        if not new_line:
            m = re.match(r"^\*\s+[?？]\s*(.+)$", stripped)
            if m:
                new_line = f"- [?] {m.group(1).strip()}"

        # Pattern: `？question` at line start (no bullet)
        if not new_line:
            m = re.match(r"^[?？]\s*(.+)$", stripped)
            if m:
                new_line = f"- [?] {m.group(1).strip()}"

        # Pattern: `N. ？question` or `N. ?question` (numbered)
        if not new_line:
            m = re.match(r"^\d+[.)]\s*[?？]\s*(.+)$", stripped)
            if m:
                new_line = f"- [?] {m.group(1).strip()}"

        if new_line:
            # Preserve leading whitespace
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = indent + new_line
            converted += 1

    if converted > 0:
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return converted


def _extract_local_context(lines: list[str], question_line: int, window: int = LOCAL_CONTEXT_WINDOW) -> str:
    """Extract surrounding context (paragraph above the question)."""
    start = max(0, question_line - window)
    end = question_line
    context_lines = []
    for line in lines[start:end]:
        stripped = line.strip()
        # Skip other [?] questions, hint lines, empty lines at start
        if stripped.startswith("- [?]") or "提问语法" in stripped:
            continue
        context_lines.append(line)
    return "\n".join(context_lines).strip()


def parse_research_questions(filepath: Path) -> list[dict]:
    """
    Parse [?] research questions from a file.
    First normalizes informal markers (？, ?, numbered) to `- [?]` format.
    Scans the ENTIRE file for inline `- [?]` markers.
    Returns list of {question, line_number, raw_line, local_context}. Skips [x] lines.
    """
    # Auto-convert informal markers first
    converted = _normalize_question_markers(filepath)
    if converted > 0:
        print(f"  Auto-converted {converted} informal question(s) to [?] format")

    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    questions = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip hint line (提问语法)
        if "提问语法" in stripped:
            continue

        # Match - [?] question pattern anywhere in the file
        m = re.match(r"^- \[\?\]\s+(.+)$", stripped)
        if m:
            local_ctx = _extract_local_context(lines, i)
            questions.append(
                {
                    "question": m.group(1).strip(),
                    "line_number": i,  # 0-indexed
                    "raw_line": line,
                    "local_context": local_ctx,
                }
            )

    return questions


# ── Context Assembly ─────────────────────────────────────────


def _extract_section(text: str, header_pattern: str, max_chars: int) -> str:
    """Extract content under a markdown header matching the pattern.
    Stops at next heading of equal or higher level (fewer or equal #'s)."""
    lines = text.split("\n")
    collecting = False
    collected = []
    chars = 0
    section_level = 0  # track heading level of matched section

    for line in lines:
        stripped = line.strip()
        if not collecting and re.match(header_pattern, stripped):
            # Determine heading level (count leading #'s)
            section_level = len(stripped) - len(stripped.lstrip("#"))
            collecting = True
            continue
        if collecting:
            # Stop at same-level or higher heading (not sub-headings)
            heading_match = re.match(r"^(#{1,6})\s", stripped)
            if heading_match and collected:
                this_level = len(heading_match.group(1))
                if this_level <= section_level:
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

    # Section 1: 综合评估 (~6k chars)
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


def _extract_answer_section(filepath: Path) -> str:
    """Extract existing 'Research Questions — AI Answers' section content (between header and ---)."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    collecting = False
    collected = []
    for line in lines:
        if line.strip().startswith("## Research Questions — AI Answers"):
            collecting = True
            continue
        if collecting:
            if line.strip() == "---":
                break
            collected.append(line)

    return "\n".join(collected).strip()


# ── Prompt ───────────────────────────────────────────────────

BATCH_PROMPT_TEMPLATE = """## 背景
{company} ({ticker}) {quarters} 财报分析。以下是分析的核心发现和业绩数据摘要。

## 分析核心发现
{analysis_summary}

## 业绩数据
{performance_snapshot}

## 投资论点
{thesis_summary}

---

## 研究问题（共{n}题）

{questions_block}

## 回答要求
1. 编号对应每题，先复述原题再回答
2. **增量价值优先**——上下文摘录仅供理解问题背景，不要复述分析文件中已有的结论或数据。重点提供：
   - 行业横向对比（竞争对手同期表现）
   - 历史纵向趋势（该公司或行业过去几年的模式）
   - 外部数据验证（第三方来源、行业报告、公开财务数据）
   - 独立判断和推理（基于你的知识得出新结论）
3. 每题回答应完整详尽，不设字数上限
4. 结构：**一句话结论**（含多头/空头信号）→ **关键论据**（区分"transcript证据 (p.XX)"和"外部知识/推理"）→ 不确定处标注「需额外数据」
5. 如果问题要求解释概念或竞争对手分析，请提供清晰完整的解释，不受字数限制
6. 中文，不用emoji，不用分隔线

## 数据诚信要求（极其重要）
- **禁止编造外部数据。** 不得虚构任何第三方数据源的具体数据点。
- **禁止编造不存在的公司、产品或事件。** 如果你不确定某公司/产品是否存在，不要提及。
- 每条"外部数据"必须标注来源类别：
  - 「SEC/IR」— 来自 SEC 文件或 IR 材料，注明文件类型（10-K/10-Q/earnings call）
  - 「新闻/行业报告」— 来自新闻、行业研究、分析师文章等，必须注明出处名称和大致时间，知道 URL 则附链接
  - 「个人估算」— 基于公开数据推算，必须写明假设条件和计算步骤
  - 「无可靠数据」— 没有可靠来源时直接说明，不要用真实公司名包装虚构数字
- 可以引用新闻、博客、行业报告，但必须是你确信真实存在的来源
- 如果某题你缺乏外部数据来回答，请聚焦于逻辑推理和 transcript 分析，不要用虚构数据填充。承认信息局限比编造权威数据有价值得多。"""

SYSTEM_PROMPT = (
    "你是资深买方股票分析师，擅长跨公司横向对比和行业趋势分析。"
    "用户已经有了详细的财报分析，现在需要你提供增量洞察——"
    "不要复述分析中已有的内容，而是补充行业背景、竞品对比、历史趋势、外部数据验证。"
    "回答要有独立判断，不只是引用transcript。中文回答。\n\n"
    "【严格禁止编造外部数据】\n"
    "- 禁止虚构任何第三方数据源的具体数据点\n"
    "- 禁止编造不存在的公司、产品、融资事件或行业报告\n"
    "- 禁止伪造精确数字（如份额百分比、CPM 变化、bid volume）来增强论点可信度\n"
    "- 引用外部数据时，必须区分以下类别并明确标注：\n"
    "  (a)「SEC/IR」— 来自 SEC 文件、公司 IR、公开财报，注明文件类型\n"
    "  (b)「新闻/行业报告」— 来自新闻报道、行业研究报告、分析师文章等，必须注明出处名称（如 Bloomberg、Reuters、AdExchanger）。如果你确切知道 URL，附上链接；如果不确定 URL，只写出处名称和大致时间\n"
    "  (c)「个人估算」— 基于公开数据的推算，必须写明假设和计算过程\n"
    "  (d)「不确定/无数据」— 如果你不确定某个数据点，直接说「我没有这个数据」\n"
    "- 可以引用新闻、博客、行业报告等外部来源，但必须是你确信真实存在的，并注明出处\n"
    "- 如果你不知道答案，说「我不知道」比编造一个看似权威的假数据要好 100 倍\n"
    "- 绝不允许用真实公司名包装虚构数据——这比不回答更有害"
)


def _build_questions_block(questions: list[dict]) -> str:
    """Build the numbered questions block with local context for each."""
    parts = []
    for i, q in enumerate(questions, 1):
        ctx_snippet = q.get("local_context", "")
        if ctx_snippet:
            # Truncate very long contexts
            if len(ctx_snippet) > 800:
                ctx_snippet = ctx_snippet[:800] + "..."
            parts.append(
                f"### Q{i}. {q['question']}\n"
                f"> 上下文摘录：\n> {ctx_snippet[:500].replace(chr(10), chr(10) + '> ')}\n"
            )
        else:
            parts.append(f"### Q{i}. {q['question']}\n")
    return "\n".join(parts)


def build_batch_prompt(questions: list[dict], context: dict) -> str:
    """Build the full batch prompt for all questions."""
    questions_block = _build_questions_block(questions)
    return BATCH_PROMPT_TEMPLATE.format(
        company=context["company"],
        ticker=context.get("ticker", ""),
        quarters=context["quarters"],
        analysis_summary=context["analysis_summary"] or "（无）",
        performance_snapshot=context["performance_snapshot"] or "（无）",
        thesis_summary=context["thesis_summary"],
        n=len(questions),
        questions_block=questions_block,
    )


FOLLOWUP_PROMPT_TEMPLATE = """## 背景
{company} ({ticker}) {quarters} 财报分析——追问轮次。

## 分析核心发现
{analysis_summary}

## 业绩数据
{performance_snapshot}

## 投资论点
{thesis_summary}

## 上一轮研究问答
以下是上一轮 /rq 的问答记录。追问基于此展开，请勿重复已答内容。

{prior_answers}

---

## 追问（共{n}题）

{questions_block}

## 回答要求
1. 编号对应每题，先复述原题再回答
2. **这是追问轮次**——你已有上一轮的完整问答记录。请：
   - 在上一轮回答的基础上深入，不要重复已有内容
   - 如果追问质疑了上一轮的某个结论，重新审视并给出修正后的判断
   - 如果追问要求补充细节，聚焦在增量信息上
3. 每题回答应完整详尽，不设字数上限
4. 结构：**一句话结论**（含多头/空头信号）→ **关键论据**（区分"transcript证据 (p.XX)"和"外部知识/推理"）→ 不确定处标注「需额外数据」
5. 如果问题要求解释概念或竞争对手分析，请提供清晰完整的解释，不受字数限制
6. 中文，不用emoji，不用分隔线

## 数据诚信要求（极其重要）
- **禁止编造外部数据。** 不得虚构任何第三方数据源的具体数据点。
- **禁止编造不存在的公司、产品或事件。** 如果你不确定某公司/产品是否存在，不要提及。
- 每条"外部数据"必须标注来源类别：
  - 「SEC/IR」— 来自 SEC 文件或 IR 材料，注明文件类型（10-K/10-Q/earnings call）
  - 「新闻/行业报告」— 来自新闻、行业研究、分析师文章等，必须注明出处名称和大致时间，知道 URL 则附链接
  - 「个人估算」— 基于公开数据推算，必须写明假设条件和计算步骤
  - 「无可靠数据」— 没有可靠来源时直接说明，不要用真实公司名包装虚构数字
- 可以引用新闻、博客、行业报告，但必须是你确信真实存在的来源
- 如果某题你缺乏外部数据来回答，请聚焦于逻辑推理和 transcript 分析，不要用虚构数据填充。承认信息局限比编造权威数据有价值得多。"""


def build_followup_prompt(questions: list[dict], context: dict, prior_answers: str) -> str:
    """Build the followup prompt including prior Q&A as context."""
    questions_block = _build_questions_block(questions)
    # Truncate prior answers if too long
    if len(prior_answers) > MAX_PRIOR_ANSWERS_CHARS:
        prior_answers = prior_answers[:MAX_PRIOR_ANSWERS_CHARS] + "\n\n... (prior answers truncated)"
    return FOLLOWUP_PROMPT_TEMPLATE.format(
        company=context["company"],
        ticker=context.get("ticker", ""),
        quarters=context["quarters"],
        analysis_summary=context["analysis_summary"] or "（无）",
        performance_snapshot=context["performance_snapshot"] or "（无）",
        thesis_summary=context["thesis_summary"],
        prior_answers=prior_answers,
        n=len(questions),
        questions_block=questions_block,
    )


# ── Legacy single-question prompt (kept for --inline mode) ───

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
- 中文，回答应完整详尽，不用emoji，不用分隔线
- 禁止编造外部数据源。可以引用新闻/行业报告但必须注明出处。引用外部数据必须标注「SEC/IR」「新闻/行业报告」「个人估算」或「无可靠数据」。不知道就说不知道。"""


def build_prompt(question: str, context: dict) -> str:
    """Build the full prompt for a single question (legacy inline mode)."""
    return PROMPT_TEMPLATE.format(
        company=context["company"],
        ticker=context.get("ticker", ""),
        quarters=context["quarters"],
        analysis_summary=context["analysis_summary"] or "（无）",
        performance_snapshot=context["performance_snapshot"] or "（无）",
        thesis_summary=context["thesis_summary"],
        question=question,
    )


# ── API Calls ────────────────────────────────────────────────


def _load_api_keys() -> tuple[str, str]:
    """Load OpenAI and Grok API keys from config files."""
    openai_key = ""
    grok_key = ""

    if CHATGPT_CONFIG.exists():
        with open(CHATGPT_CONFIG, "r", encoding="utf-8") as f:
            openai_key = json.load(f).get("openai_api_key", "")

    if GROK_CONFIG.exists():
        with open(GROK_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            grok_key = cfg.get("grok_api_key", "")

    return openai_key, grok_key


def send_batch_gpt(prompt: str, openai_key: str, model: str = None) -> str:
    """Send batch prompt to GPT. Returns answer text."""
    from openai import OpenAI

    client = OpenAI(api_key=openai_key)
    model_name = model or "o3"

    print(f"  Sending to {model_name}...")
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=8000,
    )
    answer = resp.choices[0].message.content
    print(f"  GPT done ({len(answer)} chars)")
    return answer


def send_batch_grok(prompt: str, grok_key: str) -> str | None:
    """Send batch prompt to Grok. Returns answer text or None."""
    if not grok_key:
        print("  No Grok API key, skipping Grok")
        return None

    from openai import OpenAI

    print("  Sending to Grok...")
    client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
    resp = client.chat.completions.create(
        model="grok-4-1-fast-reasoning",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    answer = resp.choices[0].message.content
    print(f"  Grok done ({len(answer)} chars)")
    return answer


def send_to_chatgpt(question: str, context: dict, model: str = None) -> str:
    """Send a single question to ChatGPT (legacy inline mode)."""
    openai_key, _ = _load_api_keys()
    from openai import OpenAI

    client = OpenAI(api_key=openai_key)
    prompt = build_prompt(question, context)
    model_name = model or "gpt-5.2-chat-latest"

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=3000,
    )
    return resp.choices[0].message.content


# ── Write Back ───────────────────────────────────────────────


def write_answers_to_top(filepath: Path, questions: list[dict],
                         gpt_answer: str, grok_answer: str | None,
                         ticker: str, model: str = None) -> None:
    """
    Write dual-AI answers as a section at the top of the file (after frontmatter).
    Each answer includes the original question text.
    Also marks inline [?] questions as [x].
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build answer section
    section_parts = []
    section_parts.append(f"## Research Questions — AI Answers\n")
    section_parts.append(f"> {len(questions)} questions | {now_str}\n")

    if gpt_answer:
        gpt_label = model or "o3"  # matches default in send_batch_gpt
        section_parts.append(f"### {gpt_label}\n")
        section_parts.append(gpt_answer)
        section_parts.append("")

    if grok_answer:
        section_parts.append("### Grok\n")
        section_parts.append(grok_answer)
        section_parts.append("")

    section_parts.append("---\n")
    answer_block = "\n".join(section_parts)

    # Re-read file
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Remove existing answer section if present (for re-runs)
    new_lines = []
    skip = False
    for line in lines:
        if line.strip().startswith("## Research Questions — AI Answers"):
            skip = True
            continue
        if skip:
            if line.strip() == "---":
                skip = False
                continue  # skip the --- separator itself
            continue  # skip all content inside the answer section
        new_lines.append(line)
    lines = new_lines

    # Find insertion point: after frontmatter + hint line, before first # heading
    insert_idx = 0
    in_frontmatter = False
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == "---":
            in_frontmatter = False
            insert_idx = i + 1
            continue
        if not in_frontmatter and insert_idx > 0:
            # Skip hint line and blank lines after frontmatter
            if line.strip().startswith("> [?] 提问语法") or line.strip() == "":
                insert_idx = i + 1
                continue
            break

    # If no frontmatter, insert before first heading
    if insert_idx == 0:
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_idx = i
                break

    # Insert answer block
    answer_lines = answer_block.split("\n")
    final_lines = lines[:insert_idx] + answer_lines + lines[insert_idx:]

    # Mark all [?] questions as [x]
    for i, line in enumerate(final_lines):
        stripped = line.strip()
        if "提问语法" in stripped:
            continue
        if re.match(r"^- \[\?\]\s+", stripped):
            for q in questions:
                if q["question"] in line:
                    final_lines[i] = line.replace("- [?]", "- [x]", 1)
                    break

    filepath.write_text("\n".join(final_lines), encoding="utf-8")
    print(f"  ✓ Answers written to top of {filepath.name}")
    print(f"  ✓ Marked {len(questions)} question(s) as [x]")


def write_answers_to_file(filepath: Path, qa_pairs: list[dict]) -> None:
    """
    Write answers back inline (legacy mode).
    For each pair: [?] → [x], insert blockquote answer below.
    """
    for pair in qa_pairs:
        text = filepath.read_text(encoding="utf-8")
        lines = text.split("\n")

        question_text = pair["question"]
        answer = pair["answer"]
        model = pair.get("model", "GPT-5.2")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^- \[\?\]\s+", line.strip()) and question_text in line:
                target_idx = i
                break

        if target_idx is None:
            print(f"  Warning: Could not find [?] line for: {question_text[:50]}...")
            continue

        lines[target_idx] = lines[target_idx].replace("- [?]", "- [x]", 1)

        answer_lines = answer.strip().split("\n")
        formatted = [f"  > **{model} | {now_str}**", "  >"]
        for aline in answer_lines:
            formatted.append(f"  > {aline}")
        formatted.append("")

        insert_pos = target_idx + 1
        while insert_pos < len(lines) and lines[insert_pos].strip().startswith(">"):
            insert_pos += 1

        for j, fline in enumerate(formatted):
            lines.insert(insert_pos + j, fline)

        filepath.write_text("\n".join(lines), encoding="utf-8")
        print(f"  ✓ Wrote answer for: {question_text[:60]}...")


def write_followup_answers(filepath: Path, questions: list[dict],
                           gpt_answer: str, grok_answer: str | None,
                           model: str = None) -> None:
    """Append follow-up answers to existing answer section."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build followup block
    parts = []
    parts.append(f"\n── Follow-up | {len(questions)} questions | {now_str} ──\n")

    if gpt_answer:
        gpt_label = model or "o3"
        parts.append(f"### {gpt_label}\n")
        parts.append(gpt_answer)
        parts.append("")

    if grok_answer:
        parts.append("### Grok\n")
        parts.append(grok_answer)
        parts.append("")

    followup_block = "\n".join(parts)

    # Read file and find the --- terminator of the answer section
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    in_section = False
    terminator_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## Research Questions — AI Answers"):
            in_section = True
            continue
        if in_section and line.strip() == "---":
            terminator_idx = i
            break

    if terminator_idx is None:
        # No existing answer section — write fresh instead
        print("  ⚠ No existing answer section found, writing as fresh round")
        write_answers_to_top(filepath, questions, gpt_answer, grok_answer, "TICKER", model)
        return

    # Insert followup block before the --- terminator
    followup_lines = followup_block.split("\n")
    final_lines = lines[:terminator_idx] + followup_lines + lines[terminator_idx:]

    # Mark new [?] questions as [x]
    for i, line in enumerate(final_lines):
        stripped = line.strip()
        if "提问语法" in stripped:
            continue
        if re.match(r"^- \[\?\]\s+", stripped):
            for q in questions:
                if q["question"] in line:
                    final_lines[i] = line.replace("- [?]", "- [x]", 1)
                    break

    filepath.write_text("\n".join(final_lines), encoding="utf-8")
    print(f"  ✓ Follow-up answers appended to {filepath.name}")
    print(f"  ✓ Marked {len(questions)} question(s) as [x]")


# ── Insight Extraction ────────────────────────────────────────


INSIGHT_EXTRACTION_PROMPT = """你是投资分析助手。从以下研究问答中提取 2-5 条可在下一季度财报中验证的假设。

每条假设必须：
- 有明确的验证标准（下季度能在 transcript 中找到证据）
- 与投资决策相关
- 不是简单的事实复述

返回 JSON array:
[{{"title": "简短标题", "hypothesis": "假设内容", "criteria": "验证标准：下季度如果看到 X 则验证"}}]

仅返回 JSON，不要其他内容。

---

研究问答内容：
{answers}"""


def _extract_and_save_insights(
    ticker: str, company: str, quarter: str,
    gpt_answer: str, questions: list[dict],
    openai_key: str,
) -> int:
    """
    Extract verifiable hypotheses from /rq answers via o4-mini,
    save to Insight Ledger. Returns count saved.
    """
    from openai import OpenAI

    # Lazy import insight_ledger — lives in transcript-analyzer
    ledger_dir = Path.home() / ".claude" / "skills" / "transcript-analyzer" / "browser"
    sys.path.insert(0, str(ledger_dir))
    import insight_ledger  # noqa: E402

    # Build concise input: questions + GPT answers
    q_text = "\n".join(f"Q{i+1}. {q['question']}" for i, q in enumerate(questions))
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        answers=f"## 问题\n{q_text}\n\n## GPT 回答\n{gpt_answer[:6000]}"
    )

    client = OpenAI(api_key=openai_key)
    resp = client.chat.completions.create(
        model="o4-mini",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=2000,
    )
    raw = resp.choices[0].message.content.strip()

    # Parse JSON — strip markdown fences and find JSON array
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # Reasoning models may add text around the JSON — extract the array
    json_match = re.search(r'\[[\s\S]*\]', raw)
    if not json_match:
        print(f"  ⚠ No JSON array found in insight extraction response")
        return 0
    raw = json_match.group(0)

    items = json.loads(raw)
    if not isinstance(items, list):
        return 0

    # Read current next_id from ledger frontmatter
    ledger_path = insight_ledger.get_ledger_path(ticker)
    next_num = 1
    if ledger_path.exists():
        text = ledger_path.read_text(encoding="utf-8")
        m = re.search(r"^next_id:\s*(\d+)", text, re.MULTILINE)
        if m:
            next_num = int(m.group(1))

    today = datetime.now().strftime("%Y-%m-%d")
    saved = 0

    for item in items[:5]:  # cap at 5
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        hypothesis = str(item.get("hypothesis", "")).strip()
        criteria = str(item.get("criteria", "")).strip()
        if not hypothesis or not criteria:
            continue

        ins = insight_ledger.Insight(
            id=f"INS-{next_num:03d}",
            title=title or hypothesis[:30],
            date=today,
            source_quarter=quarter,
            type="/rq 研究问题",
            hypothesis=hypothesis,
            criteria=criteria,
            status="⏳ 待验证",
        )
        insight_ledger.save_insight(ticker, company, ins)
        next_num += 1
        saved += 1

    return saved


# ── Main ─────────────────────────────────────────────────────


def run(ticker: str, dry_run: bool = False, file_path: str = None,
        model: str = None, gpt_only: bool = False, inline: bool = False,
        followup: bool = False):
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
        ctx_len = len(q.get("local_context", ""))
        print(f"  {i}. {q['question'][:80]} (context: {ctx_len} chars)")

    # 3. Assemble context
    print(f"\nAssembling context...")
    context = assemble_context(ticker, analysis_path)
    context["ticker"] = ticker
    print(f"  Company: {context['company']}")
    print(f"  Quarters: {context['quarters']}")
    print(f"  Analysis context: {len(context['analysis_summary'])} chars")
    print(f"  Performance data: {len(context['performance_snapshot'])} chars")
    print(f"  Thesis: {'loaded' if 'thesis' not in context['thesis_summary'] else 'none'}")

    # 4. Build batch prompt
    if followup:
        prior_answers = _extract_answer_section(analysis_path)
        if not prior_answers:
            print("  ⚠ No previous answers found — running in normal mode instead")
            followup = False
            batch_prompt = build_batch_prompt(questions, context)
        else:
            print(f"  Prior answers: {len(prior_answers)} chars (follow-up context)")
            batch_prompt = build_followup_prompt(questions, context, prior_answers)
    else:
        batch_prompt = build_batch_prompt(questions, context)
    print(f"  Batch prompt: {len(batch_prompt)} chars")

    # 5. Dry run
    if dry_run:
        print(f"\n{'─' * 40}")
        print("DRY RUN — Batch prompt preview:\n")
        print(batch_prompt[:4000])
        if len(batch_prompt) > 4000:
            print(f"\n  ... ({len(batch_prompt) - 4000} more chars)")
        return

    # 6. Legacy inline mode
    if inline:
        _run_inline(ticker, questions, context, analysis_path, model)
        return

    # 7. Load API keys
    openai_key, grok_key = _load_api_keys()
    if not openai_key:
        print("Error: No OpenAI API key configured", file=sys.stderr)
        return

    # 8. Send to GPT + Grok in parallel
    print(f"\n── Sending to AI models ──")
    gpt_answer = None
    grok_answer = None

    if gpt_only or not grok_key:
        # Sequential GPT only
        try:
            gpt_answer = send_batch_gpt(batch_prompt, openai_key, model)
        except Exception as e:
            print(f"  ⚠ GPT error: {e}. Retrying...")
            try:
                gpt_answer = send_batch_gpt(batch_prompt, openai_key, model)
            except Exception as e2:
                print(f"  ✗ GPT failed: {e2}")
    else:
        # Parallel GPT + Grok
        with ThreadPoolExecutor(max_workers=2) as ex:
            gpt_future = ex.submit(send_batch_gpt, batch_prompt, openai_key, model)
            grok_future = ex.submit(send_batch_grok, batch_prompt, grok_key)

            try:
                gpt_answer = gpt_future.result()
            except Exception as e:
                print(f"  ⚠ GPT error: {e}")

            try:
                grok_answer = grok_future.result()
            except Exception as e:
                print(f"  ⚠ Grok error: {e}")

    if not gpt_answer and not grok_answer:
        print("\n✗ No answers received from any model.")
        return

    # 9. Write answers to file
    print(f"\nWriting answers to {analysis_path.name}...")
    if followup:
        write_followup_answers(analysis_path, questions, gpt_answer, grok_answer, model=model)
    else:
        write_answers_to_top(analysis_path, questions, gpt_answer, grok_answer, ticker, model=model)

    # 10. Extract insights for next quarter (non-blocking)
    if gpt_answer:
        try:
            n = _extract_and_save_insights(
                ticker, context["company"], context.get("quarters", ""),
                gpt_answer, questions, openai_key,
            )
            if n > 0:
                print(f"  ✓ Extracted {n} insight(s) for next quarter tracking")
        except Exception as e:
            import traceback
            print(f"  ⚠ Insight extraction skipped: {type(e).__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Done! {len(questions)} question(s) answered.")
    if gpt_answer:
        print(f"  GPT: {len(gpt_answer)} chars")
    if grok_answer:
        print(f"  Grok: {len(grok_answer)} chars")
    print(f"{'=' * 60}\n")


def _run_inline(ticker, questions, context, analysis_path, model):
    """Legacy inline mode: send each question individually, write answer below."""
    openai_key, _ = _load_api_keys()
    model_display = model or "GPT-5.2"

    qa_pairs = []
    for i, q in enumerate(questions, 1):
        print(f"\n── Sending question {i}/{len(questions)} to {model_display} ──")
        print(f"  Q: {q['question'][:80]}")

        try:
            answer = send_to_chatgpt(q["question"], context, model=model)
            qa_pairs.append(
                {"question": q["question"], "answer": answer, "model": model_display}
            )
            print(f"  ✓ Got answer ({len(answer)} chars)")
        except Exception as e:
            print(f"  ⚠ Error: {e}. Retrying...")
            try:
                answer = send_to_chatgpt(q["question"], context, model=model)
                qa_pairs.append(
                    {"question": q["question"], "answer": answer, "model": model_display}
                )
                print(f"  ✓ Got answer on retry ({len(answer)} chars)")
            except Exception as e2:
                print(f"  ✗ Failed after retry: {e2}")
                continue

    if not qa_pairs:
        print("\n✗ No answers received.")
        return

    print(f"\nWriting {len(qa_pairs)} answer(s) to {analysis_path.name}...")
    write_answers_to_file(analysis_path, qa_pairs)

    answered = len(qa_pairs)
    remaining = len(questions) - answered
    print(f"\n{'=' * 60}")
    print(f"Done! {answered} answered, {remaining} remaining.")
    print(f"{'=' * 60}\n")


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Research Questions Router — Send [?] questions to GPT + Grok"
    )
    parser.add_argument("ticker", help="Ticker symbol (e.g., SHOP-CA)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview prompts without sending",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Specific analysis file path (default: latest)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="GPT model (default: gpt-5.2-chat-latest). Options: o3, o4-mini, gpt-4o",
    )
    parser.add_argument(
        "--gpt-only",
        action="store_true",
        help="Send to GPT only, skip Grok",
    )
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Legacy mode: write answers inline below each question",
    )
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Follow-up mode: include prior answers as context, append new answers",
    )
    args = parser.parse_args()
    run(
        args.ticker,
        dry_run=args.dry_run,
        file_path=args.file,
        model=args.model,
        gpt_only=args.gpt_only,
        inline=args.inline,
        followup=args.followup,
    )
