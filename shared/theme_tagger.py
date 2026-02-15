"""Tag ingested content against the user's active investment theses.

2-pass hybrid approach:
  Pass 1 — Ticker match:  detected_tickers vs thesis tickers + peers
  Pass 2a — Keyword match: bull/bear/kill_criteria/supply_chain keywords vs text
  Pass 2b — LLM fallback:  Gemini 2.0 Flash semantic classification (hybrid mode)

Usage:
    from shared.theme_tagger import tag_themes, get_active_thesis_tickers
    result = tag_themes(text, detected_tickers=["PM"], mode="hybrid")
    # {"themes": ["PM"], "theme_details": {"PM": {"confidence": 0.95, ...}}}

CLI test:
    python theme_tagger.py --test "ZYN nicotine pouch market share" --mode keyword
    python theme_tagger.py --list-theses
    python theme_tagger.py --file path/to/file.md
"""

import io
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# ── Paths ────────────────────────────────────────────────────

THESIS_DIR = Path(r"C:\Users\thisi\PORTFOLIO\research\companies")

# ── Thesis Cache ─────────────────────────────────────────────

_thesis_cache: dict[str, dict] = {}  # ticker -> parsed thesis dict
_thesis_mtimes: dict[str, float] = {}  # yaml path -> mtime at load time
_thesis_file_paths: set[str] = set()  # set of yaml file paths at load time


def _load_theses(force: bool = False) -> dict[str, dict]:
    """Load and cache active thesis.yaml files.

    Filters:
      - conviction >= 1
      - bull_case does NOT start with "TODO"

    Caches with file mtime check so edits are picked up without restart.
    Also detects deleted files by comparing cached file count.
    """
    global _thesis_cache, _thesis_mtimes, _thesis_file_paths

    if yaml is None:
        return {}

    if not THESIS_DIR.exists():
        return {}

    yaml_files = list(THESIS_DIR.glob("*/thesis.yaml"))

    # Check if any file changed since last load
    needs_reload = force or not _thesis_cache
    if not needs_reload:
        for yf in yaml_files:
            try:
                current_mtime = yf.stat().st_mtime
            except OSError:
                continue
            cached_mtime = _thesis_mtimes.get(str(yf))
            if cached_mtime is None or current_mtime != cached_mtime:
                needs_reload = True
                break

    # Check if number of files changed (detects deletions)
    if not needs_reload:
        current_file_paths = {str(yf) for yf in yaml_files}
        if current_file_paths != _thesis_file_paths:
            needs_reload = True

    if not needs_reload:
        return _thesis_cache

    # Full reload
    new_cache: dict[str, dict] = {}
    new_mtimes: dict[str, float] = {}
    new_file_paths: set[str] = set()

    for yf in yaml_files:
        try:
            mtime = yf.stat().st_mtime
            with open(yf, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue

            ticker = data.get("ticker", "")
            conviction = data.get("conviction", 0)
            bull_case = str(data.get("bull_case", ""))

            # Filter: conviction >= 1, bull_case not TODO
            if conviction < 1:
                continue
            if bull_case.upper().startswith("TODO"):
                continue

            # Extract fields we need
            thesis = {
                "ticker": ticker,
                "conviction": conviction,
                "bull_case": bull_case,
                "bear_case_1": str(data.get("bear_case_1", "")),
                "bear_case_2": str(data.get("bear_case_2", "")),
                "kill_criteria": [],
                "supply_chain": data.get("supply_chain", []) or [],
                "peers": [],
            }

            # Kill criteria (active only)
            for kc in data.get("kill_criteria", []) or []:
                if isinstance(kc, dict) and kc.get("status") == "active":
                    cond = kc.get("condition", "")
                    if cond:
                        thesis["kill_criteria"].append(cond)

            # Peers
            for peer in data.get("peers", []) or []:
                if isinstance(peer, dict) and peer.get("ticker"):
                    thesis["peers"].append(peer["ticker"])

            new_cache[ticker] = thesis
            new_mtimes[str(yf)] = mtime
            new_file_paths.add(str(yf))

        except Exception:
            continue

    _thesis_cache = new_cache
    _thesis_mtimes = new_mtimes
    _thesis_file_paths = new_file_paths
    return _thesis_cache


def _extract_keywords(thesis: dict) -> list[str]:
    """Extract matchable keywords from a thesis entry.

    Pulls meaningful phrases from bull_case, bear_case_1, bear_case_2,
    kill_criteria conditions, and supply_chain items.

    Returns two tiers of lowercased keywords:
      - Phrase-level fragments (split on +, :, etc.)
      - Word-level significant terms (proper nouns, domain terms 4+ chars)

    Both tiers are used for matching; the threshold logic in _pass2a
    requires >= 2 distinct hits regardless of tier.
    """
    raw_texts: list[str] = []

    for field in ("bull_case", "bear_case_1", "bear_case_2"):
        val = thesis.get(field, "")
        if val and not val.upper().startswith("TODO"):
            raw_texts.append(val)

    for cond in thesis.get("kill_criteria", []):
        raw_texts.append(cond)

    for item in thesis.get("supply_chain", []):
        raw_texts.append(str(item))

    # Stopwords to skip when extracting single-word keywords
    _stopwords = {
        "the",
        "and",
        "for",
        "are",
        "not",
        "but",
        "all",
        "can",
        "has",
        "was",
        "one",
        "our",
        "out",
        "new",
        "now",
        "due",
        "from",
        "with",
        "into",
        "than",
        "that",
        "this",
        "also",
        "more",
        "most",
        "will",
        "been",
        "have",
        "each",
        "when",
        "then",
        "them",
        "they",
        "very",
        "over",
        "under",
        "below",
        "above",
        "after",
        "before",
        "between",
        "growth",
        "share",
        "market",
        "global",
        "category",
        "volume",
        "revenue",
        "margin",
        "cost",
        "price",
        "risk",
        "loss",
        "gain",
    }

    keywords: list[str] = []
    seen: set[str] = set()

    for text in raw_texts:
        # Tier 1: Split on common delimiters to get phrase fragments
        # Include full-width Chinese punctuation: ：，、；（）
        fragments = re.split(r"[+:;|/(),\uff1a\uff0c\u3001\uff1b\uff08\uff09]+", text)
        for frag in fragments:
            frag = frag.strip().lower()
            if len(frag) >= 3 and frag not in seen:
                if not frag.replace(".", "").replace("%", "").isdigit():
                    keywords.append(frag)
                    seen.add(frag)

        # Tier 2: Extract significant individual words/bigrams
        # Uppercase words in original text = likely proper nouns/tickers/brands
        # Use lookaround instead of \b to handle CJK-adjacent English terms
        # (e.g. "GPU市场份额" should extract "GPU")
        words = re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9]{2,}(?![A-Za-z0-9])", text)
        for w in words:
            wl = w.lower()
            if wl not in seen and wl not in _stopwords and len(wl) >= 3:
                keywords.append(wl)
                seen.add(wl)

        # Also extract Chinese terms (they're significant by nature)
        cn_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        for ct in cn_terms:
            if ct not in seen:
                keywords.append(ct)
                seen.add(ct)

    return keywords


# ── Pass 1: Ticker Match ─────────────────────────────────────


def _pass1_ticker_match(
    detected_tickers: list[str], theses: dict[str, dict]
) -> dict[str, dict]:
    """Match detected tickers against thesis tickers and their peers.

    Direct thesis ticker match  → confidence 0.95
    Peer of a thesis ticker     → confidence 0.80
    """
    matches: dict[str, dict] = {}

    if not detected_tickers:
        return matches

    ticker_set = {t.upper() for t in detected_tickers}

    # Build reverse peer map: peer_ticker -> list of thesis tickers
    peer_to_thesis: dict[str, list[str]] = {}
    for ticker, thesis in theses.items():
        for peer in thesis.get("peers", []):
            peer_upper = peer.upper()
            if peer_upper not in peer_to_thesis:
                peer_to_thesis[peer_upper] = []
            peer_to_thesis[peer_upper].append(ticker)

    # Direct match
    for t in ticker_set:
        if t in theses:
            matches[t] = {
                "confidence": 0.95,
                "matched_by": "ticker_mention",
                "matched_kw": [],
            }

    # Peer match (only if thesis itself wasn't already directly matched)
    for t in ticker_set:
        if t in peer_to_thesis:
            for thesis_ticker in peer_to_thesis[t]:
                if thesis_ticker not in matches:
                    matches[thesis_ticker] = {
                        "confidence": 0.80,
                        "matched_by": "peer_mention",
                        "matched_kw": [f"peer:{t}"],
                    }

    return matches


# ── Pass 2a: Keyword Match ───────────────────────────────────

_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")


def _pass2a_keyword_match(
    text: str, theses: dict[str, dict], already_matched: set[str]
) -> dict[str, dict]:
    """Match text against thesis keywords for theses not already matched.

    A thesis is matched if >= 2 distinct keyword phrases hit.
    Confidence = min(0.70, 0.25 * number_of_hits).
    2 hits = 0.50, 3+ hits = 0.70 (capped).
    """
    matches: dict[str, dict] = {}
    text_lower = text.lower()

    for ticker, thesis in theses.items():
        if ticker in already_matched:
            continue

        keywords = _extract_keywords(thesis)
        if not keywords:
            continue

        hits: list[str] = []
        seen_kw: set[str] = set()
        for kw in keywords:
            if kw in seen_kw:
                continue
            seen_kw.add(kw)
            # For short ASCII keywords (< 6 chars, no CJK), use word boundary
            # to avoid false positives. CJK keywords and longer phrases use
            # plain substring matching (word boundaries don't work for CJK).
            if len(kw) < 6 and not _HAS_CJK.search(kw):
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text_lower):
                    hits.append(kw)
            else:
                if kw in text_lower:
                    hits.append(kw)

        if len(hits) >= 2:
            confidence = min(0.70, 0.25 * len(hits))
            matches[ticker] = {
                "confidence": round(confidence, 2),
                "matched_by": "keyword",
                "matched_kw": hits[:5],  # Cap at 5 for readability
            }

    return matches


# ── Pass 2b: LLM Fallback (Gemini Flash) ─────────────────────


def _pass2b_llm_match(text: str, theses: dict[str, dict]) -> dict[str, dict]:
    """Use Gemini 2.0 Flash to semantically classify text against theses.

    Only called in hybrid mode when Pass 1 + Pass 2a found nothing.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.home() / "13F-CLAUDE" / ".env")
    except ImportError:
        pass

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {}

    try:
        from google import genai
    except ImportError:
        return {}

    # Build thesis summaries for the prompt
    thesis_lines = []
    for ticker, th in theses.items():
        summary = f"- {ticker}: {th['bull_case']}"
        if th.get("supply_chain"):
            summary += f" | Themes: {', '.join(th['supply_chain'][:3])}"
        thesis_lines.append(summary)

    if not thesis_lines:
        return {}

    theses_text = "\n".join(thesis_lines)
    truncated = text[:4000]

    prompt = f"""You are an investment research classifier. Given the text below, identify which investment theses it is relevant to.

Active investment theses:
{theses_text}

Rules:
- Return ONLY a JSON array of matching ticker symbols, e.g. ["PM", "NVDA"]
- Only include tickers where the text has MEANINGFUL relevance to the thesis (not just passing mentions)
- Return [] if no theses match
- Be conservative: only match if the text would be useful for monitoring/updating the thesis

Text:
{truncated}

Response (JSON array only):"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        import json

        result_text = response.text.strip()
        # Strip markdown code fences
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
        parsed = json.loads(result_text.strip())
        if isinstance(parsed, list):
            matches: dict[str, dict] = {}
            for item in parsed:
                t = str(item).upper()
                if t in theses:
                    matches[t] = {
                        "confidence": 0.60,
                        "matched_by": "llm",
                        "matched_kw": [],
                    }
            return matches
    except Exception:
        pass

    return {}


# ── Public API ───────────────────────────────────────────────


def tag_themes(
    text: str,
    detected_tickers: list[str] | None = None,
    mode: str = "hybrid",
) -> dict:
    """Tag text content against active investment theses.

    Args:
        text: Content to analyze
        detected_tickers: Pre-detected ticker symbols in the text
        mode: "keyword" (fast, free), "llm" (Gemini Flash), or "hybrid" (default)

    Returns:
        {
          "themes": ["PM", "NVDA"],          # sorted ticker list
          "theme_details": {
            "PM": {"confidence": 0.95, "matched_by": "ticker_mention", "matched_kw": []},
            ...
          }
        }
    """
    empty_result = {"themes": [], "theme_details": {}}

    if not text or len(text.strip()) < 20:
        return empty_result

    theses = _load_theses()
    if not theses:
        return empty_result

    all_matches: dict[str, dict] = {}

    # Pass 1: Ticker match (always runs if tickers provided)
    if detected_tickers:
        p1 = _pass1_ticker_match(detected_tickers, theses)
        all_matches.update(p1)

    if mode in ("keyword", "hybrid"):
        # Pass 2a: Keyword match (skip already-matched theses)
        p2a = _pass2a_keyword_match(text, theses, set(all_matches.keys()))
        all_matches.update(p2a)

    if mode == "llm":
        # LLM only (no keyword pass)
        p2b = _pass2b_llm_match(text, theses)
        for t, detail in p2b.items():
            if t not in all_matches:
                all_matches[t] = detail
    elif mode == "hybrid" and not all_matches:
        # Pass 2b: LLM fallback only if nothing matched yet
        p2b = _pass2b_llm_match(text, theses)
        for t, detail in p2b.items():
            if t not in all_matches:
                all_matches[t] = detail

    if not all_matches:
        return empty_result

    # Sort by confidence descending
    sorted_tickers = sorted(
        all_matches.keys(), key=lambda t: all_matches[t]["confidence"], reverse=True
    )

    return {
        "themes": sorted_tickers,
        "theme_details": {t: all_matches[t] for t in sorted_tickers},
    }


def get_active_thesis_tickers() -> list[str]:
    """Return sorted list of tickers with active theses."""
    theses = _load_theses()
    return sorted(theses.keys())


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    # Windows-safe UTF-8 stdout
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Tag text against active investment theses"
    )
    parser.add_argument("--test", type=str, help="Test text to tag")
    parser.add_argument(
        "--mode",
        choices=["keyword", "llm", "hybrid"],
        default="hybrid",
        help="Tagging mode (default: hybrid)",
    )
    parser.add_argument("--tickers", type=str, help="Comma-separated detected tickers")
    parser.add_argument("--file", type=str, help="Read text from file")
    parser.add_argument(
        "--list-theses", action="store_true", help="List active theses and exit"
    )
    args = parser.parse_args()

    # --list-theses mode
    if args.list_theses:
        theses = _load_theses()
        if not theses:
            out.write(
                "No active theses found (need thesis.yaml with conviction>=1 and bull_case not TODO)\n"
            )
            out.flush()
            sys.exit(0)

        out.write(f"Active theses ({len(theses)}):\n")
        out.write("-" * 80 + "\n")
        for ticker in sorted(theses.keys()):
            th = theses[ticker]
            peers = ", ".join(th["peers"]) if th["peers"] else "none"
            kc_count = len(th["kill_criteria"])
            sc_count = len(th["supply_chain"])
            out.write(
                f"  {ticker:8s} conv={th['conviction']}  peers=[{peers}]  KC={kc_count}  SC={sc_count}\n"
            )
            out.write(f"           bull: {th['bull_case'][:70]}\n")
        out.flush()
        sys.exit(0)

    # Determine input text
    if args.test:
        text = args.test
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        out.write(
            'Usage: python theme_tagger.py --test "text" [--mode keyword|llm|hybrid] [--tickers NVDA,PM]\n'
            "       python theme_tagger.py --list-theses\n"
            "       python theme_tagger.py --file path/to/file.md\n"
        )
        out.flush()
        sys.exit(1)

    # Parse tickers
    detected_tickers = None
    if args.tickers:
        detected_tickers = [t.strip().upper() for t in args.tickers.split(",")]

    result = tag_themes(text, detected_tickers=detected_tickers, mode=args.mode)

    out.write(f"\nMode: {args.mode}\n")
    if detected_tickers:
        out.write(f"Detected tickers: {detected_tickers}\n")
    out.write(f"Themes: {result['themes']}\n")
    if result["theme_details"]:
        out.write("\nDetails:\n")
        for ticker, detail in result["theme_details"].items():
            out.write(
                f"  {ticker}: confidence={detail['confidence']:.2f}  "
                f"matched_by={detail['matched_by']}  "
                f"kw={detail['matched_kw']}\n"
            )
    else:
        out.write("No themes matched.\n")
    out.flush()
