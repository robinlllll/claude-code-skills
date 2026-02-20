"""Unified AI client for multi-model dispatch.

Wraps Gemini, GPT, Grok, and Claude APIs with:
- Consistent async interface
- Retry with exponential backoff
- Error handling (return exception, don't crash)
- Token/cost tracking
- JSON extraction from responses

Usage:
    result = await call_model("gemini", prompt, system_prompt)
    result = await call_model("gpt", prompt)
    result = await call_model("grok", prompt)
    result = await call_model("claude", prompt)
"""

import asyncio
import json
import time
from typing import Optional

from config import (
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    XAI_API_KEY,
    ANTHROPIC_API_KEY,
    MODELS,
)

# Retry settings
MAX_RETRIES = 3
BACKOFF_SCHEDULE = [5, 15, 30]  # seconds


async def call_model(
    provider: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 8000,
    temperature: Optional[float] = None,
) -> dict:
    """Call an AI model and return structured result.

    Args:
        provider: "gemini", "gpt", "grok", or "claude"
        prompt: User prompt
        system_prompt: Optional system prompt
        model: Override model ID
        max_tokens: Max output tokens
        temperature: Temperature (ignored by GPT-5.2)

    Returns:
        {
            "content": str,       # Model response text
            "provider": str,
            "model": str,
            "tokens": {"input": int, "output": int},
            "elapsed_s": float,
            "error": None | str,
        }
    """
    dispatch = {
        "gemini": _call_gemini,
        "gpt": _call_gpt,
        "grok": _call_grok,
        "claude": _call_claude,
    }

    if provider not in dispatch:
        return _error_result(provider, model, f"Unknown provider: {provider}")

    fn = dispatch[provider]
    model = model or MODELS.get(provider) or MODELS.get(f"{provider}_analysis")

    for attempt in range(MAX_RETRIES):
        try:
            result = await fn(prompt, system_prompt, model, max_tokens, temperature)
            return result
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]
                print(
                    f"  [{provider}] Attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                print(f"  [{provider}] All {MAX_RETRIES} attempts failed: {e}")
                return _error_result(provider, model, str(e))


def _error_result(provider: str, model: str, error: str) -> dict:
    return {
        "content": "",
        "provider": provider,
        "model": model or "unknown",
        "tokens": {"input": 0, "output": 0},
        "elapsed_s": 0,
        "error": error,
    }


# ============ Gemini ============


async def _call_gemini(prompt, system_prompt, model, max_tokens, temperature):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    loop = asyncio.get_event_loop()

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

    def _call():
        t0 = time.time()
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
        )
        elapsed = time.time() - t0
        return response, elapsed

    response, elapsed = await loop.run_in_executor(None, _call)
    text = response.text or ""

    # Extract usage if available
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

    return {
        "content": text,
        "provider": "gemini",
        "model": model,
        "tokens": {"input": input_tokens, "output": output_tokens},
        "elapsed_s": round(elapsed, 1),
        "error": None,
    }


# ============ GPT ============


async def _call_gpt(prompt, system_prompt, model, max_tokens, temperature):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    loop = asyncio.get_event_loop()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    def _call():
        t0 = time.time()
        # GPT-5.2 quirks: use max_completion_tokens, no temperature
        kwargs = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        response = client.chat.completions.create(**kwargs)
        elapsed = time.time() - t0
        return response, elapsed

    response, elapsed = await loop.run_in_executor(None, _call)
    text = response.choices[0].message.content or ""

    return {
        "content": text,
        "provider": "gpt",
        "model": model,
        "tokens": {
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        },
        "elapsed_s": round(elapsed, 1),
        "error": None,
    }


# ============ Grok ============


async def _call_grok(prompt, system_prompt, model, max_tokens, temperature):
    if not XAI_API_KEY:
        raise ValueError("XAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")
    loop = asyncio.get_event_loop()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    def _call():
        t0 = time.time()
        kwargs = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = client.chat.completions.create(**kwargs)
        elapsed = time.time() - t0
        return response, elapsed

    response, elapsed = await loop.run_in_executor(None, _call)
    text = response.choices[0].message.content or ""

    return {
        "content": text,
        "provider": "grok",
        "model": model,
        "tokens": {
            "input": response.usage.prompt_tokens if response.usage else 0,
            "output": response.usage.completion_tokens if response.usage else 0,
        },
        "elapsed_s": round(elapsed, 1),
        "error": None,
    }


# ============ Claude ============


async def _call_claude(prompt, system_prompt, model, max_tokens, temperature):
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    loop = asyncio.get_event_loop()

    def _call():
        t0 = time.time()
        kwargs = {
            "model": model or "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        response = client.messages.create(**kwargs)
        elapsed = time.time() - t0
        return response, elapsed

    response, elapsed = await loop.run_in_executor(None, _call)
    text = response.content[0].text if response.content else ""

    return {
        "content": text,
        "provider": "claude",
        "model": response.model,
        "tokens": {
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
        },
        "elapsed_s": round(elapsed, 1),
        "error": None,
    }


# ============ Utilities ============


def extract_json(text: str) -> dict | None:
    """Extract JSON object from model response text (robust)."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    return None


async def parallel_dispatch(tasks: list[dict]) -> list[dict]:
    """Run multiple AI calls in parallel.

    Args:
        tasks: List of dicts with keys: provider, prompt, system_prompt, model

    Returns:
        List of results in same order as tasks
    """
    coros = []
    for task in tasks:
        coros.append(
            call_model(
                provider=task["provider"],
                prompt=task["prompt"],
                system_prompt=task.get("system_prompt"),
                model=task.get("model"),
                max_tokens=task.get("max_tokens", 8000),
                temperature=task.get("temperature"),
            )
        )

    results = await asyncio.gather(*coros, return_exceptions=True)

    # Convert exceptions to error results
    final = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            final.append(
                _error_result(
                    tasks[i]["provider"],
                    tasks[i].get("model"),
                    str(r),
                )
            )
        else:
            final.append(r)

    return final
