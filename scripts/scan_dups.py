"""Scan question set for near-duplicate events (same underlying question, two markets)."""
import json
import re
import sys

sys.path.insert(0, ".")


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tokens(t):
    stop = {"will", "the", "a", "an", "in", "by", "of", "to", "or", "be", "before",
            "during", "at", "on", "for", "and", "than", "more", "get"}
    return {w for w in norm(t).split() if w not in stop and len(w) > 2}


qs = [json.loads(l) for l in open("data/questions.jsonl")]
n = len(qs)
dups = []
for i in range(n):
    for j in range(i + 1, n):
        ti, tj = tokens(qs[i]["title"]), tokens(qs[j]["title"])
        if not ti or not tj:
            continue
        jac = len(ti & tj) / len(ti | tj)
        if jac >= 0.6:
            dups.append((jac, i, j, qs[i]["title"][:50], qs[j]["title"][:50]))

dups.sort(reverse=True)
print(f"near-duplicate pairs (jaccard>=0.6): {len(dups)}")
for jac, i, j, a, b in dups[:20]:
    print(f"  {jac:.2f} [{i}] {a!r}")
    print(f"        [{j}] {b!r}")
