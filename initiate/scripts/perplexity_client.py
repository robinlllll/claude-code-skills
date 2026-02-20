"""Perplexity API client for deep web research with citations.

Uses OpenAI-compatible SDK with Perplexity's base_url.
Model: sonar-pro (deep search with source citations).
"""

import asyncio
import time
from typing import Optional

from config import PERPLEXITY_API_KEY, PERPLEXITY_BASE_URL, MODELS


def _get_client():
    """Create Perplexity client (OpenAI-compatible)."""
    from openai import OpenAI

    if not PERPLEXITY_API_KEY:
        raise ValueError("PERPLEXITY_API_KEY not set. Add to ~/Screenshots/.env")
    return OpenAI(api_key=PERPLEXITY_API_KEY, base_url=PERPLEXITY_BASE_URL)


async def search(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Run a single Perplexity search query.

    Returns dict with: content, citations, model, usage, elapsed_s
    """
    client = _get_client()
    model = model or MODELS["perplexity"]

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": query})

    loop = asyncio.get_event_loop()

    def _call():
        t0 = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        elapsed = time.time() - t0
        return response, elapsed

    response, elapsed = await loop.run_in_executor(None, _call)

    # Extract citations if available
    citations = []
    if hasattr(response, "citations") and response.citations:
        citations = response.citations

    return {
        "content": response.choices[0].message.content,
        "citations": citations,
        "model": model,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
        "elapsed_s": round(elapsed, 1),
    }


async def research_topic(
    ticker: str,
    company_name: str,
    topic: str,
    queries: list[str],
    system_prompt: Optional[str] = None,
) -> dict:
    """Run multiple Perplexity queries for a research topic.

    Args:
        ticker: Stock ticker symbol
        company_name: Full company name
        topic: Research topic label (e.g., "industry", "competitive")
        queries: List of search queries
        system_prompt: Optional system prompt for all queries

    Returns dict with: topic, results[], total_tokens, elapsed_s
    """
    default_system = (
        f"You are a CFA-level equity research analyst investigating {company_name} ({ticker}). "
        f"Provide factual, data-driven answers with specific numbers, dates, and sources. "
        f"Cite all claims. If data is unavailable or uncertain, say so explicitly. "
        f"Prioritize data from the last 12 months where available, and always specify "
        f"the date or time period of each data point cited."
    )
    sys_prompt = system_prompt or default_system

    results = []
    total_tokens = 0
    t0 = time.time()

    # Run queries sequentially to respect rate limits
    for query in queries:
        try:
            result = await search(query, system_prompt=sys_prompt)
            results.append(
                {
                    "query": query,
                    "content": result["content"],
                    "citations": result["citations"],
                    "tokens": result["usage"]["completion_tokens"],
                }
            )
            total_tokens += (
                result["usage"]["prompt_tokens"] + result["usage"]["completion_tokens"]
            )
            # Small delay between queries
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(
                {
                    "query": query,
                    "content": f"ERROR: {e}",
                    "citations": [],
                    "tokens": 0,
                }
            )

    return {
        "topic": topic,
        "ticker": ticker,
        "results": results,
        "total_tokens": total_tokens,
        "elapsed_s": round(time.time() - t0, 1),
    }


# ----------- Pre-built query templates for coverage initiation -----------
# Subsection-level queries aligned with the 9-section framework.
# S1-S3 get deep, targeted queries. S5/S7 get 1 broad query each.


def get_industry_queries(ticker: str, company_name: str) -> list[str]:
    """S1: Market & Growth — subsection-level queries (1.1.1–1.2.4). v2: longer, tables, recency."""
    return [
        # 1.1.1 Define the market + 1.1.2 TAM + 1.1.3 SAM
        f"What are {company_name}'s ({ticker}) business segments as of the most recent fiscal year? "
        f"For EACH segment, provide in table format: "
        f"(1) Total addressable market (TAM) in dollars, specifying the source report and year of the estimate. "
        f"(2) Serviceable addressable market (SAM) broken down by geography (North America, Europe, Asia-Pacific, Rest of World) and by end market/application. "
        f"(3) Historical CAGR over the past 5 years and 10 years. "
        f"(4) Projected CAGR over the next 3-5 years from at least two independent sources. "
        f"Include specific market size figures from industry reports (Gartner, IDC, Grand View Research, etc.), "
        f"specifying the report date. If sell-side and buy-side estimates differ, note both perspectives. "
        f"Organize all data in a clear table with columns: Segment | TAM ($) | SAM ($) | 5Y CAGR | 10Y CAGR | Projected CAGR | Source.",

        # 1.1.3 Growth decomposition + 1.1.4 Secular vs Cyclical
        f"Break down the historical market growth in {company_name}'s ({ticker}) industry over the past 10 years "
        f"into three components: (1) penetration/adoption rate growth, (2) volume/unit growth, "
        f"and (3) price/ASP changes. Provide specific numbers and percentage contributions per segment. "
        f"For each component, classify whether it represents a secular trend (structural, long-term) "
        f"or a cyclical driver (tied to economic/business cycles). "
        f"Include data from industry associations, company filings, and market research firms. "
        f"If available, show how these components changed during different macro environments "
        f"(expansion vs recession). Present growth decomposition in a table format by segment and time period.",

        # 1.2.1 Lifecycle + 1.2.2 Cyclicality drivers
        f"For each of {company_name}'s ({ticker}) business segments, identify the current stage of the industry lifecycle "
        f"(emerging, growth, mature, or declining) as of 2025-2026, and explain the key characteristics "
        f"that place it at that stage (revenue growth rate, market penetration, competitive dynamics, innovation pace). "
        f"If the industry is cyclical, analyze WHY the cycle exists using a structured framework: "
        f"(1) Demand-side factors: Is demand discretionary or non-discretionary? Is there a bullwhip effect? "
        f"What is demand elasticity? "
        f"(2) Supply-side factors: What are the fixed costs as a percentage of total costs? How hard is it to exit? "
        f"What is the time lag between the decision to add capacity and that capacity becoming operational? "
        f"Is there input cost volatility? "
        f"Provide historical evidence for these cyclical drivers, citing specific industry data points.",

        # 1.2.3 Downturn performance + 1.2.4 Current cycle position
        f"How did {company_name}'s ({ticker}) industry perform during three major downturns: "
        f"(1) the 2008-2009 Global Financial Crisis, (2) the 2020 COVID-19 shock, "
        f"and (3) the 2022-2023 interest rate hiking cycle? "
        f"For each event, provide in table format: peak-to-trough revenue decline (%), margin compression (bps), "
        f"recovery time to prior peak (months), and any structural changes that persisted after recovery. "
        f"Based on these historical patterns and current leading indicators, "
        f"where is the industry in the current cycle as of early 2026 (expansion, peak, contraction, trough)? "
        f"How do current profit margins (operating margin, gross margin) compare to the 5-year, 10-year, "
        f"and 20-year historical averages? Present margin comparisons in a table. "
        f"What does this margin positioning suggest about the cycle stage and forward earnings risk?",
    ]


def get_competitive_queries(ticker: str, company_name: str) -> list[str]:
    """S2: Competitive Landscape — subsection-level queries (2.1.1–2.3.6). v2: longer, tables, share trends."""
    return [
        # 2.1.1 Key players + market share + 2.1.2 HHI
        f"List ALL major competitors of {company_name} ({ticker}) in each product segment — "
        f"include public companies, private companies, and international players. "
        f"For each competitor, provide in table format: company name, most recent annual revenue (with year), "
        f"estimated market share percentage (with year and source), year-over-year share change, "
        f"and primary geographic focus. "
        f"Calculate or estimate the HHI (Herfindahl-Hirschman Index) for each major segment. "
        f"Is the market concentrated (HHI > 2500), moderately concentrated (1500-2500), or fragmented (< 1500)? "
        f"How has HHI changed over the past 5 years? If sell-side reports provide different market share estimates, "
        f"note the range. Present all data in a comprehensive competitor table.",

        # 2.1.3 Share volatility + 2.1.4 Share trends (delta)
        f"How has market share among {company_name}'s ({ticker}) competitors changed over the past 10-20 years? "
        f"Identify which major players are GAINING share and which are LOSING share. "
        f"For each significant share shift, explain the primary drivers: was it organic growth, M&A, pricing strategy, "
        f"product innovation, geographic expansion, or customer churn? "
        f"Include specific share percentage changes with dates. "
        f"Have any major players entered or exited the market in the past 10 years? If so, what drove the entry/exit? "
        f"Present market share trends in a table showing share by player over 5-year intervals. "
        f"Include both sell-side analyst estimates and company-reported data where available.",

        # 2.2.3 Pricing trends
        f"What are the historical and current pricing trends (Average Selling Prices - ASPs) in {company_name}'s ({ticker}) "
        f"industry by major product line over the past 5-10 years? "
        f"Are prices generally rising, falling, or stable? Provide specific ASP data points with dates. "
        f"What are the key factors driving pricing power in this industry? "
        f"Consider both sell-side analyst perspectives (consensus pricing models) and buy-side investor views "
        f"(pricing as a moat indicator) where available. "
        f"How do {company_name}'s prices compare to key competitors for equivalent products or services? "
        f"Provide specific price comparison examples. "
        f"What is the price elasticity of demand in this market? Present pricing trends in a table format.",

        # 2.3.1-2.3.5 Porter's Five Forces (detailed)
        f"Analyze Porter's Five Forces for {company_name}'s ({ticker}) industry with SPECIFIC and recent evidence "
        f"(prioritize data from the last 12 months where available): "
        f"(1) Threat of new entrants — discuss capital requirements (specify $), regulatory hurdles (name specific regulations), "
        f"brand loyalty barriers, and scale barriers. Name any successful or unsuccessful new entrants in the past 5 years. "
        f"(2) Supplier power — analyze supplier concentration, switching costs for input procurement, "
        f"and threat of forward integration. Name key suppliers and their bargaining leverage. "
        f"(3) Buyer power — analyze buyer concentration, switching costs for customers, "
        f"and price sensitivity. Identify the top customer concentration percentage. "
        f"(4) Threat of substitutes — what alternative products, services, or technologies could replace offerings? "
        f"What is their current market penetration and growth rate? "
        f"(5) Rivalry intensity — what is the industry growth rate? How differentiated are products? "
        f"What are exit barriers? For each force, provide a rating (HIGH/MEDIUM/LOW) with specific justification.",

        # 2.3.6 Revenue/profit map
        f"Map the complete value chain for {company_name}'s ({ticker}) industry from raw materials/inputs "
        f"to end consumer/user. Identify the key stages and major players at each stage. "
        f"For each value chain stage, estimate: (1) the revenue share as a percentage of total industry value, "
        f"and (2) the profit share (operating profit) as a percentage of total industry profit. "
        f"Which players in the value chain capture the most economic value, and why? "
        f"Has this profit distribution shifted in the past 5-10 years? If so, what drove the shift? "
        f"Present the value chain analysis in a table: Stage | Key Players | Revenue Share % | Profit Share % | Trend.",
    ]


def get_moat_queries(ticker: str, company_name: str) -> list[str]:
    """S3: Barriers & Moat — subsection-level queries (3.1–3.5). v2: historical moat trends, threats."""
    return [
        # 3.1 Unique assets (patents, brand, licensing, raw materials) + historical trends
        f"What are {company_name}'s ({ticker}) unique assets and how has their strength evolved over the past 5-10 years? "
        f"Cover four categories: "
        f"(1) Patents and proprietary technology — how many active patents, how interconnected are they, "
        f"how do they compare vs key competitors in patent count and quality? "
        f"How has the patent portfolio changed over the past 5 years (growing, stable, declining)? "
        f"When do key patents expire? "
        f"(2) Brand strength — is the brand utility-based (functional) or story/legacy-based (aspirational)? "
        f"What is the gross margin premium versus direct competitors (most recent data with year)? "
        f"Has this premium expanded or contracted over the past 5 years? Provide specific margin data. "
        f"(3) Licenses and permits — what specific regulatory approvals are required for operation? "
        f"Have regulatory requirements become more or less stringent over time? "
        f"(4) Access to raw materials or favorable locations — are these advantages persistent or being competed away? "
        f"For each asset category, name specific threats to its durability.",

        # 3.2 Switching costs + 3.3 Network effects + historical evolution
        f"Analyze switching costs and network effects for {company_name}'s ({ticker}) customers: "
        f"SWITCHING COSTS: How deeply embedded are its products in customer operations or workflows? "
        f"What is the estimated total cost (financial + time + effort + risk) for a typical customer to switch "
        f"to a competitor, relative to the annual contract value or product price? "
        f"Provide customer retention rates, annual churn rates, and Net Promoter Score (NPS) if available "
        f"(most recent data, specifying year). How have these metrics trended over the past 5 years? "
        f"Are switching costs increasing or decreasing as the industry evolves? "
        f"NETWORK EFFECTS: Does {company_name} benefit from network effects (direct, two-sided, data, platform)? "
        f"If so, describe the mechanism. Is the network open or closed? Can customers be multi-tenant/multi-platform? "
        f"Has the network effect strengthened or weakened over the past 5 years? "
        f"Present retention/churn metrics in a table where available.",

        # 3.4 Economies of scale + historical development
        f"Does {company_name} ({ticker}) have economies of scale, and how have they evolved? "
        f"(1) Supply-side scale: What are the manufacturing or operational cost advantages at volume? "
        f"Provide specific unit cost comparisons vs smaller competitors if available. "
        f"How has the cost advantage changed over the past 10 years as the company has grown? "
        f"(2) Demand-side scale: Do more customers make the product or service better for others? "
        f"(3) Distribution/logistics scale: Are there logistics cost advantages from greater density or volume? "
        f"What is the estimated efficient scale in this industry (revenue or market share threshold needed to compete effectively), "
        f"and how many companies currently operate at or above efficient scale? "
        f"Is industry growth fast enough for new entrants to reach efficient scale within 5-10 years? "
        f"How has the company's operating margin and SGA-as-percentage-of-revenue trended over the past 10 years "
        f"compared to competitors? Present scale metrics in a table format.",
    ]


def get_management_queries(ticker: str, company_name: str) -> list[str]:
    """S5: Management & Governance. v2: deeper comp structure, insider ownership."""
    return [
        f"Who is {company_name}'s ({ticker}) current management team (CEO, CFO, key executives)? "
        f"For each, provide: professional background, relevant industry experience, start date in current role, "
        f"and notable prior positions. "
        f"How is executive compensation structured for the most recent fiscal year? "
        f"Break down: base salary, annual cash bonus target (and actual payout vs target), "
        f"equity awards (type, vesting schedule), and performance metrics used. "
        f"Is compensation aligned with long-term shareholder interests? "
        f"Cite evidence: What are the specific performance targets? Is there meaningful insider ownership? "
        f"Have there been any recent management changes, board disputes, or governance concerns?",
    ]


def get_risk_queries(ticker: str, company_name: str) -> list[str]:
    """S7: Risks. v2: 6 categories, impact/probability, historical precedents with stock impact."""
    return [
        f"What are the major risks facing {company_name} ({ticker}) as of 2025-2026? "
        f"Cover six categories: (1) Industry cycle risks — where are we in the cycle and what's the downside? "
        f"(2) Regulatory risks — pending or potential regulation that could impact the business model. "
        f"(3) Operational risks — supply chain, key person, execution risks. "
        f"(4) Financial risks — debt levels, liquidity, covenant compliance, refinancing timeline. "
        f"(5) Technology disruption risks — emerging technologies that could disrupt the business. "
        f"(6) Strategic risks — competitive landscape shifts, M&A integration, market entry failures. "
        f"For each major risk, provide: brief description, potential financial impact (revenue/margin/earnings), "
        f"estimated probability (high/medium/low), and a historical precedent — name a specific company "
        f"that faced this exact risk, the date, what happened, and the stock price impact. "
        f"Present risks in a table: Risk | Category | Impact | Probability | Historical Precedent.",
    ]


def get_catalyst_queries(ticker: str, company_name: str) -> list[str]:
    """Recent catalysts, news, and events — enriches S1-S3 with current context. v2: table format, impact ratings."""
    return [
        f"What are the most important recent developments for {company_name} ({ticker}) "
        f"in the past 6 months (through early 2026)? Include: "
        f"earnings surprises and their magnitude (actual vs consensus EPS), guidance changes (direction and magnitude), "
        f"M&A activity (target, deal value, strategic rationale), major product launches, "
        f"significant management changes, regulatory actions or decisions, "
        f"major contract wins or losses (value if disclosed), "
        f"and notable analyst upgrades/downgrades (firm, old/new rating, price target change). "
        f"For each development, provide the precise date and source. "
        f"Present all developments in a table: Date | Event | Details | Impact/Significance.",

        f"What are the upcoming catalysts and key events for {company_name} ({ticker}) "
        f"over the next 12 months (through early 2027)? Include: "
        f"confirmed earnings dates, anticipated product launches or refreshes, "
        f"pending regulatory decisions (specify agency and expected timeline), "
        f"significant contract renewals (value if known), capacity expansions (location, timeline, capex), "
        f"and any material pending litigation or legal outcomes. "
        f"For each event, specify the expected date or timeframe and assess potential impact. "
        f"Which of these events could materially change the investment thesis — either positively or negatively — "
        f"and why? Rate each catalyst's potential impact (HIGH/MEDIUM/LOW). "
        f"Present in table: Date/Period | Event | Impact Rating | Bull Case | Bear Case.",
    ]
