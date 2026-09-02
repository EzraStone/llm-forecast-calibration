"""Phase 0 pre-flight: connectivity, structured output, sampling variance."""
import asyncio
import json

from src.client import AttemptExhausted, completion
from src.config import MODEL_SLUG

FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "reference_class": {"type": "string"},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "confidence_note": {"type": "string"},
    },
    "required": ["probability", "reference_class", "key_drivers", "confidence_note"],
}


def check1():
    print("=== CHECK 1: connectivity + slug ===")
    body, latency, attempt = asyncio.run(
        completion([{"role": "user", "content": "Reply with the single word: pong"}],
                   reasoning_effort="low")
    )
    print(json.dumps(body, indent=2))
    print(f"[ok] model={body.get('model')} latency={latency:.1f}s attempt={attempt}")
    return body


def check2():
    print("\n=== CHECK 2: structured output ===")
    body, latency, attempt = asyncio.run(
        completion(
            [
                {"role": "system", "content": "You are a careful forecaster. Answer strictly as JSON."},
                {"role": "user", "content": "What is the probability that a fair coin lands heads? Give a number in [0,1]."},
            ],
            reasoning_effort="low",
            response_format={"type": "json_schema", "json_schema": {"name": "forecast", "schema": FORECAST_SCHEMA}},
        )
    )
    content = body["choices"][0]["message"]["content"]
    print(content)
    parsed = json.loads(content)
    p = parsed["probability"]
    assert isinstance(p, float) or isinstance(p, int), f"probability not numeric: {p!r}"
    assert 0.0 <= p <= 1.0, f"probability out of range: {p!r}"
    print(f"[ok] structured output parses; probability={p} (in [0,1]) latency={latency:.1f}s")
    return parsed


async def _ten_samples():
    q = (
        "Question: Will a randomly selected major tech company beat earnings "
        "estimates in its next quarterly report?\n\n"
        "This question is closed and resolved. Forecast strictly from priors and "
        "reasoning. Give your probability that the answer is YES."
    )
    msgs = [
        {"role": "system", "content": "You are a careful superforecaster. Answer strictly as JSON."},
        {"role": "user", "content": q},
    ]
    tasks = [
        completion(
            msgs,
            temperature=1.0,
            reasoning_effort="high",
            response_format={"type": "json_schema", "json_schema": {"name": "forecast", "schema": FORECAST_SCHEMA}},
        )
        for _ in range(10)
    ]
    out = []
    for coro, done in zip(tasks, await asyncio.gather(*tasks, return_exceptions=True)):
        if isinstance(done, Exception):
            out.append(f"ERROR: {done}")
        else:
            body, latency, attempt = done
            try:
                p = json.loads(body["choices"][0]["message"]["content"])["probability"]
            except Exception as e:
                p = f"PARSE_ERROR: {e}"
            out.append(p)
    return out


def check3():
    print("\n=== CHECK 3: sampling variance (temp=1.0, effort=high, 10 calls) ===")
    probs = asyncio.run(_ten_samples())
    for i, p in enumerate(probs):
        print(f"  sample {i}: {p}")
    numeric = [p for p in probs if isinstance(p, (int, float))]
    if not numeric:
        raise SystemExit("FAIL: no numeric probabilities returned")
    if len(set(numeric)) == 1:
        print(f"\n[WARN] all {len(numeric)} probabilities identical: {numeric[0]}")
        print("Temperature appears NOT honored with reasoning enabled.")
        print("Conditions D/E (K=30 aggregation) cannot test sampling aggregation as specified.")
        print("Fallback per spec: prompt-perturbation ensembling; record in LIMITATIONS immediately.")
    else:
        u = (max(numeric) - min(numeric)) if numeric else 0
        print(f"\n[ok] {len(set(numeric))} distinct values across {len(numeric)} samples, range={u:.3f}")
        print("Temperature is honored: sampling aggregation is viable.")


def main():
    print(f"model slug: {MODEL_SLUG}")
    check1()
    check2()
    check3()
    print("\nPRE-FLIGHT COMPLETE")


if __name__ == "__main__":
    main()
