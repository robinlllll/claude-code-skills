"""
Podcast analysis prompt templates.

Usage:
    from prompts import get_podcast_prompt

    prompt = get_podcast_prompt(
        podcast_name="The a16z Show",
        episode_title="The Hidden Economics Powering AI",
        episode_date="2026-01-26",
        tickers_detected=["NVDA", "MSFT"],
        portfolio_context="NVDA: Bull thesis, conviction HIGH...",
        holdings_context="NVDA: 42 holders (3 new, 12 increased)...",
        research_context="Recent notes mention NVDA margin expansion...",
    )
"""

from .prompt_podcast import get_podcast_prompt


def build_portfolio_context(tickers: list[str]) -> dict[str, str]:
    """Gather portfolio context for detected tickers.

    Returns dict with keys: portfolio_context, holdings_context, research_context.
    Each value is a formatted string ready to inject into the prompt.
    Failures are silently skipped — missing context is acceptable.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path.home() / ".claude" / "skills"))

    portfolio_lines = []
    holdings_lines = []
    research_lines = []

    # 1. Thesis summaries
    for ticker in tickers:
        thesis_path = (
            Path.home()
            / "PORTFOLIO"
            / "research"
            / "companies"
            / ticker
            / "thesis.yaml"
        )
        if thesis_path.exists():
            try:
                import yaml

                with open(thesis_path, "r", encoding="utf-8") as f:
                    thesis = yaml.safe_load(f)
                if thesis:
                    conviction = thesis.get("conviction", "?")
                    direction = thesis.get("direction", "?")
                    bull = thesis.get("bull_case", "N/A")
                    bear = thesis.get("bear_case", "N/A")
                    kc = thesis.get("kill_criteria", [])
                    kc_str = "; ".join(kc) if isinstance(kc, list) else str(kc)
                    portfolio_lines.append(
                        f"- **{ticker}**: Direction={direction}, Conviction={conviction}\n"
                        f"  Bull: {bull}\n"
                        f"  Bear: {bear}\n"
                        f"  Kill Criteria: {kc_str}"
                    )
            except Exception:
                pass

    # 2. 13F holdings
    try:
        from importlib import import_module

        q13f = import_module("shared.13f_query")
        for ticker in tickers:
            try:
                one_liner = q13f.one_line_summary(ticker)
                if one_liner and "no holdings" not in one_liner.lower():
                    holdings_lines.append(f"- **{ticker}**: {one_liner}")
            except Exception:
                pass
    except ImportError:
        pass

    # 3. Recent vault research (search for recent notes mentioning tickers)
    vault_base = Path.home() / "Documents" / "Obsidian Vault" / "研究"
    if vault_base.exists():
        for ticker in tickers:
            try:
                # Search research notes and earnings analysis
                search_dirs = [
                    vault_base / "研究笔记",
                    vault_base / "财报分析" / f"{ticker}-US",
                ]
                found = []
                for search_dir in search_dirs:
                    if not search_dir.exists():
                        continue
                    for md_file in sorted(
                        search_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
                    )[:3]:  # Latest 3 files
                        with open(md_file, "r", encoding="utf-8") as f:
                            content = f.read(500)  # Just read beginning
                        if ticker in content or ticker.lower() in content.lower():
                            found.append(md_file.name)
                if found:
                    research_lines.append(
                        f"- **{ticker}**: Recent notes — {', '.join(found[:3])}"
                    )
            except Exception:
                pass

    return {
        "portfolio_context": "\n".join(portfolio_lines) if portfolio_lines else "",
        "holdings_context": "\n".join(holdings_lines) if holdings_lines else "",
        "research_context": "\n".join(research_lines) if research_lines else "",
    }


__all__ = ["get_podcast_prompt", "build_portfolio_context"]
