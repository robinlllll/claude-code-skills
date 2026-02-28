"""
Preflight validation for multi-AI pipelines.

Usage:
    from shared.preflight import validate_api_keys, validate_server, preflight_all

    results = validate_api_keys()
    # {"gemini": True, "openai": False, "xai": True}

    server_ok = validate_server("http://localhost:8000")
    # True/False

    report = preflight_all(require_keys=["gemini", "openai"], server_url="http://localhost:8000")
    # {"api_keys": {...}, "server": True, "all_ok": False, "failures": ["openai API key"]}
"""

import os
from pathlib import Path
from typing import Dict, List, Optional


def _load_env_files() -> None:
    """Load .env files from known locations into os.environ."""
    env_paths = [
        Path(os.path.expanduser("~")) / "Screenshots" / ".env",
        Path(os.path.expanduser("~")) / "13F-CLAUDE" / ".env",
        Path(os.path.expanduser("~"))
        / ".claude"
        / "skills"
        / "transcript-analyzer"
        / "browser"
        / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key and value and key not in os.environ:
                            os.environ[key] = value
            except Exception:
                pass


def validate_api_keys(verbose: bool = False) -> Dict[str, bool]:
    """
    Validate that all AI provider API keys are present and non-empty.

    Returns dict mapping provider name to validity boolean.
    Does NOT make test API calls — just checks that keys exist.
    Use validate_api_keys_live() for actual test calls.
    """
    _load_env_files()

    providers = {
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "xai": ["XAI_API_KEY"],
    }

    results = {}
    for provider, key_names in providers.items():
        found = False
        for key_name in key_names:
            val = os.environ.get(key_name, "").strip()
            if val and len(val) > 10:  # Minimum viable key length
                found = True
                if verbose:
                    print(f"  {provider}: {key_name} = {val[:8]}...{val[-4:]}")
                break
        results[provider] = found
        if not found and verbose:
            print(f"  {provider}: MISSING (checked {key_names})")

    return results


def validate_api_keys_live(
    providers: Optional[List[str]] = None,
    verbose: bool = True,
) -> Dict[str, str]:
    """
    Make a trivial test call to each AI provider and confirm it works.

    Args:
        providers: List of providers to test. Default: ["gemini", "gpt", "grok"]
        verbose: Print results as they complete.

    Returns:
        Dict mapping provider -> "OK (1.2s)" or error string.
    """
    import time

    _load_env_files()
    targets = providers or ["gemini", "gpt", "grok"]
    results = {}

    for name in targets:
        t0 = time.time()
        err = None
        try:
            if name == "gemini":
                key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get(
                    "GOOGLE_API_KEY", ""
                )
                if not key:
                    err = "GEMINI_API_KEY not set"
                else:
                    from google import genai

                    client = genai.Client(api_key=key)
                    resp = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents="Reply with exactly: OK",
                    )
                    if not (resp.text and resp.text.strip()):
                        err = "Empty response"

            elif name == "gpt":
                key = os.environ.get("OPENAI_API_KEY", "")
                if not key:
                    err = "OPENAI_API_KEY not set"
                else:
                    from openai import OpenAI

                    client = OpenAI(api_key=key)
                    resp = client.chat.completions.create(
                        model="gpt-5.2-chat-latest",
                        messages=[
                            {"role": "user", "content": "Reply with exactly: OK"}
                        ],
                        max_completion_tokens=100,
                    )
                    if not (resp.choices and resp.choices[0].message.content):
                        err = "Empty response"

            elif name == "grok":
                key = os.environ.get("XAI_API_KEY", "")
                if not key:
                    err = "XAI_API_KEY not set"
                else:
                    from openai import OpenAI

                    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
                    resp = client.chat.completions.create(
                        model="grok-4-1-fast-reasoning",
                        messages=[
                            {"role": "user", "content": "Reply with exactly: OK"}
                        ],
                        max_tokens=20,
                    )
                    if not (resp.choices and resp.choices[0].message.content):
                        err = "Empty response"
            else:
                err = f"Unknown provider: {name}"

        except Exception as e:
            err = str(e)[:200]

        elapsed = time.time() - t0
        results[name] = err if err else f"OK ({elapsed:.1f}s)"

        if verbose:
            status = results[name]
            icon = "PASS" if status.startswith("OK") else "FAIL"
            print(f"  [{icon}] {name:8s} -> {status}")

    return results


def validate_server(url: str = "http://localhost:8000", timeout: float = 3.0) -> bool:
    """Check if a server is responding."""
    try:
        import urllib.request

        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status < 500
    except Exception:
        return False


def validate_file_target(file_path: str) -> Dict[str, object]:
    """
    Validate that a file path points to the correct target.
    Returns {"exists": bool, "is_correct": bool, "suggestion": str|None}
    """
    p = Path(file_path)
    result = {"exists": p.exists(), "is_correct": True, "suggestion": None}

    # Check for common wrong-file patterns
    if p.name == "index.html" and "portfolio_monitor" in str(p):
        result["is_correct"] = False
        result["suggestion"] = str(p.parent / "index_v2.html")

    return result


def preflight_all(
    require_keys: Optional[List[str]] = None,
    server_url: Optional[str] = None,
    target_files: Optional[List[str]] = None,
) -> Dict:
    """
    Run all preflight checks. Returns a comprehensive report.

    Args:
        require_keys: List of provider names to require (e.g., ["gemini", "openai"])
        server_url: URL to check for server availability
        target_files: List of file paths to validate
    """
    report = {"all_ok": True, "failures": []}

    # API keys
    key_results = validate_api_keys()
    report["api_keys"] = key_results
    if require_keys:
        for provider in require_keys:
            if not key_results.get(provider, False):
                report["all_ok"] = False
                report["failures"].append(f"{provider} API key missing or invalid")

    # Server
    if server_url:
        server_ok = validate_server(server_url)
        report["server"] = server_ok
        if not server_ok:
            report["all_ok"] = False
            report["failures"].append(f"Server not responding at {server_url}")

    # File targets
    if target_files:
        file_results = {}
        for f in target_files:
            file_results[f] = validate_file_target(f)
            if not file_results[f]["is_correct"]:
                report["all_ok"] = False
                suggestion = file_results[f]["suggestion"]
                report["failures"].append(f"Wrong file target: {f} → use {suggestion}")
        report["file_targets"] = file_results

    return report


if __name__ == "__main__":
    import sys as _sys

    print("=" * 50)
    print("  API Preflight Check")
    print("=" * 50)

    # Accept provider names as args: python preflight.py gemini gpt
    targets = _sys.argv[1:] if len(_sys.argv) > 1 else None
    results = validate_api_keys_live(providers=targets)

    print("=" * 50)
    all_ok = all(v.startswith("OK") for v in results.values())
    if all_ok:
        print("  All checks passed. Safe to run batch.")
    else:
        failed = [k for k, v in results.items() if not v.startswith("OK")]
        print(f"  BLOCKED: {', '.join(failed)} failed. Fix before running batch.")
    print("=" * 50)

    _sys.exit(0 if all_ok else 1)
