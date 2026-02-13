#!/usr/bin/env python3
"""
Gemini analyzer — sends transcript PDFs to Gemini 3 Pro for analysis.

Uses google.genai Client (new SDK), uploads PDFs, sends prompt with ThinkingConfig.
Includes retry logic with exponential backoff.
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


# Load .env file
def load_env():
    for env_path in [Path.home() / ".env", Path(__file__).parent / ".env"]:
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value and key not in os.environ:
                            os.environ[key] = value


load_env()

# Add skills to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Import prompt template
PROMPT_DIR = (
    Path(__file__).resolve().parent.parent.parent / "organizer-transcript" / "prompts"
)
sys.path.insert(0, str(PROMPT_DIR))
from prompt_claude import get_claude_prompt

# Load config
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_gemini_analysis(manifest: dict, config: dict) -> dict:
    """
    Run Gemini analysis on transcript PDFs.

    Returns dict with status and output path.
    """
    workdir = Path(manifest["workdir"])
    output_path = workdir / "gemini_output.md"

    gemini_config = config["models"]["gemini"]
    model_id = gemini_config["model_id"]
    max_retries = gemini_config["max_retries"]
    backoff_schedule = gemini_config["backoff_schedule"]

    # Get API key
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        error_msg = "STATUS: FAILED\n\nNo GOOGLE_API_KEY or GEMINI_API_KEY environment variable set."
        output_path.write_text(error_msg, encoding="utf-8")
        return {"status": "failed", "error": "No API key"}

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        error_msg = "STATUS: FAILED\n\ngoogle-genai package not installed. Run: pip install google-genai"
        output_path.write_text(error_msg, encoding="utf-8")
        return {"status": "failed", "error": "google-genai not installed"}

    # Build prompt
    ticker = manifest["ticker"]
    company = manifest["company"]
    curr_q = manifest["quarter"]
    prev_q = manifest["prev_quarter"]
    quarters_comparison = f"{curr_q} vs {prev_q}"

    # Build company-specific notes from insights
    company_notes = ""
    if manifest.get("insights"):
        company_notes = manifest["insights"]

    prompt = get_claude_prompt(
        company_name=company,
        ticker=ticker,
        curr=curr_q,
        prev=prev_q,
        quarters_comparison=quarters_comparison,
        company_specific_notes=company_notes,
    )

    # Initialize client
    client = genai.Client(api_key=api_key)

    # Upload PDFs
    parts = []
    pdf_paths = []
    if manifest.get("curr_pdf"):
        pdf_paths.append(manifest["curr_pdf"])
    if manifest.get("prev_pdf"):
        pdf_paths.append(manifest["prev_pdf"])

    for pdf_path in pdf_paths:
        pdf_file = Path(pdf_path)
        if pdf_file.exists():
            print(f"Uploading {pdf_file.name}...")
            try:
                uploaded = client.files.upload(file=str(pdf_file))
                parts.append(uploaded)
            except Exception as e:
                print(f"WARNING: Failed to upload {pdf_file.name}: {e}")

    parts.append(prompt)

    # Call Gemini with retry
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"Calling Gemini {model_id} (attempt {attempt + 1}/{max_retries})...")
            response = client.models.generate_content(
                model=model_id,
                contents=parts,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(
                        thinking_level=gemini_config["thinking_level"]
                    )
                ),
            )

            # Write output
            output_text = response.text or ""
            output_path.write_text(output_text, encoding="utf-8")
            print(f"Gemini analysis complete: {len(output_text)} chars")

            return {
                "status": "success",
                "output_path": str(output_path).replace("\\", "/"),
                "chars": len(output_text),
            }

        except Exception as e:
            last_error = str(e)
            print(f"Gemini attempt {attempt + 1} failed: {last_error}")

            if attempt < max_retries - 1:
                wait = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
                print(f"Retrying in {wait}s...")
                time.sleep(wait)

    # All retries exhausted
    error_msg = f"STATUS: FAILED\n\nAll {max_retries} Gemini attempts failed.\nLast error: {last_error}"
    output_path.write_text(error_msg, encoding="utf-8")

    return {
        "status": "failed",
        "error": last_error,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run Gemini analysis on earnings transcript"
    )
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file")
    args = parser.parse_args()

    # Load manifest
    manifest_path = Path(args.manifest)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    config = load_config()

    result = run_gemini_analysis(manifest, config)

    # Print result as JSON for the caller
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
