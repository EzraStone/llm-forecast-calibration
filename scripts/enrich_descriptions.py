"""One-off: enrich questions.jsonl with Manifold market descriptions.

Pulls /v0/market/{id} for each question, uses textDescription (plain text),
truncates to a sane prompt budget, and screens for outcome-leak text.
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")
import httpx

MM_BASE = "https://api.manifold.markets/v0"
LEAK_PAT = "resolved as YES"  # crude; real screen is human reading at gate 2


async def main():
    qs = [json.loads(l) for l in open("data/questions.jsonl")]
    sem = asyncio.Semaphore(8)

    async with httpx.AsyncClient(timeout=60) as client:
        async def enrich(q):
            mid = q["qid"].replace("manifold-", "")
            async with sem:
                try:
                    r = await client.get(f"{MM_BASE}/market/{mid}")
                    r.raise_for_status()
                    m = r.json()
                except Exception as e:
                    print(f"  FAIL {q['qid']}: {e}", flush=True)
                    return q
            desc = (m.get("textDescription") or "").strip()
            if not desc:
                # some markets only carry rich-text description JSON
                rich = m.get("description")
                if isinstance(rich, dict):
                    parts = []
                    def walk(node):
                        if isinstance(node, dict):
                            if node.get("type") == "text" and node.get("text"):
                                parts.append(node["text"])
                            for c in node.get("content", []) or []:
                                walk(c)
                    walk(rich)
                    desc = " ".join(parts).strip()
            if LEAK_PAT in desc.lower():
                print(f"  LEAK-SCREEN HIT {q['qid']}: {q['title'][:60]!r}", flush=True)
                desc = ""
            q["description"] = desc[:3000]
            return q

        out = await asyncio.gather(*[enrich(q) for q in qs])

    with open("data/questions.jsonl", "w", encoding="utf-8") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    n_desc = sum(1 for q in out if q["description"])
    print(f"descriptions: {n_desc}/{len(out)} non-empty")


asyncio.run(main())
