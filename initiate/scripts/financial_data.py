"""Financial data collector using yfinance.

Fetches: price, valuation multiples, margins, analyst estimates,
insider transactions, institutional ownership, historical prices,
peer comparison data.
"""

import asyncio


async def fetch_yfinance_data(ticker: str) -> dict:
    """Fetch comprehensive financial data from yfinance.

    Returns dict with sections:
    - price: current price, 52-week range, market cap
    - valuation: P/E, PEG, EV/EBITDA, P/B, P/S, P/FCF
    - margins: gross, operating, net, EBITDA
    - growth: revenue growth, earnings growth
    - analysts: target prices, recommendations, rating distribution
    - insiders: recent insider transactions
    - institutions: top institutional holders
    - history: 10-year annual price data for drawdown analysis
    - financials: income statement, balance sheet, cash flow (annual)
    - peers: list of peer tickers for comparison
    """
    loop = asyncio.get_event_loop()

    def _fetch():
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info or {}
        result = {"ticker": ticker, "source": "yfinance"}

        # --- Price & Market Data ---
        result["price"] = {
            "current": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "avg_volume": info.get("averageVolume"),
            "beta": info.get("beta"),
            "currency": info.get("currency", "USD"),
        }

        # --- Company Info ---
        result["company"] = {
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "description": info.get("longBusinessSummary", "")[:1000],
            "employees": info.get("fullTimeEmployees"),
            "website": info.get("website"),
            "country": info.get("country"),
        }

        # --- Valuation Multiples ---
        result["valuation"] = {
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "peg": info.get("pegRatio"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "ev_revenue": info.get("enterpriseToRevenue"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
        }

        # --- Margins & Profitability ---
        result["margins"] = {
            "gross": info.get("grossMargins"),
            "operating": info.get("operatingMargins"),
            "net": info.get("profitMargins"),
            "ebitda": info.get("ebitdaMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
        }

        # --- Growth ---
        result["growth"] = {
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "earnings_quarterly_growth": info.get("earningsQuarterlyGrowth"),
        }

        # --- Analyst Estimates ---
        result["analysts"] = {
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "target_median": info.get("targetMedianPrice"),
            "recommendation": info.get("recommendationKey"),
            "recommendation_mean": info.get("recommendationMean"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
        }

        # --- Dividends ---
        result["dividends"] = {
            "yield": info.get("dividendYield"),
            "rate": info.get("dividendRate"),
            "payout_ratio": info.get("payoutRatio"),
        }

        # --- Financial Statements (Annual) ---
        try:
            inc = stock.financials
            if inc is not None and not inc.empty:
                result["income_statement"] = {}
                for col in inc.columns[:5]:  # Last 5 years
                    year = str(col.year) if hasattr(col, "year") else str(col)[:4]
                    result["income_statement"][year] = {
                        row: _safe_num(inc.at[row, col]) for row in inc.index
                    }
        except Exception:
            result["income_statement"] = {}

        try:
            bs = stock.balance_sheet
            if bs is not None and not bs.empty:
                result["balance_sheet"] = {}
                for col in bs.columns[:5]:
                    year = str(col.year) if hasattr(col, "year") else str(col)[:4]
                    result["balance_sheet"][year] = {
                        row: _safe_num(bs.at[row, col]) for row in bs.index
                    }
        except Exception:
            result["balance_sheet"] = {}

        try:
            cf = stock.cashflow
            if cf is not None and not cf.empty:
                result["cash_flow"] = {}
                for col in cf.columns[:5]:
                    year = str(col.year) if hasattr(col, "year") else str(col)[:4]
                    result["cash_flow"][year] = {
                        row: _safe_num(cf.at[row, col]) for row in cf.index
                    }
        except Exception:
            result["cash_flow"] = {}

        # --- Insider Transactions ---
        try:
            insiders = stock.insider_transactions
            if insiders is not None and not insiders.empty:
                result["insider_transactions"] = insiders.head(20).to_dict(
                    orient="records"
                )
            else:
                result["insider_transactions"] = []
        except Exception:
            result["insider_transactions"] = []

        # --- Institutional Holders ---
        try:
            inst = stock.institutional_holders
            if inst is not None and not inst.empty:
                result["institutional_holders"] = inst.head(15).to_dict(
                    orient="records"
                )
            else:
                result["institutional_holders"] = []
        except Exception:
            result["institutional_holders"] = []

        # --- Historical Prices (monthly, 10 years for drawdown analysis) ---
        try:
            hist = stock.history(period="10y", interval="1mo")
            if hist is not None and not hist.empty:
                prices = []
                for date, row in hist.iterrows():
                    prices.append(
                        {
                            "date": date.strftime("%Y-%m-%d"),
                            "close": round(row["Close"], 2) if row["Close"] else None,
                            "volume": int(row["Volume"]) if row["Volume"] else None,
                        }
                    )
                result["price_history_monthly"] = prices
            else:
                result["price_history_monthly"] = []
        except Exception:
            result["price_history_monthly"] = []

        return result

    return await loop.run_in_executor(None, _fetch)


def _safe_num(val):
    """Convert pandas/numpy values to JSON-safe Python types."""
    if val is None:
        return None
    try:
        import math

        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return str(val)
