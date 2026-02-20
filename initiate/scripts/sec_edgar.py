"""SEC EDGAR data fetcher for financial statements, proxy data, and filings.

Uses the free EDGAR XBRL API for structured financial data and
the EFTS full-text search for filing documents.

Rate limit: 10 requests/second with User-Agent header (SEC requirement).
"""

import time
import requests
from typing import Optional

from config import SEC_USER_AGENT, SEC_BASE_URL, SEC_RATE_LIMIT


class SECEdgarClient:
    """Client for SEC EDGAR APIs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": SEC_USER_AGENT,
                "Accept": "application/json",
            }
        )
        self._last_request_time = 0
        self._cik_map = None

    def _rate_limit(self):
        """Enforce SEC rate limit (10 requests/sec)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < SEC_RATE_LIMIT:
            time.sleep(SEC_RATE_LIMIT - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str) -> Optional[dict]:
        """GET request with rate limiting and error handling."""
        self._rate_limit()
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 404:
                return None
            print(f"  SEC EDGAR HTTP error: {e}")
            return None
        except Exception as e:
            print(f"  SEC EDGAR error: {e}")
            return None

    def _load_cik_map(self):
        """Load ticker → CIK mapping from SEC."""
        if self._cik_map is not None:
            return
        url = "https://www.sec.gov/files/company_tickers.json"
        data = self._get(url)
        if not data:
            self._cik_map = {}
            return
        # Build ticker → CIK mapping
        self._cik_map = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = entry.get("cik_str", 0)
            self._cik_map[ticker] = int(cik)

    def get_cik(self, ticker: str) -> Optional[int]:
        """Get CIK number for a ticker."""
        self._load_cik_map()
        return self._cik_map.get(ticker.upper())

    def get_company_facts(self, ticker: str) -> Optional[dict]:
        """Get all XBRL financial facts for a company.

        Returns structured financial data: revenue, net income, EPS, assets, etc.
        organized by taxonomy (us-gaap, dei) and concept.
        """
        cik = self.get_cik(ticker)
        if not cik:
            print(f"  CIK not found for {ticker}")
            return None

        url = f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik:010d}.json"
        data = self._get(url)
        if not data:
            return None

        return data

    def get_submissions(self, ticker: str) -> Optional[dict]:
        """Get company filing submissions (recent filings list).

        Returns filing history with form types, dates, and accession numbers.
        """
        cik = self.get_cik(ticker)
        if not cik:
            return None

        url = f"{SEC_BASE_URL}/submissions/CIK{cik:010d}.json"
        return self._get(url)

    def extract_financial_history(self, ticker: str) -> dict:
        """Extract structured 10-year financial history from XBRL data.

        Returns dict with both annual (10-K) and quarterly (10-Q) data:
        - revenue: [{period, value, filed, form}]  (annual)
        - revenue_quarterly: [...]  (quarterly)
        - net_income, net_income_quarterly, etc.
        """
        facts = self.get_company_facts(ticker)
        if not facts:
            return {"error": f"No XBRL data found for {ticker}"}

        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        # Mapping of our field names to XBRL concept names (try multiple)
        concept_map = {
            "revenue": [
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
            ],
            "net_income": [
                "NetIncomeLoss",
                "ProfitLoss",
            ],
            "eps_diluted": [
                "EarningsPerShareDiluted",
            ],
            "total_assets": [
                "Assets",
            ],
            "total_equity": [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ],
            "operating_income": [
                "OperatingIncomeLoss",
            ],
            "gross_profit": [
                "GrossProfit",
            ],
            "operating_cash_flow": [
                "NetCashProvidedByUsedInOperatingActivities",
            ],
            "capex": [
                "PaymentsToAcquirePropertyPlantAndEquipment",
            ],
            "shares_outstanding": [
                "CommonStockSharesOutstanding",
                "EntityCommonStockSharesOutstanding",
            ],
        }

        result = {"ticker": ticker, "source": "SEC EDGAR XBRL"}

        for field_name, concept_names in concept_map.items():
            annual_values = []
            quarterly_values = []

            for concept in concept_names:
                concept_data = us_gaap.get(concept, {})
                units = concept_data.get("units", {})
                # Try USD first, then USD/shares for EPS, then shares
                for unit_key in ["USD", "USD/shares", "shares"]:
                    if unit_key in units:
                        for entry in units[unit_key]:
                            form = entry.get("form", "")
                            filed = entry.get("filed", "")
                            end_date = entry.get("end", "")
                            start_date = entry.get("start", "")
                            val = entry.get("val")
                            if val is None:
                                continue

                            item = {
                                "period_end": end_date,
                                "period_start": start_date,
                                "filed": filed,
                                "value": val,
                                "form": form,
                            }

                            if form == "10-K":
                                annual_values.append(item)
                            elif form == "10-Q":
                                quarterly_values.append(item)

                if annual_values or quarterly_values:
                    break  # Found data for this field

            # Deduplicate annual by period_end, keep latest filed
            seen = {}
            for v in annual_values:
                key = v["period_end"]
                if key not in seen or v["filed"] > seen[key]["filed"]:
                    seen[key] = v
            result[field_name] = sorted(
                seen.values(), key=lambda x: x["period_end"], reverse=True
            )[:12]

            # Deduplicate quarterly by period_end, keep latest filed
            seen_q = {}
            for v in quarterly_values:
                key = v["period_end"]
                if key not in seen_q or v["filed"] > seen_q[key]["filed"]:
                    seen_q[key] = v
            result[f"{field_name}_quarterly"] = sorted(
                seen_q.values(), key=lambda x: x["period_end"], reverse=True
            )[:20]  # Last 5 years of quarters

        return result

    def extract_filing_list(
        self, ticker: str, form_types: list[str] = None
    ) -> list[dict]:
        """Get list of recent filings with metadata.

        Args:
            ticker: Stock ticker
            form_types: Filter by form type (e.g., ["10-K", "DEF 14A", "8-K"])

        Returns list of {form, filing_date, accession_number, primary_doc_url}
        """
        if form_types is None:
            form_types = ["10-K", "DEF 14A", "8-K"]

        submissions = self.get_submissions(ticker)
        if not submissions:
            return []

        recent = submissions.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        cik = self.get_cik(ticker)
        filings = []

        for i in range(len(forms)):
            if forms[i] in form_types:
                acc_clean = accessions[i].replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{primary_docs[i]}"
                    if primary_docs[i]
                    else None
                )
                filings.append(
                    {
                        "form": forms[i],
                        "filing_date": dates[i],
                        "accession_number": accessions[i],
                        "primary_doc_url": doc_url,
                    }
                )

        return filings[:20]  # Limit to 20 most recent

    def get_company_info(self, ticker: str) -> dict:
        """Get basic company information from submissions endpoint."""
        submissions = self.get_submissions(ticker)
        if not submissions:
            return {}

        return {
            "name": submissions.get("name", ""),
            "cik": submissions.get("cik", ""),
            "sic": submissions.get("sic", ""),
            "sic_description": submissions.get("sicDescription", ""),
            "ticker": ticker.upper(),
            "exchanges": submissions.get("exchanges", []),
            "fiscal_year_end": submissions.get("fiscalYearEnd", ""),
            "state": submissions.get("stateOfIncorporation", ""),
            "website": submissions.get("website", ""),
        }


# Convenience function for async usage
async def fetch_sec_data(ticker: str) -> dict:
    """Async wrapper: Fetch all SEC data for a ticker.

    Returns combined dict with company_info, financial_history, filings.
    Runs in executor since requests is synchronous.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    def _fetch():
        client = SECEdgarClient()
        return {
            "source": "SEC EDGAR",
            "company_info": client.get_company_info(ticker),
            "financial_history": client.extract_financial_history(ticker),
            "filings": client.extract_filing_list(ticker),
        }

    return await loop.run_in_executor(None, _fetch)
