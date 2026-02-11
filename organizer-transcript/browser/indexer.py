#!/usr/bin/env python3
"""
Transcript Indexer
Scans earnings transcript folders and builds a searchable index.
"""

import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


# Configuration
TRANSCRIPTS_ROOT = Path.home() / "Downloads" / "Earnings Transcripts"


@dataclass
class Transcript:
    """Represents a single earnings transcript."""

    filename: str
    path: str
    quarter: Optional[str]  # Q1, Q2, Q3, Q4
    year: Optional[int]
    event_type: str  # "Earnings Call", "Conference", "Investor Day", etc.
    transcript_type: str  # "CORRECTED", "RAW", "CALLSTREET"
    date: Optional[str]  # YYYY-MM-DD
    sort_key: str  # For sorting: YYYY-Q# or date
    event_name: str = (
        ""  # Full event name from filename (e.g. "UBS Financial Services Conference")
    )


@dataclass
class Company:
    """Represents a company with its transcripts."""

    ticker: str
    company: str
    folder_path: str
    transcripts: list
    latest_quarter: Optional[str]
    latest_date: Optional[str]
    count: int


def parse_folder_name(folder_name: str) -> tuple[str, str]:
    """
    Parse folder name to extract ticker and company name.

    Formats:
    - "Apple, Inc (AAPL-US)" -> ("AAPL-US", "Apple, Inc")
    - "AAPL-US" -> ("AAPL-US", "AAPL-US")
    - "000660-KR" -> ("000660-KR", "000660-KR")
    """
    # Format: Company Name (TICKER-EXCHANGE) — supports dotted tickers like NOVO.B-DK
    match = re.match(r"^(.+?)\s*\(([A-Z0-9.]+-[A-Z]+)\)$", folder_name)
    if match:
        return match.group(2), match.group(1).strip()

    # Format: TICKER-EXCHANGE only (e.g., ASSA.B-SE)
    if re.match(r"^[A-Z0-9.]+-[A-Z]+$", folder_name):
        return folder_name, folder_name

    # Fallback: use folder name as both
    return folder_name, folder_name


def parse_transcript_filename(filename: str) -> dict:
    """
    Parse transcript filename to extract metadata.

    Example filenames:
    - CORRECTED TRANSCRIPT_ Apple, Inc.(AAPL-US), Q1 2025 Earnings Call, 30-January-2025 5_00 PM ET.pdf
    - RAW TRANSCRIPT_ Adobe Inc.(ADBE-US), Q4 2025 Earnings Call, 10-December-2025 5_00 PM ET.pdf
    - RAW TRANSCRIPT_ Apple, Inc.(AAPL-US), World Wide Developers Conference...
    """
    result = {
        "quarter": None,
        "year": None,
        "event_type": "Other",
        "transcript_type": "UNKNOWN",
        "date": None,
    }

    # Extract transcript type
    if filename.startswith("CORRECTED TRANSCRIPT"):
        result["transcript_type"] = "CORRECTED"
    elif filename.startswith("RAW TRANSCRIPT"):
        result["transcript_type"] = "RAW"
    elif filename.startswith("CALLSTREET"):
        result["transcript_type"] = "CALLSTREET"

    # Extract quarter and year: Q1 2025, Q2 2024, etc.
    quarter_match = re.search(r"Q([1-4])\s+(\d{4})", filename)
    if quarter_match:
        result["quarter"] = f"Q{quarter_match.group(1)}"
        result["year"] = int(quarter_match.group(2))

    # Determine event type — Earnings Call vs everything else
    if "Earnings Call" in filename:
        result["event_type"] = "Earnings Call"
    elif "Conference" in filename or "Forum" in filename or "Summit" in filename:
        result["event_type"] = "Conference"
    elif "Investor Day" in filename or "Investor Meeting" in filename:
        result["event_type"] = "Investor Day"
    elif "Analyst Day" in filename or "Analyst Meeting" in filename:
        result["event_type"] = "Analyst Day"
    elif "Capital Markets Day" in filename:
        result["event_type"] = "Capital Markets Day"
    elif "Acquisition of" in filename or "Merger" in filename:
        result["event_type"] = "M&A Call"
    elif "Business Update" in filename:
        result["event_type"] = "Business Update"
    elif "Sales and Revenue" in filename or "Trading Update" in filename:
        result["event_type"] = "Sales Update"
    elif "Guidance Call" in filename:
        result["event_type"] = "Guidance Call"
    elif "Keynote" in filename or "WWDC" in filename or "GTC" in filename:
        result["event_type"] = "Keynote"
    elif "Annual General Meeting" in filename or "AGM" in filename:
        result["event_type"] = "AGM"
    elif "Fireside" in filename:
        result["event_type"] = "Fireside Chat"

    # Extract event name for conferences (the specific conference name)
    event_name_match = re.search(
        r"\([A-Z0-9.]+-[A-Z]+\),\s*(?:Q[1-4]\s+\d{4}\s+)?(.+?),\s*\d{1,2}-[A-Za-z]+-\d{4}",
        filename,
    )
    if event_name_match:
        result["event_name"] = event_name_match.group(1).strip()
    else:
        result["event_name"] = result["event_type"]

    # Extract date: 30-January-2025
    date_match = re.search(r"(\d{1,2})-([A-Za-z]+)-(\d{4})", filename)
    if date_match:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        year = int(date_match.group(3))

        # Convert month name to number
        months = {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12,
        }
        month = months.get(month_name, 1)
        result["date"] = f"{year}-{month:02d}-{day:02d}"

    return result


def scan_transcripts(root_dir: Path = None) -> dict[str, Company]:
    """
    Scan all transcript folders and build an index.

    Returns:
        Dictionary mapping ticker to Company objects
    """
    root_dir = root_dir or TRANSCRIPTS_ROOT
    companies = {}

    if not root_dir.exists():
        return companies

    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue

        ticker, company_name = parse_folder_name(folder.name)

        # Find all PDF transcripts
        transcripts = []
        for pdf in folder.glob("*.pdf"):
            metadata = parse_transcript_filename(pdf.name)

            # Create sort key for ordering (newest first)
            # Prefer date for accurate chronological sort, fall back to year-quarter
            if metadata["date"]:
                sort_key = metadata["date"]
            elif metadata["year"] and metadata["quarter"]:
                sort_key = f"{metadata['year']}-{metadata['quarter']}"
            else:
                sort_key = "0000-00"

            transcript = Transcript(
                filename=pdf.name,
                path=str(pdf),
                quarter=metadata["quarter"],
                year=metadata["year"],
                event_type=metadata["event_type"],
                transcript_type=metadata["transcript_type"],
                date=metadata["date"],
                sort_key=sort_key,
                event_name=metadata.get("event_name", metadata["event_type"]),
            )
            transcripts.append(transcript)

        # Sort transcripts by date (newest first)
        transcripts.sort(key=lambda t: t.sort_key, reverse=True)

        # Determine latest quarter (from earnings calls only)
        earnings_calls = [t for t in transcripts if t.event_type == "Earnings Call"]
        if earnings_calls:
            latest = earnings_calls[0]
            latest_quarter = (
                f"{latest.quarter} {latest.year}"
                if latest.quarter and latest.year
                else None
            )
            latest_date = latest.date
        else:
            latest_quarter = None
            latest_date = transcripts[0].date if transcripts else None

        # Handle duplicate tickers (merge transcripts from both folders)
        if ticker in companies:
            existing = companies[ticker]
            # Combine transcripts from both folders
            merged_transcripts = existing.transcripts + [asdict(t) for t in transcripts]
            # Deduplicate by filename
            seen = set()
            unique_transcripts = []
            for t in merged_transcripts:
                if t["filename"] not in seen:
                    seen.add(t["filename"])
                    unique_transcripts.append(t)
            # Sort by sort_key descending
            unique_transcripts.sort(key=lambda t: t["sort_key"], reverse=True)
            # Use the company name from the folder with more transcripts (more canonical)
            best_name = (
                company_name if len(transcripts) > existing.count else existing.company
            )
            best_folder = (
                str(folder)
                if len(transcripts) > existing.count
                else existing.folder_path
            )
            # Recalculate latest quarter from merged set
            merged_earnings = [
                t for t in unique_transcripts if t["event_type"] == "Earnings Call"
            ]
            if merged_earnings:
                m_latest = merged_earnings[0]
                m_latest_quarter = (
                    f"{m_latest['quarter']} {m_latest['year']}"
                    if m_latest["quarter"] and m_latest["year"]
                    else None
                )
                m_latest_date = m_latest["date"]
            else:
                m_latest_quarter = latest_quarter or existing.latest_quarter
                m_latest_date = latest_date or existing.latest_date
            companies[ticker] = Company(
                ticker=ticker,
                company=best_name,
                folder_path=best_folder,
                transcripts=unique_transcripts,
                latest_quarter=m_latest_quarter,
                latest_date=m_latest_date,
                count=len(unique_transcripts),
            )
        else:
            companies[ticker] = Company(
                ticker=ticker,
                company=company_name,
                folder_path=str(folder),
                transcripts=[asdict(t) for t in transcripts],
                latest_quarter=latest_quarter,
                latest_date=latest_date,
                count=len(transcripts),
            )

    return companies


def get_company_list(companies: dict[str, Company]) -> list[dict]:
    """
    Get a summary list of all companies for the UI.
    """
    result = []
    for ticker, company in companies.items():
        result.append(
            {
                "ticker": ticker,
                "company": company.company,
                "count": company.count,
                "latest_quarter": company.latest_quarter,
                "latest_date": company.latest_date,
            }
        )

    # Sort by company name
    result.sort(key=lambda c: c["company"].lower())
    return result


def search_companies(companies: dict[str, Company], query: str) -> list[dict]:
    """
    Search companies by ticker or name.
    """
    query = query.lower().strip()
    if not query:
        return get_company_list(companies)

    result = []
    for ticker, company in companies.items():
        if query in ticker.lower() or query in company.company.lower():
            result.append(
                {
                    "ticker": ticker,
                    "company": company.company,
                    "count": company.count,
                    "latest_quarter": company.latest_quarter,
                    "latest_date": company.latest_date,
                }
            )

    result.sort(key=lambda c: c["company"].lower())
    return result


if __name__ == "__main__":
    # Test the indexer
    print("Scanning transcripts...")
    companies = scan_transcripts()
    print(f"Found {len(companies)} companies")

    # Show first 5
    for i, (ticker, company) in enumerate(list(companies.items())[:5]):
        print(f"\n{ticker}: {company.company}")
        print(f"  Transcripts: {company.count}")
        print(f"  Latest: {company.latest_quarter}")
        if company.transcripts:
            print(f"  Recent: {company.transcripts[0]['filename'][:60]}...")
