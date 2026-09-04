"""Top-up pass: retry dead-lettered calls whose failure was transient (attempt_exhausted:
429/timeout cascades), while the API window is open. Truncation-driven schema violations
are NOT retried: deterministic failure, same params.

Reads dead_letter.jsonl, deletes the attempt_exhausted entries, and re-queues them by
removing from a completed-keys override... simplest correct mechanism: rewrite the
dead_letter file to keep only non-retryable entries, then invoke the runner normally
(resume logic retries anything not in raw files).
"""
import json
import sys

sys.path.insert(0, ".")

RETRYABLE = "attempt_exhausted"

kept, retried = [], []
for line in open("data/raw/dead_letter.jsonl"):
    rec = json.loads(line)
    if (rec.get("error") or "").startswith(RETRYABLE):
        retried.append(line)
    else:
        kept.append(line)

with open("data/raw/dead_letter.jsonl", "w") as f:
    f.writelines(kept)

# retried entries must ALSO be removed from raw condition files? No: errored calls were
# never written to condition files (only dead_letter). Removing them from dead_letter
# makes the runner see them as incomplete and re-attempt them.
print(f"requeueing {len(retried)} transient failures; keeping {len(kept)} deterministic ones")
with open("logs/dead_letter_requeued.jsonl", "w") as f:
    f.writelines(retried)
