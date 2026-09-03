"""Reorder question set: post_cutoff questions first (protect the honest stratum
in a partial run), then by resolve date, then qid. Idempotent.

The same-event dedupe (8 manual drops found at Gate 2 review: repeated
'Daily Coinflip' markets, Stripe/OpenRouter pair, Bitcoin typo-variant, Trump
WC-final pair, Hormuz mirror) was applied 2026-09-03; this script only reorders.
"""
import json

qs = [json.loads(l) for l in open("data/questions.jsonl")]
qs.sort(key=lambda q: (q["stratum"], q["resolve_date"], q["qid"]))
with open("data/questions.jsonl", "w", encoding="utf-8") as f:
    for q in qs:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")
print(f"reordered {len(qs)}: first={qs[0]['stratum']}, last={qs[-1]['stratum']}")
