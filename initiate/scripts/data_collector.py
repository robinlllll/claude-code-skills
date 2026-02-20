"""Phase 1: Data Collection Orchestrator with caching.

Runs 4 parallel data collection agents:
1. Perplexity — industry, competitive, management, risk web research
2. SEC EDGAR — financial history (XBRL), filing list, company info
3. yfinance — price, multiples, margins, analysts, insiders, institutions
4. Local knowledge — vault search, 13F data, transcripts

Outputs: data_pack.json (cached by ticker+date, TTL 7 days)

Usage:
    python data_collector.py TICKER [--refresh]
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Script dir on sys.path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from config import RUNS_DIR, CACHE_TTL_DAYS, SHARED_DIR, VAULT_PATH, preflight_check


def get_cache_path(ticker: str) -> Path:
    """Get cache file path for a ticker's data pack."""
    cache_dir = RUNS_DIR / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{ticker.upper()}_data_pack.json"


def load_cached(ticker: str) -> dict | None:
    """Load cached data pack if still valid (within TTL)."""
    cache_path = get_cache_path(ticker)
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cached_at = data.get("_meta", {}).get("cached_at", "")
        if not cached_at:
            return None

        cached_dt = datetime.fromisoformat(cached_at)
        if datetime.now() - cached_dt > timedelta(days=CACHE_TTL_DAYS):
            print(f"  Cache expired ({CACHE_TTL_DAYS}d TTL)")
            return None

        print(f"  Cache hit: {cache_path.name} (from {cached_at[:10]})")
        return data
    except Exception:
        return None


def save_cache(ticker: str, data: dict):
    """Save data pack to cache."""
    data["_meta"] = {
        "cached_at": datetime.now().isoformat(),
        "ticker": ticker.upper(),
        "ttl_days": CACHE_TTL_DAYS,
    }
    cache_path = get_cache_path(ticker)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Cached: {cache_path.name}")


async def collect_perplexity(ticker: str, company_name: str) -> dict:
    """Collect deep web research via Perplexity — subsection-level queries for S1-S3.

    All 5 topic groups run in PARALLEL for maximum speed.
    Within each topic, queries still run sequentially (Perplexity rate limits).
    """
    from perplexity_client import (
        research_topic,
        get_industry_queries,
        get_competitive_queries,
        get_moat_queries,
        get_management_queries,
        get_risk_queries,
        get_catalyst_queries,
    )

    print("  [Perplexity] Starting deep web research (5 topics in parallel)...")
    t0 = time.time()

    # Run ALL 5 topic groups in parallel
    industry, competitive, moat, management, risks, catalysts = await asyncio.gather(
        research_topic(
            ticker, company_name, "industry",
            get_industry_queries(ticker, company_name),
        ),
        research_topic(
            ticker, company_name, "competitive",
            get_competitive_queries(ticker, company_name),
        ),
        research_topic(
            ticker, company_name, "moat",
            get_moat_queries(ticker, company_name),
        ),
        research_topic(
            ticker, company_name, "management",
            get_management_queries(ticker, company_name),
        ),
        research_topic(
            ticker, company_name, "risks",
            get_risk_queries(ticker, company_name),
        ),
        research_topic(
            ticker, company_name, "catalysts",
            get_catalyst_queries(ticker, company_name),
        ),
        return_exceptions=True,
    )

    # Handle failures gracefully
    all_topics_raw = [
        ("industry", industry),
        ("competitive", competitive),
        ("moat", moat),
        ("management", management),
        ("risks", risks),
        ("catalysts", catalysts),
    ]
    result = {"source": "perplexity"}
    all_topics = []
    for name, topic in all_topics_raw:
        if isinstance(topic, BaseException):
            print(f"    {name} FAILED: {topic}")
            result[name] = {"topic": name, "results": [], "total_tokens": 0, "elapsed_s": 0}
        else:
            result[name] = topic
            all_topics.append(topic)
            print(f"    {name}: {topic['total_tokens']} tokens, {topic['elapsed_s']}s")

    total_tokens = sum(t["total_tokens"] for t in all_topics)
    elapsed = round(time.time() - t0, 1)
    n_queries = sum(len(t["results"]) for t in all_topics)
    print(f"  [Perplexity] Done: {n_queries} queries, {total_tokens} tokens, {elapsed}s (parallel)")

    result["total_tokens"] = total_tokens
    result["elapsed_s"] = elapsed
    return result


async def collect_sec_edgar(ticker: str) -> dict:
    """Collect SEC EDGAR data: company info, financial history, filings."""
    from sec_edgar import fetch_sec_data

    print("  [SEC EDGAR] Starting XBRL + filings fetch...")
    t0 = time.time()

    result = await fetch_sec_data(ticker)
    elapsed = round(time.time() - t0, 1)

    # Count data quality
    fin_hist = result.get("financial_history", {})
    revenue_years = len(fin_hist.get("revenue", []))
    filings_count = len(result.get("filings", []))

    print(f"  [SEC EDGAR] Done: {revenue_years}yr revenue history, {filings_count} filings, {elapsed}s")
    result["elapsed_s"] = elapsed
    return result


async def collect_yfinance(ticker: str) -> dict:
    """Collect yfinance data: price, multiples, financials, analysts, insiders."""
    from financial_data import fetch_yfinance_data

    print("  [yfinance] Starting market data fetch...")
    t0 = time.time()

    result = await fetch_yfinance_data(ticker)
    elapsed = round(time.time() - t0, 1)

    company_name = result.get("company", {}).get("name", ticker)
    market_cap = result.get("price", {}).get("market_cap")
    cap_str = f"${market_cap/1e9:.1f}B" if market_cap else "N/A"

    print(f"  [yfinance] Done: {company_name}, MCap {cap_str}, {elapsed}s")
    result["elapsed_s"] = elapsed
    return result


async def collect_local_knowledge(ticker: str) -> dict:
    """Collect local vault data: thesis, transcripts, 13F, supply chain."""
    loop = asyncio.get_event_loop()

    def _collect():
        result = {
            "source": "local_vault",
            "thesis": None,
            "transcripts": [],
            "research_notes": [],
            "thirteen_f": [],
        }

        # Check thesis
        thesis_path = (
            Path.home() / "PORTFOLIO" / "portfolio_monitor" / "research"
            / "companies" / ticker.upper() / "thesis.md"
        )
        if thesis_path.exists():
            try:
                content = thesis_path.read_text(encoding="utf-8")
                # Truncate to first 3000 chars for context
                result["thesis"] = content[:3000]
                print(f"  [Local] Found thesis.md ({len(content)} chars)")
            except Exception:
                pass

        # Check earnings analyses
        earnings_dir = VAULT_PATH / "研究" / "财报分析" / f"{ticker.upper()}-US"
        if earnings_dir.exists():
            for f in sorted(earnings_dir.glob("*.md"), reverse=True)[:3]:
                try:
                    content = f.read_text(encoding="utf-8")
                    result["transcripts"].append({
                        "file": f.name,
                        "excerpt": content[:2000],
                    })
                except Exception:
                    pass
            if result["transcripts"]:
                print(f"  [Local] Found {len(result['transcripts'])} earnings analyses")

        # Check research notes
        research_dir = VAULT_PATH / "研究" / "研究笔记"
        if research_dir.exists():
            for f in research_dir.glob(f"{ticker.upper()}*.md"):
                try:
                    content = f.read_text(encoding="utf-8")
                    result["research_notes"].append({
                        "file": f.name,
                        "excerpt": content[:1500],
                    })
                except Exception:
                    pass

        # Check 13F data
        thirteenf_dir = Path.home() / "13F-CLAUDE" / "output"
        if thirteenf_dir.exists():
            import csv
            for manager_dir in thirteenf_dir.iterdir():
                if not manager_dir.is_dir():
                    continue
                for quarter_dir in sorted(manager_dir.iterdir(), reverse=True)[:2]:
                    for csv_file in quarter_dir.glob("*.csv"):
                        try:
                            with open(csv_file, "r", encoding="utf-8") as cf:
                                reader = csv.DictReader(cf)
                                for row in reader:
                                    row_ticker = (
                                        row.get("ticker", "") or
                                        row.get("Ticker", "") or
                                        row.get("TICKER", "")
                                    )
                                    if row_ticker.upper() == ticker.upper():
                                        result["thirteen_f"].append({
                                            "manager": manager_dir.name,
                                            "quarter": quarter_dir.name,
                                            "data": dict(row),
                                        })
                        except Exception:
                            pass

        if result["thirteen_f"]:
            print(f"  [Local] Found {len(result['thirteen_f'])} 13F holdings")

        return result

    print("  [Local] Searching vault...")
    t0 = time.time()
    result = await loop.run_in_executor(None, _collect)
    result["elapsed_s"] = round(time.time() - t0, 1)
    print(f"  [Local] Done: {result['elapsed_s']}s")
    return result


async def collect_all(ticker: str, refresh: bool = False) -> dict:
    """Run all 4 data collection agents in parallel.

    Args:
        ticker: Stock ticker
        refresh: If True, ignore cache and re-fetch

    Returns: Complete data_pack dict with all sources
    """
    # Check cache first
    if not refresh:
        cached = load_cached(ticker)
        if cached:
            return cached

    # Preflight
    keys = preflight_check()
    print(f"\n  API Keys: Perplexity={'OK' if keys['perplexity'] else 'MISSING'}, "
          f"OpenAI={'OK' if keys['openai'] else 'MISSING'}, "
          f"Gemini={'OK' if keys['gemini'] else 'MISSING'}")

    if not keys["perplexity"]:
        print("  WARNING: Perplexity key missing. Web research will be skipped.")

    # Get company name from yfinance first (quick call)
    print(f"\n{'='*60}")
    print(f"  Phase 1: Data Collection for {ticker.upper()}")
    print(f"{'='*60}\n")

    t0 = time.time()

    # Step 1: Quick yfinance call to get company name
    from financial_data import fetch_yfinance_data
    yf_data = await fetch_yfinance_data(ticker)
    company_name = yf_data.get("company", {}).get("name", ticker.upper())
    print(f"  Company: {company_name}\n")

    # Step 2: Run remaining collectors in parallel
    async def _skip_perplexity():
        return {"source": "perplexity", "skipped": True}

    perplexity_coro = (
        collect_perplexity(ticker, company_name)
        if keys["perplexity"]
        else _skip_perplexity()
    )

    sec_result, perplexity_result, local_result = await asyncio.gather(
        collect_sec_edgar(ticker),
        perplexity_coro,
        collect_local_knowledge(ticker),
        return_exceptions=True,
    )

    # Handle failures gracefully
    data_pack = {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "collected_at": datetime.now().isoformat(),
        "yfinance": yf_data,
    }

    if isinstance(sec_result, BaseException):
        print(f"  SEC EDGAR FAILED: {sec_result}")
        data_pack["sec_edgar"] = {"error": str(sec_result)}
    else:
        data_pack["sec_edgar"] = sec_result

    if isinstance(perplexity_result, BaseException):
        print(f"  Perplexity FAILED: {perplexity_result}")
        data_pack["perplexity"] = {"error": str(perplexity_result)}
    else:
        data_pack["perplexity"] = perplexity_result

    if isinstance(local_result, BaseException):
        print(f"  Local knowledge FAILED: {local_result}")
        data_pack["local"] = {"error": str(local_result)}
    else:
        data_pack["local"] = local_result

    total_elapsed = round(time.time() - t0, 1)

    # Summary
    print(f"\n{'='*60}")
    print(f"  Phase 1 Complete: {total_elapsed}s total")
    print(f"  Sources: yfinance={'OK'}, "
          f"SEC={'OK' if 'error' not in data_pack.get('sec_edgar', {}) else 'FAIL'}, "
          f"Perplexity={'OK' if 'error' not in data_pack.get('perplexity', {}) else 'FAIL/SKIP'}, "
          f"Local={'OK' if 'error' not in data_pack.get('local', {}) else 'FAIL'}")
    print(f"{'='*60}\n")

    # Cache the result
    save_cache(ticker, data_pack)

    return data_pack


# ============ CLI entry point ============

async def main():
    """CLI entry point for standalone data collection."""
    import argparse

    parser = argparse.ArgumentParser(description="Coverage Initiation — Phase 1: Data Collection")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache, re-fetch all data")
    parser.add_argument("--summary", action="store_true", help="Print data summary after collection")
    args = parser.parse_args()

    data_pack = await collect_all(args.ticker.upper(), refresh=args.refresh)

    if args.summary:
        print_summary(data_pack)

    # Save to workspace
    workspace = RUNS_DIR / f"{args.ticker.upper()}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    workspace.mkdir(parents=True, exist_ok=True)
    output_path = workspace / "data_pack.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data_pack, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {output_path}")


def print_summary(data_pack: dict):
    """Print a human-readable summary of the data pack."""
    ticker = data_pack.get("ticker", "???")
    company = data_pack.get("company_name", "???")

    print(f"\n{'='*60}")
    print(f"  DATA PACK SUMMARY: {company} ({ticker})")
    print(f"{'='*60}")

    # yfinance
    yf = data_pack.get("yfinance", {})
    price = yf.get("price", {})
    val = yf.get("valuation", {})
    print(f"\n  PRICE: ${price.get('current', 'N/A')} | "
          f"MCap: ${(price.get('market_cap') or 0)/1e9:.1f}B | "
          f"52W: ${price.get('52w_low', 'N/A')}-${price.get('52w_high', 'N/A')}")
    print(f"  VALUATION: P/E {val.get('pe_trailing', 'N/A')} | "
          f"EV/EBITDA {val.get('ev_ebitda', 'N/A')} | "
          f"PEG {val.get('peg', 'N/A')}")

    # SEC
    sec = data_pack.get("sec_edgar", {})
    if "error" not in sec:
        fin = sec.get("financial_history", {})
        rev = fin.get("revenue", [])
        if rev:
            latest_rev = rev[0].get("value", 0)
            print(f"  SEC: {len(rev)}yr revenue history | Latest: ${latest_rev/1e9:.2f}B")
        filings = sec.get("filings", [])
        print(f"  FILINGS: {len(filings)} recent ({', '.join(f['form'] for f in filings[:5])})")

    # Perplexity
    pplx = data_pack.get("perplexity", {})
    if "error" not in pplx and not pplx.get("skipped"):
        total_tokens = pplx.get("total_tokens", 0)
        topics = [k for k in ["industry", "competitive", "management", "risks"] if k in pplx]
        print(f"  PERPLEXITY: {len(topics)} topics, {total_tokens} tokens")

    # Local
    local = data_pack.get("local", {})
    if "error" not in local:
        has_thesis = "YES" if local.get("thesis") else "no"
        n_transcripts = len(local.get("transcripts", []))
        n_13f = len(local.get("thirteen_f", []))
        print(f"  LOCAL: thesis={has_thesis}, earnings={n_transcripts}, 13F={n_13f}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
