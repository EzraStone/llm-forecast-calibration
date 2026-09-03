"""Print full reasoning traces for human outcome-leak review (Gate 2)."""
import json
import sys

sys.path.insert(0, ".")

qs = {q["qid"]: q for q in (json.loads(l) for l in open("data/questions.jsonl"))}

picks = []
for cond in ("B", "D", "E"):
    for line in open(f"data/raw/{cond}.jsonl"):
        r = json.loads(line)
        q = qs.get(r["qid"])
        if q is None:
            continue  # dropped in dedupe; skip
        picks.append((cond, r, q))
        break

print(f"picks: {len(picks)}")
for cond, r, q in picks:
    print("=" * 70)
    print(f"CONDITION {cond} | {r['qid']} | effort={r['reasoning_effort']} temp={r['temperature']} prompt={r['prompt_version']}")
    print(f"TITLE: {q['title']}")
    print(f"TRUE OUTCOME: {'YES' if q['outcome'] else 'NO'} (crowd {q['baseline_crowd_prob']})")
    msg = r["raw_response"]["choices"][0]["message"]
    print("--- REASONING (verbatim, first 2200 chars) ---")
    print((msg.get("reasoning_content") or "")[:2200])
    print("--- CONTENT ---")
    print(msg.get("content"))
    print()
