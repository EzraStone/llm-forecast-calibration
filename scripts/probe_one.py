"""Diagnose high-effort response shape: one call, print raw HTTP status/headers/body."""
import asyncio
import sys

sys.path.insert(0, ".")
import httpx

from src.config import BASE_URL, TOKENROUTER_API_KEY

HEADERS = {"Authorization": f"Bearer {TOKENROUTER_API_KEY}", "Content-Type": "application/json"}
SCHEMA = {
    "type": "object",
    "properties": {"probability": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
    "required": ["probability"],
}


async def main():
    payload = {
        "model": "z-ai/glm-5.3-free",
        "messages": [
            {"role": "system", "content": "You are a careful superforecaster."},
            {"role": "user", "content": "Estimate the probability that global internet traffic grows more than 20% in a typical recent year. Reply as JSON."},
        ],
        "temperature": 1.0,
        "reasoning_effort": "high",
        "max_tokens": 16384,
        "response_format": {"type": "json_schema", "json_schema": {"name": "forecast", "schema": SCHEMA}},
    }
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload)
    print("STATUS:", r.status_code)
    print("HEADERS:", dict(r.headers))
    print("BODY[:2000]:", r.text[:2000])


asyncio.run(main())
