"""Minimal async TokenRouter client: retries, timeout, backoff."""
import asyncio
import random
import time

import httpx

from src.config import BASE_URL, MAX_ATTEMPTS, MODEL_SLUG, REQUEST_TIMEOUT_S, RETRY_STATUS, TOKENROUTER_API_KEY

_HEADERS = {
    "Authorization": f"Bearer {TOKENROUTER_API_KEY}",
    "Content-Type": "application/json",
}


class AttemptExhausted(Exception):
    """All attempts failed; carries the last error message."""


async def completion(
    messages,
    temperature=0.0,
    reasoning_effort="high",
    response_format=None,
    max_tokens=4096,
):
    """One chat completion with retry on 429/5xx/timeout. Returns (body, latency_s, attempt)."""
    payload = {
        "model": MODEL_SLUG,
        "messages": messages,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
                r = await client.post(
                    f"{BASE_URL}/chat/completions", headers=_HEADERS, json=payload
                )
            if r.status_code == 200:
                try:
                    return r.json(), time.perf_counter() - t0, attempt
                except Exception as e:
                    # Transient provider bug observed under rate pressure: HTTP 200
                    # with an empty or non-JSON body. Retry like a 5xx.
                    last_err = f"200-with-bad-body: {type(e).__name__}: {r.text[:120]!r}"
            elif r.status_code in RETRY_STATUS:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            else:
                raise AttemptExhausted(f"HTTP {r.status_code}: {r.text[:200]}")
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(min(2 ** attempt, 30) + random.uniform(0, 1))
    raise AttemptExhausted(last_err or "unknown error")
