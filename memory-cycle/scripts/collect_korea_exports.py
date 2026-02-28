"""Collect Korean semiconductor memory export data.

Signal Group B (Fundamentals) - LEADING indicator:
- HS 854232 = semiconductor memory devices (DRAM + NAND)
- Track value (USD) AND volume (kg) separately
- Value/volume ratio = pricing power vs volume dumping
- If value up but volume flat/down -> "Mix-driven, not cycle expansion"

Primary: Korea Customs Service (data.go.kr) API
Fallback: KITA (kita.net) web scrape
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from base_collector import BaseCollector, CollectorResult, make_signal

# Korea Customs Service API (public data portal)
CUSTOMS_API_URL = "https://unipass.customs.go.kr/ets/index.do"
# KITA trade statistics
KITA_URL = "https://stat.kita.net/stat/kts/prod/prodItemImpExpList.screen"

# HS Code for semiconductor memory
HS_CODE = "854232"


class KoreaExportsCollector(BaseCollector):
    SOURCE_NAME = "korea_exports"

    def collect(self, result: CollectorResult):
        # Try KITA API approach first (more reliable)
        try:
            self._collect_kita(result)
            if result.signals:
                return
        except Exception as e:
            result.errors.append(f"KITA approach failed: {e}")

        # Fallback: try Korea trade statistics API
        try:
            self._collect_customs_api(result)
        except Exception as e:
            result.errors.append(f"Customs API failed: {e}")

    def _collect_kita(self, result: CollectorResult):
        """Collect from KITA trade statistics API."""
        import requests

        # KITA provides Korean export data by HS code
        # Use their OpenAPI endpoint
        print("  [Korea] Trying KITA trade statistics...")

        # KITA OpenAPI for trade by commodity
        api_url = "https://stat.kita.net/apigw/stat/getCmmdtyClCodeInfo.do"

        # Build date range: last 5 years monthly
        end = datetime.now()
        start = end - timedelta(days=365 * 5)

        # Try the KITA statistics page endpoint
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )

        # Use KITA's statistical data API
        params = {
            "hsSgn": HS_CODE,
            "strtYymm": start.strftime("%Y%m"),
            "endYymm": end.strftime("%Y%m"),
            "expImpSe": "1",  # 1 = export
        }

        try:
            resp = session.get(
                "https://stat.kita.net/apigw/stat/getCmmdtyEximPeriodTrend.do",
                params=params,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", data.get("items", []))
                if items:
                    self._parse_kita_data(items, result)
                    return
        except Exception:
            pass

        # If JSON API fails, note it
        result.errors.append("KITA API returned no data; may need manual seed")
        print("  [Korea] KITA API returned no data. Will need manual CSV seed.")

    def _collect_customs_api(self, result: CollectorResult):
        """Fallback: Korea Customs Service via data.go.kr."""

        print("  [Korea] Trying Korea Customs API...")

        # data.go.kr trade statistics API
        api_url = "https://apis.data.go.kr/1220000/prodstsmrize/getProdTotExStsmrize"

        # This requires an API key from data.go.kr
        # For now, we'll note this as needing configuration
        result.errors.append(
            "Korea Customs API requires data.go.kr API key. "
            "Seed manually or configure KOREA_TRADE_API_KEY in .env"
        )

    def _parse_kita_data(self, items: list, result: CollectorResult):
        """Parse KITA trade data response."""
        count = 0
        for item in items:
            period = item.get("yymm", item.get("period", ""))
            if not period or len(period) < 6:
                continue

            # Parse YYYYMM to date
            try:
                date_str = f"{period[:4]}-{period[4:6]}-01"
            except (IndexError, ValueError):
                continue

            # Export value (thousand USD typically)
            exp_value = item.get("expAmt", item.get("expDlr", 0))
            exp_volume = item.get("expWgt", item.get("expKg", 0))

            if exp_value:
                val = float(exp_value)
                result.signals.append(
                    make_signal(
                        date=date_str,
                        source=self.SOURCE_NAME,
                        metric="korea_memory_export_value",
                        value=val,
                        unit="thousand_USD",
                        signal_group="B",
                        sub_cycle="ALL",
                        metadata="Korea HS854232 export value",
                    )
                )
                count += 1

            if exp_volume:
                vol = float(exp_volume)
                result.signals.append(
                    make_signal(
                        date=date_str,
                        source=self.SOURCE_NAME,
                        metric="korea_memory_export_volume",
                        value=vol,
                        unit="kg",
                        signal_group="B",
                        sub_cycle="ALL",
                        metadata="Korea HS854232 export volume",
                    )
                )

                # Value/volume ratio (pricing power indicator)
                if exp_value and vol > 0:
                    ratio = float(exp_value) / vol
                    result.signals.append(
                        make_signal(
                            date=date_str,
                            source=self.SOURCE_NAME,
                            metric="korea_memory_value_volume_ratio",
                            value=round(ratio, 4),
                            unit="USD/kg",
                            signal_group="B",
                            sub_cycle="ALL",
                            metadata="Value/volume = pricing power",
                        )
                    )

        print(f"  [Korea] Parsed {count} monthly export data points")


def seed_from_csv(csv_path: str) -> CollectorResult:
    """Seed Korean export data from a manually prepared CSV.

    CSV format: date,value_kusd,volume_kg
    Example:
        2019-01-01,8500000,120000
        2019-02-01,7200000,110000
    """
    import csv

    result = CollectorResult(source="korea_exports")
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row["date"]
                val = float(row.get("value_kusd", 0))
                vol = float(row.get("volume_kg", 0))

                if val:
                    result.signals.append(
                        make_signal(
                            date=date,
                            source="korea_exports",
                            metric="korea_memory_export_value",
                            value=val,
                            unit="thousand_USD",
                            signal_group="B",
                            sub_cycle="ALL",
                        )
                    )
                if vol:
                    result.signals.append(
                        make_signal(
                            date=date,
                            source="korea_exports",
                            metric="korea_memory_export_volume",
                            value=vol,
                            unit="kg",
                            signal_group="B",
                            sub_cycle="ALL",
                        )
                    )
                if val and vol > 0:
                    result.signals.append(
                        make_signal(
                            date=date,
                            source="korea_exports",
                            metric="korea_memory_value_volume_ratio",
                            value=round(val / vol, 4),
                            unit="USD/kg",
                            signal_group="B",
                            sub_cycle="ALL",
                        )
                    )

        result.status = "success"
        result.save_signals()
        result.rows_added = len(result.signals)
        print(f"  [Korea] Seeded {result.rows_added} signals from CSV")
    except Exception as e:
        result.status = "failed"
        result.errors.append(str(e))
    result.log()
    return result


def run() -> CollectorResult:
    return KoreaExportsCollector().run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", help="Path to CSV file to seed data from")
    args = parser.parse_args()

    if args.seed:
        r = seed_from_csv(args.seed)
    else:
        r = run()

    print(
        f"\n[Korea Exports] {r.status}: {r.rows_added} signals, {r.duration_seconds}s"
    )
    if r.errors:
        for e in r.errors:
            print(f"  ERROR: {e}")
