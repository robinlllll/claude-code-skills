"""Phase 4: Report Assembler — combines section outputs into final report.

Merges S1-S9 into a single markdown report with:
- YAML frontmatter
- Executive summary (from S8)
- Table of contents
- Full 9-section analysis
- Appendix: data sources, model metadata, token usage

Saves to Obsidian vault and workspace.

Usage:
    python report_assembler.py TICKER --workspace DIR
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR


def _sanitize_markdown(text: str) -> str:
    """Escape bare < characters that Obsidian misinterprets as HTML tags.

    Preserves valid HTML: <a id="...">, <br>, <br/>.
    Escapes things like <20%, <12 months, <N that break rendering.
    """
    # Escape < followed by a digit (e.g. <20%, <12)
    text = re.sub(r"<(\d)", r"\\<\1", text)
    return text


SECTION_TITLES = {
    "S1": "1. Market & Growth",
    "S2": "2. Competitive Landscape",
    "S3": "3. Barriers & Moat",
    "S4": "4. Company & Financials",
    "S5": "5. Management & Governance",
    "S6": "6. Valuation & Expected Returns",
    "S7": "7. Risks",
    "RT": "Red Team Review (Adversarial Analysis)",
    "S8": "8. Final Investment Insights & Strategy Recommendations",
    "S9": "9. Suggestions for Further Research",
}


def assemble_report(
    ticker: str,
    company_name: str,
    sections: dict,
    data_pack: dict,
    total_tokens: dict = None,
    total_elapsed_s: float = 0,
    workspace: Path = None,
) -> str:
    """Assemble final coverage initiation report.

    Args:
        ticker: Stock ticker
        company_name: Full company name
        sections: Dict of section results from dispatcher
        data_pack: Original data pack
        total_tokens: Token usage summary
        total_elapsed_s: Total pipeline time
        workspace: Working directory for saving artifacts

    Returns:
        Full markdown report string
    """
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H%M")

    # ===== Frontmatter =====
    report = f"""---
title: "{company_name} ({ticker}) — Coverage Initiation"
ticker: {ticker}
date: {today}
type: coverage-initiation
tags: [coverage-initiation, {ticker}]
models:
  primary: gemini (S1, S2, S3, S6)
  challenger: gpt (S4, S5, S7)
  red_team: grok (adversarial review)
  synthesis: gemini/claude (S8, S9)
pipeline_time: {total_elapsed_s}s
tokens: {(total_tokens or {}).get("input", 0) + (total_tokens or {}).get("output", 0):,}
---

# {company_name} ({ticker}) — Coverage Initiation Report

**Date:** {today}
**Analyst:** Multi-AI Pipeline (Gemini + GPT + Grok + Claude)
**Pipeline Time:** {total_elapsed_s:.0f}s

"""

    # ===== Quick Facts =====
    yf = data_pack.get("yfinance", {})
    price = yf.get("price", {})
    val = yf.get("valuation", {})
    company = yf.get("company", {})

    report += f"""## Quick Facts

| Metric | Value |
|--------|-------|
| **Sector** | {company.get("sector", "N/A")} |
| **Industry** | {company.get("industry", "N/A")} |
| **Market Cap** | ${(price.get("market_cap") or 0) / 1e9:.1f}B |
| **Price** | ${price.get("current", "N/A")} |
| **52-Week Range** | ${price.get("52w_low", "N/A")} — ${price.get("52w_high", "N/A")} |
| **P/E (Trailing)** | {val.get("pe_trailing", "N/A")} |
| **EV/EBITDA** | {val.get("ev_ebitda", "N/A")} |
| **Employees** | {f"{company["employees"]:,}" if company.get("employees") else "N/A"} |

"""

    # ===== Table of Contents =====
    report += "## Table of Contents\n\n"
    for key, title in SECTION_TITLES.items():
        section = sections.get(key, {})
        status = "done" if section.get("content") else "failed"
        provider = section.get("provider", "?")
        report += f"- [{title}](#{key.lower()}) — _{provider}_ ({status})\n"
    report += "\n---\n\n"

    # ===== Sections =====
    for key, title in SECTION_TITLES.items():
        section = sections.get(key, {})
        content = section.get("content", "")
        provider = section.get("provider", "unknown")
        model = section.get("model", "unknown")

        report += f'<a id="{key.lower()}"></a>\n\n'
        report += f"# {title}\n\n"
        report += f"*Model: {provider} ({model})*\n\n"

        if content:
            report += _sanitize_markdown(content.strip())
        else:
            error = section.get("error", "No content generated")
            report += f"> **Section failed:** {error}\n"

        report += "\n\n---\n\n"

    # ===== Appendix =====
    report += _build_appendix(
        ticker, data_pack, sections, total_tokens, total_elapsed_s
    )

    # ===== Save =====
    # Save to Obsidian vault
    vault_dir = OUTPUT_DIR / ticker.upper()
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / f"{timestamp} {ticker} Coverage Initiation.md"
    vault_path.write_text(report, encoding="utf-8")
    print(f"  Report saved: {vault_path}")

    # Save to workspace
    if workspace:
        workspace.mkdir(parents=True, exist_ok=True)
        ws_path = workspace / "report.md"
        ws_path.write_text(report, encoding="utf-8")
        print(f"  Workspace copy: {ws_path}")

    return report


def _build_appendix(
    ticker: str,
    data_pack: dict,
    sections: dict,
    total_tokens: dict,
    total_elapsed_s: float,
) -> str:
    """Build the appendix with data sources and metadata."""
    parts = ["# Appendix\n"]

    # A. Data Sources
    parts.append("## A. Data Sources\n")
    parts.append("| Source | Status | Key Data |")
    parts.append("|--------|--------|----------|")

    # yfinance
    yf = data_pack.get("yfinance", {})
    parts.append(
        f"| yfinance | OK | MCap ${(yf.get('price', {}).get('market_cap') or 0) / 1e9:.1f}B, "
        f"P/E {yf.get('valuation', {}).get('pe_trailing', 'N/A')} |"
    )

    # SEC EDGAR
    sec = data_pack.get("sec_edgar", {})
    if "error" not in sec:
        rev_years = len(sec.get("financial_history", {}).get("revenue", []))
        filings_n = len(sec.get("filings", []))
        parts.append(
            f"| SEC EDGAR | OK | {rev_years}yr revenue history, {filings_n} filings |"
        )
    else:
        parts.append(f"| SEC EDGAR | FAIL | {sec.get('error', 'Unknown')} |")

    # Perplexity
    pplx = data_pack.get("perplexity", {})
    if "error" not in pplx and not pplx.get("skipped"):
        tokens = pplx.get("total_tokens", 0)
        n_topics = sum(
            1
            for k in ["industry", "competitive", "moat", "management", "risks"]
            if k in pplx and not isinstance(pplx[k], str)
        )
        n_queries = sum(
            len(pplx.get(k, {}).get("results", []))
            for k in ["industry", "competitive", "moat", "management", "risks"]
        )
        parts.append(
            f"| Perplexity | OK | {n_topics} topics, {n_queries} queries, {tokens} tokens |"
        )
    else:
        parts.append("| Perplexity | SKIP/FAIL | — |")

    # Local
    local = data_pack.get("local", {})
    if "error" not in local:
        thesis = "yes" if local.get("thesis") else "no"
        earnings = len(local.get("transcripts", []))
        thirteenf = len(local.get("thirteen_f", []))
        parts.append(
            f"| Local Vault | OK | thesis={thesis}, earnings={earnings}, 13F={thirteenf} |"
        )
    else:
        parts.append("| Local Vault | FAIL | — |")

    parts.append("")

    # B. Model Performance
    parts.append("## B. Model Performance\n")
    parts.append("| Section | Model | Tokens (in/out) | Time |")
    parts.append("|---------|-------|-----------------|------|")

    for key in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "RT", "S8", "S9"]:
        s = sections.get(key, {})
        title = SECTION_TITLES.get(key, key)
        provider = s.get("provider", "?")
        model = s.get("model", "?")
        tokens = s.get("tokens", {})
        elapsed = s.get("elapsed_s", 0)
        parts.append(
            f"| {title} | {provider} ({model}) | "
            f"{tokens.get('input', 0):,} / {tokens.get('output', 0):,} | "
            f"{elapsed}s |"
        )

    parts.append("")
    parts.append(
        f"**Total tokens:** {(total_tokens or {}).get('input', 0):,} input + "
        f"{(total_tokens or {}).get('output', 0):,} output"
    )
    parts.append(f"**Total time:** {total_elapsed_s:.0f}s")
    parts.append("")

    # C. Collected At
    parts.append("## C. Metadata\n")
    parts.append(f"- **Data collected:** {data_pack.get('collected_at', 'N/A')}")
    parts.append(f"- **Report generated:** {datetime.now().isoformat()}")
    parts.append("- **Pipeline version:** 0.1.0")
    parts.append("")

    return "\n".join(parts)


# ============ CLI entry point ============


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Coverage Initiation — Phase 4: Report Assembly"
    )
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument(
        "--workspace", required=True, help="Workspace directory with sections.json"
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    sections_path = workspace / "sections.json"

    if not sections_path.exists():
        print(f"  ERROR: {sections_path} not found. Run section_dispatcher.py first.")
        sys.exit(1)

    with open(sections_path, "r", encoding="utf-8") as f:
        dispatch_result = json.load(f)

    # Load data pack
    sys.path.insert(0, str(Path(__file__).parent))
    from data_collector import load_cached

    data_pack = load_cached(args.ticker.upper())
    if not data_pack:
        print(f"  ERROR: No cached data pack for {args.ticker}")
        sys.exit(1)

    assemble_report(
        ticker=args.ticker.upper(),
        company_name=data_pack["company_name"],
        sections=dispatch_result["sections"],
        data_pack=data_pack,
        total_tokens=dispatch_result.get("total_tokens"),
        total_elapsed_s=dispatch_result.get("total_elapsed_s", 0),
        workspace=workspace,
    )


if __name__ == "__main__":
    main()
