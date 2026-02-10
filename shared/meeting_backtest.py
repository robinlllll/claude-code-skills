"""周会选股回测 (Meeting Picks Backtest)

Measures whether stock picks discussed in weekly meetings predicted future returns,
and whether Robin acted on the right ones. Compares "discussed AND traded" vs
"discussed but DIDN'T trade", split by bullish/bearish sentiment.

Usage:
    python meeting_backtest.py [--no-cache] [--verbose]
"""

import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import random
from statistics import mean, median
from typing import Optional

# Windows GBK fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import yaml

# Shared utilities
SKILLS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILLS_DIR))
from shared.entity_resolver import resolve_entity
from shared.frontmatter_utils import build_frontmatter

# Paths
VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"
MEETING_DIR = VAULT_DIR / "周会"
TRADES_PATH = Path.home() / "PORTFOLIO" / "portfolio_monitor" / "data" / "trades.json"
PRICE_CACHE_DIR = Path.home() / "PORTFOLIO" / "portfolio_monitor" / "data" / "price_cache"
CACHE_PATH = Path(__file__).parent / "data" / "meeting_backtest_cache.json"
REPORT_DIR = VAULT_DIR / "写作" / "投资回顾"

# Analysis windows
MAIN_WINDOWS = [7, 30, 90]
ALL_WINDOWS = [1, 3, 7, 14, 21, 30, 45, 60, 90, 180]

# Sector classification for attribution analysis
SECTOR_MAP = {
    # Semiconductors
    "NVDA": "Semi", "AMD": "Semi", "MU": "Semi", "INTC": "Semi",
    "AVGO": "Semi", "ASML": "Semi", "TSM": "Semi", "QCOM": "Semi",
    # Technology
    "AAPL": "Tech", "MSFT": "Tech", "AMZN": "Tech", "NOW": "Tech",
    "SAP": "Tech", "DELL": "Tech", "HPQ": "Tech", "ORCL": "Tech",
    "CRM": "Tech", "ANSS": "Tech",
    # Communication / Media
    "GOOGL": "Comm", "META": "Comm", "SNAP": "Comm", "PINS": "Comm",
    "NFLX": "Comm", "DIS": "Comm", "CMCSA": "Comm", "PSKY": "Comm",
    # China Internet
    "BABA": "China", "JD": "China", "PDD": "China", "BIDU": "China",
    "TCOM": "China", "BEKE": "China", "FUTU": "China", "QFIN": "China",
    "NTES": "China", "BILI": "China", "IQ": "China", "VIPS": "China",
    "WB": "China", "YMM": "China", "DDL": "China", "BZ": "China",
    "LKNCY": "China", "KE": "China", "ZH": "China", "0700.HK": "China",
    "6690.HK": "China", "1024.HK": "China", "YUMC": "China",
    "HTHT": "China", "FINV": "China",
    # Financials
    "HOOD": "Fin", "SCHW": "Fin", "IBKR": "Fin", "JPM": "Fin",
    "BAC": "Fin", "WFC": "Fin", "AXP": "Fin", "PYPL": "Fin",
    "COIN": "Fin", "MSCI": "Fin", "MCO": "Fin", "XYZ": "Fin",
    "EFX": "Fin", "TRU": "Fin", "FICO": "Fin", "MA": "Fin",
    "V": "Fin", "DFS": "Fin",
    # Consumer Discretionary
    "TSLA": "ConsDisc", "NKE": "ConsDisc", "LULU": "ConsDisc",
    "DECK": "ConsDisc", "ONON": "ConsDisc", "CMG": "ConsDisc",
    "SBUX": "ConsDisc", "RH": "ConsDisc", "M": "ConsDisc",
    "TJX": "ConsDisc", "ROST": "ConsDisc", "VFC": "ConsDisc",
    "ABNB": "ConsDisc", "BKNG": "ConsDisc", "EXPE": "ConsDisc",
    "HLT": "ConsDisc", "UAA": "ConsDisc", "DLTR": "ConsDisc",
    "SKX": "ConsDisc",
    # Housing / Building
    "BLDR": "Housing", "FND": "Housing", "POOL": "Housing",
    "HD": "Housing", "LOW": "Housing", "IBP": "Housing",
    "WMS": "Housing", "GMS": "Housing",
    # Consumer Staples
    "PM": "Staples", "BTI": "Staples", "MO": "Staples",
    "DEO": "Staples", "STZ": "Staples", "PEP": "Staples",
    "COST": "Staples", "WMT": "Staples", "BF-B": "Staples",
    # Healthcare / Beauty
    "LLY": "Health", "NVO": "Health", "EL": "Health",
    # Luxury / European
    "MC.PA": "Luxury", "RMS.PA": "Luxury", "BRBY.L": "Luxury",
    "WOSG.L": "Luxury", "ZGN": "Luxury", "RACE": "Luxury",
    "P911.DE": "Luxury",
    # Transport / Industrial
    "CSX": "Indust", "UNP": "Indust",
}

SECTOR_ETFS = {
    "Semi": "SMH", "Tech": "XLK", "Comm": "XLC", "China": "FXI",
    "Fin": "XLF", "ConsDisc": "XLY", "Housing": "XHB",
    "Staples": "XLP", "Health": "XLV", "Luxury": "EWL",
    "Indust": "XLI", "Other": "SPY",
}

SECTOR_LABELS = {
    "Semi": "半导体", "Tech": "科技", "Comm": "通信/媒体", "China": "中概",
    "Fin": "金融", "ConsDisc": "可选消费", "Housing": "住房/建材",
    "Staples": "必选消费", "Health": "医疗", "Luxury": "奢侈品",
    "Indust": "工业", "Other": "其他",
}


# ── Sentiment enum ──────────────────────────────────────────────

class Sentiment:
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


# ── Ticker Normalizer ───────────────────────────────────────────

class TickerNormalizer:
    """Three-way mapping: meeting ↔ trades.json ↔ yfinance."""

    # Special ticker mappings (meeting format → canonical yfinance)
    SPECIAL = {
        "BRK.B": "BRK-B",
        "BRK B": "BRK-B",
        "BRKB": "BRK-B",
        "ANTA.HK": "2020.HK",
        # Company names → yfinance tickers
        "BURBERRY": "BRBY.L",
        "LVMH": "MC.PA",
        "HERMÈS": "RMS.PA",
        "HERMES": "RMS.PA",
        "RICHEMONT": "CFR.SW",
        "KUAISHOU": "1024.HK",
        "JT": "2914.T",
        # Renamed/delisted tickers
        "SQ": "XYZ",  # Block Inc (SQ → XYZ rename)
        "DFS": "DFS",  # Discover Financial (acquired by Capital One)
        "PARA": "PSKY",  # Paramount → Skydance (PARA → PSKY)
        "SKX": "SKX",  # Skechers (privatized at $63, May 2025)
        "FBM": "FBM",  # Foundation Building Materials
        "ANSS": "ANSS",  # Ansys (acquired by Synopsys)
        "ATAD": "ATAT",  # Typo fix: ATAD → ATAT
        # European tickers
        "EXPN": "EXPN.L",  # Experian on London
        "WOSG": "WOSG.L",  # Watches of Switzerland
        "ICBC": "1398.HK",  # ICBC Hong Kong listing
        "CFR.PA": "CFR.SW",  # Richemont is on Swiss exchange, not Paris
        "BF.B": "BF-B",  # Brown-Forman (yfinance uses dash)
        # A-shares that need .SS/.SZ
        "600519": "600519.SS",
        "600887": "600887.SS",
        "002594": "002594.SZ",
        "000333": "000333.SZ",
        "000858": "000858.SZ",
        "000568": "000568.SZ",
        # Chinese company names → tickers
        "海尔智家": "6690.HK",
        "美的集团": "000333.SZ",
        "格力电器": "000651.SZ",
        "安踏体育": "2020.HK",
        "快手": "1024.HK",
    }

    # Privatized/delisted tickers with known final price
    PRIVATIZED = {
        "SKX": {"final_price": 63.0, "delist_date": date(2025, 5, 15)},
    }

    # yfinance ticker → additional trades.json keys (for renamed tickers)
    TRADES_ALIASES = {
        "XYZ": ["SQ"],      # Block Inc was SQ in trades.json
        "PSKY": ["PARA"],    # Paramount was PARA in trades.json
    }

    @staticmethod
    def meeting_to_yfinance(ticker: str) -> str:
        """Convert meeting ticker format to yfinance format."""
        original = ticker.strip()
        ticker = original.upper()

        # Strip $ prefix
        if ticker.startswith("$"):
            ticker = ticker[1:]

        # Special cases (check both upper and original for Chinese names)
        if ticker in TickerNormalizer.SPECIAL:
            return TickerNormalizer.SPECIAL[ticker]
        if original in TickerNormalizer.SPECIAL:
            return TickerNormalizer.SPECIAL[original]

        # A-shares: .SH → .SS for yfinance
        if ticker.endswith(".SH"):
            return ticker[:-3] + ".SS"

        # Already has exchange suffix → as-is
        if re.match(r"^\d+\.HK$", ticker):
            return ticker
        if re.match(r"^\d+\.(SZ|SS|T)$", ticker):
            return ticker
        if re.match(r"^[A-Z]+\.(PA|L|DE|AS|MI|SW)$", ticker):
            return ticker

        # Pure numeric → check if A-share (6-digit) or HK (4-5 digit)
        if re.match(r"^\d{6}$", ticker):
            # A-share: 6xxxxx → .SS, 0xxxxx/3xxxxx → .SZ
            if ticker.startswith("6"):
                return ticker + ".SS"
            else:
                return ticker + ".SZ"
        if re.match(r"^\d{4,5}$", ticker):
            return ticker + ".HK"

        # US stock (plain letters)
        return ticker

    @staticmethod
    def trades_to_yfinance(ticker: str) -> str:
        """Convert trades.json ticker format to yfinance format."""
        ticker = ticker.strip()

        # HK stocks ending in D (e.g., 690D → 0690.HK)
        m = re.match(r"^(\d+)D$", ticker)
        if m:
            num = m.group(1).zfill(4)
            return f"{num}.HK"

        # Pure numeric → HK stock
        if re.match(r"^\d{3,5}$", ticker):
            return ticker + ".HK"

        # Already has suffix (e.g., 7974.T)
        if "." in ticker:
            # .SH → .SS
            if ticker.endswith(".SH"):
                return ticker[:-3] + ".SS"
            return ticker

        # BRK B → BRK-B
        if ticker == "BRK B":
            return "BRK-B"

        # US stock
        return ticker

    @staticmethod
    def yfinance_to_trades_match(yf_ticker: str) -> list[str]:
        """Generate possible trades.json keys for a yfinance ticker.
        Returns a list of possible formats to match against trades index."""
        yf_ticker = yf_ticker.strip().upper()
        candidates = []

        # HK stocks: 0690.HK → [690D, 0690, 690]
        m = re.match(r"^(\d+)\.HK$", yf_ticker)
        if m:
            num = m.group(1)
            candidates.append(num.lstrip("0") + "D")  # 690D
            candidates.append(num)  # 0690
            candidates.append(num.lstrip("0"))  # 690
            return candidates

        # A-shares: 600519.SS → [600519]
        m = re.match(r"^(\d+)\.(SS|SZ)$", yf_ticker)
        if m:
            candidates.append(m.group(1))
            return candidates

        # Japan: 7974.T → [7974.T]
        if yf_ticker.endswith(".T"):
            candidates.append(yf_ticker)
            return candidates

        # BRK-B → [BRK B, BRK-B]
        if "-" in yf_ticker:
            candidates.append(yf_ticker.replace("-", " "))
            candidates.append(yf_ticker)
            return candidates

        # US stock: NVDA → [NVDA]
        candidates.append(yf_ticker)

        # Add aliases for renamed tickers (e.g., XYZ → also check SQ)
        aliases = TickerNormalizer.TRADES_ALIASES.get(yf_ticker, [])
        candidates.extend(aliases)

        return candidates


# ── Sentiment Extractor ─────────────────────────────────────────

class SentimentExtractor:
    """Classify sentiment from 潜在行动提示 section text."""

    # Compound patterns checked first (order matters)
    COMPOUND_RULES = [
        (r"中性偏多", Sentiment.BULLISH),
        (r"中性偏谨慎", Sentiment.BEARISH),
        (r"中性偏空", Sentiment.BEARISH),
        (r"中性偏乐观", Sentiment.BULLISH),
        (r"偏乐观", Sentiment.BULLISH),
        (r"偏悲观", Sentiment.BEARISH),
        (r"不太看好", Sentiment.BEARISH),
        (r"比较看好", Sentiment.BULLISH),
        (r"相对看好", Sentiment.BULLISH),
        (r"整体偏多", Sentiment.BULLISH),
        (r"整体偏空", Sentiment.BEARISH),
    ]

    BULLISH_PATTERNS = [
        r"偏多", r"加仓", r"建仓", r"买入", r"逢低", r"布局",
        r"逐步加", r"小仓位", r"试探性", r"维持偏高仓位",
        r"重新纳入", r"择机", r"考虑配置",
        r"看好", r"增持", r"利好", r"反弹",
        r"吸纳", r"上行", r"低估",
    ]

    BEARISH_PATTERNS = [
        r"偏空", r"减仓", r"回避", r"卖出", r"已卖",
        r"偏谨慎", r"不加仓", r"降低.*暴露", r"不买",
        r"减少预期", r"小幅减仓",
        r"看空", r"悲观", r"承压", r"下行",
        r"高估", r"泡沫", r"利空", r"估值偏高",
        r"不建议", r"止损", r"清仓",
    ]

    NEUTRAL_PATTERNS = [
        r"中性", r"观察", r"维持(?!偏高)", r"观望",
    ]

    @staticmethod
    def classify(text: str) -> str:
        """Classify sentiment from action hint text."""
        if not text or not text.strip():
            return Sentiment.UNKNOWN

        # Check compound patterns first
        for pattern, sentiment in SentimentExtractor.COMPOUND_RULES:
            if re.search(pattern, text):
                return sentiment

        # Count bullish vs bearish signals
        bull_count = sum(1 for p in SentimentExtractor.BULLISH_PATTERNS if re.search(p, text))
        bear_count = sum(1 for p in SentimentExtractor.BEARISH_PATTERNS if re.search(p, text))

        if bull_count > 0 and bull_count > bear_count:
            return Sentiment.BULLISH
        if bear_count > 0 and bear_count > bull_count:
            return Sentiment.BEARISH

        # Check neutral
        for p in SentimentExtractor.NEUTRAL_PATTERNS:
            if re.search(p, text):
                return Sentiment.NEUTRAL

        return Sentiment.UNKNOWN


# ── Meeting Parser ──────────────────────────────────────────────

class MeetingParser:
    """Parse weekly meeting .md files into structured data."""

    # Pattern to match section headers with tickers like ## $NVDA（...）
    TICKER_SECTION_RE = re.compile(
        r"^\s*##\s+\$([A-Z0-9]+(?:\.[A-Z]+)?)"  # $TICKER with optional .HK/.T etc
        r"(?:\s*[（(].*)?$",                        # optional Chinese/English parens
        re.MULTILINE,
    )

    # Pattern for Chinese company sections like ## 海尔智家（Haier Smart Home）
    CHINESE_SECTION_RE = re.compile(
        r"^\s*##\s+([^\n#]+?)(?:\s*[（(].*)?$",
        re.MULTILINE,
    )

    # Action hint section header
    ACTION_HINT_RE = re.compile(
        r"###\s*潜在行动提示",
        re.MULTILINE,
    )

    # Next section header (any ### or ##)
    NEXT_SECTION_RE = re.compile(
        r"^(?:\s*#{2,3}\s)",
        re.MULTILINE,
    )

    def parse_all(self) -> list[dict]:
        """Parse all meeting files. Returns list of meeting dicts."""
        meetings = []
        files = sorted(MEETING_DIR.glob("会议实录 *.md"))
        for f in files:
            m = self._parse_file(f)
            if m:
                meetings.append(m)
        return meetings

    def _parse_file(self, filepath: Path) -> Optional[dict]:
        """Parse a single meeting file."""
        text = filepath.read_text(encoding="utf-8")

        # Extract frontmatter
        fm = self._extract_frontmatter(text)
        if not fm:
            return None

        meeting_date = fm.get("created")
        if isinstance(meeting_date, str):
            meeting_date = datetime.strptime(meeting_date, "%Y-%m-%d").date()
        elif isinstance(meeting_date, datetime):
            meeting_date = meeting_date.date()

        tickers_list = fm.get("tickers", [])

        # Extract per-ticker sentiments from body
        ticker_sentiments = self._extract_sentiments(text, tickers_list)

        return {
            "date": meeting_date,
            "file": filepath.name,
            "tickers_raw": tickers_list,
            "picks": ticker_sentiments,  # list of {ticker_raw, ticker_yf, sentiment, action_text}
        }

    def _extract_frontmatter(self, text: str) -> Optional[dict]:
        """Extract YAML frontmatter from markdown."""
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return None
        try:
            return yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            return None

    # Chinese company section → yfinance ticker
    CHINESE_TICKER_MAP = {
        "海尔智家": "6690.HK",
        "美的集团": "000333.SZ",
        "格力电器": "000651.SZ",
        "安踏体育": "2020.HK",
        "快手": "1024.HK",
        "茅台": "600519.SS",
        "五粮液": "000858.SZ",
        "泸州老窖": "000568.SZ",
        "洋河": "002304.SZ",
        "阿里巴巴": "BABA",
        "京东": "JD",
        "拼多多": "PDD",
        "腾讯": "0700.HK",
        "百度": "BIDU",
        "比亚迪": "002594.SZ",
        "日本烟草": "2914.T",
    }

    def _extract_sentiments(self, text: str, tickers_list: list) -> list[dict]:
        """Extract sentiment for each ticker mentioned in the meeting."""
        results = []
        seen_tickers = set()

        # Strategy 1: Find ## $TICKER sections and their action hints
        for match in self.TICKER_SECTION_RE.finditer(text):
            raw_ticker = match.group(1)
            section_start = match.start()
            action_text = self._find_action_hint(text, section_start)
            sentiment = SentimentExtractor.classify(action_text)

            # Fallback: check 核心观点摘要 section for sentiment
            if sentiment == Sentiment.UNKNOWN:
                summary_text = self._find_core_summary(text, section_start)
                sentiment = SentimentExtractor.classify(summary_text)
                if sentiment != Sentiment.UNKNOWN and not action_text:
                    action_text = summary_text

            # Fallback: try full section text for broader keyword matching
            if sentiment == Sentiment.UNKNOWN:
                full_section = self._get_full_section_text(text, section_start)
                sentiment = SentimentExtractor.classify(full_section)
                if sentiment != Sentiment.UNKNOWN and not action_text:
                    action_text = full_section[:200]

            yf_ticker = TickerNormalizer.meeting_to_yfinance(raw_ticker)

            results.append({
                "ticker_raw": raw_ticker,
                "ticker_yf": yf_ticker,
                "sentiment": sentiment,
                "action_text": (action_text or "")[:200],
            })
            seen_tickers.add(raw_ticker.upper())
            seen_tickers.add(yf_ticker.upper())

        # Strategy 1.5: Find Chinese company name sections (## 海尔智家)
        for match in re.finditer(r"^\s*##\s+([^\n#$]+?)(?:\s*[（(].*)?$", text, re.MULTILINE):
            section_name = match.group(1).strip()
            # Check if this is a known Chinese company name
            yf_ticker = None
            for cn_name, cn_ticker in self.CHINESE_TICKER_MAP.items():
                if cn_name in section_name:
                    yf_ticker = cn_ticker
                    break

            if yf_ticker and yf_ticker.upper() not in seen_tickers:
                section_start = match.start()
                action_text = self._find_action_hint(text, section_start)
                sentiment = SentimentExtractor.classify(action_text)
                if sentiment == Sentiment.UNKNOWN:
                    summary_text = self._find_core_summary(text, section_start)
                    sentiment = SentimentExtractor.classify(summary_text)
                    if sentiment != Sentiment.UNKNOWN and not action_text:
                        action_text = summary_text

                if sentiment == Sentiment.UNKNOWN:
                    full_section = self._get_full_section_text(text, section_start)
                    sentiment = SentimentExtractor.classify(full_section)
                    if sentiment != Sentiment.UNKNOWN and not action_text:
                        action_text = full_section[:200]

                results.append({
                    "ticker_raw": section_name,
                    "ticker_yf": yf_ticker,
                    "sentiment": sentiment,
                    "action_text": (action_text or "")[:200],
                })
                seen_tickers.add(yf_ticker.upper())

        # Strategy 2: For tickers in frontmatter but without a dedicated section,
        # try the summary table and meeting header
        meeting_summary = self._get_meeting_summary(text)

        for ticker_raw in tickers_list:
            ticker_str = str(ticker_raw).strip()
            yf_ticker = TickerNormalizer.meeting_to_yfinance(ticker_str)

            if ticker_str.upper() in seen_tickers or yf_ticker.upper() in seen_tickers:
                continue

            # Try entity resolution for company names (e.g., "Burberry", "LVMH")
            resolved = resolve_entity(ticker_str)
            if resolved:
                resolved_yf = TickerNormalizer.meeting_to_yfinance(resolved["ticker"])
                if resolved_yf.upper() in seen_tickers:
                    continue
                yf_ticker = resolved_yf

            # Try multiple fallback strategies for sentiment
            action_text = None
            sentiment = Sentiment.UNKNOWN

            # Fallback A: Summary table at bottom
            action_text = self._find_summary_table_entry(text, ticker_str)
            if action_text:
                sentiment = SentimentExtractor.classify(action_text)

            # Fallback B: Search in meeting header summary
            if sentiment == Sentiment.UNKNOWN and meeting_summary:
                ticker_sentiment = self._extract_ticker_sentiment_from_summary(
                    meeting_summary, ticker_str
                )
                if ticker_sentiment:
                    sentiment = ticker_sentiment[0]
                    if not action_text:
                        action_text = ticker_sentiment[1]

            results.append({
                "ticker_raw": ticker_str,
                "ticker_yf": yf_ticker,
                "sentiment": sentiment,
                "action_text": (action_text or "")[:200],
            })
            seen_tickers.add(ticker_str.upper())
            seen_tickers.add(yf_ticker.upper())

        return results

    def _find_action_hint(self, text: str, section_start: int) -> Optional[str]:
        """Find the 潜在行动提示 text for a given section."""
        # Search forward from section_start for the action hint header
        search_text = text[section_start:]

        # Find the action hint within this section (before the next ## section)
        next_h2 = re.search(r"\n\s*## ", search_text[5:])  # skip the current ## header
        section_end = section_start + 5 + next_h2.start() if next_h2 else len(text)
        section_text = text[section_start:section_end]

        action_match = self.ACTION_HINT_RE.search(section_text)
        if not action_match:
            return None

        # Get text after the header until the next ### or ##
        after_hint = section_text[action_match.end():]
        next_section = self.NEXT_SECTION_RE.search(after_hint)
        if next_section:
            hint_text = after_hint[:next_section.start()]
        else:
            hint_text = after_hint[:500]  # safety limit

        return hint_text.strip()

    def _find_core_summary(self, text: str, section_start: int) -> Optional[str]:
        """Find the 核心观点摘要 text for a given section."""
        search_text = text[section_start:]
        next_h2 = re.search(r"\n\s*## ", search_text[5:])
        section_end = 5 + next_h2.start() if next_h2 else len(search_text)
        section_text = search_text[:section_end]

        summary_match = re.search(r"###\s*核心观点摘要", section_text)
        if not summary_match:
            return None

        after = section_text[summary_match.end():]
        next_sec = self.NEXT_SECTION_RE.search(after)
        if next_sec:
            return after[:next_sec.start()].strip()
        return after[:500].strip()

    def _get_full_section_text(self, text: str, section_start: int) -> str:
        """Get the full text of a ## section for broader sentiment classification."""
        search_text = text[section_start:]
        next_h2 = re.search(r"\n\s*## ", search_text[5:])
        if next_h2:
            return search_text[:5 + next_h2.start()]
        return search_text[:2000]

    def _get_meeting_summary(self, text: str) -> Optional[str]:
        """Get the 会议摘要 text from the meeting header."""
        match = re.search(r"会议摘要[:：]\s*(.+?)(?=\n会议时间|\n原文链接|\n---|\n##)", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_ticker_sentiment_from_summary(self, summary: str, ticker_str: str) -> Optional[tuple]:
        """Extract sentiment for a specific ticker from the meeting summary text.
        Returns (sentiment, context_text) or None."""
        # Search for ticker mention in summary followed by sentiment keyword
        patterns = [
            re.escape(f"${ticker_str}"),
            re.escape(ticker_str),
        ]
        resolved = resolve_entity(ticker_str)
        if resolved:
            cn = resolved.get("canonical_name", "")
            if cn:
                patterns.append(re.escape(cn))

        for pattern in patterns:
            if not pattern:
                continue
            # Find the ticker and grab surrounding context (~100 chars each side)
            m = re.search(pattern, summary, re.IGNORECASE)
            if m:
                start = max(0, m.start() - 20)
                end = min(len(summary), m.end() + 100)
                context = summary[start:end]
                sentiment = SentimentExtractor.classify(context)
                if sentiment != Sentiment.UNKNOWN:
                    return (sentiment, context)
        return None

    def _find_summary_table_entry(self, text: str, ticker_str: str) -> Optional[str]:
        """Find a ticker's entry in the summary table at the bottom."""
        # Look for the summary table section
        table_match = re.search(r"一句话汇报摘要", text)
        if not table_match:
            return None

        table_text = text[table_match.start():]
        # Search for the ticker in table rows
        patterns = [
            re.escape(f"${ticker_str}"),
            re.escape(ticker_str),
        ]
        # Also try entity-resolved name
        resolved = resolve_entity(ticker_str)
        if resolved:
            patterns.append(re.escape(resolved.get("canonical_name", "")))

        for pattern in patterns:
            if not pattern:
                continue
            row_match = re.search(
                rf"\|\s*[^|]*{pattern}[^|]*\|\s*([^|]+)\|",
                table_text,
                re.IGNORECASE,
            )
            if row_match:
                return row_match.group(1).strip()

        return None


# ── Trade Matcher ───────────────────────────────────────────────

class TradeMatcher:
    """Match meeting picks against actual trades AND existing positions.

    "Acted On" = held a position on meeting date OR traded within window.
    Position is reconstructed from cumulative BUY/SELL in trades.json.
    """

    def __init__(self):
        self.trades_by_ticker: dict[str, list[dict]] = defaultdict(list)
        # position_timeline[ticker] = sorted list of (date, cumulative_qty)
        self.position_timeline: dict[str, list[tuple[date, float]]] = defaultdict(list)
        self._load_trades()

    def _load_trades(self):
        """Load trades.json, index by ticker, and build position timelines."""
        with open(TRADES_PATH, encoding="utf-8") as f:
            data = json.load(f)

        trades = data.get("trades", data) if isinstance(data, dict) else data

        # First pass: collect all stock trades
        ticker_trades: dict[str, list[dict]] = defaultdict(list)
        for trade in trades:
            asset_type = trade.get("asset_type", "")
            if asset_type not in ("STK", ""):
                continue

            ticker = trade.get("ticker", "").strip()
            if not ticker:
                continue

            trade_date = trade.get("exit_date") or trade.get("entry_date")
            if not trade_date:
                continue

            d = datetime.strptime(trade_date, "%Y-%m-%d").date()
            direction = trade.get("direction", "")
            quantity = trade.get("quantity", 0.0)

            self.trades_by_ticker[ticker.upper()].append({
                "date": d,
                "direction": direction,
                "ticker": ticker,
                "quantity": quantity,
            })

            ticker_trades[ticker.upper()].append({
                "date": d,
                "signed_qty": quantity if direction == "BUY" else -quantity,
            })

        # Second pass: build cumulative position timeline per ticker
        for ticker, t_list in ticker_trades.items():
            t_list.sort(key=lambda x: x["date"])
            cumulative = 0.0
            timeline = []
            for t in t_list:
                cumulative += t["signed_qty"]
                timeline.append((t["date"], cumulative))
            self.position_timeline[ticker] = timeline

    def _held_position_on_date(self, trade_ticker: str, check_date: date) -> bool:
        """Check if a non-zero position was held on check_date.
        Uses the last known cumulative position on or before check_date."""
        timeline = self.position_timeline.get(trade_ticker.upper(), [])
        if not timeline:
            return False

        # Find the last entry on or before check_date
        pos = 0.0
        for d, cum_qty in timeline:
            if d > check_date:
                break
            pos = cum_qty
        return abs(pos) > 0.01  # non-zero position

    def get_position_shares(self, yf_ticker: str, check_date: date) -> float:
        """Get cumulative share count on check_date. Returns 0 if no position."""
        candidates = TickerNormalizer.yfinance_to_trades_match(yf_ticker)
        for candidate in candidates:
            timeline = self.position_timeline.get(candidate.upper(), [])
            pos = 0.0
            for d, cum_qty in timeline:
                if d > check_date:
                    break
                pos = cum_qty
            if abs(pos) > 0.01:
                return pos
        return 0.0

    def is_acted_on(self, yf_ticker: str, meeting_date: date,
                    pre_days: int = 3, post_days: int = 7) -> tuple[bool, str]:
        """Check if ticker was acted on: held position OR traded in window.
        Returns (acted_on, reason) where reason is 'held'/'traded'/''.
        """
        candidates = TickerNormalizer.yfinance_to_trades_match(yf_ticker)

        # Check 1: held position on meeting date
        for candidate in candidates:
            if self._held_position_on_date(candidate, meeting_date):
                return True, "held"

        # Check 2: new trade within window
        window_start = meeting_date - timedelta(days=pre_days)
        window_end = meeting_date + timedelta(days=post_days)
        for candidate in candidates:
            for trade in self.trades_by_ticker.get(candidate.upper(), []):
                if window_start <= trade["date"] <= window_end:
                    return True, "traded"

        return False, ""

    def get_trades_in_window(self, yf_ticker: str, meeting_date: date,
                              pre_days: int = 3, post_days: int = 7) -> list[dict]:
        """Get all trades within the window."""
        window_start = meeting_date - timedelta(days=pre_days)
        window_end = meeting_date + timedelta(days=post_days)

        candidates = TickerNormalizer.yfinance_to_trades_match(yf_ticker)
        found = []
        for candidate in candidates:
            for trade in self.trades_by_ticker.get(candidate.upper(), []):
                if window_start <= trade["date"] <= window_end:
                    found.append(trade)
        return found


# ── Price Fetcher ───────────────────────────────────────────────

class PriceFetcher:
    """Fetch forward prices via yfinance with caching."""

    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self.cache: dict = {}
        self._load_cache()

    def _load_cache(self):
        """Load price cache from disk."""
        if self.use_cache and CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, encoding="utf-8") as f:
                    self.cache = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.cache = {}

    def _save_cache(self):
        """Save price cache to disk."""
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2, default=str)

    def _get_close_price(self, ticker: str, target_date: date, max_forward_days: int = 5) -> Optional[float]:
        """Get closing price on or near target_date (searching forward for weekends/holidays)."""
        cache_key = f"{ticker}_{target_date.isoformat()}"
        if cache_key in self.cache:
            val = self.cache[cache_key]
            return val if val is not None else None

        # Try local price cache first
        local_cache_file = PRICE_CACHE_DIR / f"{ticker}.json"
        if local_cache_file.exists():
            try:
                with open(local_cache_file, encoding="utf-8") as f:
                    local_data = json.load(f)
                # Local cache format: list of {date, close} or {date: close}
                if isinstance(local_data, dict):
                    for d_offset in range(max_forward_days + 1):
                        check_date = (target_date + timedelta(days=d_offset)).isoformat()
                        if check_date in local_data:
                            price = float(local_data[check_date])
                            self.cache[cache_key] = price
                            return price
            except (json.JSONDecodeError, OSError, ValueError):
                pass

        return None  # Will be fetched via yfinance batch

    def fetch_returns(self, ticker: str, base_date: date, windows: list[int] = None) -> dict:
        """Fetch forward returns for given windows (in trading days).
        Returns {7: 0.05, 30: 0.12, 90: -0.03} or None for failed lookups."""
        if windows is None:
            windows = [7, 30, 90]

        results = {}
        base_price = self._get_close_price(ticker, base_date)

        if base_price is None:
            # Need to fetch via yfinance
            base_price = self._yfinance_price(ticker, base_date)

        if base_price is None or base_price <= 0:
            return {w: None for w in windows}

        for w in windows:
            future_date = base_date + timedelta(days=int(w * 1.5))  # rough calendar days
            future_price = self._get_close_price(ticker, future_date)
            if future_price is None:
                future_price = self._yfinance_price(ticker, base_date + timedelta(days=w))
            if future_price is not None and future_price > 0:
                results[w] = (future_price - base_price) / base_price
            else:
                results[w] = None

        return results

    def batch_fetch(self, picks: list[dict], windows: list[int] = None):
        """Batch-fetch prices for all picks using yfinance download.
        Mutates picks in-place to add returns, excess_returns, entry_sensitivity."""
        if windows is None:
            windows = ALL_WINDOWS

        try:
            import yfinance as yf
        except ImportError:
            print("  [WARN] yfinance not installed, skipping price fetch")
            for pick in picks:
                pick["returns"] = {w: None for w in windows}
                pick["excess_returns"] = {w: None for w in windows}
                pick["spy_returns"] = {w: None for w in windows}
                pick["entry_sensitivity"] = {0: None, 1: None, 2: None}
            return

        # Collect unique (ticker, date) pairs
        ticker_dates: dict[str, set[date]] = defaultdict(set)
        for pick in picks:
            yf_ticker = pick["ticker_yf"]
            meeting_date = pick["meeting_date"]
            ticker_dates[yf_ticker].add(meeting_date)
            for w in windows:
                ticker_dates[yf_ticker].add(meeting_date + timedelta(days=int(w * 1.5)))

        # Find date range
        all_dates = []
        for dates in ticker_dates.values():
            all_dates.extend(dates)
        if not all_dates:
            return

        start_date = min(all_dates) - timedelta(days=7)
        end_date = min(max(all_dates) + timedelta(days=7), date.today())

        # Batch download (include SPY for benchmark)
        unique_tickers = list(ticker_dates.keys())
        if "SPY" not in unique_tickers:
            unique_tickers.append("SPY")
        print(f"  Fetching prices for {len(unique_tickers)} tickers ({start_date} to {end_date})...")

        # Download in batches of 50 to avoid timeouts
        all_prices = {}
        batch_size = 50
        for i in range(0, len(unique_tickers), batch_size):
            batch = unique_tickers[i:i + batch_size]
            try:
                df = yf.download(
                    batch,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    auto_adjust=True,
                    progress=False,
                )
                if df.empty:
                    continue

                if isinstance(df.columns, __import__("pandas").MultiIndex):
                    close_df = df["Close"]
                else:
                    close_df = df[["Close"]]
                    if len(batch) == 1:
                        close_df.columns = batch

                for ticker in batch:
                    if ticker in close_df.columns:
                        series = close_df[ticker].dropna()
                        all_prices[ticker] = {
                            d.date().isoformat(): float(v)
                            for d, v in series.items()
                        }
            except Exception as e:
                print(f"  [WARN] Failed batch {i}-{i+len(batch)}: {e}")

        # Inject privatized ticker prices
        for ticker, priv_info in TickerNormalizer.PRIVATIZED.items():
            if ticker in unique_tickers or ticker in all_prices:
                prices = all_prices.setdefault(ticker, {})
                fprice = priv_info["final_price"]
                delist = priv_info["delist_date"]
                if not prices:
                    # yfinance returned nothing — fill ALL dates with deal price
                    d = start_date
                    while d <= end_date:
                        prices[d.isoformat()] = fprice
                        d += timedelta(days=1)
                    print(f"  [INFO] {ticker}: no yfinance data, using ${fprice} for all dates (privatized)")
                else:
                    # yfinance has some data — only fill post-delist
                    d = delist
                    while d <= end_date:
                        prices.setdefault(d.isoformat(), fprice)
                        d += timedelta(days=1)
                    print(f"  [INFO] {ticker}: injected ${fprice} for dates after {delist} (privatized)")

        # Cache all fetched prices
        for ticker, prices in all_prices.items():
            for d_str, price in prices.items():
                self.cache[f"{ticker}_{d_str}"] = price

        # SPY prices for benchmark
        spy_prices = all_prices.get("SPY", {})

        # Compute returns for each pick
        for pick in picks:
            yf_ticker = pick["ticker_yf"]
            meeting_date = pick["meeting_date"]
            prices = all_prices.get(yf_ticker, {})

            base_price = self._find_nearest_price(prices, meeting_date, forward=True)
            spy_base = self._find_nearest_price(spy_prices, meeting_date, forward=True)

            returns = {}
            spy_rets = {}
            excess = {}
            for w in windows:
                target = meeting_date + timedelta(days=w)
                future_price = self._find_nearest_price(prices, target, forward=True)
                spy_future = self._find_nearest_price(spy_prices, target, forward=True)

                if base_price and future_price and base_price > 0:
                    returns[w] = (future_price - base_price) / base_price
                else:
                    returns[w] = None

                if spy_base and spy_future and spy_base > 0:
                    spy_rets[w] = (spy_future - spy_base) / spy_base
                else:
                    spy_rets[w] = None

                if returns[w] is not None and spy_rets[w] is not None:
                    excess[w] = returns[w] - spy_rets[w]
                else:
                    excess[w] = None

            pick["returns"] = returns
            pick["spy_returns"] = spy_rets
            pick["excess_returns"] = excess
            pick["base_price"] = base_price

            # Entry sensitivity: 30d returns with base shifted +0/+1/+2 days
            entry_sens = {}
            for offset in [0, 1, 2]:
                shifted_date = meeting_date + timedelta(days=offset)
                shifted_base = self._find_nearest_price(prices, shifted_date, forward=True)
                target_30 = shifted_date + timedelta(days=30)
                shifted_future = self._find_nearest_price(prices, target_30, forward=True)
                if shifted_base and shifted_future and shifted_base > 0:
                    entry_sens[offset] = (shifted_future - shifted_base) / shifted_base
                else:
                    entry_sens[offset] = None
            pick["entry_sensitivity"] = entry_sens

        self._save_cache()

    @staticmethod
    def _find_nearest_price(prices: dict, target_date: date, forward: bool = True,
                            max_days: int = 5) -> Optional[float]:
        """Find the nearest available price to target_date."""
        for offset in range(max_days + 1):
            d = target_date + timedelta(days=offset if forward else -offset)
            d_str = d.isoformat()
            if d_str in prices:
                return prices[d_str]
        # Try the other direction
        for offset in range(1, max_days + 1):
            d = target_date + timedelta(days=-offset if forward else offset)
            d_str = d.isoformat()
            if d_str in prices:
                return prices[d_str]
        return None

    def _yfinance_price(self, ticker: str, target_date: date) -> Optional[float]:
        """Fetch a single price via yfinance (fallback)."""
        try:
            import yfinance as yf
            start = target_date - timedelta(days=3)
            end = target_date + timedelta(days=7)
            df = yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                             auto_adjust=True, progress=False)
            if df.empty:
                return None
            # Find nearest date
            for offset in range(8):
                d = target_date + timedelta(days=offset)
                if d in df.index:
                    price = float(df.loc[d, "Close"])
                    self.cache[f"{ticker}_{d.isoformat()}"] = price
                    return price
            return None
        except Exception:
            return None


# ── Aggregator ──────────────────────────────────────────────────

class Aggregator:
    """Aggregate picks into 5 groups and compute statistics."""

    GROUPS = {
        "bullish_acted": "Bullish + Acted On",
        "bullish_discussed": "Bullish + Discussed Only",
        "bearish_acted": "Bearish + Acted On",
        "bearish_discussed": "Bearish + Discussed Only",
        "neutral": "Neutral / Unknown",
    }

    @staticmethod
    def classify_pick(pick: dict) -> str:
        """Assign a pick to one of the 5 groups."""
        sentiment = pick["sentiment"]
        acted = pick["acted_on"]

        if sentiment == Sentiment.BULLISH:
            return "bullish_acted" if acted else "bullish_discussed"
        elif sentiment == Sentiment.BEARISH:
            return "bearish_acted" if acted else "bearish_discussed"
        else:
            return "neutral"

    @staticmethod
    def aggregate(picks: list[dict], windows: list[int] = None) -> dict:
        """Compute group-level statistics including excess returns."""
        if windows is None:
            windows = MAIN_WINDOWS

        groups = defaultdict(list)
        for pick in picks:
            group = Aggregator.classify_pick(pick)
            groups[group].append(pick)

        stats = {}
        for group_key, group_name in Aggregator.GROUPS.items():
            group_picks = groups.get(group_key, [])
            group_stats = {
                "name": group_name,
                "count": len(group_picks),
                "picks": group_picks,
            }

            for w in windows:
                returns = [p["returns"][w] for p in group_picks
                           if p.get("returns", {}).get(w) is not None]
                excess = [p["excess_returns"][w] for p in group_picks
                          if p.get("excess_returns", {}).get(w) is not None]
                if returns:
                    group_stats[f"avg_{w}d"] = mean(returns)
                    group_stats[f"med_{w}d"] = median(returns)
                    group_stats[f"win_rate_{w}d"] = sum(1 for r in returns if r > 0) / len(returns)
                    group_stats[f"n_{w}d"] = len(returns)
                else:
                    group_stats[f"avg_{w}d"] = None
                    group_stats[f"med_{w}d"] = None
                    group_stats[f"win_rate_{w}d"] = None
                    group_stats[f"n_{w}d"] = 0

                if excess:
                    group_stats[f"excess_avg_{w}d"] = mean(excess)
                    group_stats[f"excess_med_{w}d"] = median(excess)
                    group_stats[f"excess_wr_{w}d"] = sum(1 for r in excess if r > 0) / len(excess)
                else:
                    group_stats[f"excess_avg_{w}d"] = None
                    group_stats[f"excess_med_{w}d"] = None
                    group_stats[f"excess_wr_{w}d"] = None

            # Entry sensitivity stats (30d returns at different entry offsets)
            for offset in [0, 1, 2]:
                es = [p["entry_sensitivity"][offset] for p in group_picks
                      if p.get("entry_sensitivity", {}).get(offset) is not None]
                if es:
                    group_stats[f"entry_{offset}_avg"] = mean(es)
                    group_stats[f"entry_{offset}_med"] = median(es)
                else:
                    group_stats[f"entry_{offset}_avg"] = None
                    group_stats[f"entry_{offset}_med"] = None

            stats[group_key] = group_stats

        return stats


# ── Portfolio Analyzer ─────────────────────────────────────────

class PortfolioAnalyzer:
    """Advanced portfolio analysis: rolling baskets, regime conditioning, bootstrap."""

    @staticmethod
    def rolling_portfolio(picks: list[dict], hold_days: int = 30) -> dict:
        """Build equal-weight basket per meeting, compute portfolio statistics.

        Each meeting creates a basket of bullish picks with hold_days forward returns.
        Baskets are treated as sequential bets for portfolio statistics.
        """
        meeting_baskets = defaultdict(list)
        for p in picks:
            if p["sentiment"] == Sentiment.BULLISH:
                meeting_baskets[p["meeting_date"]].append(p)

        if not meeting_baskets:
            return {"error": "No bullish picks"}

        sorted_dates = sorted(meeting_baskets.keys())

        # Compute per-basket returns
        basket_data = []
        for md in sorted_dates:
            basket = meeting_baskets[md]
            rets = [p["returns"].get(hold_days) for p in basket
                    if p.get("returns", {}).get(hold_days) is not None]
            exc = [p["excess_returns"].get(hold_days) for p in basket
                   if p.get("excess_returns", {}).get(hold_days) is not None]

            if rets:
                basket_data.append({
                    "date": md,
                    "return": mean(rets),
                    "excess": mean(exc) if exc else None,
                    "n_picks": len(rets),
                })

        if len(basket_data) < 3:
            return {"error": f"Only {len(basket_data)} baskets, need >= 3"}

        rets = [b["return"] for b in basket_data]
        exc = [b["excess"] for b in basket_data if b["excess"] is not None]

        # Cumulative returns and drawdown
        cum = 1.0
        peak = 1.0
        max_dd = 0.0
        cum_excess = 1.0
        peak_exc = 1.0
        max_dd_exc = 0.0

        for b in basket_data:
            cum *= (1 + b["return"])
            if cum > peak:
                peak = cum
            dd = (cum - peak) / peak
            if dd < max_dd:
                max_dd = dd

            if b["excess"] is not None:
                cum_excess *= (1 + b["excess"])
                if cum_excess > peak_exc:
                    peak_exc = cum_excess
                dd_e = (cum_excess - peak_exc) / peak_exc
                if dd_e < max_dd_exc:
                    max_dd_exc = dd_e

        total_return = cum - 1
        total_excess = cum_excess - 1

        # Time span
        days_span = (sorted_dates[-1] - sorted_dates[0]).days
        years = max(days_span / 365.25, 0.1)
        baskets_per_year = len(rets) / years

        mean_ret = mean(rets)
        std_ret = (sum((r - mean_ret) ** 2 for r in rets) / len(rets)) ** 0.5

        ann_return = (1 + total_return) ** (1 / years) - 1
        ann_vol = std_ret * (baskets_per_year ** 0.5)
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0

        exc_sharpe = None
        if exc:
            mean_exc = mean(exc)
            std_exc = (sum((e - mean_exc) ** 2 for e in exc) / len(exc)) ** 0.5
            exc_ann_vol = std_exc * (baskets_per_year ** 0.5)
            exc_ann = (1 + total_excess) ** (1 / years) - 1
            exc_sharpe = exc_ann / exc_ann_vol if exc_ann_vol > 0 else 0

        if len(rets) > 2 and std_ret > 0:
            skew = sum((r - mean_ret) ** 3 for r in rets) / (len(rets) * std_ret ** 3)
            kurt = sum((r - mean_ret) ** 4 for r in rets) / (len(rets) * std_ret ** 4) - 3
        else:
            skew = kurt = 0

        return {
            "baskets": basket_data,
            "total_return": total_return,
            "ann_return": ann_return,
            "ann_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "max_drawdown_excess": max_dd_exc,
            "n_baskets": len(basket_data),
            "win_rate": sum(1 for r in rets if r > 0) / len(rets),
            "skewness": skew,
            "kurtosis": kurt,
            "mean_basket_return": mean_ret,
            "median_basket_return": median(rets),
            "total_excess": total_excess,
            "excess_sharpe": exc_sharpe,
            "avg_picks_per_basket": mean(b["n_picks"] for b in basket_data),
            "years": years,
        }

    @staticmethod
    def regime_analysis(picks: list[dict]) -> dict:
        """Condition backtest on market regime (SPY 50D MA, VIX level)."""
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            return {"error": "yfinance/pandas not installed"}

        meeting_dates = sorted(set(p["meeting_date"] for p in picks))
        if not meeting_dates:
            return {"error": "No picks"}

        start = meeting_dates[0] - timedelta(days=80)
        end = min(meeting_dates[-1] + timedelta(days=7), date.today())

        spy_df = yf.download("SPY", start=start.isoformat(), end=end.isoformat(),
                             auto_adjust=True, progress=False)
        vix_df = yf.download("^VIX", start=start.isoformat(), end=end.isoformat(),
                             auto_adjust=True, progress=False)

        if spy_df.empty:
            return {"error": "Failed to download SPY"}

        # Handle potential MultiIndex
        spy_close = spy_df["Close"]
        if hasattr(spy_close, "columns"):
            spy_close = spy_close.squeeze()
        spy_ma50 = spy_close.rolling(50).mean()

        vix_close = None
        vix_median = None
        if not vix_df.empty:
            vix_close = vix_df["Close"]
            if hasattr(vix_close, "columns"):
                vix_close = vix_close.squeeze()
            vix_median = float(vix_close.median())

        # Classify each meeting date
        regime_data = {}
        for md in meeting_dates:
            md_ts = pd.Timestamp(md)
            spy_above_ma = None
            vix_level = None

            for offset in range(5):
                check = md_ts - pd.Timedelta(days=offset)
                if check in spy_close.index and check in spy_ma50.index:
                    s = float(spy_close.loc[check]) if not hasattr(spy_close.loc[check], '__len__') else float(spy_close.loc[check].iloc[0])
                    m = float(spy_ma50.loc[check]) if not hasattr(spy_ma50.loc[check], '__len__') else float(spy_ma50.loc[check].iloc[0])
                    if not (s != s) and not (m != m):  # NaN check
                        spy_above_ma = s > m
                        break

            if vix_close is not None:
                for offset in range(5):
                    check = md_ts - pd.Timedelta(days=offset)
                    if check in vix_close.index:
                        v = float(vix_close.loc[check]) if not hasattr(vix_close.loc[check], '__len__') else float(vix_close.loc[check].iloc[0])
                        if not (v != v):
                            vix_level = v
                            break

            regime_data[md] = {
                "spy_above_ma50": spy_above_ma,
                "vix_level": vix_level,
                "vix_high": vix_level > vix_median if vix_level is not None and vix_median is not None else None,
            }

        results = {}
        for regime_name, filter_fn in [
            ("SPY > 50D MA", lambda md: regime_data.get(md, {}).get("spy_above_ma50") is True),
            ("SPY < 50D MA", lambda md: regime_data.get(md, {}).get("spy_above_ma50") is False),
            ("VIX Low", lambda md: regime_data.get(md, {}).get("vix_high") is False),
            ("VIX High", lambda md: regime_data.get(md, {}).get("vix_high") is True),
        ]:
            regime_picks = [p for p in picks if filter_fn(p["meeting_date"])]
            bullish = [p for p in regime_picks if p["sentiment"] == Sentiment.BULLISH]
            bearish = [p for p in regime_picks if p["sentiment"] == Sentiment.BEARISH]

            bull_exc = [p["excess_returns"][30] for p in bullish
                        if p.get("excess_returns", {}).get(30) is not None]
            bear_exc = [p["excess_returns"][30] for p in bearish
                        if p.get("excess_returns", {}).get(30) is not None]

            results[regime_name] = {
                "total_picks": len(regime_picks),
                "bull_n": len(bullish),
                "bear_n": len(bearish),
                "bull_exc_30d": mean(bull_exc) if bull_exc else None,
                "bull_wr_30d": sum(1 for e in bull_exc if e > 0) / len(bull_exc) if bull_exc else None,
                "bear_exc_30d": mean(bear_exc) if bear_exc else None,
            }

        results["vix_median"] = vix_median
        return results

    @staticmethod
    def bootstrap_test(picks: list[dict], n_iterations: int = 1000) -> dict:
        """Placebo test: randomize ticker assignments, compare to actual results.

        For each iteration, randomly sample the same number of returns from
        the full pool. Tests whether actual selection outperforms random.
        """
        bullish_acted = [p for p in picks
                         if p["sentiment"] == Sentiment.BULLISH and p["acted_on"]
                         and p.get("excess_returns", {}).get(30) is not None]

        if len(bullish_acted) < 5:
            return {"error": "Too few bullish+acted picks for bootstrap"}

        actual_excess = mean(p["excess_returns"][30] for p in bullish_acted)

        all_excess = [p["excess_returns"][30] for p in picks
                      if p.get("excess_returns", {}).get(30) is not None]

        if not all_excess:
            return {"error": "No excess returns available"}

        n_sample = len(bullish_acted)
        random.seed(42)
        random_means = sorted(mean(random.choices(all_excess, k=n_sample))
                              for _ in range(n_iterations))

        percentile = sum(1 for r in random_means if r < actual_excess) / n_iterations * 100

        # Also test bearish-discussed
        bearish_discussed = [p for p in picks
                             if p["sentiment"] == Sentiment.BEARISH and not p["acted_on"]
                             and p.get("excess_returns", {}).get(30) is not None]

        bear_result = {}
        if len(bearish_discussed) >= 5:
            actual_bear = mean(p["excess_returns"][30] for p in bearish_discussed)
            n_bear = len(bearish_discussed)
            bear_random = sorted(mean(random.choices(all_excess, k=n_bear))
                                 for _ in range(n_iterations))
            bear_percentile = sum(1 for r in bear_random if r > actual_bear) / n_iterations * 100
            bear_result = {
                "bear_actual": actual_bear,
                "bear_random_mean": mean(bear_random),
                "bear_random_5th": bear_random[int(0.05 * n_iterations)],
                "bear_random_95th": bear_random[int(0.95 * n_iterations)],
                "bear_percentile": bear_percentile,
                "bear_n": n_bear,
            }

        # Simple out-of-sample: first 2/3 vs last 1/3
        sorted_bull = sorted(bullish_acted, key=lambda p: p["meeting_date"])
        split_idx = len(sorted_bull) * 2 // 3
        if split_idx >= 5 and len(sorted_bull) - split_idx >= 3:
            train_excess = mean(p["excess_returns"][30] for p in sorted_bull[:split_idx])
            test_excess = mean(p["excess_returns"][30] for p in sorted_bull[split_idx:])
        else:
            train_excess = test_excess = None

        return {
            "actual_excess": actual_excess,
            "random_mean": mean(random_means),
            "random_std": (sum((r - mean(random_means)) ** 2 for r in random_means) / len(random_means)) ** 0.5,
            "random_5th": random_means[int(0.05 * n_iterations)],
            "random_95th": random_means[int(0.95 * n_iterations)],
            "percentile": percentile,
            "n_iterations": n_iterations,
            "n_sample": n_sample,
            "train_excess": train_excess,
            "test_excess": test_excess,
            **bear_result,
        }

    @staticmethod
    def sector_attribution(picks: list[dict]) -> dict:
        """Sector attribution: is alpha from stock selection or sector allocation?"""
        try:
            import yfinance as yf
        except ImportError:
            return {}

        # Classify picks into sectors
        for p in picks:
            p["sector"] = SECTOR_MAP.get(p["ticker_yf"], "Other")

        # Collect needed sector ETFs
        sectors_needed = set(p["sector"] for p in picks)
        etf_map = {s: SECTOR_ETFS.get(s, "SPY") for s in sectors_needed}
        unique_etfs = list(set(etf_map.values()))

        # Date range
        dates = [p["meeting_date"] for p in picks]
        start = min(dates) - timedelta(days=7)
        end = min(max(dates) + timedelta(days=200), date.today())

        # Download sector ETF prices
        print("  Downloading sector ETF prices for attribution...")
        etf_prices = {}
        try:
            df = yf.download(unique_etfs, start=start.isoformat(),
                             end=end.isoformat(), auto_adjust=True, progress=False)
            if not df.empty:
                import pandas as pd
                if isinstance(df.columns, pd.MultiIndex):
                    close_df = df["Close"]
                else:
                    close_df = df[["Close"]]
                    if len(unique_etfs) == 1:
                        close_df.columns = unique_etfs
                for etf in unique_etfs:
                    if etf in close_df.columns:
                        series = close_df[etf].dropna()
                        etf_prices[etf] = {
                            d.date().isoformat(): float(v) for d, v in series.items()
                        }
        except Exception as e:
            print(f"  [WARN] Sector ETF download failed: {e}")
            return {}

        # Compute sector-adjusted excess for each pick
        for p in picks:
            etf = etf_map[p["sector"]]
            prices = etf_prices.get(etf, {})
            sect_excess = {}
            for w in [7, 30, 90]:
                raw = p.get("returns", {}).get(w)
                if raw is None:
                    sect_excess[w] = None
                    continue
                base = PriceFetcher._find_nearest_price(prices, p["meeting_date"])
                future = PriceFetcher._find_nearest_price(
                    prices, p["meeting_date"] + timedelta(days=w))
                if base and future and base > 0:
                    sect_excess[w] = raw - (future - base) / base
                else:
                    sect_excess[w] = None
            p["sector_excess"] = sect_excess

        # Aggregate by group: compare SPY-adjusted vs sector-adjusted
        group_results = {}
        for group_key, group_name in Aggregator.GROUPS.items():
            gp = [p for p in picks if Aggregator.classify_pick(p) == group_key]
            valid = [p for p in gp
                     if p.get("sector_excess", {}).get(30) is not None
                     and p.get("excess_returns", {}).get(30) is not None]
            if valid:
                group_results[group_key] = {
                    "name": group_name,
                    "n": len(valid),
                    "spy_excess_30": mean(p["excess_returns"][30] for p in valid),
                    "sector_excess_30": mean(p["sector_excess"][30] for p in valid),
                }

        # Breakdown by sector for bullish picks
        sector_breakdown = {}
        bullish = [p for p in picks
                   if p.get("sentiment") == Sentiment.BULLISH
                   and p.get("sector_excess", {}).get(30) is not None
                   and p.get("excess_returns", {}).get(30) is not None
                   and p.get("returns", {}).get(30) is not None]
        for sector in sorted(sectors_needed):
            sp = [p for p in bullish if p["sector"] == sector]
            if len(sp) >= 2:
                sector_breakdown[sector] = {
                    "n": len(sp),
                    "raw_avg": mean(p["returns"][30] for p in sp),
                    "spy_excess": mean(p["excess_returns"][30] for p in sp),
                    "sector_excess": mean(p["sector_excess"][30] for p in sp),
                    "etf": etf_map[sector],
                }

        return {"groups": group_results, "sectors": sector_breakdown}

    # Approximate FX rates to USD for non-USD tickers
    FX_TO_USD = {
        ".HK": 1 / 7.8,    # HKD → USD
        ".T": 1 / 150.0,   # JPY → USD
        ".PA": 1.08,        # EUR → USD
        ".L": 1.27,         # GBP → USD (prices in pence, handled below)
        ".SW": 1.12,        # CHF → USD
        ".SZ": 1 / 7.2,    # CNY → USD
        ".SS": 1 / 7.2,    # CNY → USD
        ".DE": 1.08,        # EUR → USD
    }

    @staticmethod
    def _to_usd(ticker: str, local_value: float) -> float:
        """Convert a local-currency value to approximate USD."""
        for suffix, rate in PortfolioAnalyzer.FX_TO_USD.items():
            if ticker.upper().endswith(suffix):
                # London stocks: prices in pence, convert to pounds first
                if suffix == ".L":
                    return local_value / 100 * rate
                return local_value * rate
        return local_value  # assume USD

    @staticmethod
    def position_weighted(picks: list[dict]) -> dict:
        """Compare equal-weight vs position-weighted returns for acted picks."""
        held = [p for p in picks
                if p.get("acted_reason") == "held"
                and p.get("returns", {}).get(30) is not None
                and p.get("base_price")
                and p.get("position_shares")]

        if len(held) < 5:
            return {}

        # Compute dollar exposure per pick (convert non-USD to USD)
        for p in held:
            local_value = abs(p["position_shares"]) * p["base_price"]
            p["position_value"] = PortfolioAnalyzer._to_usd(
                p["ticker_yf"], local_value)

        total_value = sum(p["position_value"] for p in held)
        if total_value <= 0:
            return {}

        # Position-weighted returns
        pw_returns = {}
        ew_returns = {}
        for w in [7, 30, 90]:
            valid = [p for p in held if p.get("returns", {}).get(w) is not None]
            valid_excess = [p for p in held if p.get("excess_returns", {}).get(w) is not None]
            if not valid:
                continue
            tv = sum(p["position_value"] for p in valid)
            if tv > 0:
                pw_returns[w] = sum(
                    p["returns"][w] * p["position_value"] / tv for p in valid)
            ew_returns[w] = mean(p["returns"][w] for p in valid)

            if valid_excess:
                tv_e = sum(p["position_value"] for p in valid_excess)
                if tv_e > 0:
                    pw_returns[f"excess_{w}"] = sum(
                        p["excess_returns"][w] * p["position_value"] / tv_e
                        for p in valid_excess)
                ew_returns[f"excess_{w}"] = mean(
                    p["excess_returns"][w] for p in valid_excess)

        # Top 10 positions by dollar value
        sorted_held = sorted(held, key=lambda p: p["position_value"], reverse=True)
        top_positions = []
        for p in sorted_held[:10]:
            top_positions.append({
                "ticker": p["ticker_yf"],
                "date": p["meeting_date"],
                "shares": p["position_shares"],
                "value": p["position_value"],
                "pct_of_total": p["position_value"] / total_value,
                "return_30": p["returns"].get(30),
                "excess_30": p["excess_returns"].get(30),
            })

        return {
            "n_held": len(held),
            "total_value": total_value,
            "pw_returns": pw_returns,
            "ew_returns": ew_returns,
            "top_positions": top_positions,
        }

    @staticmethod
    def oos_attribution(picks: list[dict]) -> dict:
        """OOS attribution: what went wrong in the test period?"""
        bullish = [p for p in picks
                   if p.get("sentiment") == Sentiment.BULLISH
                   and p.get("excess_returns", {}).get(30) is not None]

        if len(bullish) < 10:
            return {}

        sorted_bull = sorted(bullish, key=lambda p: p["meeting_date"])
        split_idx = len(sorted_bull) * 2 // 3

        train = sorted_bull[:split_idx]
        test = sorted_bull[split_idx:]

        if len(test) < 5:
            return {}

        train_excess = mean(p["excess_returns"][30] for p in train)
        test_excess = mean(p["excess_returns"][30] for p in test)
        split_date = test[0]["meeting_date"]

        # Worst detractors in test period
        test_sorted = sorted(test, key=lambda p: p["excess_returns"][30])
        detractors = []
        for p in test_sorted[:10]:
            detractors.append({
                "ticker": p["ticker_yf"],
                "date": p["meeting_date"],
                "excess_30": p["excess_returns"][30],
                "raw_30": p["returns"].get(30),
                "acted": p["acted_on"],
                "sector": p.get("sector", "Other"),
            })

        # Best performers in test period
        contributors = []
        for p in reversed(test_sorted[-10:]):
            contributors.append({
                "ticker": p["ticker_yf"],
                "date": p["meeting_date"],
                "excess_30": p["excess_returns"][30],
                "raw_30": p["returns"].get(30),
                "acted": p["acted_on"],
                "sector": p.get("sector", "Other"),
            })

        # Sector distribution in test period
        sector_counts = defaultdict(lambda: {"n": 0, "excess_sum": 0.0})
        for p in test:
            s = p.get("sector", "Other")
            sector_counts[s]["n"] += 1
            sector_counts[s]["excess_sum"] += p["excess_returns"][30]

        sector_avg = {}
        for s, data in sector_counts.items():
            if data["n"] >= 2:
                sector_avg[s] = {
                    "n": data["n"],
                    "avg_excess": data["excess_sum"] / data["n"],
                }

        # Acted vs discussed in each period
        train_acted = [p for p in train if p["acted_on"]]
        train_discussed = [p for p in train if not p["acted_on"]]
        test_acted = [p for p in test if p["acted_on"]]
        test_discussed = [p for p in test if not p["acted_on"]]

        period_split = {}
        if train_acted:
            period_split["train_acted"] = mean(p["excess_returns"][30] for p in train_acted)
        if train_discussed:
            period_split["train_discussed"] = mean(p["excess_returns"][30] for p in train_discussed)
        if test_acted:
            period_split["test_acted"] = mean(p["excess_returns"][30] for p in test_acted)
        if test_discussed:
            period_split["test_discussed"] = mean(p["excess_returns"][30] for p in test_discussed)

        return {
            "split_date": split_date,
            "train_n": len(train),
            "test_n": len(test),
            "train_excess": train_excess,
            "test_excess": test_excess,
            "detractors": detractors,
            "contributors": contributors,
            "sector_avg": sector_avg,
            "period_split": period_split,
        }

    @staticmethod
    def conviction_consistency(picks: list[dict]) -> dict:
        """Conviction Consistency Attribution: do repeated signals predict better?

        Since all picks come from a single analyst (Robin), we reframe
        "analyst attribution" as conviction consistency — tracking whether
        stocks mentioned multiple times with consistent sentiment outperform
        one-off mentions or stocks with flip-flopping sentiment.
        """
        from collections import Counter

        # Group picks by ticker
        ticker_picks = defaultdict(list)
        for p in picks:
            if p.get("excess_returns", {}).get(30) is not None:
                ticker_picks[p["ticker_yf"]].append(p)

        if not ticker_picks:
            return {}

        # Classify each ticker's conviction pattern
        # Categories: consistent_bull, consistent_bear, flip_flop, one_off
        categories = {}
        for ticker, tpicks in ticker_picks.items():
            sentiments = [p["sentiment"] for p in tpicks]
            n = len(tpicks)

            bull_count = sentiments.count(Sentiment.BULLISH)
            bear_count = sentiments.count(Sentiment.BEARISH)

            if n == 1:
                cat = "one_off"
            elif bull_count >= n * 0.6 and bear_count == 0:
                cat = "consistent_bull"
            elif bear_count >= n * 0.6 and bull_count == 0:
                cat = "consistent_bear"
            elif bull_count > 0 and bear_count > 0:
                cat = "flip_flop"
            else:
                cat = "mixed_neutral"

            # Compute average excess for this ticker across all its mentions
            excesses = [p["excess_returns"][30] for p in tpicks]
            acted_any = any(p["acted_on"] for p in tpicks)

            categories[ticker] = {
                "category": cat,
                "mentions": n,
                "bull_count": bull_count,
                "bear_count": bear_count,
                "avg_excess": mean(excesses),
                "acted": acted_any,
                "picks": tpicks,
            }

        # Aggregate by category
        cat_stats = defaultdict(lambda: {
            "tickers": [], "n_mentions": 0, "excesses": [],
            "acted_excesses": [], "not_acted_excesses": [],
        })
        for ticker, info in categories.items():
            cat = info["category"]
            cat_stats[cat]["tickers"].append(ticker)
            cat_stats[cat]["n_mentions"] += info["mentions"]
            for p in info["picks"]:
                ex = p["excess_returns"][30]
                cat_stats[cat]["excesses"].append(ex)
                if p["acted_on"]:
                    cat_stats[cat]["acted_excesses"].append(ex)
                else:
                    cat_stats[cat]["not_acted_excesses"].append(ex)

        summary = {}
        for cat, data in cat_stats.items():
            summary[cat] = {
                "n_tickers": len(data["tickers"]),
                "n_mentions": data["n_mentions"],
                "avg_excess": mean(data["excesses"]) if data["excesses"] else 0,
                "acted_excess": mean(data["acted_excesses"]) if data["acted_excesses"] else None,
                "not_acted_excess": mean(data["not_acted_excesses"]) if data["not_acted_excesses"] else None,
            }

        # Top consistent bulls that were NOT acted on (biggest missed conviction)
        missed_convictions = []
        for ticker, info in categories.items():
            if info["category"] == "consistent_bull" and not info["acted"]:
                missed_convictions.append({
                    "ticker": ticker,
                    "mentions": info["mentions"],
                    "avg_excess": info["avg_excess"],
                })
        missed_convictions.sort(key=lambda x: x["avg_excess"], reverse=True)

        # Flip-floppers: stocks where sentiment changed direction
        flip_detail = []
        for ticker, info in categories.items():
            if info["category"] == "flip_flop":
                flip_detail.append({
                    "ticker": ticker,
                    "mentions": info["mentions"],
                    "bull_count": info["bull_count"],
                    "bear_count": info["bear_count"],
                    "avg_excess": info["avg_excess"],
                    "acted": info["acted"],
                })
        flip_detail.sort(key=lambda x: x["mentions"], reverse=True)

        # Frequency vs performance: do more-discussed stocks do better?
        freq_buckets = {"1x": [], "2-3x": [], "4+x": []}
        for ticker, info in categories.items():
            for p in info["picks"]:
                if p["sentiment"] == Sentiment.BULLISH:
                    ex = p["excess_returns"][30]
                    if info["mentions"] == 1:
                        freq_buckets["1x"].append(ex)
                    elif info["mentions"] <= 3:
                        freq_buckets["2-3x"].append(ex)
                    else:
                        freq_buckets["4+x"].append(ex)

        freq_summary = {}
        for bucket, excs in freq_buckets.items():
            if excs:
                freq_summary[bucket] = {
                    "n": len(excs),
                    "avg_excess": mean(excs),
                    "win_rate": sum(1 for e in excs if e > 0) / len(excs),
                }

        return {
            "summary": summary,
            "missed_convictions": missed_convictions[:10],
            "flip_detail": flip_detail[:15],
            "freq_summary": freq_summary,
            "total_tickers": len(ticker_picks),
        }

    @staticmethod
    def trade_management_sim(picks: list[dict]) -> dict:
        """Simulate mechanical stop-loss / take-profit / time-stop rules.

        Tests rules on bullish+acted picks using ALL_WINDOWS return data:
        - Stop-loss: exit if drawdown hits threshold (using min of available windows)
        - Take-profit: exit if gain hits threshold
        - Time-stop: force exit at N days regardless
        - Combined: stop-loss + take-profit together

        Uses available window returns (1,3,7,14,21,30,45,60,90,180d) as checkpoints.
        """
        bullish_acted = [p for p in picks
                         if p.get("sentiment") == Sentiment.BULLISH
                         and p.get("acted_on")
                         and p.get("returns", {}).get(30) is not None]

        if len(bullish_acted) < 10:
            return {}

        checkpoints = [1, 3, 7, 14, 21, 30, 45, 60, 90, 180]

        def simulate_rule(picks_list, stop_loss=None, take_profit=None,
                          time_stop=None) -> dict:
            """Simulate a single rule. Returns stats about the exits."""
            exits = []
            for p in picks_list:
                rets = p.get("returns", {})
                exit_day = None
                exit_return = None

                for day in checkpoints:
                    r = rets.get(day)
                    if r is None:
                        continue

                    # Time stop: exit at this day
                    if time_stop and day >= time_stop:
                        exit_day = day
                        exit_return = r
                        break

                    # Stop-loss: exit if return < threshold
                    if stop_loss and r <= stop_loss:
                        exit_day = day
                        exit_return = r
                        break

                    # Take-profit: exit if return > threshold
                    if take_profit and r >= take_profit:
                        exit_day = day
                        exit_return = r
                        break

                # If no rule triggered, use last available return
                if exit_return is None:
                    for day in reversed(checkpoints):
                        r = rets.get(day)
                        if r is not None:
                            exit_day = day
                            exit_return = r
                            break

                if exit_return is not None:
                    # Get SPY return for the same period
                    spy_ret = p.get("spy_returns", {}).get(exit_day, 0)
                    exits.append({
                        "ticker": p["ticker_yf"],
                        "date": p["meeting_date"],
                        "exit_day": exit_day,
                        "exit_return": exit_return,
                        "excess": exit_return - spy_ret,
                    })

            if not exits:
                return {}

            returns = [e["exit_return"] for e in exits]
            excesses = [e["excess"] for e in exits]
            avg_hold = mean(e["exit_day"] for e in exits)

            return {
                "n": len(exits),
                "avg_return": mean(returns),
                "avg_excess": mean(excesses),
                "median_return": median(returns),
                "win_rate": sum(1 for r in returns if r > 0) / len(returns),
                "avg_hold_days": avg_hold,
                "worst": min(returns),
                "best": max(returns),
            }

        # Baseline: buy & hold to 30d
        baseline = simulate_rule(bullish_acted, time_stop=30)

        # Rule simulations
        rules = {}

        # Stop-loss rules
        for sl in [-0.05, -0.10, -0.15, -0.20]:
            label = f"止损 {sl:.0%}"
            rules[label] = simulate_rule(bullish_acted, stop_loss=sl)

        # Take-profit rules
        for tp in [0.10, 0.15, 0.20, 0.30]:
            label = f"止盈 +{tp:.0%}"
            rules[label] = simulate_rule(bullish_acted, take_profit=tp)

        # Time-stop rules
        for ts in [14, 30, 45, 60, 90]:
            label = f"持有 {ts}天"
            rules[label] = simulate_rule(bullish_acted, time_stop=ts)

        # Combined rules (stop-loss + take-profit)
        combos = [
            (-0.10, 0.20, "止损-10% / 止盈+20%"),
            (-0.10, 0.30, "止损-10% / 止盈+30%"),
            (-0.15, 0.20, "止损-15% / 止盈+20%"),
            (-0.05, 0.15, "止损-5% / 止盈+15%"),
        ]
        for sl, tp, label in combos:
            rules[label] = simulate_rule(bullish_acted, stop_loss=sl, take_profit=tp)

        # Combined with time stop
        timed_combos = [
            (-0.10, 0.20, 45, "止损-10% / 止盈+20% / 45天"),
            (-0.10, 0.30, 90, "止损-10% / 止盈+30% / 90天"),
        ]
        for sl, tp, ts, label in timed_combos:
            rules[label] = simulate_rule(bullish_acted, stop_loss=sl,
                                         take_profit=tp, time_stop=ts)

        # Find optimal rule (highest avg excess)
        best_rule = None
        best_excess = baseline.get("avg_excess", 0) if baseline else 0
        for label, result in rules.items():
            if result and result.get("avg_excess", 0) > best_excess:
                best_excess = result["avg_excess"]
                best_rule = label

        return {
            "baseline": baseline,
            "rules": rules,
            "best_rule": best_rule,
            "n_picks": len(bullish_acted),
        }


# ── Report Generator ────────────────────────────────────────────

class ReportGenerator:
    """Generate Obsidian-compatible Markdown report."""

    @staticmethod
    def _excess_returns_section(stats: dict, windows: list[int]) -> list[str]:
        """SPY-adjusted excess returns table."""
        lines = ["## SPY-Adjusted 超额收益", ""]
        lines.append("> 每条 pick 的收益减去同窗口 SPY 收益，消除市场 beta 影响。正值 = 跑赢大盘。")
        lines.append("")
        header = "| 组别 | 数量 |"
        separator = "| --- | ---: |"
        for w in windows:
            header += f" {w}天超额均值 | {w}天超额中位数 | {w}天跑赢率 |"
            separator += " ---: | ---: | ---: |"
        lines.append(header)
        lines.append(separator)
        for group_key in Aggregator.GROUPS:
            g = stats.get(group_key, {})
            row = f"| {g.get('name', group_key)} | {g.get('count', 0)} |"
            for w in windows:
                avg = g.get(f"excess_avg_{w}d")
                med = g.get(f"excess_med_{w}d")
                wr = g.get(f"excess_wr_{w}d")
                row += f" {avg:.1%} |" if avg is not None else " N/A |"
                row += f" {med:.1%} |" if med is not None else " N/A |"
                row += f" {wr:.0%} |" if wr is not None else " N/A |"
            lines.append(row)
        lines.append("")
        return lines

    @staticmethod
    def _entry_sensitivity_section(stats: dict) -> list[str]:
        """Entry point sensitivity analysis."""
        lines = ["## 入场点敏感性", ""]
        lines.append("> 30 天收益在不同入场时间的稳定性。Offset 0 = 周会日收盘，1 = 次日收盘，2 = 后两日收盘。")
        lines.append("> 如果 offset 0 明显好于 1/2，说明收益可能来自「已走完的价格」而非前瞻信号。")
        lines.append("")
        lines.append("| 组别 | Off.0 均值 | Off.1 均值 | Off.2 均值 | Off.0 中位数 | Off.1 中位数 | Off.2 中位数 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for group_key in Aggregator.GROUPS:
            g = stats.get(group_key, {})
            row = f"| {g.get('name', group_key)} |"
            for offset in [0, 1, 2]:
                avg = g.get(f"entry_{offset}_avg")
                row += f" {avg:.1%} |" if avg is not None else " N/A |"
            for offset in [0, 1, 2]:
                med = g.get(f"entry_{offset}_med")
                row += f" {med:.1%} |" if med is not None else " N/A |"
            lines.append(row)
        lines.append("")
        return lines

    @staticmethod
    def _decay_curve_section(picks: list[dict]) -> list[str]:
        """Alpha decay curve across all windows."""
        lines = ["## Alpha 衰减曲线", ""]
        lines.append("> 不同持有期的平均超额收益（vs SPY），观察 alpha 的衰减/累积形状。")
        lines.append("> 峰值位置 = 最佳止盈节奏，转负位置 = 该关仓了。")
        lines.append("")
        groups = defaultdict(list)
        for pick in picks:
            group = Aggregator.classify_pick(pick)
            groups[group].append(pick)
        key_groups = ["bullish_acted", "bullish_discussed", "bearish_acted", "bearish_discussed"]
        header = "| 持有期 |"
        separator = "| ---: |"
        for gk in key_groups:
            header += f" {Aggregator.GROUPS[gk]} |"
            separator += " ---: |"
        lines.append(header)
        lines.append(separator)
        for w in ALL_WINDOWS:
            row = f"| {w}天 |"
            for gk in key_groups:
                gp = groups.get(gk, [])
                excess = [p["excess_returns"][w] for p in gp
                          if p.get("excess_returns", {}).get(w) is not None]
                if excess:
                    row += f" {mean(excess):.1%} |"
                else:
                    row += " N/A |"
            lines.append(row)
        lines.append("")
        return lines

    @staticmethod
    def _held_vs_traded_section(picks: list[dict], windows: list[int]) -> list[str]:
        """Breakdown of held positions vs window trades."""
        lines = ["## 持仓 vs 窗口交易", ""]
        lines.append("> 区分「会议时已持仓」和「会议后窗口内新交易」，回答周会是确认器还是信号源。")
        lines.append("")
        held = [p for p in picks if p.get("acted_reason") == "held"]
        traded = [p for p in picks if p.get("acted_reason") == "traded"]
        not_acted = [p for p in picks if not p.get("acted_on")]
        lines.append(f"- **已持仓 (Held):** {len(held)} 条 — 会议日已有仓位")
        lines.append(f"- **窗口交易 (Traded):** {len(traded)} 条 — 会议前后 [-3d, +7d] 新交易")
        lines.append(f"- **未交易:** {len(not_acted)} 条")
        lines.append("")
        header = "| 类型 | 数量 |"
        separator = "| --- | ---: |"
        for w in windows:
            header += f" {w}天均值 | {w}天超额 |"
            separator += " ---: | ---: |"
        lines.append(header)
        lines.append(separator)
        for label, group in [("已持仓", held), ("窗口交易", traded), ("未交易", not_acted)]:
            row = f"| {label} | {len(group)} |"
            for w in windows:
                rets = [p["returns"][w] for p in group if p.get("returns", {}).get(w) is not None]
                excess = [p["excess_returns"][w] for p in group if p.get("excess_returns", {}).get(w) is not None]
                avg_r = f"{mean(rets):.1%}" if rets else "N/A"
                avg_e = f"{mean(excess):.1%}" if excess else "N/A"
                row += f" {avg_r} | {avg_e} |"
            lines.append(row)
        lines.append("")
        # Sentiment × acted status cross-tab
        lines.append("### 按情绪 × 持仓状态")
        lines.append("")
        lines.append("| 情绪 | 状态 | 数量 | 30天均值 | 30天超额 |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for sent in [Sentiment.BULLISH, Sentiment.BEARISH]:
            sent_cn = "看多" if sent == Sentiment.BULLISH else "看空"
            for label, reason_filter in [("持仓", "held"), ("交易", "traded"), ("未交易", "")]:
                if reason_filter:
                    sub = [p for p in picks if p["sentiment"] == sent and p.get("acted_reason") == reason_filter]
                else:
                    sub = [p for p in picks if p["sentiment"] == sent and not p.get("acted_on")]
                if not sub:
                    continue
                rets = [p["returns"][30] for p in sub if p.get("returns", {}).get(30) is not None]
                excess = [p["excess_returns"][30] for p in sub if p.get("excess_returns", {}).get(30) is not None]
                avg_r = f"{mean(rets):.1%}" if rets else "N/A"
                avg_e = f"{mean(excess):.1%}" if excess else "N/A"
                lines.append(f"| {sent_cn} | {label} | {len(sub)} | {avg_r} | {avg_e} |")
        lines.append("")
        return lines

    @staticmethod
    def _rolling_portfolio_section(picks: list[dict]) -> list[str]:
        """Rolling portfolio simulation section."""
        lines = ["## 滚动组合模拟", ""]
        lines.append("> 每场周会创建等权多头 basket（所有 bullish picks），持有 30 天。")
        lines.append("> 各 basket 独立计算收益后汇总，模拟「机械跟单」的组合表现。")
        lines.append("")
        result = PortfolioAnalyzer.rolling_portfolio(picks)
        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        lines.append("| 指标 | 原始 | SPY-Adjusted |")
        lines.append("| --- | ---: | ---: |")
        lines.append(f"| 总收益 | {result['total_return']:.1%} | {result['total_excess']:.1%} |")
        lines.append(f"| 年化收益 | {result['ann_return']:.1%} | — |")
        lines.append(f"| 年化波动 | {result['ann_vol']:.1%} | — |")
        lines.append(f"| 夏普比率 | {result['sharpe']:.2f} | {result['excess_sharpe']:.2f} |" if result.get('excess_sharpe') is not None else f"| 夏普比率 | {result['sharpe']:.2f} | N/A |")
        lines.append(f"| 最大回撤 | {result['max_drawdown']:.1%} | {result['max_drawdown_excess']:.1%} |")
        lines.append(f"| Basket 胜率 | {result['win_rate']:.0%} | — |")
        lines.append(f"| Basket 平均收益 | {result['mean_basket_return']:.1%} | — |")
        lines.append(f"| Basket 中位数收益 | {result['median_basket_return']:.1%} | — |")
        lines.append(f"| 偏度 (Skewness) | {result['skewness']:.2f} | — |")
        lines.append(f"| 峰度 (Kurtosis) | {result['kurtosis']:.2f} | — |")
        lines.append(f"| Basket 数 | {result['n_baskets']} | — |")
        lines.append(f"| 平均 picks/basket | {result['avg_picks_per_basket']:.1f} | — |")
        lines.append(f"| 时间跨度 | {result['years']:.1f} 年 | — |")
        lines.append("")

        # Per-basket detail
        lines.append("### 每期 Basket 收益")
        lines.append("")
        lines.append("| 日期 | Picks 数 | 30天收益 | 30天超额 |")
        lines.append("| --- | ---: | ---: | ---: |")
        for b in result["baskets"]:
            exc_s = f"{b['excess']:.1%}" if b["excess"] is not None else "N/A"
            lines.append(f"| {b['date']} | {b['n_picks']} | {b['return']:.1%} | {exc_s} |")
        lines.append("")
        return lines

    @staticmethod
    def _regime_section(picks: list[dict]) -> list[str]:
        """Regime conditioning section."""
        lines = ["## Regime 条件回测", ""]
        lines.append("> 按市场环境拆分：SPY 是否在 50 日均线上方，VIX 高/低（以中位数为界）。")
        lines.append("> 观察 alpha 在不同 regime 下是否稳定。若只在牛市有 alpha → 更像 beta 杠杆。")
        lines.append("")
        result = PortfolioAnalyzer.regime_analysis(picks)
        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        vix_med = result.pop("vix_median", None)
        if vix_med:
            lines.append(f"VIX 中位数: **{vix_med:.1f}**")
            lines.append("")

        lines.append("| Regime | 总提及 | 多头 | 空头 | 多头30天超额 | 多头跑赢率 | 空头30天超额 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for rn in ["SPY > 50D MA", "SPY < 50D MA", "VIX Low", "VIX High"]:
            r = result.get(rn, {})
            be = r.get("bull_exc_30d")
            bw = r.get("bull_wr_30d")
            ae = r.get("bear_exc_30d")
            be_s = f"{be:.1%}" if be is not None else "N/A"
            bw_s = f"{bw:.0%}" if bw is not None else "N/A"
            ae_s = f"{ae:.1%}" if ae is not None else "N/A"
            lines.append(f"| {rn} | {r.get('total_picks', 0)} | {r.get('bull_n', 0)} | {r.get('bear_n', 0)} | {be_s} | {bw_s} | {ae_s} |")
        lines.append("")
        return lines

    @staticmethod
    def _bootstrap_section(picks: list[dict]) -> list[str]:
        """Bootstrap/placebo test section."""
        lines = ["## 随机化检验 (Placebo Test)", ""]
        lines.append("> 保持每组样本量不变，从全部 picks 池中随机抽样 1,000 次。")
        lines.append("> 比较实际超额与随机分布，分位数 > 90% = 统计显著。")
        lines.append("")
        result = PortfolioAnalyzer.bootstrap_test(picks)
        if "error" in result:
            lines.append(f"*{result['error']}*")
            lines.append("")
            return lines

        lines.append("### 多头+交易组 (30天超额)")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("| --- | ---: |")
        lines.append(f"| 实际超额 | {result['actual_excess']:.1%} |")
        lines.append(f"| 随机均值 | {result['random_mean']:.1%} |")
        lines.append(f"| 随机 5th pctile | {result['random_5th']:.1%} |")
        lines.append(f"| 随机 95th pctile | {result['random_95th']:.1%} |")
        lines.append(f"| **你的分位** | **{result['percentile']:.0f}%** |")
        lines.append(f"| 样本数 | {result['n_sample']} |")
        lines.append("")

        if result['percentile'] >= 90:
            lines.append(f"> **统计显著 (p<0.10):** 实际超额 {result['actual_excess']:.1%} 在随机分布的第 {result['percentile']:.0f} 百分位。选股能力非随机。")
        elif result['percentile'] >= 70:
            lines.append(f"> **弱显著:** 实际超额在第 {result['percentile']:.0f} 百分位，有信号但不够强。")
        else:
            lines.append(f"> **不显著:** 实际超额在第 {result['percentile']:.0f} 百分位，无法排除运气。")
        lines.append("")

        # OOS split
        if result.get("train_excess") is not None:
            lines.append("### 简单 Out-of-Sample (前 2/3 vs 后 1/3)")
            lines.append("")
            lines.append(f"- 训练期 (前 2/3) 超额: **{result['train_excess']:.1%}**")
            lines.append(f"- 测试期 (后 1/3) 超额: **{result['test_excess']:.1%}**")
            if result['test_excess'] is not None and result['train_excess'] is not None:
                if result['test_excess'] > 0:
                    lines.append("> OOS 仍为正 → 信号可能持久")
                else:
                    lines.append("> OOS 为负 → 可能过拟合或 regime 变化")
            lines.append("")

        if "bear_actual" in result:
            lines.append("### 空头+未交易组 (30天超额)")
            lines.append("")
            lines.append("| 指标 | 值 |")
            lines.append("| --- | ---: |")
            lines.append(f"| 实际超额 | {result['bear_actual']:.1%} |")
            lines.append(f"| 随机均值 | {result['bear_random_mean']:.1%} |")
            lines.append(f"| **低于随机%** | **{result['bear_percentile']:.0f}%** |")
            lines.append("")
            if result['bear_percentile'] >= 90:
                lines.append(f"> **空头信号显著:** 看空组实际超额低于 {result['bear_percentile']:.0f}% 的随机结果，回避决策有价值。")
            else:
                lines.append(f"> 空头信号在第 {result['bear_percentile']:.0f} 百分位，信号不够强。")
            lines.append("")

        return lines

    @staticmethod
    def _sector_attribution_section(picks: list[dict]) -> list[str]:
        """Sector attribution analysis section."""
        lines = ["## 行业归因 (Sector Attribution)", ""]
        lines.append("> Alpha 是来自选股还是行业配置？将每条 pick 的收益减去其所属行业 ETF 收益。")
        lines.append("> 若行业调整后 Alpha ≈ SPY调整后 Alpha → 真选股能力。若大幅缩水 → 主要是行业 beta。")
        lines.append("")

        result = PortfolioAnalyzer.sector_attribution(picks)
        if not result:
            lines.append("*行业归因数据不足*")
            lines.append("")
            return lines

        # Group comparison: SPY-adjusted vs sector-adjusted
        groups = result.get("groups", {})
        if groups:
            lines.append("### 各组 SPY-adjusted vs 行业-adjusted (30天)")
            lines.append("")
            lines.append("| 组别 | 数量 | vs SPY | vs 行业ETF | 差值 |")
            lines.append("| --- | ---: | ---: | ---: | ---: |")
            for gk in ["bullish_acted", "bullish_discussed", "bearish_acted",
                        "bearish_discussed", "neutral"]:
                g = groups.get(gk)
                if not g:
                    continue
                spy_e = g["spy_excess_30"]
                sect_e = g["sector_excess_30"]
                diff = spy_e - sect_e
                lines.append(
                    f"| {g['name']} | {g['n']} | {spy_e:.1%} | {sect_e:.1%} | {diff:+.1%} |")
            lines.append("")
            lines.append("> 差值为正 → 部分 Alpha 来自行业配置（选对了行业），差值为负 → 反而在行业内还跑赢了。")
            lines.append("")

        # Sector breakdown for bullish picks
        sectors = result.get("sectors", {})
        if sectors:
            lines.append("### 看多 picks 行业拆解 (30天)")
            lines.append("")
            lines.append("| 行业 | ETF | 数量 | 原始均值 | vs SPY | vs 行业ETF |")
            lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
            for sector in sorted(sectors.keys(),
                                 key=lambda s: sectors[s]["n"], reverse=True):
                s = sectors[sector]
                label = SECTOR_LABELS.get(sector, sector)
                lines.append(
                    f"| {label} | {s['etf']} | {s['n']} | "
                    f"{s['raw_avg']:.1%} | {s['spy_excess']:.1%} | "
                    f"{s['sector_excess']:.1%} |")
            lines.append("")

        return lines

    @staticmethod
    def _position_weighted_section(picks: list[dict]) -> list[str]:
        """Position-weighted vs equal-weight comparison."""
        lines = ["## 仓位加权回测", ""]
        lines.append("> 用实际持仓股数 × 基准价格计算仓位权重，对比等权与实际加权的收益差异。")
        lines.append("> 若加权 > 等权 → 重仓股选得更好；若加权 < 等权 → 重仓拖累了表现。")
        lines.append("")

        result = PortfolioAnalyzer.position_weighted(picks)
        if not result:
            lines.append("*仓位数据不足（需要 ≥5 笔持仓 + 基准价格 + 持仓股数）*")
            lines.append("")
            return lines

        pw = result["pw_returns"]
        ew = result["ew_returns"]

        lines.append(f"持仓样本数: **{result['n_held']}**")
        lines.append("")
        lines.append("| 窗口 | 等权收益 | 加权收益 | 等权超额 | 加权超额 | 加权效应 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for w in [7, 30, 90]:
            ew_r = ew.get(w)
            pw_r = pw.get(w)
            ew_e = ew.get(f"excess_{w}")
            pw_e = pw.get(f"excess_{w}")
            ew_s = f"{ew_r:.1%}" if ew_r is not None else "N/A"
            pw_s = f"{pw_r:.1%}" if pw_r is not None else "N/A"
            ew_es = f"{ew_e:.1%}" if ew_e is not None else "N/A"
            pw_es = f"{pw_e:.1%}" if pw_e is not None else "N/A"
            if pw_e is not None and ew_e is not None:
                diff = pw_e - ew_e
                diff_s = f"{diff:+.1%}"
            else:
                diff_s = "N/A"
            lines.append(f"| {w}天 | {ew_s} | {pw_s} | {ew_es} | {pw_es} | {diff_s} |")
        lines.append("")

        # Top positions table
        top = result.get("top_positions", [])
        if top:
            lines.append("### 持仓价值 Top 10")
            lines.append("")
            lines.append("| 股票 | 日期 | 股数 | 美元敞口 | 占比 | 30天超额 |")
            lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
            for p in top:
                exc = f"{p['excess_30']:.1%}" if p['excess_30'] is not None else "N/A"
                lines.append(
                    f"| {p['ticker']} | {p['date']} | {p['shares']:.0f} | "
                    f"${p['value']:,.0f} | {p['pct_of_total']:.1%} | {exc} |")
            lines.append("")

        return lines

    @staticmethod
    def _oos_attribution_section(picks: list[dict]) -> list[str]:
        """OOS attribution: what went wrong in the test period?"""
        lines = ["## OOS 归因分析", ""]
        lines.append("> 将看多 picks 按时间分为前 2/3（训练期）和后 1/3（测试期）。")
        lines.append("> 深入分析测试期 Alpha 消失的原因：是哪些股票拖累？是行业轮动还是个股暴雷？")
        lines.append("")

        result = PortfolioAnalyzer.oos_attribution(picks)
        if not result:
            lines.append("*OOS 归因数据不足*")
            lines.append("")
            return lines

        lines.append(f"分割日期: **{result['split_date']}**")
        lines.append(f"训练期: {result['train_n']} 条 | 测试期: {result['test_n']} 条")
        lines.append("")

        # Period × acted split
        ps = result.get("period_split", {})
        if ps:
            lines.append("### 训练 vs 测试 × 交易/讨论")
            lines.append("")
            lines.append("| 期间 | 交易 30天超额 | 讨论 30天超额 |")
            lines.append("| --- | ---: | ---: |")
            ta = ps.get("train_acted")
            td = ps.get("train_discussed")
            lines.append(
                f"| 训练期 | {ta:.1%} | {td:.1%} |" if ta is not None and td is not None
                else f"| 训练期 | {f'{ta:.1%}' if ta else 'N/A'} | {f'{td:.1%}' if td else 'N/A'} |")
            tea = ps.get("test_acted")
            ted = ps.get("test_discussed")
            lines.append(
                f"| 测试期 | {tea:.1%} | {ted:.1%} |" if tea is not None and ted is not None
                else f"| 测试期 | {f'{tea:.1%}' if tea else 'N/A'} | {f'{ted:.1%}' if ted else 'N/A'} |")
            lines.append("")

        # Sector breakdown in test period
        sa = result.get("sector_avg", {})
        if sa:
            lines.append("### 测试期行业表现")
            lines.append("")
            lines.append("| 行业 | 数量 | 平均30天超额 |")
            lines.append("| --- | ---: | ---: |")
            for sector in sorted(sa.keys(),
                                 key=lambda s: sa[s]["avg_excess"]):
                s = sa[sector]
                label = SECTOR_LABELS.get(sector, sector)
                lines.append(f"| {label} | {s['n']} | {s['avg_excess']:.1%} |")
            lines.append("")

        # Detractors
        det = result.get("detractors", [])
        if det:
            lines.append("### 测试期最大拖累 (看多 picks)")
            lines.append("")
            lines.append("| 日期 | 股票 | 行业 | 是否交易 | 30天超额 | 30天原始 |")
            lines.append("| --- | --- | --- | --- | ---: | ---: |")
            for p in det:
                label = SECTOR_LABELS.get(p["sector"], p["sector"])
                acted_s = "是" if p["acted"] else "否"
                raw = f"{p['raw_30']:.1%}" if p["raw_30"] is not None else "N/A"
                lines.append(
                    f"| {p['date']} | {p['ticker']} | {label} | {acted_s} | "
                    f"{p['excess_30']:.1%} | {raw} |")
            lines.append("")

        # Contributors
        con = result.get("contributors", [])
        if con:
            lines.append("### 测试期最大贡献 (看多 picks)")
            lines.append("")
            lines.append("| 日期 | 股票 | 行业 | 是否交易 | 30天超额 | 30天原始 |")
            lines.append("| --- | --- | --- | --- | ---: | ---: |")
            for p in con:
                label = SECTOR_LABELS.get(p["sector"], p["sector"])
                acted_s = "是" if p["acted"] else "否"
                raw = f"{p['raw_30']:.1%}" if p["raw_30"] is not None else "N/A"
                lines.append(
                    f"| {p['date']} | {p['ticker']} | {label} | {acted_s} | "
                    f"{p['excess_30']:.1%} | {raw} |")
            lines.append("")

        return lines

    @staticmethod
    def _conviction_consistency_section(picks: list[dict]) -> list[str]:
        """Conviction Consistency Attribution report section."""
        lines = ["## 信号一致性归因 (Conviction Consistency)", ""]
        lines.append("> 周会只有一位主讲人，因此将「分析师归因」改为「信号一致性归因」。")
        lines.append("> 追踪同一只股票被反复讨论时，一致看多/看空 vs 翻来覆去 vs 仅提一次的表现差异。")
        lines.append("")

        result = PortfolioAnalyzer.conviction_consistency(picks)
        if not result:
            lines.append("*数据不足*")
            lines.append("")
            return lines

        lines.append(f"覆盖 **{result['total_tickers']}** 只不同股票")
        lines.append("")

        # Category summary table
        cat_labels = {
            "consistent_bull": "一致看多",
            "consistent_bear": "一致看空",
            "flip_flop": "多空反复",
            "one_off": "仅提一次",
            "mixed_neutral": "多次中性",
        }
        cat_order = ["consistent_bull", "consistent_bear", "flip_flop",
                      "one_off", "mixed_neutral"]

        lines.append("### 按信号一致性分类")
        lines.append("")
        lines.append("| 类型 | 股票数 | 提及数 | 30天超额均值 | 交易组超额 | 仅讨论超额 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")

        summary = result.get("summary", {})
        for cat in cat_order:
            s = summary.get(cat)
            if not s:
                continue
            label = cat_labels.get(cat, cat)
            acted_s = f"{s['acted_excess']:.1%}" if s['acted_excess'] is not None else "—"
            not_acted_s = f"{s['not_acted_excess']:.1%}" if s['not_acted_excess'] is not None else "—"
            lines.append(
                f"| {label} | {s['n_tickers']} | {s['n_mentions']} | "
                f"{s['avg_excess']:.1%} | {acted_s} | {not_acted_s} |")
        lines.append("")

        # Frequency vs performance
        freq = result.get("freq_summary", {})
        if freq:
            lines.append("### 讨论频次 vs 看多表现")
            lines.append("")
            lines.append("> 同一只股票被看多的次数越多，表现是否越好？")
            lines.append("")
            lines.append("| 频次 | 看多提及数 | 30天超额均值 | 跑赢率 |")
            lines.append("| --- | ---: | ---: | ---: |")
            for bucket in ["1x", "2-3x", "4+x"]:
                f = freq.get(bucket)
                if f:
                    lines.append(
                        f"| {bucket} | {f['n']} | {f['avg_excess']:.1%} | {f['win_rate']:.0%} |")
            lines.append("")

        # Missed convictions
        missed = result.get("missed_convictions", [])
        if missed:
            lines.append("### 错过的高确信度信号 (一致看多但未交易)")
            lines.append("")
            lines.append("| 股票 | 讨论次数 | 30天超额均值 |")
            lines.append("| --- | ---: | ---: |")
            for m in missed[:10]:
                lines.append(f"| {m['ticker']} | {m['mentions']} | {m['avg_excess']:.1%} |")
            lines.append("")

        # Flip-floppers
        flips = result.get("flip_detail", [])
        if flips:
            lines.append("### 多空反复的股票")
            lines.append("")
            lines.append("> 同一只股票既被看多又被看空，信号噪音最大。")
            lines.append("")
            lines.append("| 股票 | 讨论次数 | 看多次 | 看空次 | 30天超额均值 | 有持仓 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
            for f in flips[:15]:
                acted_s = "是" if f["acted"] else "否"
                lines.append(
                    f"| {f['ticker']} | {f['mentions']} | {f['bull_count']} | "
                    f"{f['bear_count']} | {f['avg_excess']:.1%} | {acted_s} |")
            lines.append("")

        return lines

    @staticmethod
    def _trade_management_section(picks: list[dict]) -> list[str]:
        """Trade Management Simulation report section."""
        lines = ["## 止损止盈规则模拟 (Trade Management)", ""]
        lines.append("> 对看多+已交易组模拟机械式止损/止盈/持有期限规则。")
        lines.append("> 使用 1/3/7/14/21/30/45/60/90/180 天检查点，首次触发即退出。")
        lines.append("> 目标：找到能提升超额收益或降低回撤的最优规则。")
        lines.append("")

        result = PortfolioAnalyzer.trade_management_sim(picks)
        if not result:
            lines.append("*数据不足（需要至少 10 条看多+交易记录）*")
            lines.append("")
            return lines

        lines.append(f"模拟样本: **{result['n_picks']}** 条看多+已交易 picks")
        lines.append("")

        baseline = result.get("baseline", {})
        if baseline:
            lines.append("### 基准 (买入持有30天)")
            lines.append("")
            lines.append(f"- 平均收益: **{baseline['avg_return']:.1%}**")
            lines.append(f"- 平均超额: **{baseline['avg_excess']:.1%}**")
            lines.append(f"- 胜率: {baseline['win_rate']:.0%}")
            lines.append(f"- 最差: {baseline['worst']:.1%} / 最佳: {baseline['best']:.1%}")
            lines.append("")

        rules = result.get("rules", {})
        if rules:
            # Stop-loss rules
            lines.append("### 止损规则")
            lines.append("")
            lines.append("| 规则 | 平均收益 | 平均超额 | 胜率 | 平均持有天数 | 最差 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
            for label, r in rules.items():
                if label.startswith("止损") and "/" not in label and r:
                    lines.append(
                        f"| {label} | {r['avg_return']:.1%} | {r['avg_excess']:.1%} | "
                        f"{r['win_rate']:.0%} | {r['avg_hold_days']:.0f} | {r['worst']:.1%} |")
            lines.append("")

            # Take-profit rules
            lines.append("### 止盈规则")
            lines.append("")
            lines.append("| 规则 | 平均收益 | 平均超额 | 胜率 | 平均持有天数 | 最佳 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
            for label, r in rules.items():
                if label.startswith("止盈") and r:
                    lines.append(
                        f"| {label} | {r['avg_return']:.1%} | {r['avg_excess']:.1%} | "
                        f"{r['win_rate']:.0%} | {r['avg_hold_days']:.0f} | {r['best']:.1%} |")
            lines.append("")

            # Time-stop rules
            lines.append("### 持有期限规则")
            lines.append("")
            lines.append("| 规则 | 平均收益 | 平均超额 | 胜率 | 最差 | 最佳 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
            for label, r in rules.items():
                if label.startswith("持有") and r:
                    lines.append(
                        f"| {label} | {r['avg_return']:.1%} | {r['avg_excess']:.1%} | "
                        f"{r['win_rate']:.0%} | {r['worst']:.1%} | {r['best']:.1%} |")
            lines.append("")

            # Combined rules
            lines.append("### 组合规则 (止损 + 止盈)")
            lines.append("")
            lines.append("| 规则 | 平均收益 | 平均超额 | 胜率 | 平均持有天数 | 最差 | 最佳 |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
            for label, r in rules.items():
                if "/" in label and r:
                    lines.append(
                        f"| {label} | {r['avg_return']:.1%} | {r['avg_excess']:.1%} | "
                        f"{r['win_rate']:.0%} | {r['avg_hold_days']:.0f} | "
                        f"{r['worst']:.1%} | {r['best']:.1%} |")
            lines.append("")

        # Best rule highlight
        best = result.get("best_rule")
        if best:
            best_r = rules.get(best, {})
            lines.append(f"### 最优规则: **{best}**")
            lines.append("")
            if best_r:
                imp = best_r["avg_excess"] - baseline.get("avg_excess", 0)
                lines.append(f"- 超额提升: **{imp:+.1%}** (从 {baseline.get('avg_excess', 0):.1%} → {best_r['avg_excess']:.1%})")
                lines.append(f"- 平均持有天数: {best_r['avg_hold_days']:.0f} 天")
                lines.append(f"- 胜率: {best_r['win_rate']:.0%}")
                lines.append(f"- 最大亏损: {best_r['worst']:.1%}")
            lines.append("")
        else:
            lines.append("### 结论: 买入持有已是最优")
            lines.append("")
            lines.append("> 没有机械规则能跑赢简单的 30 天买入持有。说明 Alpha 衰减曲线的形状")
            lines.append("> 不适合用固定阈值截断——可能需要基于个股特征的动态规则。")
            lines.append("")

        return lines

    @staticmethod
    def generate(stats: dict, picks: list[dict], meetings_count: int,
                 windows: list[int] = None) -> str:
        """Generate full markdown report."""
        if windows is None:
            windows = [7, 30, 90]

        today = date.today().isoformat()
        unique_tickers = len(set(p["ticker_yf"] for p in picks))
        total_picks = len(picks)

        # Frontmatter
        lines = [
            "---",
            f"date: {today}",
            "type: backtest",
            "tags: [backtest, meeting-picks, decision-audit]",
            f"meetings_analyzed: {meetings_count}",
            f"unique_tickers: {unique_tickers}",
            f"total_picks: {total_picks}",
            "---",
            "",
            "# 周会选股回测报告",
            "",
            f"> 分析了 **{meetings_count}** 场周会中讨论的 **{unique_tickers}** 只股票、共 **{total_picks}** 次提及。",
            f"> 将每次提及按看法（多/空/中性）× 是否交易分为 5 组，测算讨论后 {'/'.join(str(w) for w in windows)} 天的前瞻收益。",
            f"> 生成日期: {today}",
            "",
        ]

        # Summary table
        lines.append("## 汇总表")
        lines.append("")
        header = "| 组别 | 数量 |"
        separator = "| --- | ---: |"
        for w in windows:
            header += f" {w}天均值 | {w}天中位数 | {w}天胜率 |"
            separator += " ---: | ---: | ---: |"
        lines.append(header)
        lines.append(separator)

        for group_key in Aggregator.GROUPS:
            g = stats.get(group_key, {})
            row = f"| {g.get('name', group_key)} | {g.get('count', 0)} |"
            for w in windows:
                avg = g.get(f"avg_{w}d")
                med = g.get(f"med_{w}d")
                wr = g.get(f"win_rate_{w}d")
                n = g.get(f"n_{w}d", 0)
                avg_s = f"{avg:.1%}" if avg is not None else "N/A"
                med_s = f"{med:.1%}" if med is not None else "N/A"
                wr_s = f"{wr:.0%} ({n})" if wr is not None else "N/A"
                row += f" {avg_s} | {med_s} | {wr_s} |"
            lines.append(row)

        lines.append("")

        # Key insights
        lines.append("## 核心发现")
        lines.append("")
        lines.extend(ReportGenerator._generate_insights(stats, windows))
        lines.append("")

        # New analysis sections
        lines.extend(ReportGenerator._excess_returns_section(stats, windows))
        lines.extend(ReportGenerator._entry_sensitivity_section(stats))
        lines.extend(ReportGenerator._decay_curve_section(picks))
        lines.extend(ReportGenerator._held_vs_traded_section(picks, windows))
        lines.extend(ReportGenerator._rolling_portfolio_section(picks))
        lines.extend(ReportGenerator._regime_section(picks))
        lines.extend(ReportGenerator._bootstrap_section(picks))
        lines.extend(ReportGenerator._sector_attribution_section(picks))
        lines.extend(ReportGenerator._position_weighted_section(picks))
        lines.extend(ReportGenerator._oos_attribution_section(picks))
        lines.extend(ReportGenerator._conviction_consistency_section(picks))
        lines.extend(ReportGenerator._trade_management_section(picks))

        # Top / Bottom performers
        lines.append("## 最佳与最差选股")
        lines.append("")

        # Sort by 30d returns
        picks_with_returns = [p for p in picks if p.get("returns", {}).get(30) is not None]
        if picks_with_returns:
            sorted_picks = sorted(picks_with_returns, key=lambda p: p["returns"][30], reverse=True)

            lines.append("### Top 10 (30天收益)")
            lines.append("")
            lines.append("| 日期 | 股票 | 看法 | 是否交易 | 7天 | 30天 | 90天 |")
            lines.append("| --- | --- | --- | --- | ---: | ---: | ---: |")
            for p in sorted_picks[:10]:
                lines.append(ReportGenerator._pick_row(p, windows))
            lines.append("")

            lines.append("### Bottom 10 (30天收益)")
            lines.append("")
            lines.append("| 日期 | 股票 | 看法 | 是否交易 | 7天 | 30天 | 90天 |")
            lines.append("| --- | --- | --- | --- | ---: | ---: | ---: |")
            for p in sorted_picks[-10:]:
                lines.append(ReportGenerator._pick_row(p, windows))
            lines.append("")

        # Missed opportunities: Bullish + Discussed Only with highest 30d returns
        bullish_missed = [p for p in picks_with_returns
                          if p["sentiment"] == Sentiment.BULLISH and not p["acted_on"]]
        if bullish_missed:
            bullish_missed.sort(key=lambda p: p["returns"][30], reverse=True)
            lines.append("### 错过的机会 (看多但未交易，30天涨幅最高)")
            lines.append("")
            lines.append("| 日期 | 股票 | 7天 | 30天 | 90天 | 行动建议原文 |")
            lines.append("| --- | --- | ---: | ---: | ---: | --- |")
            for p in bullish_missed[:10]:
                r7 = f"{p['returns'].get(7, 0):.1%}" if p['returns'].get(7) is not None else "N/A"
                r30 = f"{p['returns'].get(30, 0):.1%}" if p['returns'].get(30) is not None else "N/A"
                r90 = f"{p['returns'].get(90, 0):.1%}" if p['returns'].get(90) is not None else "N/A"
                action = p.get("action_text", "")[:60].replace("|", "/").replace("\n", " ")
                lines.append(f"| {p['meeting_date']} | {p['ticker_yf']} | {r7} | {r30} | {r90} | {action} |")
            lines.append("")

        # Correct avoidances: Bearish + Discussed Only with lowest 30d returns
        bearish_avoided = [p for p in picks_with_returns
                           if p["sentiment"] == Sentiment.BEARISH and not p["acted_on"]]
        if bearish_avoided:
            bearish_avoided.sort(key=lambda p: p["returns"][30])
            lines.append("### 正确回避 (看空且未交易，30天跌幅最大)")
            lines.append("")
            lines.append("| 日期 | 股票 | 7天 | 30天 | 90天 |")
            lines.append("| --- | --- | ---: | ---: | ---: |")
            for p in bearish_avoided[:10]:
                r7 = f"{p['returns'].get(7, 0):.1%}" if p['returns'].get(7) is not None else "N/A"
                r30 = f"{p['returns'].get(30, 0):.1%}" if p['returns'].get(30) is not None else "N/A"
                r90 = f"{p['returns'].get(90, 0):.1%}" if p['returns'].get(90) is not None else "N/A"
                lines.append(f"| {p['meeting_date']} | {p['ticker_yf']} | {r7} | {r30} | {r90} |")
            lines.append("")

        # Frequency analysis
        lines.append("## 频次分析")
        lines.append("")
        lines.extend(ReportGenerator._frequency_analysis(picks, windows))
        lines.append("")

        # Missing data
        missing = [p for p in picks if all(
            p.get("returns", {}).get(w) is None for w in windows
        )]
        if missing:
            lines.append("## 缺失数据")
            lines.append("")
            lines.append(f"共 {len(missing)} 条提及无法获取价格数据:")
            lines.append("")
            for p in missing[:30]:
                lines.append(f"- {p['meeting_date']} {p['ticker_yf']} (raw: {p['ticker_raw']})")
            if len(missing) > 30:
                lines.append(f"- ... 及另外 {len(missing) - 30} 条")
            lines.append("")

        # Full detail table
        lines.append("## 完整数据表")
        lines.append("")
        lines.append("| 日期 | 股票 | 看法 | 是否交易 | 7天 | 30天 | 90天 | 分组 |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | --- |")
        sorted_all = sorted(picks, key=lambda p: (str(p["meeting_date"]), p["ticker_yf"]))
        for p in sorted_all:
            group = Aggregator.classify_pick(p)
            group_name = Aggregator.GROUPS.get(group, group)
            lines.append(ReportGenerator._pick_row(p, windows, extra=group_name))
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _pick_row(pick: dict, windows: list[int], extra: str = None) -> str:
        """Format a single pick as a table row."""
        sentiment_cn = {
            Sentiment.BULLISH: "多",
            Sentiment.BEARISH: "空",
            Sentiment.NEUTRAL: "中性",
            Sentiment.UNKNOWN: "未知",
        }
        reason = pick.get("acted_reason", "")
        if not pick["acted_on"]:
            acted = "✗"
        elif reason == "held":
            acted = "持仓"
        else:
            acted = "交易"
        cols = [
            str(pick["meeting_date"]),
            pick["ticker_yf"],
            sentiment_cn.get(pick["sentiment"], pick["sentiment"]),
            acted,
        ]
        for w in windows:
            r = pick.get("returns", {}).get(w)
            cols.append(f"{r:.1%}" if r is not None else "N/A")
        if extra:
            cols.append(extra)
        return "| " + " | ".join(cols) + " |"

    @staticmethod
    def _generate_insights(stats: dict, windows: list[int]) -> list[str]:
        """Generate key insight bullets."""
        lines = []
        w = 30  # primary comparison window

        ba = stats.get("bullish_acted", {})
        bd = stats.get("bullish_discussed", {})
        bea = stats.get("bearish_acted", {})
        bed = stats.get("bearish_discussed", {})

        # 1. Bullish acted vs discussed
        ba_avg = ba.get(f"avg_{w}d")
        bd_avg = bd.get(f"avg_{w}d")
        if ba_avg is not None and bd_avg is not None:
            if ba_avg > bd_avg:
                lines.append(f"1. **选股执行正确:** 看多且交易的股票 30 天平均涨 {ba_avg:.1%}，优于看多但未交易的 {bd_avg:.1%}。说明交易决策整体合理。")
            else:
                lines.append(f"1. **错失机会:** 看多但未交易的股票 30 天平均涨 {bd_avg:.1%}，反而优于看多且交易的 {ba_avg:.1%}。可能存在执行犹豫。")

        # 2. Bearish accuracy
        bea_avg = bea.get(f"avg_{w}d")
        bed_avg = bed.get(f"avg_{w}d")
        if bed_avg is not None:
            if bed_avg < 0:
                lines.append(f"2. **空头判断准确:** 看空且未交易的股票 30 天平均跌 {bed_avg:.1%}，回避决策正确。")
            else:
                lines.append(f"2. **空头判断偏差:** 看空但未交易的股票 30 天平均涨 {bed_avg:.1%}，空头观点可能偏保守。")

        # 3. Win rate comparison
        ba_wr = ba.get(f"win_rate_{w}d")
        bd_wr = bd.get(f"win_rate_{w}d")
        if ba_wr is not None and bd_wr is not None:
            lines.append(f"3. **胜率对比:** 看多且交易 {ba_wr:.0%} vs 看多未交易 {bd_wr:.0%} (30天正收益比例)")

        # 4. Overall sentiment accuracy
        all_bullish = [p for p in (ba.get("picks", []) + bd.get("picks", []))
                       if p.get("returns", {}).get(w) is not None]
        all_bearish = [p for p in (bea.get("picks", []) + bed.get("picks", []))
                       if p.get("returns", {}).get(w) is not None]
        if all_bullish:
            bull_correct = sum(1 for p in all_bullish if p["returns"][w] > 0)
            lines.append(f"4. **多头准确率:** {bull_correct}/{len(all_bullish)} ({bull_correct/len(all_bullish):.0%}) 的看多观点在 30 天内实现正收益")
        if all_bearish:
            bear_correct = sum(1 for p in all_bearish if p["returns"][w] < 0)
            lines.append(f"5. **空头准确率:** {bear_correct}/{len(all_bearish)} ({bear_correct/len(all_bearish):.0%}) 的看空观点在 30 天内实现负收益")

        # 6. Excess return insight
        ba_excess = ba.get(f"excess_avg_{w}d")
        bd_excess = bd.get(f"excess_avg_{w}d")
        if ba_excess is not None:
            if ba_excess > 0.005:
                lines.append(f"6. **SPY-adjusted alpha:** 看多+交易组 30 天超额 {ba_excess:.1%}（扣除市场 beta 后仍有 alpha）")
            elif ba_excess > -0.005:
                lines.append(f"6. **SPY-adjusted alpha 约为零:** 看多+交易组 30 天超额仅 {ba_excess:.1%}，收益主要来自 beta")
            else:
                lines.append(f"6. **跑输大盘:** 看多+交易组 30 天超额 {ba_excess:.1%}，选股不如直接买 SPY")

        bed_excess = bed.get(f"excess_avg_{w}d")
        if bed_excess is not None:
            if bed_excess < -0.005:
                lines.append(f"7. **空头信号有效:** 看空+未交易组 30 天超额 {bed_excess:.1%}，回避决策创造了 alpha")
            else:
                lines.append(f"7. **空头信号无效:** 看空+未交易组 30 天超额 {bed_excess:.1%}，这些股票其实也没跑输大盘")

        return lines

    @staticmethod
    def _frequency_analysis(picks: list[dict], windows: list[int]) -> list[str]:
        """Analyze most frequently discussed tickers."""
        lines = []
        ticker_counts = defaultdict(lambda: {"count": 0, "bullish": 0, "bearish": 0, "returns_30d": []})

        for p in picks:
            t = p["ticker_yf"]
            ticker_counts[t]["count"] += 1
            if p["sentiment"] == Sentiment.BULLISH:
                ticker_counts[t]["bullish"] += 1
            elif p["sentiment"] == Sentiment.BEARISH:
                ticker_counts[t]["bearish"] += 1
            r30 = p.get("returns", {}).get(30)
            if r30 is not None:
                ticker_counts[t]["returns_30d"].append(r30)

        # Sort by frequency
        sorted_tickers = sorted(ticker_counts.items(), key=lambda x: x[1]["count"], reverse=True)

        lines.append("### 讨论次数最多的股票 (Top 20)")
        lines.append("")
        lines.append("| 股票 | 讨论次数 | 看多次 | 看空次 | 平均30天收益 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")

        for ticker, data in sorted_tickers[:20]:
            avg_r = mean(data["returns_30d"]) if data["returns_30d"] else None
            avg_s = f"{avg_r:.1%}" if avg_r is not None else "N/A"
            lines.append(f"| {ticker} | {data['count']} | {data['bullish']} | {data['bearish']} | {avg_s} |")

        return lines


# ── Main Pipeline ───────────────────────────────────────────────

def run(use_cache: bool = True, verbose: bool = False):
    """Run the full meeting backtest pipeline."""
    windows = MAIN_WINDOWS

    print("=" * 60)
    print("  周会选股回测 (Meeting Picks Backtest)")
    print("=" * 60)
    print()

    # Step 1: Parse meetings
    print("[1/6] Parsing meeting files...")
    parser = MeetingParser()
    meetings = parser.parse_all()
    print(f"  Found {len(meetings)} meetings")

    total_picks = sum(len(m["picks"]) for m in meetings)
    print(f"  Total ticker mentions: {total_picks}")

    all_tickers = set()
    for m in meetings:
        for p in m["picks"]:
            all_tickers.add(p["ticker_yf"])
    print(f"  Unique tickers: {len(all_tickers)}")

    # Step 2: Sentiment overview
    print()
    print("[2/6] Sentiment distribution...")
    sentiment_counts = defaultdict(int)
    for m in meetings:
        for p in m["picks"]:
            sentiment_counts[p["sentiment"]] += 1
    for s, c in sorted(sentiment_counts.items()):
        print(f"  {s}: {c}")

    # Step 3: Match against trades
    print()
    print("[3/6] Matching against trades.json...")
    matcher = TradeMatcher()
    print(f"  Loaded {sum(len(v) for v in matcher.trades_by_ticker.values())} stock trades")

    # Flatten all picks with meeting date
    all_picks = []
    for m in meetings:
        for p in m["picks"]:
            pick = {**p, "meeting_date": m["date"]}
            acted, reason = matcher.is_acted_on(p["ticker_yf"], m["date"])
            pick["acted_on"] = acted
            pick["acted_reason"] = reason  # 'held' or 'traded' or ''
            if reason == "held":
                pick["position_shares"] = matcher.get_position_shares(
                    p["ticker_yf"], m["date"])
            else:
                pick["position_shares"] = 0.0
            all_picks.append(pick)

    acted_count = sum(1 for p in all_picks if p["acted_on"])
    held_count = sum(1 for p in all_picks if p.get("acted_reason") == "held")
    traded_count = sum(1 for p in all_picks if p.get("acted_reason") == "traded")
    print(f"  Acted on: {acted_count}/{len(all_picks)} ({acted_count/len(all_picks):.0%})")
    print(f"    - Held position: {held_count}")
    print(f"    - Traded in window: {traded_count}")

    # Step 4: Fetch prices
    print()
    print("[4/6] Fetching forward prices...")
    fetcher = PriceFetcher(use_cache=use_cache)
    fetcher.batch_fetch(all_picks, ALL_WINDOWS)

    priced_count = sum(1 for p in all_picks
                       if any(p.get("returns", {}).get(w) is not None for w in windows))
    print(f"  Got prices for {priced_count}/{len(all_picks)} mentions")

    # Step 5: Aggregate
    print()
    print("[5/6] Aggregating into groups...")
    stats = Aggregator.aggregate(all_picks, ALL_WINDOWS)

    for group_key, group_name in Aggregator.GROUPS.items():
        g = stats.get(group_key, {})
        avg_30 = g.get("avg_30d")
        avg_s = f"{avg_30:.1%}" if avg_30 is not None else "N/A"
        print(f"  {group_name}: {g['count']} picks, 30d avg: {avg_s}")

    # Step 6: Generate report
    print()
    print("[6/6] Generating report...")
    report = ReportGenerator.generate(stats, all_picks, len(meetings), windows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{date.today().isoformat()}_meeting_backtest.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved to: {report_path}")

    # Console summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for group_key, group_name in Aggregator.GROUPS.items():
        g = stats.get(group_key, {})
        print(f"  {group_name} ({g['count']} picks):")
        for w in windows:
            avg = g.get(f"avg_{w}d")
            exc = g.get(f"excess_avg_{w}d")
            avg_s = f"{avg:.1%}" if avg is not None else "N/A"
            exc_s = f"excess {exc:+.1%}" if exc is not None else ""
            print(f"    {w}d:  {avg_s}  {exc_s}")
        print()

    if verbose:
        print("  Detailed picks (first 20):")
        for p in all_picks[:20]:
            r30 = p.get("returns", {}).get(30)
            r_s = f"{r30:.1%}" if r30 is not None else "N/A"
            acted_s = "ACTED" if p["acted_on"] else "MISSED"
            print(f"    {p['meeting_date']} {p['ticker_yf']:10s} {p['sentiment']:8s} {acted_s:6s} 30d:{r_s}")

    return report_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="周会选股回测")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cached prices")
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = ap.parse_args()
    run(use_cache=not args.no_cache, verbose=args.verbose)
