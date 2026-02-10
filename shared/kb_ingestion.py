#!/usr/bin/env python3
"""
Knowledge Base Ingestion Pipeline.
Processes PDF, Word, Markdown, TXT, and URLs into the knowledge index.
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    import io
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

# Shared module imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.ticker_detector import detect_tickers, detect_primary_ticker
from shared.framework_tagger import tag_content

# Paths
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
OUTPUT_DIR = VAULT_DIR / "研究" / "研报摘要"
CONFIG_FILE = Path.home() / ".claude" / "skills" / "socratic-writer" / "data" / "config.json"


def _load_gemini_key():
    """Load Gemini API key from config."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")
    return ""


def _compute_hash(text, source_org=""):
    """Compute canonical hash for dedup."""
    content = (text[:5000] + source_org).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _extract_pdf_via_gemini(path):
    """Extract text from scanned/image PDF via Gemini file upload."""
    gemini_key = _load_gemini_key()
    if not gemini_key:
        print("  ⚠️ Scanned PDF detected but no Gemini API key — cannot OCR")
        return None

    try:
        from google import genai

        print("  📷 Scanned PDF detected, using Gemini OCR...")
        client = genai.Client(api_key=gemini_key)
        uploaded = client.files.upload(file=str(path))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                uploaded,
                "Extract ALL text from this PDF document. Output the full text "
                "content faithfully, preserving structure (headings, paragraphs, "
                "bullet points, tables). Do NOT summarize. Output in the original language.",
            ],
        )
        text = response.text
        if text and len(text) > 50:
            print(f"  📷 Gemini OCR extracted {len(text)} chars")
            return text
        print("  ⚠️ Gemini OCR returned insufficient text")
        return None
    except Exception as e:
        print(f"  ⚠️ Gemini OCR failed: {e}")
        return None


def _extract_text(file_path):
    """Extract text from file based on extension."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        text = None
        # Try pdfplumber first (fast, works for text-based PDFs)
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            if text_parts:
                text = "\n\n".join(text_parts)
        except ImportError:
            print("Warning: pdfplumber not installed, trying Gemini OCR...")

        # Fallback: Gemini file upload for scanned/image PDFs
        if not text:
            text = _extract_pdf_via_gemini(path)

        return text

    elif ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            print("Warning: python-docx not installed. Install with: pip install python-docx")
            return None

    elif ext in (".md", ".txt", ".text"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    else:
        print(f"Unsupported file type: {ext}")
        return None


def _detect_language(text):
    """Simple language detection based on character ratio."""
    if not text:
        return "en"
    chinese_chars = sum(1 for c in text[:2000] if '\u4e00' <= c <= '\u9fff')
    return "zh" if chinese_chars > len(text[:2000]) * 0.1 else "en"


def _generate_summary(text, gemini_key):
    """Generate structured summary using Gemini."""
    if not gemini_key:
        return text[:500] + "..." if len(text) > 500 else text

    try:
        from google import genai

        client = genai.Client(api_key=gemini_key)
        prompt = f"""你是一个投资研究助手。请为以下文档生成结构化摘要：

1. **核心观点**（1句话）
2. **关键数据点**（3-5个，带数字）
3. **主要结论/建议**（1-2句）
4. **文档类型**：研报 / 专家纪要 / 新闻分析 / 学术论文 / 其他

文档内容：
{text[:8000]}"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        summary = response.text

        # Validation: summary should be >50 chars
        if len(summary) < 50:
            return text[:500] + "..."
        return summary

    except Exception as e:
        print(f"Warning: Gemini summary failed ({e}), using fallback")
        return text[:500] + "..." if len(text) > 500 else text


def _classify_document(text, summary=""):
    """Classify document type."""
    combined = (text[:3000] + summary).lower()
    if any(w in combined for w in ["目标价", "target price", "rating", "评级", "buy", "sell", "hold", "overweight"]):
        return "research_report"
    if any(w in combined for w in ["专家", "expert", "纪要", "minutes", "call notes", "访谈"]):
        return "expert_call"
    if any(w in combined for w in ["earnings", "财报", "q1", "q2", "q3", "q4", "quarter"]):
        return "transcript"
    return "article"


def ingest_file(file_path, source_type="auto", source_org="", author="", ticker_override=""):
    """
    Main ingestion entry point for local files.
    ticker_override: if provided, use this as primary ticker instead of auto-detection.
    Returns dict with ingestion results.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    print(f"📄 Processing: {path.name}")

    # 1. Extract text
    text = _extract_text(path)
    if not text:
        return {"error": f"Failed to extract text from {path.name}"}

    # 2. Compute hash for dedup
    canonical_hash = _compute_hash(text, source_org)

    # 3. Detect primary ticker from title/header (most reliable)
    title = path.stem.replace("_", " ").replace("-", " ")
    if ticker_override:
        primary_ticker = ticker_override.upper()
        print(f"  🏷️ Primary (override): {primary_ticker}")
    else:
        primary_ticker = detect_primary_ticker(path.name, text[:1000])

    # 4. Detect mentioned tickers from full text
    ticker_results = detect_tickers(text)
    tickers = [t['ticker'] if isinstance(t, dict) else t for t in ticker_results]

    # Ensure primary ticker is first in the list
    if primary_ticker:
        if primary_ticker in tickers:
            tickers.remove(primary_ticker)
        tickers.insert(0, primary_ticker)
    elif tickers:
        primary_ticker = tickers[0]
    print(f"  🏷️ Primary: {primary_ticker or 'none'}")
    print(f"  🏷️ Mentioned: {tickers[1:] if len(tickers) > 1 else 'none'}")

    # 4. Framework tagging
    try:
        framework_tags = tag_content(text, mode="keyword")
    except Exception:
        framework_tags = []
    print(f"  📐 Framework: {framework_tags or 'none'}")

    # 5. Generate summary
    gemini_key = _load_gemini_key()
    summary = _generate_summary(text, gemini_key)
    print(f"  📝 Summary generated ({len(summary)} chars)")

    # 6. Classify document
    if source_type == "auto":
        source_type = _classify_document(text, summary)
    print(f"  📂 Type: {source_type}")

    # 7. Detect language
    language = _detect_language(text)

    # 8. Save to Obsidian
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:80]
    output_name = f"{date_str} - {source_type}_{safe_title}.md"
    output_path = OUTPUT_DIR / output_name

    frontmatter = {
        "tags": ["knowledge-base", source_type] + ([primary_ticker] if primary_ticker else []),
        "date": date_str,
        "source": source_org or "local",
        "ticker": primary_ticker or "",
        "tickers": tickers,
        "source_type": source_type,
        "framework_tags": framework_tags,
        "author": author,
        "comments": "",
    }

    content = f"""---
{chr(10).join(f'{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else (f"{chr(34)}{chr(34)}" if v == "" and k == "comments" else v)}' for k, v in frontmatter.items() if v or k == "comments")}
---

# {title}

## 摘要

{summary}

## 原文

{text[:50000]}
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  💾 Saved: {output_path.relative_to(VAULT_DIR)}")

    # 10. Write to knowledge_index
    from shared.task_manager import add_to_knowledge_index
    doc_id = add_to_knowledge_index(
        source_type=source_type,
        title=title,
        file_path=str(output_path),
        ticker=primary_ticker,
        tickers_mentioned=tickers,
        author=author,
        source_org=source_org,
        publish_date=date_str,
        summary=summary[:2000],
        framework_tags=framework_tags,
        canonical_hash=canonical_hash,
        word_count=len(text.split()),
        language=language,
    )

    if doc_id is None:
        print("  ⚠️ Duplicate detected (same content already in index)")
    else:
        print(f"  ✅ Indexed as #{doc_id}")

    return {
        "path": str(output_path),
        "title": title,
        "primary_ticker": primary_ticker,
        "tickers": tickers,
        "summary": summary[:500],
        "source_type": source_type,
        "framework_tags": framework_tags,
        "doc_id": doc_id,
    }


def ingest_url(url):
    """Ingest a URL."""
    print(f"🌐 Fetching: {url}")

    # Route known URLs
    if "mp.weixin.qq.com" in url:
        print("  → WeChat article detected, use /wechat-hao instead")
        return {"error": "WeChat URLs should use /wechat-hao", "redirect": "/wechat-hao"}

    # Generic URL extraction via trafilatura
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"error": f"Failed to fetch URL: {url}"}
        text = trafilatura.extract(downloaded, include_comments=False) or ""
        if not text:
            return {"error": "No content extracted from URL"}
    except ImportError:
        return {"error": "trafilatura not installed. Run: pip install trafilatura"}

    # Save as temp file then process
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
        temp_path = f.name

    result = ingest_file(temp_path, source_org=url)
    Path(temp_path).unlink(missing_ok=True)
    return result


def search_index(query=None, ticker=None, source_type=None, days=None):
    """Search the knowledge index. Wrapper for task_manager function."""
    from shared.task_manager import search_knowledge_index
    return search_knowledge_index(query=query, ticker=ticker, source_type=source_type, days=days)


def index_stats(ticker=None):
    """Get index statistics. Wrapper for task_manager function."""
    from shared.task_manager import knowledge_index_stats
    return knowledge_index_stats(ticker=ticker)


def main():
    """CLI interface."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  kb_ingestion.py ingest FILE [--org ORG] [--author AUTHOR]")
        print("  kb_ingestion.py url URL")
        print("  kb_ingestion.py search QUERY")
        print("  kb_ingestion.py search --ticker TICKER")
        print("  kb_ingestion.py stats [TICKER]")
        return

    command = sys.argv[1]

    if command == "ingest" and len(sys.argv) > 2:
        file_path = sys.argv[2]
        org = ""
        author = ""
        ticker = ""
        for i, arg in enumerate(sys.argv[3:], 3):
            if arg == "--org" and i + 1 < len(sys.argv):
                org = sys.argv[i + 1]
            elif arg == "--author" and i + 1 < len(sys.argv):
                author = sys.argv[i + 1]
            elif arg == "--ticker" and i + 1 < len(sys.argv):
                ticker = sys.argv[i + 1]
        result = ingest_file(file_path, source_org=org, author=author, ticker_override=ticker)
        if "error" in result:
            print(f"\n❌ {result['error']}")
        else:
            print(f"\n✅ Ingested: {result['title']}")
            print(f"   Tickers: {result['tickers']}")
            print(f"   Type: {result['source_type']}")
            print(f"   Path: {result['path']}")
            print(f"\n💡 Next: /research {result['tickers'][0] if result['tickers'] else 'TICKER'}")

    elif command == "url" and len(sys.argv) > 2:
        result = ingest_url(sys.argv[2])
        if "error" in result:
            print(f"\n❌ {result['error']}")

    elif command == "search":
        ticker = None
        query = None
        args_list = sys.argv[2:]
        i = 0
        while i < len(args_list):
            arg = args_list[i]
            if arg == "--ticker" and i + 1 < len(args_list):
                ticker = args_list[i + 1]
                i += 2
            elif not arg.startswith("--"):
                query = arg
                i += 1
            else:
                i += 1
        results = search_index(query=query, ticker=ticker)
        if not results:
            print("No results found.")
        else:
            print(f"\n🔍 Found {len(results)} results:")
            for r in results:
                # Convert Row to dict for easier access
                row = dict(r) if hasattr(r, 'keys') else r
                source_type = row['source_type'] if isinstance(row, dict) else r[1]
                title = row['title'] if isinstance(row, dict) else r[4]
                publish_date = row['publish_date'] if isinstance(row, dict) else r[7]
                summary = row['summary'] if isinstance(row, dict) else r[10]
                file_path = row['file_path'] if isinstance(row, dict) else r[9]

                print(f"  [{source_type}] {title} ({publish_date or 'unknown date'})")
                if summary:
                    print(f"    Summary: {summary[:100]}...")
                print(f"    Path: {file_path}")

    elif command == "stats":
        ticker = sys.argv[2] if len(sys.argv) > 2 else None
        stats = index_stats(ticker=ticker)
        if not stats:
            print("Knowledge index is empty.")
        else:
            total = sum(s[1] for s in stats)
            print(f"\n📚 Knowledge Index: {total} documents")
            for s in stats:
                print(f"  {s[0]}: {s[1]}")

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
