"""Tag text content with analysis framework section IDs.

Reads analysis_framework.yaml and matches content to framework sections
using keyword, LLM (Gemini), or hybrid modes.

Usage:
    from shared.framework_tagger import tag_content
    sections = tag_content(text, mode="hybrid")  # ["S1", "S3.2", "S6"]

CLI test:
    python framework_tagger.py --test "Philip Morris ZYN sales grew 35%, TAM is $15B"
"""

import os
import re
import sys
from pathlib import Path

import yaml

# ── Framework Loading ────────────────────────────────────────

FRAMEWORK_PATH = Path(__file__).parent / "analysis_framework.yaml"

_framework_cache = None


def _load_framework() -> dict:
    """Load and cache the analysis framework YAML."""
    global _framework_cache
    if _framework_cache is not None:
        return _framework_cache
    with open(FRAMEWORK_PATH, encoding="utf-8") as f:
        _framework_cache = yaml.safe_load(f)
    return _framework_cache


def _build_keyword_index() -> dict[str, list[str]]:
    """Build mapping: keyword (lowercased) → list of section/subsection IDs.

    Returns e.g. {"TAM": ["S1", "S1.1"], "market share": ["S2", "S2.1"]}
    """
    fw = _load_framework()
    index = {}  # keyword_lower → set of IDs
    for section_key, section in fw["sections"].items():
        sid = section["id"]
        for sub in section.get("subsections", []):
            sub_id = sub["id"]
            for kw in sub.get("keywords", []):
                kw_lower = kw.lower()
                if kw_lower not in index:
                    index[kw_lower] = set()
                index[kw_lower].add(sid)
                index[kw_lower].add(sub_id)
    # Convert sets to sorted lists
    return {k: sorted(v) for k, v in index.items()}


# ── Keyword Tagging ──────────────────────────────────────────


def _tag_by_keyword(text: str) -> list[str]:
    """Tag content using keyword matching against framework.

    Returns list of section IDs (e.g. ["S1", "S2.1", "S4"]).
    Only includes a section if keyword hits >= threshold.
    """
    fw = _load_framework()
    threshold = fw.get("tagging", {}).get("keyword_threshold", 2)
    sub_threshold = fw.get("tagging", {}).get("subsection_threshold", 1)

    text_lower = text.lower()
    # Count hits per section and subsection
    section_hits = {}  # "S1" → count
    subsection_hits = {}  # "S1.1" → count

    for section_key, section in fw["sections"].items():
        sid = section["id"]
        for sub in section.get("subsections", []):
            sub_id = sub["id"]
            for kw in sub.get("keywords", []):
                kw_lower = kw.lower()
                # Use word boundary for short keywords, substring for longer
                if len(kw_lower) <= 3:
                    # Short keywords: need word boundary
                    pattern = r"\b" + re.escape(kw_lower) + r"\b"
                    count = len(re.findall(pattern, text_lower))
                else:
                    count = text_lower.count(kw_lower)
                if count > 0:
                    section_hits[sid] = section_hits.get(sid, 0) + count
                    subsection_hits[sub_id] = subsection_hits.get(sub_id, 0) + count

    result = set()
    for sid, hits in section_hits.items():
        if hits >= threshold:
            result.add(sid)
    for sub_id, hits in subsection_hits.items():
        if hits >= sub_threshold:
            result.add(sub_id)

    return sorted(result)


# ── LLM Tagging (Gemini) ────────────────────────────────────


def _tag_by_llm(text: str) -> list[str]:
    """Tag content using Gemini Flash for classification.

    Sends a truncated text + framework section descriptions to Gemini,
    asks it to return matching section IDs.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.home() / "13F-CLAUDE" / ".env")
    except ImportError:
        pass

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _tag_by_keyword(text)  # Fallback

    try:
        from google import genai
    except ImportError:
        return _tag_by_keyword(text)

    fw = _load_framework()
    # Build section descriptions for the prompt
    section_desc = []
    for section_key, section in fw["sections"].items():
        sid = section["id"]
        name = section["name_en"]
        subs = ", ".join(s["name"] for s in section.get("subsections", []))
        section_desc.append(f"- {sid}: {name} ({subs})")

    sections_text = "\n".join(section_desc)
    # Truncate input to ~4000 chars for cost/speed
    truncated = text[:4000]

    prompt = f"""Classify this text into framework sections. Return ONLY a JSON array of matching section IDs.

Framework sections:
{sections_text}

Rules:
- Return section IDs like ["S1", "S4.2"] — use parent ID (S1) for broad coverage, subsection ID (S1.1) for specific match
- Only include sections the text meaningfully covers (not just mentions in passing)
- Return [] if no sections match

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
            return [s for s in parsed if isinstance(s, str) and s.startswith("S")]
    except Exception:
        pass

    return _tag_by_keyword(text)  # Fallback on any error


# ── Public API ───────────────────────────────────────────────


def tag_content(text: str, mode: str = "hybrid") -> list[str]:
    """Tag text with analysis framework section IDs.

    Args:
        text: Content to analyze
        mode: "keyword" (fast, free), "llm" (Gemini), or "hybrid" (default)

    Returns:
        Sorted list of section IDs, e.g. ["S1", "S3.2", "S6"]
    """
    if not text or len(text.strip()) < 50:
        return []

    if mode == "keyword":
        return _tag_by_keyword(text)
    elif mode == "llm":
        return _tag_by_llm(text)
    elif mode == "hybrid":
        kw_result = _tag_by_keyword(text)
        if kw_result:
            return kw_result
        # Keyword found nothing → try LLM
        return _tag_by_llm(text)
    else:
        return _tag_by_keyword(text)


def get_section_info(section_id: str) -> dict | None:
    """Get display info for a section ID.

    Returns dict with name_en, name_cn, icon, or None if not found.
    """
    fw = _load_framework()
    for section_key, section in fw["sections"].items():
        if section["id"] == section_id:
            return {
                "id": section["id"],
                "name_en": section["name_en"],
                "name_cn": section["name_cn"],
                "icon": section["icon"],
            }
        # Check subsections
        if section_id.startswith(section["id"] + "."):
            for sub in section.get("subsections", []):
                if sub["id"] == section_id:
                    return {
                        "id": sub["id"],
                        "name": sub["name"],
                        "parent_id": section["id"],
                        "parent_name": section["name_en"],
                        "icon": section["icon"],
                    }
    return None


def get_all_sections() -> list[dict]:
    """Return list of all top-level sections with id, name_en, name_cn, icon."""
    fw = _load_framework()
    return [
        {
            "id": s["id"],
            "name_en": s["name_en"],
            "name_cn": s["name_cn"],
            "icon": s["icon"],
        }
        for s in fw["sections"].values()
    ]


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Tag text with analysis framework sections"
    )
    parser.add_argument("--test", type=str, help="Test text to tag")
    parser.add_argument(
        "--mode",
        choices=["keyword", "llm", "hybrid"],
        default="keyword",
        help="Tagging mode (default: keyword)",
    )
    parser.add_argument("--file", type=str, help="Read text from file")
    args = parser.parse_args()

    if args.test:
        text = args.test
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print(
            'Usage: python framework_tagger.py --test "text" [--mode keyword|llm|hybrid]'
        )
        sys.exit(1)

    sections = tag_content(text, mode=args.mode)
    # Use errors='replace' to handle emoji on Windows GBK console
    import io

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    out.write(f"Sections: {sections}\n")

    for sid in sections:
        info = get_section_info(sid)
        if info:
            if "parent_id" in info:
                out.write(
                    f"  {sid}: {info['icon']} {info['parent_name']} > {info['name']}\n"
                )
            else:
                out.write(
                    f"  {sid}: {info['icon']} {info['name_en']} ({info['name_cn']})\n"
                )
    out.flush()
