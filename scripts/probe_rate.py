"""Paced throughput probe: 10 single-attempt calls at 8.5s spacing, high effort."""
import asyncio
import json
import sys
import time

import httpx

sys.path.insert(0, ".")
from src.config import BASE_URL, TOKENROUTER_API_KEY

HEADERS = {"Authorization": f"Bearer {TOKENROUTER_API_KEY}", "Content-Type": "application/json"}
SCHEMA = {
    "type": "object",
    "properties": {"probability": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
    "required": ["probability"],
}


async def one_call(i):
    payload = {
        "model": "z-ai/glm-5.3-free",
        "messages": [
            {"role": "system", "content": "You are a careful superforecaster."},
            {"role": "user", "content": f"Estimate the probability that global internet traffic grows more than 20% in a typical recent year (variant {i}). Reply as JSON."},
        ],
        "temperature": 1.0,
        "reasoning_effort": "high",
        "max_tokens": 16384,
        "response_format": {"type": "json_schema", "json_schema": {"name": "forecast", "schema": SCHEMA}},
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload)
        dt = time.perf_counter() - t0
        if r.status_code == 200:
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            p = json.loads(content)["probability"]
            rtoks = body.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens")
            return ("OK", dt, p, rtoks)
        return (f"HTTP{r.status_code}", dt, r.text[:80], None)
    except Exception as e:
        return (f"EXC:{type(e).__name__}", time.perf_counter() - t0, str(e)[:80], None)


async def main():
    results = []
    for i in range(5):
        t0 = time.perf_counter()
        results.append(await one_call(i))
        elapsed = time.perf_counter() - t0
        wait = max(0.0, 8.5 - elapsed)
        print(f"call {i}: {results[-1]}  (took {elapsed:.1f}s, waiting {wait:.1f}s)", flush=True)
        if wait:
            await asyncio.sleep(wait)
    ok = [r for r in results if r[0] == "OK"]
    print(f"\nsuccess: {len(ok)}/5")
    if ok:
        lats = sorted(r[1] for r in ok)
        print(f"latency min/med/max: {lats[0]:.1f}/{lats[len(lats)//2]:.1f}/{lats[-1]:.1f}s")
        print("probabilities:", [r[2] for r in ok])


asyncio.run(main())
