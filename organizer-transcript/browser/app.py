#!/usr/bin/env python3
"""
Transcript Browser - FastAPI Backend
Browse earnings transcripts and generate analysis prompts.
Supports company-specific notes and analysis history tracking.
Now with Obsidian vault integration for persistent analysis storage.
"""

import json
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional

from indexer import scan_transcripts, search_companies
from obsidian import (
    save_analysis as obsidian_save_analysis,
    save_company_notes as obsidian_save_notes,
    get_analysis_history as obsidian_get_history,
    get_obsidian_uri,
    check_obsidian_configured,
    EARNINGS_FOLDER,
)
from ai_provider import get_all_providers, get_default_provider

# Add parent directory to path for prompts import
import sys

_prompts_dir = Path(__file__).parent.parent
if str(_prompts_dir) not in sys.path:
    sys.path.insert(0, str(_prompts_dir))
from prompts import get_prompt_for_provider


# Configuration
BROWSER_DIR = Path(__file__).parent
TEMPLATES_DIR = BROWSER_DIR / "templates"
STATIC_DIR = BROWSER_DIR / "static"
PROMPTS_DIR = BROWSER_DIR.parent / "prompts"
DATA_DIR = BROWSER_DIR / "data"
COMPANY_NOTES_FILE = DATA_DIR / "company_notes.json"
ANALYSIS_HISTORY_FILE = DATA_DIR / "analysis_history.json"
RECENT_ADDITIONS_FILE = DATA_DIR / "recent_additions.json"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Global index (loaded on startup)
companies_index = {}


@asynccontextmanager
async def lifespan(app):
    """Load transcript index on startup."""
    global companies_index
    print("Scanning transcript folders...")
    companies_index = scan_transcripts()
    print(f"Indexed {len(companies_index)} companies")
    yield


# Initialize app
app = FastAPI(title="Transcript Browser", version="1.0.0", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_json_file(filepath: Path) -> dict:
    """Load JSON file, return empty dict if not exists."""
    if filepath.exists():
        return json.loads(filepath.read_text(encoding="utf-8"))
    return {}


def load_json_list(filepath: Path) -> list:
    """Load JSON file as list, return empty list if not exists."""
    if filepath.exists():
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return []
    return []


def get_recent_tickers(hours: int = 24) -> set:
    """Get tickers that were added in the last N hours."""
    recent = load_json_list(RECENT_ADDITIONS_FILE)
    cutoff = datetime.now().timestamp() - (hours * 3600)

    recent_tickers = set()
    for item in recent:
        if item.get("ticker"):
            try:
                added_at = datetime.fromisoformat(item["added_at"]).timestamp()
                if added_at > cutoff:
                    recent_tickers.add(item["ticker"])
            except (ValueError, KeyError):
                # If no timestamp or invalid, include it anyway (just added)
                recent_tickers.add(item["ticker"])
    return recent_tickers


def save_json_file(filepath: Path, data: dict):
    """Save data to JSON file."""
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# Request/Response models
class PromptRequest(BaseModel):
    ticker: str
    transcripts: list[str]  # List of "Q4 2025" format
    provider: str = "default"  # "gemini", "claude", "chatgpt", or "default"


class PromptResponse(BaseModel):
    prompt: str
    files: list[str]


class CompanyNotes(BaseModel):
    ticker: str
    notes: str  # Company-specific analysis notes
    follow_up_questions: list[str] = []  # Questions to follow up on


class AnalysisRecord(BaseModel):
    ticker: str
    quarters: list[str]
    timestamp: str
    ai_response: Optional[str] = None
    user_comments: Optional[str] = None
    pdf_paths: Optional[list[str]] = None
    ai_provider: str = "chatgpt"
    save_to_obsidian: bool = True


# Routes
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main UI."""
    html_file = TEMPLATES_DIR / "index.html"
    return html_file.read_text(encoding="utf-8")


@app.get("/api/companies")
async def list_companies(search: str = None):
    """
    List all companies with summary stats.
    Optional search query filters by ticker or company name.
    Recently added companies appear first.
    """
    if search:
        results = search_companies(companies_index, search)
    else:
        results = []
        for ticker, company in companies_index.items():
            results.append(
                {
                    "ticker": ticker,
                    "company": company.company,
                    "count": company.count,
                    "latest_quarter": company.latest_quarter,
                    "latest_date": company.latest_date,
                }
            )

    # Add notes indicator and recent flag
    notes_data = load_json_file(COMPANY_NOTES_FILE)
    recent_tickers = get_recent_tickers(hours=24)

    for r in results:
        r["has_notes"] = r["ticker"] in notes_data
        r["is_recent"] = r["ticker"] in recent_tickers

    # Sort: recent first, then alphabetically
    results.sort(key=lambda c: (not c["is_recent"], c["company"].lower()))

    return {
        "companies": results,
        "total": len(results),
        "recent_count": len([r for r in results if r["is_recent"]]),
    }


@app.get("/api/companies/{ticker}")
async def get_company(ticker: str):
    """Get detailed transcript info for a specific company."""
    if ticker not in companies_index:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    company = companies_index[ticker]

    # Load company notes if exists
    notes_data = load_json_file(COMPANY_NOTES_FILE)
    company_notes = notes_data.get(ticker, {"notes": "", "follow_up_questions": []})

    # Load analysis history
    history_data = load_json_file(ANALYSIS_HISTORY_FILE)
    company_history = history_data.get(ticker, [])

    return {
        "ticker": company.ticker,
        "company": company.company,
        "folder_path": company.folder_path,
        "count": company.count,
        "latest_quarter": company.latest_quarter,
        "latest_date": company.latest_date,
        "transcripts": company.transcripts,
        "notes": company_notes.get("notes", ""),
        "follow_up_questions": company_notes.get("follow_up_questions", []),
        "analysis_history": company_history[-5:],  # Last 5 analyses
    }


@app.post("/api/companies/{ticker}/notes")
async def save_company_notes_endpoint(ticker: str, notes: CompanyNotes):
    """Save company-specific notes and follow-up questions."""
    # Save to JSON (existing behavior)
    notes_data = load_json_file(COMPANY_NOTES_FILE)
    notes_data[ticker] = {
        "notes": notes.notes,
        "follow_up_questions": notes.follow_up_questions,
        "updated_at": datetime.now().isoformat(),
    }
    save_json_file(COMPANY_NOTES_FILE, notes_data)

    # Also save to Obsidian
    company_name = ""
    if ticker in companies_index:
        company_name = companies_index[ticker].company

    obsidian_path = None
    try:
        path = obsidian_save_notes(
            ticker=ticker,
            company=company_name or ticker,
            notes=notes.notes,
            follow_up_questions=notes.follow_up_questions,
        )
        obsidian_path = str(path)
    except Exception as e:
        print(f"Failed to save notes to Obsidian: {e}")

    return {"status": "ok", "obsidian_path": obsidian_path}


@app.post("/api/analysis/{ticker}")
async def save_analysis_endpoint(ticker: str, record: AnalysisRecord):
    """Save analysis record (AI response + user comments)."""
    # Save to JSON (existing behavior)
    history_data = load_json_file(ANALYSIS_HISTORY_FILE)
    if ticker not in history_data:
        history_data[ticker] = []

    history_data[ticker].append(
        {
            "quarters": record.quarters,
            "timestamp": record.timestamp,
            "ai_response": record.ai_response,
            "user_comments": record.user_comments,
            "ai_provider": record.ai_provider,
        }
    )

    # Keep last 20 records per company
    history_data[ticker] = history_data[ticker][-20:]
    save_json_file(ANALYSIS_HISTORY_FILE, history_data)

    # Save to Obsidian if enabled
    obsidian_path = None
    obsidian_uri = None

    if record.save_to_obsidian:
        company_name = ""
        if ticker in companies_index:
            company_name = companies_index[ticker].company

        # Get tracked insight IDs for this analysis
        from insight_ledger import get_active_insights
        active_insights = get_active_insights(ticker)
        tracked_ids = [ins.id for ins in active_insights] if active_insights else None

        try:
            path = obsidian_save_analysis(
                ticker=ticker,
                company=company_name or ticker,
                quarters=record.quarters,
                ai_response=record.ai_response or "",
                user_comments=record.user_comments or "",
                pdf_paths=record.pdf_paths,
                ai_provider=record.ai_provider,
                tracked_insights=tracked_ids,
            )
            obsidian_path = str(path)
            obsidian_uri = get_obsidian_uri(path)
        except Exception as e:
            print(f"Failed to save analysis to Obsidian: {e}")

    return {
        "status": "ok",
        "obsidian_path": obsidian_path,
        "obsidian_uri": obsidian_uri,
    }


@app.post("/api/prompt", response_model=PromptResponse)
async def generate_prompt(request: PromptRequest):
    """Generate analysis prompt for selected transcripts.

    Uses provider-specific prompt templates:
    - gemini: Optimized for Gemini 2.5 Pro (emphasizes citations, structured breakdowns)
    - claude: Optimized for Claude (concise, table-heavy, sharp insights)
    - default/chatgpt: Original template (do not modify)
    """
    if request.ticker not in companies_index:
        raise HTTPException(
            status_code=404, detail=f"Company {request.ticker} not found"
        )

    company = companies_index[request.ticker]

    # Find matching transcript files
    # Selection labels now include event_type prefix to distinguish
    # "Earnings Call|Q4 2025" vs "Conference|Q4 2025"
    selected_files = []
    selected_labels = []

    for t in company.transcripts:
        if t["quarter"] and t["year"]:
            # New format: "event_type|Q# YYYY" (from updated frontend)
            typed_label = f"{t['event_type']}|{t['quarter']} {t['year']}"
            # Legacy format: "Q# YYYY" (backwards compatible, matches earnings only)
            legacy_label = f"{t['quarter']} {t['year']}"

            if typed_label in request.transcripts:
                selected_files.append(t["path"])
                selected_labels.append(
                    f"- {t['quarter']} {t['year']} {t['event_type']} ({t['transcript_type']})"
                )
            elif legacy_label in request.transcripts and t["event_type"] == "Earnings Call":
                # Legacy format: only match earnings calls to prevent conference contamination
                selected_files.append(t["path"])
                selected_labels.append(
                    f"- {legacy_label} {t['event_type']} ({t['transcript_type']})"
                )

    if not selected_files:
        raise HTTPException(status_code=400, detail="No matching transcripts found")

    # Determine previous and current quarters for comparison
    # Sort by year descending, then quarter descending (Q4 > Q3 > Q2 > Q1)
    def quarter_sort_key(q):
        parts = q.split()
        if len(parts) == 2:
            quarter_num = int(parts[0][1])  # Extract number from "Q1", "Q2", etc.
            year = int(parts[1])
            return (year, quarter_num)
        return (0, 0)

    quarters = sorted(request.transcripts, key=quarter_sort_key, reverse=True)
    curr = quarters[0] if quarters else "当前季度"
    prev = quarters[1] if len(quarters) > 1 else "上一季度"
    quarters_comparison = f"{curr} vs {prev}"

    # Load company-specific notes
    notes_data = load_json_file(COMPANY_NOTES_FILE)
    company_notes = notes_data.get(request.ticker, {})

    # Build company-specific section
    company_specific_notes = ""
    if company_notes.get("notes") or company_notes.get("follow_up_questions"):
        company_specific_notes = "\n5. **公司特定关注点 (Company-Specific Focus):**\n"
        if company_notes.get("notes"):
            company_specific_notes += f"   - 背景备注: {company_notes['notes']}\n"
        if company_notes.get("follow_up_questions"):
            company_specific_notes += "   - 需要跟进的问题:\n"
            for q in company_notes["follow_up_questions"]:
                company_specific_notes += f"     * {q}\n"

    # Inject prior insights from Insight Ledger
    from insight_ledger import load_ledger, format_for_prompt
    ledger = load_ledger(request.ticker)
    active_ins = [i for i in ledger.insights if "⏳" in i.status or "🔄" in i.status]
    resolved_ins = [i for i in ledger.insights if "✅" in i.status or "❌" in i.status]
    if active_ins or resolved_ins:
        company_specific_notes += format_for_prompt(active_ins, resolved_ins)

    # Get provider-specific prompt template
    prompt = get_prompt_for_provider(
        provider=request.provider,
        company_name=company.company,
        ticker=company.ticker,
        curr=curr,
        prev=prev,
        quarters_comparison=quarters_comparison,
        company_specific_notes=company_specific_notes,
    )

    return PromptResponse(prompt=prompt, files=selected_files)


@app.get("/api/refresh")
async def refresh_index():
    """Refresh the transcript index."""
    global companies_index
    companies_index = scan_transcripts()
    return {"status": "ok", "companies": len(companies_index)}


@app.get("/api/config")
async def get_config():
    """Get Obsidian and AI provider configuration status."""
    obsidian_status = check_obsidian_configured()
    providers = get_all_providers()
    default_provider = get_default_provider()

    return {
        "obsidian": obsidian_status,
        "providers": providers,
        "default_provider": default_provider.value,
    }


class AnalyzeRequest(BaseModel):
    ticker: str
    transcripts: list[str]
    provider: str  # "claude" or "gemini"


@app.post("/api/analyze")
async def run_ai_analysis(request: AnalyzeRequest):
    """
    Run AI analysis directly on transcript PDFs.
    Sends PDFs + prompt to Claude or Gemini API.
    """
    if request.ticker not in companies_index:
        raise HTTPException(
            status_code=404, detail=f"Company {request.ticker} not found"
        )

    company = companies_index[request.ticker]

    # Find matching transcript files (same logic as /api/prompt)
    pdf_paths = []
    for t in company.transcripts:
        if t["quarter"] and t["year"]:
            typed_label = f"{t['event_type']}|{t['quarter']} {t['year']}"
            legacy_label = f"{t['quarter']} {t['year']}"

            if typed_label in request.transcripts:
                pdf_paths.append(t["path"])
            elif legacy_label in request.transcripts and t["event_type"] == "Earnings Call":
                pdf_paths.append(t["path"])

    if not pdf_paths:
        raise HTTPException(status_code=400, detail="No matching transcripts found")

    # Generate the prompt with provider-specific template
    prompt_response = await generate_prompt(
        PromptRequest(
            ticker=request.ticker,
            transcripts=request.transcripts,
            provider=request.provider,  # Use provider-specific prompt template
        )
    )

    # Run analysis based on provider
    if request.provider == "claude":
        result = await analyze_with_claude(
            prompt=prompt_response.prompt,
            pdf_paths=pdf_paths,
            company=company.company,
            ticker=request.ticker,
        )
    elif request.provider == "gemini":
        result = await analyze_with_gemini(
            prompt=prompt_response.prompt,
            pdf_paths=pdf_paths,
            company=company.company,
            ticker=request.ticker,
        )
    else:
        raise HTTPException(
            status_code=400, detail=f"Unknown provider: {request.provider}"
        )

    return result


async def analyze_with_claude(
    prompt: str, pdf_paths: list[str], company: str, ticker: str
) -> dict:
    """Run analysis using Claude Opus 4.5 API."""
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        # Try loading from .env
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        return {
            "status": "error",
            "error": "ANTHROPIC_API_KEY not configured. Add it to browser/.env file.",
            "response": None,
        }

    try:
        import anthropic
        import base64

        client = anthropic.Anthropic(api_key=api_key)

        # Build message content with PDFs
        content = []

        # Add PDFs as base64
        for pdf_path in pdf_paths:
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                pdf_data = base64.standard_b64encode(pdf_file.read_bytes()).decode(
                    "utf-8"
                )
                content.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        },
                    }
                )

        # Add prompt
        content.append({"type": "text", "text": prompt})

        # Call Claude API
        message = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=16000,
            messages=[{"role": "user", "content": content}],
        )

        response_text = message.content[0].text

        return {
            "status": "ok",
            "provider": "claude",
            "model": "claude-opus-4-5-20251101",
            "response": response_text,
            "usage": {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        }

    except ImportError:
        return {
            "status": "error",
            "error": "anthropic package not installed. Run: pip install anthropic",
            "response": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Claude API error: {str(e)}",
            "response": None,
        }


async def analyze_with_gemini(
    prompt: str, pdf_paths: list[str], company: str, ticker: str
) -> dict:
    """Run analysis using Gemini 3 Pro API with thinking capability."""
    import os

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        # Try loading from .env
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        return {
            "status": "error",
            "error": "GOOGLE_API_KEY not configured. Add it to browser/.env file.",
            "response": None,
        }

    try:
        from google import genai
        from google.genai import types

        # Initialize client with new SDK
        client = genai.Client(api_key=api_key)

        # Build content parts: PDFs first, then prompt
        parts = []

        # Upload PDFs using new SDK
        for pdf_path in pdf_paths:
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                uploaded = client.files.upload(file=str(pdf_file))
                parts.append(uploaded)

        # Add prompt
        parts.append(prompt)

        # Generate response with Gemini 3 Pro and thinking enabled
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=parts,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="HIGH")
            ),
        )

        return {
            "status": "ok",
            "provider": "gemini",
            "model": "gemini-3-pro-preview",
            "response": response.text,
            "usage": None,
        }

    except ImportError:
        return {
            "status": "error",
            "error": "google-genai package not installed. Run: pip install google-genai",
            "response": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Gemini API error: {str(e)}",
            "response": None,
        }


@app.get("/api/obsidian/{ticker}/history")
async def get_obsidian_history(ticker: str):
    """Get analysis history from Obsidian vault for a ticker."""
    history = obsidian_get_history(ticker)
    return {"ticker": ticker, "analyses": history}


@app.post("/api/obsidian/open/{ticker}")
async def get_obsidian_open_uri(ticker: str, filename: str = None):
    """
    Get Obsidian URI to open a file.
    If filename provided, open that specific file.
    Otherwise, open the company's notes file.
    """

    if filename:
        filepath = EARNINGS_FOLDER / ticker.upper() / filename
    else:
        filepath = EARNINGS_FOLDER / ticker.upper() / f"_{ticker.upper()} Notes.md"

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")

    uri = get_obsidian_uri(filepath)
    return {"uri": uri, "path": str(filepath)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8008)
