"""Collect DRAM/NAND spot pricing data.

Signal Group A (Price Momentum):
- Primary: DRAMeXchange DXI index + spot prices (dramexchange.com)
- Fallback: PCPartPicker retail DDR5 module + SSD prices

DXI is the industry standard; PCPartPicker is a consumer proxy but freely scrapable.
"""

import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from base_collector import BaseCollector, CollectorResult, make_signal


class SpotPricingCollector(BaseCollector):
    SOURCE_NAME = "spot_pricing"

    def collect(self, result: CollectorResult):
        # Try DRAMeXchange first
        dxi_ok = False
        try:
            dxi_ok = self._collect_dxi(result)
        except Exception as e:
            result.errors.append(f"DXI scrape failed: {e}")

        # Always try PCPartPicker as additional/fallback signal
        try:
            self._collect_pcpartpicker(result)
        except Exception as e:
            result.errors.append(f"PCPartPicker failed: {e}")

    def _collect_dxi(self, result: CollectorResult) -> bool:
        """Attempt to scrape DRAMeXchange spot prices."""
        import requests
        from bs4 import BeautifulSoup

        print("  [Spot] Trying DRAMeXchange...")

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

        # Try the public DXI page
        try:
            resp = session.get("https://www.dramexchange.com/", timeout=15)
            if resp.status_code != 200:
                result.errors.append(f"DXI returned {resp.status_code}")
                return False

            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for spot price tables/elements
            # DRAMeXchange typically shows DDR5/DDR4 spot prices on main page
            price_found = False

            # Try to find price data in script tags (often embedded as JSON)
            for script in soup.find_all("script"):
                text = script.string or ""
                # Look for price arrays or objects
                if "DDR5" in text or "DDR4" in text or "NAND" in text:
                    price_found = True
                    # Attempt to parse embedded data
                    self._parse_dxi_embedded(text, result)
                    break

            if not price_found:
                # Try table-based extraction
                tables = soup.find_all("table")
                for table in tables:
                    text = table.get_text()
                    if "DDR" in text or "DRAM" in text:
                        self._parse_dxi_table(table, result)
                        price_found = True
                        break

            if not price_found:
                result.errors.append("DXI: no price data found on page")
                return False

            return True

        except requests.exceptions.ConnectionError:
            result.errors.append("DXI: site unreachable (may be geo-blocked)")
            return False

    def _parse_dxi_embedded(self, script_text: str, result: CollectorResult):
        """Parse embedded JSON price data from DXI page."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Look for price patterns like: "DDR5-4800": 2.45
        patterns = [
            (r'DDR5[^"]*?[\'"]\s*:\s*([\d.]+)', "ddr5_spot", "DRAM"),
            (r'DDR4[^"]*?[\'"]\s*:\s*([\d.]+)', "ddr4_spot", "DRAM"),
            (r'NAND[^"]*?[\'"]\s*:\s*([\d.]+)', "nand_spot", "NAND"),
        ]

        for pattern, metric, sub_cycle in patterns:
            matches = re.findall(pattern, script_text)
            if matches:
                price = float(matches[0])
                result.signals.append(
                    make_signal(
                        date=today,
                        source=self.SOURCE_NAME,
                        metric=f"dxi_{metric}_price",
                        value=price,
                        unit="USD",
                        signal_group="A",
                        sub_cycle=sub_cycle,
                        metadata=f"DRAMeXchange {metric}",
                    )
                )

    def _parse_dxi_table(self, table, result: CollectorResult):
        """Parse DXI price table."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                try:
                    price = float(re.sub(r"[^\d.]", "", cells[1].get_text(strip=True)))
                except (ValueError, IndexError):
                    continue

                if "ddr5" in label:
                    result.signals.append(
                        make_signal(
                            date=today,
                            source=self.SOURCE_NAME,
                            metric="dxi_ddr5_spot_price",
                            value=price,
                            unit="USD",
                            signal_group="A",
                            sub_cycle="DRAM",
                        )
                    )
                elif "ddr4" in label:
                    result.signals.append(
                        make_signal(
                            date=today,
                            source=self.SOURCE_NAME,
                            metric="dxi_ddr4_spot_price",
                            value=price,
                            unit="USD",
                            signal_group="A",
                            sub_cycle="DRAM",
                        )
                    )
                elif "nand" in label or "flash" in label:
                    result.signals.append(
                        make_signal(
                            date=today,
                            source=self.SOURCE_NAME,
                            metric="dxi_nand_spot_price",
                            value=price,
                            unit="USD",
                            signal_group="A",
                            sub_cycle="NAND",
                        )
                    )

    def _collect_pcpartpicker(self, result: CollectorResult):
        """Scrape retail DDR5 and SSD prices from PCPartPicker price trends."""
        import requests

        print("  [Spot] Collecting PCPartPicker retail prices...")

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

        # DDR5 memory price trends
        ddr5_prices = self._scrape_pcpp_category(session, "memory", "DDR5", result)
        # SSD price trends
        ssd_prices = self._scrape_pcpp_category(
            session, "internal-hard-drive", "SSD", result
        )

        print(f"  [Spot] PCPartPicker: DDR5={ddr5_prices}, SSD={ssd_prices}")

    def _scrape_pcpp_category(
        self, session, category: str, label: str, result: CollectorResult
    ) -> float | None:
        """Scrape average price for a PCPartPicker category."""
        from bs4 import BeautifulSoup

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            url = f"https://pcpartpicker.com/products/{category}/"
            params = {}
            if category == "memory":
                params["T"] = "14"  # DDR5 type filter
            elif category == "internal-hard-drive":
                params["t"] = "15"  # SSD type filter

            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                result.errors.append(f"PCPartPicker {label}: HTTP {resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract prices from product listings
            prices = []
            for price_el in soup.select("td.tdp--final-price a, .price__normal"):
                price_text = price_el.get_text(strip=True)
                match = re.search(r"\$?([\d,]+\.?\d*)", price_text)
                if match:
                    price = float(match.group(1).replace(",", ""))
                    if 10 < price < 2000:  # Sanity filter
                        prices.append(price)

            if not prices:
                result.errors.append(f"PCPartPicker {label}: no prices found")
                return None

            # Use median price as representative
            prices.sort()
            median = prices[len(prices) // 2]

            sub_cycle = "DRAM" if "DDR" in label else "NAND"
            result.signals.append(
                make_signal(
                    date=today,
                    source=self.SOURCE_NAME,
                    metric=f"pcpp_{label.lower()}_median_price",
                    value=round(median, 2),
                    unit="USD",
                    signal_group="A",
                    sub_cycle=sub_cycle,
                    metadata=f"PCPartPicker {label} median ({len(prices)} products)",
                )
            )

            return median

        except Exception as e:
            result.errors.append(f"PCPartPicker {label}: {e}")
            return None


def seed_from_csv(csv_path: str) -> CollectorResult:
    """Seed spot pricing data from a manually prepared CSV.

    CSV format: date,ddr5_price,ddr4_price,nand_price
    """
    import csv

    result = CollectorResult(source="spot_pricing")
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row["date"]
                for col, metric, sub in [
                    ("ddr5_price", "ddr5_spot_price", "DRAM"),
                    ("ddr4_price", "ddr4_spot_price", "DRAM"),
                    ("nand_price", "nand_spot_price", "NAND"),
                ]:
                    val = row.get(col)
                    if val:
                        result.signals.append(
                            make_signal(
                                date=date,
                                source="spot_pricing",
                                metric=metric,
                                value=float(val),
                                unit="USD",
                                signal_group="A",
                                sub_cycle=sub,
                            )
                        )

        result.status = "success"
        result.save_signals()
        result.rows_added = len(result.signals)
        print(f"  [Spot] Seeded {result.rows_added} signals from CSV")
    except Exception as e:
        result.status = "failed"
        result.errors.append(str(e))
    result.log()
    return result


def run() -> CollectorResult:
    return SpotPricingCollector().run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", help="Path to CSV file to seed data from")
    args = parser.parse_args()

    if args.seed:
        r = seed_from_csv(args.seed)
    else:
        r = run()

    print(f"\n[Spot Pricing] {r.status}: {r.rows_added} signals, {r.duration_seconds}s")
    if r.errors:
        for e in r.errors:
            print(f"  ERROR: {e}")
