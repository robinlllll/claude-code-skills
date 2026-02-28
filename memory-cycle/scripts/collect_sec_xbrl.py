"""Collect Micron + WDC financials from SEC EDGAR XBRL API.

Signal Group B (Fundamentals):
- Quarterly revenue, gross margin, inventory days, capex
- Capex/revenue ratio (reflexivity proxy)
- Revenue breakdown hints for sub-cycle scoring

SEC EDGAR company facts API: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from base_collector import BaseCollector, CollectorResult, make_signal

# SEC CIK numbers (zero-padded to 10 digits)
COMPANIES = {
    "MU": {"cik": "0000723125", "name": "Micron Technology", "sub_cycle": "ALL"},
    "WDC": {"cik": "0000106040", "name": "Western Digital", "sub_cycle": "NAND"},
}

SEC_API_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
USER_AGENT = "MemoryCycleTracker robin@example.com"

# XBRL concept mappings
CONCEPTS = {
    # Revenue
    "us-gaap:Revenues": "revenue",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "us-gaap:SalesRevenueNet": "revenue",
    # Cost of goods
    "us-gaap:CostOfRevenue": "cogs",
    "us-gaap:CostOfGoodsAndServicesSold": "cogs",
    "us-gaap:CostOfGoodsSold": "cogs",
    # Inventory
    "us-gaap:InventoryNet": "inventory",
    # CapEx
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "us-gaap:PaymentsToAcquireProductiveAssets": "capex",
}


class SecXbrlCollector(BaseCollector):
    SOURCE_NAME = "sec_xbrl"

    def collect(self, result: CollectorResult):
        import requests

        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

        for ticker, info in COMPANIES.items():
            print(f"  [SEC XBRL] Fetching {ticker} ({info['name']})...")
            url = SEC_API_URL.format(cik=info["cik"])

            try:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                facts = resp.json()
            except Exception as e:
                result.errors.append(f"{ticker} API error: {e}")
                continue

            # Extract quarterly data from XBRL facts
            extracted = self._extract_quarterly(facts, ticker, info, result)
            self._compute_derived(extracted, ticker, info, result)

    def _extract_quarterly(
        self, facts: dict, ticker: str, info: dict, result: CollectorResult
    ) -> dict:
        """Extract quarterly values from SEC XBRL JSON. Returns {metric: {period_end: value}}."""
        extracted = {}

        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        for concept, metric_name in CONCEPTS.items():
            concept_key = concept.split(":")[1]
            concept_data = us_gaap.get(concept_key, {})

            if not concept_data:
                continue

            # Try USD units first
            units = concept_data.get("units", {})
            values = units.get("USD", [])

            if not values:
                continue

            # Filter to quarterly filings (10-Q and 10-K with ~90 day duration)
            quarterly = {}
            for entry in values:
                form = entry.get("form", "")
                if form not in ("10-Q", "10-K"):
                    continue

                start = entry.get("start")
                end = entry.get("end")
                val = entry.get("val")

                if not end or val is None:
                    continue

                # For income/flow metrics, filter to ~quarterly duration
                if start and metric_name in ("revenue", "cogs", "capex"):
                    try:
                        d_start = datetime.strptime(start, "%Y-%m-%d")
                        d_end = datetime.strptime(end, "%Y-%m-%d")
                        days = (d_end - d_start).days
                        # Accept 80-100 day quarters; skip annual (>200 days)
                        if days > 200:
                            continue
                    except ValueError:
                        continue

                # For balance sheet (inventory), just take point-in-time
                quarterly[end] = val

            if quarterly and metric_name not in extracted:
                extracted[metric_name] = quarterly
            elif quarterly and metric_name in extracted:
                # Merge (some concepts overlap, prefer first match)
                for k, v in quarterly.items():
                    if k not in extracted[metric_name]:
                        extracted[metric_name][k] = v

        # Save raw signals
        for metric_name, periods in extracted.items():
            for end_date, val in sorted(periods.items())[-24:]:  # Last 24 quarters
                result.signals.append(
                    make_signal(
                        date=end_date,
                        source=self.SOURCE_NAME,
                        metric=f"{ticker.lower()}_{metric_name}",
                        value=float(val),
                        unit="USD",
                        signal_group="B",
                        sub_cycle=info["sub_cycle"],
                        metadata=info["name"],
                    )
                )

        return extracted

    def _compute_derived(
        self, extracted: dict, ticker: str, info: dict, result: CollectorResult
    ):
        """Compute gross margin, inventory days, capex ratio from raw data."""
        revenue = extracted.get("revenue", {})
        cogs = extracted.get("cogs", {})
        inventory = extracted.get("inventory", {})
        capex = extracted.get("capex", {})

        # Gross margin = (revenue - cogs) / revenue
        common_dates = sorted(set(revenue.keys()) & set(cogs.keys()))
        for date in common_dates[-24:]:
            rev = revenue[date]
            cost = cogs[date]
            if rev and rev > 0:
                margin = (rev - cost) / rev
                result.signals.append(
                    make_signal(
                        date=date,
                        source=self.SOURCE_NAME,
                        metric=f"{ticker.lower()}_gross_margin",
                        value=round(margin, 4),
                        unit="ratio",
                        signal_group="B",
                        sub_cycle=info["sub_cycle"],
                        metadata=f"{info['name']} gross margin",
                    )
                )

        # Inventory days = inventory / (COGS / days_in_quarter)
        # Use inventory at period end and quarterly COGS
        inv_dates = sorted(set(inventory.keys()) & set(cogs.keys()))
        for date in inv_dates[-24:]:
            inv = inventory[date]
            cost = cogs[date]
            if cost and cost > 0:
                inv_days = inv / (cost / 90)  # Approximate quarter = 90 days
                result.signals.append(
                    make_signal(
                        date=date,
                        source=self.SOURCE_NAME,
                        metric=f"{ticker.lower()}_inventory_days",
                        value=round(inv_days, 1),
                        unit="days",
                        signal_group="B",
                        sub_cycle=info["sub_cycle"],
                        metadata=f"{info['name']} inventory days",
                    )
                )

        # Capex / Revenue ratio
        capex_rev_dates = sorted(set(capex.keys()) & set(revenue.keys()))
        for date in capex_rev_dates[-24:]:
            cap = capex[date]
            rev = revenue[date]
            if rev and rev > 0 and cap:
                ratio = cap / rev
                result.signals.append(
                    make_signal(
                        date=date,
                        source=self.SOURCE_NAME,
                        metric=f"{ticker.lower()}_capex_ratio",
                        value=round(ratio, 4),
                        unit="ratio",
                        signal_group="B",
                        sub_cycle=info["sub_cycle"],
                        metadata=f"{info['name']} capex/revenue",
                    )
                )

        count = sum(len(v) for v in extracted.values())
        print(f"  [SEC XBRL] {ticker}: {count} data points extracted")


def run() -> CollectorResult:
    return SecXbrlCollector().run()


if __name__ == "__main__":
    r = run()
    print(f"\n[SEC XBRL] {r.status}: {r.rows_added} signals, {r.duration_seconds}s")
    if r.errors:
        for e in r.errors:
            print(f"  ERROR: {e}")
