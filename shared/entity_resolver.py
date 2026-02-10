"""Dual-layer entity resolution: Dictionary (deterministic) + LLM (probabilistic).

Layer 1: Exact/alias match against entity_dictionary.yaml
Layer 2: LLM disambiguation for unknown entities (marks needs_review=True)
"""

from pathlib import Path
from typing import Optional

import yaml

DICT_PATH = Path(__file__).parent / "entity_dictionary.yaml"

# Module-level cache
_entity_dict: Optional[dict] = None
_alias_map: Optional[dict[str, str]] = None  # alias_lower → TICKER


def _load_dictionary() -> tuple[dict, dict[str, str]]:
    """Load and cache entity dictionary + build alias→ticker map."""
    global _entity_dict, _alias_map
    if _entity_dict is not None and _alias_map is not None:
        return _entity_dict, _alias_map

    with open(DICT_PATH, encoding="utf-8") as f:
        _entity_dict = yaml.safe_load(f) or {}

    _alias_map = {}
    for ticker, info in _entity_dict.items():
        # Map canonical name
        canonical = info.get("canonical_name", "")
        if canonical:
            _alias_map[canonical.lower()] = ticker

        # Map all aliases
        for alias in info.get("aliases", []):
            _alias_map[alias.lower()] = ticker

        # Map all tickers
        for t in info.get("tickers", []):
            _alias_map[str(t).lower()] = ticker
            _alias_map[f"${str(t).lower()}"] = ticker  # $TICKER format

        # Map key products → ticker (useful for supply chain)
        for product in info.get("key_products", []):
            if len(product) > 3:  # Avoid short acronym collisions
                _alias_map[product.lower()] = ticker

    return _entity_dict, _alias_map


def resolve_entity(text: str) -> Optional[dict]:
    """Layer 1: Try to resolve text to a known entity via dictionary.

    Args:
        text: Company name, ticker, alias, or product name

    Returns:
        Dict with {ticker, canonical_name, confidence, needs_review} or None
    """
    entity_dict, alias_map = _load_dictionary()
    text_lower = text.strip().lower()

    # Direct match
    if text_lower in alias_map:
        ticker = alias_map[text_lower]
        info = entity_dict[ticker]
        return {
            "ticker": ticker,
            "canonical_name": info["canonical_name"],
            "confidence": 1.0,
            "needs_review": False,
        }

    # Try without leading $
    if text_lower.startswith("$"):
        clean = text_lower[1:]
        if clean in alias_map:
            ticker = alias_map[clean]
            info = entity_dict[ticker]
            return {
                "ticker": ticker,
                "canonical_name": info["canonical_name"],
                "confidence": 1.0,
                "needs_review": False,
            }

    # Try uppercase (common for tickers)
    text_upper = text.strip().upper()
    if text_upper in entity_dict:
        info = entity_dict[text_upper]
        return {
            "ticker": text_upper,
            "canonical_name": info["canonical_name"],
            "confidence": 1.0,
            "needs_review": False,
        }

    return None


def resolve_entity_fuzzy(text: str) -> Optional[dict]:
    """Layer 1.5: Fuzzy match — substring matching for longer company names.

    Only used when exact match fails. Lower confidence.
    """
    entity_dict, alias_map = _load_dictionary()
    text_lower = text.strip().lower()

    if len(text_lower) < 4:
        return None  # Too short for fuzzy matching

    # Check if text is a substring of any alias (or vice versa)
    for alias, ticker in alias_map.items():
        if len(alias) >= 4 and (alias in text_lower or text_lower in alias):
            info = entity_dict[ticker]
            return {
                "ticker": ticker,
                "canonical_name": info["canonical_name"],
                "confidence": 0.7,
                "needs_review": True,  # Fuzzy match → needs human check
            }

    return None


def get_all_tickers() -> list[str]:
    """Return all tickers in the entity dictionary."""
    entity_dict, _ = _load_dictionary()
    return list(entity_dict.keys())


def get_entity_info(ticker: str) -> Optional[dict]:
    """Get full info for a ticker from the dictionary."""
    entity_dict, _ = _load_dictionary()
    return entity_dict.get(ticker.upper())


def reload_dictionary():
    """Force reload of entity dictionary (after edits)."""
    global _entity_dict, _alias_map
    _entity_dict = None
    _alias_map = None
    _load_dictionary()
