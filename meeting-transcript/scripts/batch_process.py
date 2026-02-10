#!/usr/bin/env python3
"""
Batch process meeting transcripts through Gemini.

Stage 1 (default): ASR cleaning — chunks + corrects raw transcripts
Stage 2 (--briefing): Analytical briefing — per-company investment summaries

Usage:
    # Stage 1: Clean raw transcripts
    python batch_process.py

    # Stage 2: Generate briefings from cleaned transcripts
    python batch_process.py --briefing

    # Both stages, single file
    python batch_process.py --start 46 --end 47
    python batch_process.py --briefing --start 46 --end 47

    # Stage 2 with specific model
    python batch_process.py --briefing --briefing-model gemini-3-pro-preview
"""

import argparse
import os
import sys
import re
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Skill directory (relative to this script)
SKILL_DIR = Path(__file__).resolve().parent.parent

# Shared modules for ticker detection
sys.path.insert(0, str(Path.home() / ".claude" / "skills"))
try:
    from shared.ticker_detector import detect_tickers
    HAS_TICKER_DETECTOR = True
except ImportError:
    HAS_TICKER_DETECTOR = False

try:
    from shared.framework_tagger import tag_content
    HAS_FRAMEWORK_TAGGER = True
except ImportError:
    HAS_FRAMEWORK_TAGGER = False

# Load API key
load_dotenv(Path.home() / "13F-CLAUDE" / ".env")
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not found in ~/13F-CLAUDE/.env")
    sys.exit(1)

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

# Chunk size: ~15K chars per chunk to stay well within output limits
CHUNK_SIZE = 15000
# Minimum file size to consider "already processed" (bytes)
SKIP_THRESHOLD = 10000


def parse_args():
    parser = argparse.ArgumentParser(description="Batch clean ASR meeting transcripts via Gemini")
    parser.add_argument("--source", type=str,
                        default=str(Path.home() / "Downloads" / "周会转写" / "原文转写"),
                        help="Source directory with raw transcript files")
    parser.add_argument("--output", type=str,
                        default=str(Path.home() / "Documents" / "会议实录"),
                        help="Output directory (Obsidian vault)")
    parser.add_argument("--model", type=str, default="gemini-3-pro-preview",
                        help="Gemini model to use")
    parser.add_argument("--prompt", type=str,
                        default=str(SKILL_DIR / "prompts" / "cleaning_prompt.md"),
                        help="Path to cleaning prompt file")
    parser.add_argument("--dict", type=str,
                        default=str(SKILL_DIR / "data" / "dictionary.json"),
                        help="Path to correction dictionary")
    parser.add_argument("--start", type=int, default=0,
                        help="Start index (0-based)")
    parser.add_argument("--end", type=int, default=None,
                        help="End index (exclusive)")
    parser.add_argument("--retry", action="store_true",
                        help="Retry mode: delete and reprocess files below threshold")
    parser.add_argument("--threshold", type=int, default=80,
                        help="Minimum retention %% for retry mode (default: 80)")
    parser.add_argument("--suffix", type=str, default="会议实录",
                        help="Output filename suffix (default: 会议实录)")
    # Stage 2: Briefing mode
    parser.add_argument("--briefing", action="store_true",
                        help="Stage 2: generate analytical briefings from cleaned transcripts")
    parser.add_argument("--briefing-model", type=str, default="gemini-3-pro-preview",
                        help="Model for briefing generation (default: gemini-3-pro-preview)")
    parser.add_argument("--briefing-prompt", type=str,
                        default=str(SKILL_DIR / "prompts" / "briefing_prompt.md"),
                        help="Path to briefing prompt file")
    parser.add_argument("--briefing-suffix", type=str, default="周会分析",
                        help="Output filename suffix for briefings (default: 周会分析)")
    parser.add_argument("--force", action="store_true",
                        help="Force regeneration even if output already exists")
    return parser.parse_args()


def read_file_text(filepath: Path) -> str | None:
    """Read text content from .txt, .docx, or .pdf files."""
    suffix = filepath.suffix.lower()
    try:
        if suffix == ".txt":
            return filepath.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".docx":
            import docx
            doc = docx.Document(str(filepath))
            return "\n".join(p.text for p in doc.paragraphs)
        elif suffix == ".pdf":
            import pdfplumber
            text_parts = []
            with pdfplumber.open(str(filepath)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            return "\n".join(text_parts)
        else:
            print(f"    WARN: unsupported file type {suffix}")
            return None
    except Exception as e:
        print(f"    ERROR reading {filepath.name}: {e}")
        return None


def load_dictionary(dict_path: Path):
    """Load the iterating correction dictionary."""
    if dict_path.exists():
        return json.loads(dict_path.read_text(encoding="utf-8"))
    return {"corrections": [], "notes": []}


def save_dictionary(d, dict_path: Path):
    """Save the updated dictionary."""
    dict_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text at speaker boundaries near chunk_size limits."""
    if len(text) <= chunk_size * 1.2:
        return [text]

    chunks = []
    pos = 0
    speaker_pattern = re.compile(r'\n(?=\*?\*?[\u4e00-\u9fff])')

    while pos < len(text):
        if pos + chunk_size >= len(text):
            chunks.append(text[pos:])
            break

        search_start = pos + chunk_size - 2000
        search_end = pos + chunk_size + 2000
        segment = text[search_start:min(search_end, len(text))]

        matches = list(speaker_pattern.finditer(segment))
        if matches:
            best = None
            for m in matches:
                abs_pos = search_start + m.start()
                if abs_pos > pos + 3000:
                    best = abs_pos
            if best:
                chunks.append(text[pos:best])
                pos = best
                continue

        chunks.append(text[pos:pos + chunk_size])
        pos += chunk_size

    return chunks


def detect_dialect(text: str) -> str:
    """Detect if text is Sichuan dialect or Mandarin based on markers."""
    sichuan_markers = ["啥子", "晓得", "咋个", "搞不赢", "莫得", "恼火", "巴适",
                       "遭", "嘞", "不得行", "要得", "脑壳"]
    count = sum(text.count(m) for m in sichuan_markers)
    return "sichuan" if count >= 3 else "mandarin"


def build_prompt(base_prompt: str, dialect: str, extra_dict: dict,
                 chunk_idx: int, total_chunks: int) -> str:
    """Build the processing prompt with dialect adjustment and dictionary."""
    prompt = base_prompt

    if dialect == "mandarin":
        prompt = prompt.replace(
            "同时精通**四川方言**与**中文语音转写(ASR)纠错**",
            "精通**中文语音转写(ASR)纠错**"
        )
        prompt = prompt.replace(
            "* **口音特征**：四川话，主要特点是平翘舌不分（z/c/s混淆zh/ch/sh）、n/l不分、英文单词发音不准。",
            "* **口音特征**：普通话，主要是英文术语和公司名的ASR识别错误。"
        )

    if extra_dict.get("corrections"):
        extra_section = "\n## 5. 从历史处理中积累的额外纠错（自动生成）\n"
        for c in extra_dict["corrections"][-50:]:
            extra_section += f"* **{c['from']}** -> **{c['to']}** ({c.get('reason', '')})\n"
        prompt += extra_section

    if total_chunks > 1:
        prompt += f"\n\n# 分段处理说明\n这是第 {chunk_idx+1}/{total_chunks} 段。请完整处理这一段的所有内容，不要省略。"
        if chunk_idx == 0:
            prompt += "\n请在这一段的开头插入【会议元数据】块。"
        else:
            prompt += "\n不需要再插入元数据块，直接从对话内容开始。"

    return prompt


def process_chunk(model: str, prompt: str, filename: str, chunk_text: str,
                  chunk_idx: int, total_chunks: int) -> str | None:
    """Process a single chunk through Gemini."""
    if chunk_idx == 0:
        full_prompt = f"""{prompt}

# Input File
文件名：{filename}

以下是需要清洗的原始转写文本：

{chunk_text}"""
    else:
        full_prompt = f"""{prompt}

# Input File (续)
文件名：{filename}（第 {chunk_idx+1}/{total_chunks} 段）

以下是需要清洗的原始转写文本（续）：

{chunk_text}"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=65536,
                ),
            )
            return response.text
        except Exception as e:
            print(f"    Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    return None


def extract_date(filename: str) -> str | None:
    """Extract YYYY-MM-DD from filename like 20250118194117-..."""
    m = re.match(r'^(\d{4})(\d{2})(\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def get_source_size(filepath: Path) -> int:
    """Get the text character count of a source file."""
    text = read_file_text(filepath)
    return len(text) if text else 0


def process_file(filepath: Path, base_prompt: str, dictionary: dict,
                 model: str, output_dir: Path, suffix: str) -> tuple[bool, int, int]:
    """Process a single transcript file. Returns (ok, input_chars, output_chars)."""
    filename = filepath.name
    date_str = extract_date(filename)
    if not date_str:
        print(f"  SKIP (no date in filename): {filename}")
        return False, 0, 0
    output_name = f"{date_str}-{suffix}.md"
    output_path = output_dir / output_name

    if output_path.exists() and output_path.stat().st_size > SKIP_THRESHOLD:
        print(f"  SKIP (exists): {output_name}")
        return True, 0, 0

    raw_text = read_file_text(filepath)
    if not raw_text or len(raw_text) < 100:
        print(f"  SKIP (empty or unreadable): {filepath.name}")
        return False, 0, 0
    dialect = detect_dialect(raw_text)
    input_chars = len(raw_text)

    print(f"  Size: {input_chars:,} chars | Dialect: {dialect}")

    chunks = split_into_chunks(raw_text)
    print(f"  Chunks: {len(chunks)}")

    results = []
    for i, chunk in enumerate(chunks):
        prompt = build_prompt(base_prompt, dialect, dictionary, i, len(chunks))
        print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)...", end=" ", flush=True)
        start = time.time()
        result = process_chunk(model, prompt, filename, chunk, i, len(chunks))
        elapsed = time.time() - start

        if result:
            print(f"OK ({len(result):,} chars, {elapsed:.0f}s)")
            results.append(result)
        else:
            print(f"FAILED after {elapsed:.0f}s")
            return False, input_chars, 0

        if i < len(chunks) - 1:
            time.sleep(3)

    full_output = "\n\n".join(results)

    # Detect tickers and prepend YAML frontmatter
    if HAS_TICKER_DETECTOR:
        try:
            ticker_results = detect_tickers(full_output)
            ticker_symbols = sorted(set(t['ticker'] for t in ticker_results if t.get('confidence', 0) >= 0.85))
        except Exception:
            ticker_symbols = []
    else:
        ticker_symbols = []

    # Detect framework sections
    framework_sections = []
    if HAS_FRAMEWORK_TAGGER:
        try:
            framework_sections = tag_content(full_output, mode="keyword")
        except Exception:
            framework_sections = []

    frontmatter_lines = [
        "---",
        f"date: {date_str}",
        "type: meeting-transcript",
        f"tickers: [{', '.join(ticker_symbols)}]",
        "tags: [周会, 会议实录]",
    ]
    if framework_sections:
        frontmatter_lines.append(f"framework_sections: [{', '.join(framework_sections)}]")
    frontmatter_lines.extend(["---", ""])
    full_output = "\n".join(frontmatter_lines) + full_output

    output_path.write_text(full_output, encoding="utf-8")

    output_chars = len(full_output)
    ratio = output_chars / input_chars * 100
    print(f"  Output: {output_chars:,} chars ({ratio:.0f}% of original)")
    print(f"  Saved: {output_name}")

    return True, input_chars, output_chars


def retry_below_threshold(source_dir: Path, output_dir: Path, suffix: str, threshold: int):
    """Find and delete output files below retention threshold for reprocessing."""
    deleted = 0
    files = list(source_dir.glob("*.txt")) + list(source_dir.glob("*.docx")) + list(source_dir.glob("*.pdf"))
    files = [f for f in files if re.match(r'^\d{8}', f.name)]

    for filepath in files:
        date_str = extract_date(filepath.name)
        if not date_str:
            continue
        output_path = output_dir / f"{date_str}-{suffix}.md"
        if not output_path.exists():
            continue

        source_text = read_file_text(filepath)
        if not source_text or len(source_text) < 100:
            continue

        output_size = output_path.stat().st_size
        source_chars = len(source_text)
        # Approximate: output file bytes ≈ chars for UTF-8 CJK (3 bytes/char)
        # But we read the actual output for accurate comparison
        output_text = output_path.read_text(encoding="utf-8", errors="ignore")
        output_chars = len(output_text)
        ratio = output_chars / source_chars * 100

        if ratio < threshold:
            print(f"  DELETE {output_path.name} ({ratio:.0f}% < {threshold}%)")
            output_path.unlink()
            deleted += 1

    print(f"\nDeleted {deleted} files below {threshold}% threshold for reprocessing.")
    return deleted


def generate_briefing(cleaned_path: Path, briefing_prompt: str, model: str,
                      output_dir: Path, briefing_suffix: str,
                      force: bool = False) -> tuple[bool, int]:
    """Stage 2: Generate analytical briefing from a cleaned transcript.

    Sends the full cleaned transcript (no chunking) with the briefing prompt.
    Returns (ok, output_chars).
    """
    date_str = cleaned_path.stem.split("-" + cleaned_path.stem.split("-", 3)[-1])[0]
    # Extract date from filename like "2026-01-23-会议实录.md"
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', cleaned_path.stem)
    if not m:
        print(f"  SKIP (no date): {cleaned_path.name}")
        return False, 0
    date_str = m.group(1)

    output_name = f"{date_str}-{briefing_suffix}.md"
    output_path = output_dir / output_name

    if output_path.exists() and not force:
        print(f"  SKIP (exists): {output_name}")
        return True, 0

    # Read cleaned transcript, strip YAML frontmatter for the prompt
    text = cleaned_path.read_text(encoding="utf-8")
    # Remove frontmatter if present
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()

    if len(text) < 200:
        print(f"  SKIP (too short): {cleaned_path.name}")
        return False, 0

    input_chars = len(text)
    print(f"  Input: {input_chars:,} chars (~{int(input_chars * 1.5):,} tokens)")

    full_prompt = f"""{briefing_prompt}

---

# 会议实录

以下是经过 ASR 纠错清洗后的会议实录全文。请基于此内容，按上述要求生成投资分析纪要。

{text}"""

    print(f"  Generating briefing with {model}...", end=" ", flush=True)
    start = time.time()

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=65536,
                ),
            )
            result = response.text
            break
        except Exception as e:
            print(f"\n    Attempt {attempt+1} failed: {e}", end=" ", flush=True)
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            result = None

    elapsed = time.time() - start

    if not result:
        print(f"FAILED after {elapsed:.0f}s")
        return False, 0

    print(f"OK ({len(result):,} chars, {elapsed:.0f}s)")

    # Detect tickers from briefing output
    if HAS_TICKER_DETECTOR:
        try:
            ticker_results = detect_tickers(result)
            ticker_symbols = sorted(set(
                t['ticker'] for t in ticker_results if t.get('confidence', 0) >= 0.85
            ))
        except Exception:
            ticker_symbols = []
    else:
        # Fallback: extract $TICKER patterns from output
        ticker_symbols = sorted(set(re.findall(r'\$([A-Z]{1,5})', result)))

    # Detect framework sections from briefing
    fw_sections = []
    if HAS_FRAMEWORK_TAGGER:
        try:
            fw_sections = tag_content(result, mode="keyword")
        except Exception:
            fw_sections = []

    fm_lines = [
        "---",
        f"date: {date_str}",
        "type: meeting-briefing",
        f"tickers: [{', '.join(ticker_symbols)}]",
        "tags: [周会, 周会分析, briefing]",
        f"source: \"[[{cleaned_path.stem}]]\"",
    ]
    if fw_sections:
        fm_lines.append(f"framework_sections: [{', '.join(fw_sections)}]")
    fm_lines.extend(["---", ""])
    frontmatter = "\n".join(fm_lines)

    output_path.write_text(frontmatter + result, encoding="utf-8")
    print(f"  Saved: {output_name}")
    return True, len(result)


def run_briefing_mode(args):
    """Run Stage 2: generate analytical briefings from cleaned transcripts."""
    output_dir = Path(args.output).expanduser()
    briefing_prompt_file = Path(args.briefing_prompt).expanduser()

    if not briefing_prompt_file.exists():
        print(f"ERROR: Briefing prompt not found: {briefing_prompt_file}")
        sys.exit(1)

    briefing_prompt = briefing_prompt_file.read_text(encoding="utf-8")

    # Find all cleaned transcripts
    cleaned_files = sorted(output_dir.glob(f"*-{args.suffix}.md"))
    if not cleaned_files:
        print(f"No cleaned transcripts found in {output_dir} with suffix '{args.suffix}'")
        print("Run Stage 1 first (without --briefing) to generate cleaned transcripts.")
        sys.exit(1)

    print("=" * 60)
    print("Meeting Transcript Briefing Generator (Stage 2)")
    print(f"Briefing model: {args.briefing_model}")
    print(f"Input: {output_dir} (*-{args.suffix}.md)")
    print(f"Output: {output_dir} (*-{args.briefing_suffix}.md)")
    print(f"Files found: {len(cleaned_files)}")
    print("=" * 60)

    start_idx = args.start
    end_idx = args.end if args.end is not None else len(cleaned_files)

    results = {}
    for idx, cpath in enumerate(cleaned_files[start_idx:end_idx], start=start_idx):
        print(f"\n[{idx+1}/{len(cleaned_files)}] {cpath.name}")
        ok, out_c = generate_briefing(
            cpath, briefing_prompt, args.briefing_model,
            output_dir, args.briefing_suffix, args.force
        )
        results[cpath.name] = (ok, out_c)

        if ok and out_c > 0:
            time.sleep(5)

    # Summary
    print(f"\n{'=' * 60}")
    print("Briefing Results:")
    success = sum(1 for ok, _ in results.values() if ok)
    generated = sum(1 for ok, c in results.values() if ok and c > 0)
    for f, (ok, out_c) in results.items():
        if ok and out_c > 0:
            print(f"  OK: {f[:40]}  -> {out_c:,} chars")
        elif ok:
            print(f"  OK: {f[:40]}  (skipped)")
        else:
            print(f"  FAIL: {f[:40]}")
    print(f"\n{success}/{len(results)} processed, {generated} briefings generated")
    print(f"Output: {output_dir}")


def main():
    args = parse_args()

    # Stage 2: Briefing mode
    if args.briefing:
        run_briefing_mode(args)
        return

    # Stage 1: ASR cleaning mode
    source_dir = Path(args.source).expanduser()
    output_dir = Path(args.output).expanduser()
    prompt_file = Path(args.prompt).expanduser()
    dict_file = Path(args.dict).expanduser()

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Meeting Transcript Batch Processor (Stage 1: ASR Clean)")
    print(f"Model: {args.model}")
    print(f"Source: {source_dir}")
    print(f"Output: {output_dir}")
    if args.retry:
        print(f"Mode: RETRY (threshold: {args.threshold}%)")
    print("=" * 60)

    # Handle retry mode
    if args.retry:
        retry_below_threshold(source_dir, output_dir, args.suffix, args.threshold)

    # Load base prompt and dictionary
    base_prompt = prompt_file.read_text(encoding="utf-8")
    dictionary = load_dictionary(dict_file)

    # Get all source files sorted by date
    files = []
    for ext in ["*.txt", "*.docx", "*.pdf"]:
        files.extend(source_dir.glob(ext))
    files = [f for f in files if re.match(r'^\d{8}', f.name)]
    files = sorted(set(files), key=lambda f: f.name[:14])

    print(f"Files to process: {len(files)}")
    print()

    start_idx = args.start
    end_idx = args.end if args.end is not None else len(files)

    results = {}
    for idx, filepath in enumerate(files[start_idx:end_idx], start=start_idx):
        print(f"\n[{idx+1}/{len(files)}] {filepath.name[:40]}...")
        ok, in_c, out_c = process_file(
            filepath, base_prompt, dictionary,
            args.model, output_dir, args.suffix
        )
        results[filepath.name] = (ok, in_c, out_c)

        if ok and in_c > 0:
            time.sleep(5)

    # Summary
    print(f"\n{'=' * 60}")
    print("Results:")
    success = 0
    for f, (ok, in_c, out_c) in results.items():
        if ok:
            success += 1
            if in_c > 0:
                ratio = out_c / in_c * 100
                flag = " ⚠" if ratio < 80 else ""
                print(f"  OK: {f[:35]}  ({ratio:.0f}%{flag})")
            else:
                print(f"  OK: {f[:35]}  (skipped)")
        else:
            print(f"  FAIL: {f[:35]}")
    print(f"\n{success}/{len(results)} files processed")
    print(f"Output vault: {output_dir}")

    # Save dictionary
    save_dictionary(dictionary, dict_file)


if __name__ == "__main__":
    main()
