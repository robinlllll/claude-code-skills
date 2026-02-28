"""Collect memory stock prices, SOXX, SPY, and KRW/USD FX via yfinance.

Signal Group A (Price Momentum):
- MU, WDC, 005930.KS (Samsung), 000660.KS (SK Hynix) monthly close
- SOXX (semiconductor ETF), SPY (market benchmark)
- MU vs SOXX relative performance (2nd derivative = early peak signal)
- KRW/USD for normalizing Korean data
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from base_collector import BaseCollector, CollectorResult, make_signal

TICKERS = {
    "MU": {"name": "Micron", "sub_cycle": "ALL"},
    "WDC": {"name": "Western Digital", "sub_cycle": "NAND"},
    "005930.KS": {"name": "Samsung", "sub_cycle": "ALL"},
    "000660.KS": {"name": "SK Hynix", "sub_cycle": "DRAM"},
    "SOXX": {"name": "SOXX ETF", "sub_cycle": "ALL"},
    "SPY": {"name": "S&P 500", "sub_cycle": "ALL"},
}

FX_TICKER = "USDKRW=X"  # USD/KRW


class YFinanceCollector(BaseCollector):
    SOURCE_NAME = "yfinance"

    def __init__(self, period: str = "5y"):
        self.period = period

    def collect(self, result: CollectorResult):
        import yfinance as yf
        import pandas as pd

        # Download all stock tickers at once
        ticker_list = list(TICKERS.keys())
        print(f"  [yfinance] Downloading {len(ticker_list)} tickers...")

        try:
            data = yf.download(
                ticker_list,
                period=self.period,
                interval="1mo",
                group_by="ticker",
                progress=False,
            )
        except Exception as e:
            result.errors.append(f"Stock download failed: {e}")
            return

        # Process each ticker
        for ticker, info in TICKERS.items():
            try:
                if len(ticker_list) > 1:
                    closes = data[ticker]["Close"].dropna()
                else:
                    closes = data["Close"].dropna()

                for dt, price in closes.items():
                    date_str = pd.Timestamp(dt).strftime("%Y-%m-%d")
                    result.signals.append(
                        make_signal(
                            date=date_str,
                            source=self.SOURCE_NAME,
                            metric=f"price_{ticker.replace('.', '_')}",
                            value=round(float(price), 2),
                            unit="USD" if ".KS" not in ticker else "KRW",
                            signal_group="A",
                            sub_cycle=info["sub_cycle"],
                            metadata=info["name"],
                        )
                    )
                print(f"  [yfinance] {ticker}: {len(closes)} months")
            except Exception as e:
                result.errors.append(f"{ticker}: {e}")

        # MU vs SOXX relative performance
        try:
            mu_data = data["MU"]["Close"].dropna() if len(ticker_list) > 1 else None
            soxx_data = data["SOXX"]["Close"].dropna() if len(ticker_list) > 1 else None

            if mu_data is not None and soxx_data is not None:
                # Align dates
                aligned = pd.DataFrame({"MU": mu_data, "SOXX": soxx_data}).dropna()
                if len(aligned) > 1:
                    # Relative performance: MU return minus SOXX return (monthly)
                    mu_ret = aligned["MU"].pct_change()
                    soxx_ret = aligned["SOXX"].pct_change()
                    relative = (mu_ret - soxx_ret).dropna()

                    for dt, val in relative.items():
                        date_str = pd.Timestamp(dt).strftime("%Y-%m-%d")
                        result.signals.append(
                            make_signal(
                                date=date_str,
                                source=self.SOURCE_NAME,
                                metric="mu_vs_soxx_relative",
                                value=round(float(val), 4),
                                unit="ratio",
                                signal_group="A",
                                sub_cycle="ALL",
                                metadata="MU excess return over SOXX",
                            )
                        )
                    print(f"  [yfinance] MU vs SOXX relative: {len(relative)} months")
        except Exception as e:
            result.errors.append(f"MU vs SOXX relative: {e}")

        # KRW/USD FX rate
        try:
            print("  [yfinance] Downloading KRW/USD FX...")
            fx = yf.download(
                FX_TICKER, period=self.period, interval="1mo", progress=False
            )
            closes = fx["Close"].dropna()
            for dt, rate in closes.items():
                date_str = pd.Timestamp(dt).strftime("%Y-%m-%d")
                result.signals.append(
                    make_signal(
                        date=date_str,
                        source=self.SOURCE_NAME,
                        metric="fx_usd_krw",
                        value=round(float(rate), 2),
                        unit="KRW/USD",
                        signal_group="B",
                        sub_cycle="ALL",
                        metadata="USD/KRW exchange rate",
                    )
                )
            print(f"  [yfinance] KRW/USD: {len(closes)} months")
        except Exception as e:
            result.errors.append(f"FX download: {e}")


def run(period: str = "5y") -> CollectorResult:
    return YFinanceCollector(period=period).run()


if __name__ == "__main__":
    r = run()
    print(f"\n[yfinance] {r.status}: {r.rows_added} signals, {r.duration_seconds}s")
    if r.errors:
        for e in r.errors:
            print(f"  ERROR: {e}")
