"""
Provider-specific prompt templates for earnings transcript analysis.

Usage:
    from prompts import get_prompt_for_provider

    prompt = get_prompt_for_provider(
        provider="gemini",  # or "claude" or "chatgpt"
        company_name="Apple, Inc",
        ticker="AAPL-US",
        curr="Q4 2025",
        prev="Q3 2025",
        quarters_comparison="Q4 2025 vs Q3 2025",
        company_specific_notes=""
    )
"""

from .prompt_gemini import get_gemini_prompt
from .prompt_claude import get_claude_prompt
from .prompt_default import get_default_prompt
from .prompt_peer import get_peer_prompt


def get_prompt_for_provider(
    provider: str,
    company_name: str,
    ticker: str,
    curr: str,
    prev: str,
    quarters_comparison: str,
    company_specific_notes: str = "",
) -> str:
    """
    Get the appropriate prompt template based on the AI provider.

    Args:
        provider: One of "gemini", "claude", "chatgpt", or "default"
        company_name: Full company name
        ticker: Stock ticker (e.g., "AAPL-US")
        curr: Current quarter label (e.g., "Q4 2025")
        prev: Previous quarter label (e.g., "Q3 2025")
        quarters_comparison: Comparison string (e.g., "Q4 2025 vs Q3 2025")
        company_specific_notes: Optional company-specific analysis notes

    Returns:
        Formatted prompt string optimized for the specified provider
    """
    provider = provider.lower().strip()

    if provider == "gemini":
        return get_gemini_prompt(
            company_name=company_name,
            ticker=ticker,
            curr=curr,
            prev=prev,
            quarters_comparison=quarters_comparison,
            company_specific_notes=company_specific_notes,
        )
    elif provider == "claude":
        return get_claude_prompt(
            company_name=company_name,
            ticker=ticker,
            curr=curr,
            prev=prev,
            quarters_comparison=quarters_comparison,
            company_specific_notes=company_specific_notes,
        )
    else:
        # Default prompt for ChatGPT and any other provider
        return get_default_prompt(
            company_name=company_name,
            ticker=ticker,
            curr=curr,
            prev=prev,
            quarters_comparison=quarters_comparison,
            company_specific_notes=company_specific_notes,
        )
