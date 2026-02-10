"""Detect ticker symbols and company names in text.

Uses entity_dictionary.yaml for precise matching.
Falls back to $TICKER regex pattern for unknown tickers.
"""

import re

from .entity_resolver import resolve_entity, _load_dictionary

# Match $TICKER patterns (1-5 uppercase letters after $)
DOLLAR_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Match standalone uppercase tickers (more aggressive, higher false positive rate)
BARE_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")

# Common English words that look like tickers — exclude these
TICKER_BLACKLIST = {
    "CEO",
    "CFO",
    "COO",
    "CTO",
    "CMO",
    "CIO",
    "IPO",
    "ETF",
    "SEC",
    "FDA",
    "FTC",
    "DOJ",
    "EPA",
    "DOD",
    "GDP",
    "CPI",
    "PPI",
    "PCE",
    "PMI",
    "ISM",
    "EPS",
    "PE",
    "PB",
    "ROE",
    "ROA",
    "ROI",
    "EBITDA",
    "EBIT",
    "USA",
    "NYC",
    "UK",
    "EU",
    "HK",
    "US",
    "AI",
    "ML",
    "NLP",
    "LLM",
    "API",
    "SDK",
    "CLI",
    "YOY",
    "QOQ",
    "MOM",
    "TTM",
    "FY",
    "YTD",
    "BPS",
    "PPT",
    "USD",
    "HKD",
    "CNY",
    "EUR",
    "GBP",
    "JPY",
    "THE",
    "AND",
    "FOR",
    "ARE",
    "NOT",
    "BUT",
    "ALL",
    "CAN",
    "HAS",
    "HER",
    "WAS",
    "ONE",
    "OUR",
    "OUT",
    "DAY",
    "HAD",
    "NEW",
    "NOW",
    "OLD",
    "SEE",
    "WAY",
    "WHO",
    "DID",
    "GET",
    "HAS",
    "HIM",
    "HIS",
    "HOW",
    "ITS",
    "MAY",
    "SAY",
    "SHE",
    "TWO",
    "USE",
    "HER",
    "MAR",
    "JUN",
    "SEP",
    "DEC",
    "JAN",
    "FEB",
    "APR",
    "MAY",
    "JUL",
    "AUG",
    "OCT",
    "NOV",
    "AM",
    "PM",
    "IT",
    "IN",
    "ON",
    "AT",
    "TO",
    "UP",
    "SO",
    "VS",
    "EG",
    "IE",
    "RE",
    "OR",
    "AN",
    "AS",
    "BY",
    "IF",
    "OF",
    "OK",
    "GO",
    "DO",
    "NO",
    "EM",
    "MR",
    "MS",
    "DR",
    "EST",
    "PST",
    "CST",
    "MST",
    "GMT",
    "UTC",
    "P&L",
    "M&A",
    "R&D",
    "S&P",
    "Q&A",
    "CEO",
    "CTO",
    "CFO",
    "COO",
    "TAM",
    "SAM",
    "SOM",
}


# Match ticker in document titles/headers: (AOS), (AOS US), (AOS-US), (NVDA HK)
# Group 1 = ticker, Group 2 = country code (if present)
TITLE_TICKER_RE = re.compile(
    r"\(([A-Z]{1,6})(?:[\s\-]+(US|HK|CN|TW|JP|KR|IN|LN|GR|FP))?\s*\)"
)

# Match Reuters instrument codes in filenames: SITM.OQ, EFX.N, 7974.T, GOOGL.OQ
# Group 1 = ticker (letters or digits), Group 2 = exchange suffix
REUTERS_TICKER_RE = re.compile(
    r"\b([A-Z0-9]{1,6})\.(OQ|N|O|OB|T|HK|SS|SZ|L|PA|DE|TO|AX|SI|KS|BO|NS)\b"
)


def detect_primary_ticker(title: str, text_header: str = "") -> str | None:
    """Extract the primary subject ticker from a document title or header.

    Strategy order (highest confidence first):
    1. Parenthetical ticker in title: "(AOS-US)" or "(NVDA)"
    2. Parenthetical ticker in text_header first line
    3. Known ticker/alias in title via entity dictionary
    4. Bare known ticker in title (uppercase word matching entity_dict)

    Args:
        title: Document title or filename
        text_header: First ~1000 chars of document text

    Returns:
        Primary ticker string or None
    """
    entity_dict, alias_map = _load_dictionary()

    # Strategy 0: Reuters instrument code in title (e.g., SITM.OQ, 7974.T)
    if title:
        for match in REUTERS_TICKER_RE.finditer(title):
            raw_ticker = match.group(1)
            # Try exact match in entity dict (handles "7974" style tickers)
            if raw_ticker in entity_dict:
                return raw_ticker
            # Try uppercase
            if raw_ticker.upper() in entity_dict:
                return raw_ticker.upper()
            # Try resolving via alias map (e.g., "7974.T" → 7974 entry)
            full_code = f"{raw_ticker}.{match.group(2)}"
            resolved = resolve_entity(full_code)
            if resolved:
                return resolved["ticker"]
            resolved = resolve_entity(raw_ticker)
            if resolved:
                return resolved["ticker"]
            # If it looks like a valid ticker (all alpha, 2-5 chars), return it
            if (
                raw_ticker.isalpha()
                and 2 <= len(raw_ticker) <= 5
                and raw_ticker not in TICKER_BLACKLIST
            ):
                return raw_ticker.upper()

    # Strategy 1: Parenthetical ticker in title (highest confidence)
    if title:
        for match in TITLE_TICKER_RE.finditer(title):
            ticker = match.group(1).upper()
            has_country_code = match.group(2) is not None
            if len(ticker) < 2:
                continue
            if not has_country_code and ticker in TICKER_BLACKLIST:
                continue
            return ticker

    # Strategy 2: Parenthetical ticker in first line of text_header only
    # (not full header — avoids picking up a mentioned company instead of subject)
    if text_header:
        first_line = text_header.split("\n")[0]
        for match in TITLE_TICKER_RE.finditer(first_line):
            ticker = match.group(1).upper()
            has_country_code = match.group(2) is not None
            if len(ticker) < 2:
                continue
            if not has_country_code and ticker in TICKER_BLACKLIST:
                continue
            return ticker

    # Strategy 3: Match known aliases in title via entity dictionary
    if title:
        title_lower = title.lower()
        # Sort aliases longest-first to prefer "A.O. Smith" over "Smith"
        for alias in sorted(alias_map.keys(), key=len, reverse=True):
            if len(alias) < 4:
                continue
            # Skip raw ticker symbols — handled by Strategy 4
            if alias.upper() in entity_dict or alias.startswith("$"):
                continue
            if alias in title_lower:
                return alias_map[alias]

    # Strategy 4: Bare known ticker in title (e.g., "AOS Q3 2025 Earnings")
    if title:
        for word in re.findall(r"\b([A-Z]{2,6})\b", title):
            if word in TICKER_BLACKLIST:
                continue
            if word in entity_dict:
                return word

    return None


def detect_tickers(text: str, use_dollar_only: bool = False) -> list[dict]:
    """Detect ticker symbols in text using entity dictionary + regex.

    Args:
        text: Input text to scan
        use_dollar_only: If True, only match $TICKER patterns (fewer false positives)

    Returns:
        List of {ticker, canonical_name, source, confidence} dicts, deduplicated
    """
    found = {}  # ticker → info dict (dedup by ticker)
    entity_dict, alias_map = _load_dictionary()

    # Strategy 1: $TICKER patterns (highest confidence)
    for match in DOLLAR_TICKER_RE.finditer(text):
        ticker = match.group(1)
        if ticker in TICKER_BLACKLIST:
            continue
        resolved = resolve_entity(ticker)
        if resolved:
            found[resolved["ticker"]] = {
                "ticker": resolved["ticker"],
                "canonical_name": resolved["canonical_name"],
                "source": "dollar_pattern",
                "confidence": 1.0,
            }
        else:
            # Unknown ticker but has $ prefix — likely valid
            found[ticker] = {
                "ticker": ticker,
                "canonical_name": ticker,
                "source": "dollar_pattern_unknown",
                "confidence": 0.8,
            }

    # Strategy 2: Dictionary alias scan (match known company names/products in text)
    text_lower = text.lower()
    # Build set of raw ticker symbol forms to skip — these are common-word
    # false positives (e.g., "cost"→COST, "meta"→META) and are already
    # handled by Strategy 1 ($TICKER) and Strategy 3 (bare uppercase)
    ticker_symbol_forms = set()
    for tk in entity_dict:
        ticker_symbol_forms.add(tk.lower())
        for t in entity_dict[tk].get("tickers", []):
            ticker_symbol_forms.add(str(t).lower())
            ticker_symbol_forms.add(f"${str(t).lower()}")
    for alias, ticker in alias_map.items():
        if len(alias) < 4:
            continue  # Skip short aliases to avoid false positives
        if ticker in found:
            continue  # Already found via better method
        if alias in ticker_symbol_forms:
            continue  # Skip raw ticker symbols (handled by Strategy 1 & 3)
        # For short aliases (<8 chars), use word-boundary matching to prevent
        # substring false positives (e.g., "intel" in "intellectual")
        if len(alias) < 8:
            if not re.search(r"\b" + re.escape(alias) + r"\b", text_lower):
                continue
        else:
            if alias not in text_lower:
                continue
        info = entity_dict.get(ticker, {})
        found[ticker] = {
            "ticker": ticker,
            "canonical_name": info.get("canonical_name", ticker),
            "source": "dictionary_alias",
            "confidence": 0.95,
        }

    # Strategy 3: Bare ticker patterns (only if not dollar_only mode)
    if not use_dollar_only:
        for match in BARE_TICKER_RE.finditer(text):
            ticker = match.group(1)
            if ticker in TICKER_BLACKLIST:
                continue
            if ticker in found:
                continue  # Already found via better method
            # Only accept if it's a known ticker in our dictionary
            if ticker in entity_dict:
                info = entity_dict[ticker]
                found[ticker] = {
                    "ticker": ticker,
                    "canonical_name": info["canonical_name"],
                    "source": "bare_ticker_known",
                    "confidence": 0.85,
                }

    return sorted(found.values(), key=lambda x: x["confidence"], reverse=True)


def detect_ticker_symbols(text: str) -> list[str]:
    """Simple version: return just ticker symbols found in text."""
    results = detect_tickers(text)
    return [r["ticker"] for r in results]


def add_wikilinks(text: str) -> str:
    """Add [[wikilinks]] for known tickers/company names in text.

    Only links the first occurrence of each entity.
    """
    linked = set()
    entity_dict, alias_map = _load_dictionary()

    # Sort aliases by length (longest first) to avoid partial replacements
    sorted_aliases = sorted(alias_map.keys(), key=len, reverse=True)

    for alias in sorted_aliases:
        if len(alias) < 4:
            continue
        ticker = alias_map[alias]
        if ticker in linked:
            continue

        # Case-insensitive search for first occurrence
        pattern = re.compile(re.escape(alias), re.IGNORECASE)
        match = pattern.search(text)
        if match:
            original = match.group(0)
            text = text[: match.start()] + f"[[{original}]]" + text[match.end() :]
            linked.add(ticker)

    return text
