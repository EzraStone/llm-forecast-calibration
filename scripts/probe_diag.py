"""Diagnostic: 4 concurrent calls varying effort and max_tokens; print raw shapes."""
import asyncio
import sys
import time

sys.path.insert(0, ".")
import httpx

from src.config import BASE_URL, TOKENROUTER_API_KEY

HEADERS = {"Authorization": f"Bearer {TOKENROUTER_API_KEY}", "Content-Type": "application/json"}
SCHEMA = {
    "type": "object",
    "properties": {"probability": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
    "required": ["probability"],
}


async def one(tag, effort, max_tokens):
    payload = {
        "model": "z-ai/glm-5.3-free",
        "messages": [
            {"role": "system", "content": "You are a careful superforecaster."},
            {"role": "user", "content": "Will the sun rise tomorrow somewhere on Earth? Reply as JSON with your probability."},
        ],
        "temperature": 1.0,
        "reasoning_effort": effort,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": "forecast", "schema": SCHEMA}},
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=360) as client:
            r = await client.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload)
        dt = time.perf_counter() - t0
        try:
            body = r.json()
        except Exception:
            print(f"[{tag}] HTTP {r.status_code} latency={dt:.1f}s NON-JSON body[:300]={r.text[:300]!r}", flush=True)
            return
        msg = body.get("choices", [{}])[0].get("message", {})
        content = msg.get("content")
        usage = body.get("usage", {})
        rtoks = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        ctoks = usage.get("completion_tokens")
        finish = body.get("choices", [{}])[0].get("finish_reason")
        print(f"[{tag}] HTTP {r.status_code} lat={dt:.1f}s finish={finish} ctok={ctoks} rtok={rtoks} content={str(content)[:80]!r}", flush=True)
    except Exception as e:
        print(f"[{tag}] EXC {type(e).__name__} after {time.perf_counter()-t0:.1f}s", flush=True)


async def main():
    await asyncio.gather(
        one("low/4096", "low", 4096),
        one("high/4096", "high", 4096),
        one("high/8192", "high", 8192),
        one("max/8192", "max", 8192),
    )


asyncio.run(main())
