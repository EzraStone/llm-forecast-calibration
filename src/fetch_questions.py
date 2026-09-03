"""Phase 1: fetch resolved binary questions from Manifold and build the question set.

Source: Manifold Markets public API (https://api.manifold.markets), no auth.
Supply probe (2026-09-02): ~1000 binary resolved markets resolving Jul-Sept 2026
reachable within the offset-999 ceiling of search-markets with sort=resolve-date.

Crowd baseline: the search-markets `probability` field is frozen at ~0.99/0.01
post-resolution, so we reconstruct the market probability at close from the
last pre-resolution bet's `probAfter` via /v0/bets.

Filtering (spec section 4):
- binary, resolved, resolution in {YES, NO} (drop MKT/CANCEL/annulled)
- drop questions whose text leaks the outcome (manual review + heuristics)
- balance resolved-YES base rate toward 0.3-0.7
- stratify by resolution date vs ASSUMED_CUTOFF; target >=100 post-cutoff
- quality floor: minimum forecasters and volume to keep crowd baseline meaningful
"""
import argparse
import asyncio
import datetime as dt
import json
import random
import re
import sys

import httpx

sys.path.insert(0, ".")
from src.config import ASSUMED_CUTOFF
from src.schema import Question

MM_BASE = "https://api.manifold.markets/v0"

# Quality floor: markets need enough participants for a meaningful crowd baseline.
MIN_BETTORS = 5
MIN_VOLUME = 50.0

# Junk patterns: personal markets, trivial/self-referential, ambiguous resolution.
JUNK_PATTERNS = [
    r"\bmy\b", r"\bmyself\b", r"\bI will\b", r"\bme\b", r"\bwill I\b",
    r"\bI\b",  # broad pass first, refined below
]
# Personal/self-referential first-person patterns (case-sensitive to reduce false hits)
PERSONAL_RE = re.compile(
    r"\b(I|I'll|I'Ve|I'd|I'm|me|my|mine|myself)\b"
)
# Resolution-discretion indicators
DISCRETION_RE = re.compile(
    r"(at (my|the creator'?s?|his|her) discretion|as I see fit|I (will|'ll) decide|"
    r"how I feel|whenever I (want|decide|feel)|up to me|I determine|"
    r"resolves (to|as) .* (judgment|discretion|opinion)|by my (judgment|choice)|"
    r"unless I (say|decide|choose)|I reserve)",
    re.IGNORECASE,
)
# Leaks: outcome stated in text
LEAK_RE = re.compile(
    r"(resolved (as|to) (YES|NO)|it (was|has been) resolved|the (answer|outcome) (was|is) (YES|NO)|"
    r"\b(resolved|outcome): ?(YES|NO)\b)",
    re.IGNORECASE,
)


def ms_to_date(ms):
    if ms is None:
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).date()


def is_trivial(title):
    t = title
    # near-certain or near-impossible physics/commonsense outcomes are uninformative
    tl = t.lower()
    trivial = [
        "will the sun rise", "will water be wet", "will 2+2", "will gravity",
        "will a coin flip", "will i flip", "will this market",
    ]
    return any(x in tl for x in trivial)


def is_junk(title, description):
    text = f"{title} {description}"
    if PERSONAL_RE.search(title):
        return True
    if DISCRETION_RE.search(text):
        return True
    return False


def has_leak(title, description):
    return bool(LEAK_RE.search(f"{title} {description}"))


async def fetch_search_page(client, offset, limit=1000):
    r = await client.get(
        f"{MM_BASE}/search-markets",
        params={"filter": "resolved", "contractType": "BINARY", "sort": "resolve-date",
                "limit": limit, "offset": offset},
    )
    r.raise_for_status()
    return r.json()


async def fetch_last_prob_before(client, market_id, resolution_ms):
    """Market probability at close: probAfter of the last bet placed before resolution."""
    r = await client.get(
        f"{MM_BASE}/bets",
        params={"contractId": market_id, "limit": 1000},
    )
    r.raise_for_status()
    bets = r.json()
    pre = [b for b in bets if (b.get("createdTime") or 0) < resolution_ms and not b.get("isCancelled")]
    if not pre:
        return None
    last = max(pre, key=lambda b: b["createdTime"])
    # prefer probAfter of a filled, non-limit bet; skip redemptions
    if last.get("isRedemption") or last.get("probAfter") is None:
        candidates = [b for b in pre if not b.get("isRedemption") and b.get("probAfter") is not None]
        if not candidates:
            return None
        last = max(candidates, key=lambda b: b["createdTime"])
    return float(last["probAfter"])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/questions.jsonl")
    ap.add_argument("--target", type=int, default=250)
    ap.add_argument("--target-yes", type=int, default=125,
                    help="target count of YES-resolved questions")
    ap.add_argument("--min-post-cutoff", type=int, default=100)
    ap.add_argument("--pages", type=int, default=2, help="search-markets pages to fetch (1000/page)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    cutoff = dt.date.fromisoformat(ASSUMED_CUTOFF)

    async with httpx.AsyncClient(timeout=60) as client:
        markets = []
        for page in range(args.pages):
            batch = await fetch_search_page(client, offset=page * 1000)
            print(f"search page {page}: {len(batch)} markets", flush=True)
            markets.extend(batch)
            if len(batch) < 1000:
                break

        print(f"total markets fetched: {len(markets)}")

        # ---- static filters ----
        kept, drop_stats = [], {}
        def drop(reason):
            drop_stats[reason] = drop_stats.get(reason, 0) + 1

        for m in markets:
            if m.get("outcomeType") != "BINARY":
                drop("non_binary"); continue
            if not m.get("isResolved"):
                drop("unresolved"); continue
            if m.get("resolution") not in ("YES", "NO"):
                drop("resolution_not_yes_no"); continue
            title = (m.get("question") or "").strip()
            if not title:
                drop("no_title"); continue
            if is_trivial(title):
                drop("trivial"); continue
            if is_junk(title, ""):
                drop("junk_or_personal"); continue
            if has_leak(title, ""):
                drop("leak_suspect"); continue
            n_bettors = m.get("uniqueBettorCount") or 0
            if n_bettors < MIN_BETTORS:
                drop("too_few_bettors"); continue
            if (m.get("volume") or 0) < MIN_VOLUME:
                drop("low_volume"); continue
            rt = m.get("resolutionTime")
            if not rt:
                drop("no_resolution_time"); continue
            rdate = ms_to_date(rt)
            if rdate is None:
                drop("bad_date"); continue
            kept.append((m, rdate))

        print(f"after static filters: {len(kept)}")
        print("drop stats:", json.dumps(drop_stats, sort_keys=True))

        # ---- strata ----
        post = [x for x in kept if x[1] > cutoff]
        pre = [x for x in kept if x[1] <= cutoff]
        print(f"pre_cutoff available: {len(pre)}   post_cutoff available: {len(post)}")

        # Aim: >= min_post_cutoff post; fill the rest with pre if needed.
        post_pick = post[:]
        pre_pick = pre[:]
        random.shuffle(post_pick)
        random.shuffle(pre_pick)

        need = args.target
        if len(post_pick) >= args.min_post_cutoff:
            take_post = min(len(post_pick), need - min(len(pre_pick), args.min_post_cutoff // 2))
        else:
            take_post = len(post_pick)
        # simpler: take up to target from post first, then top up from pre
        take_post = min(len(post_pick), need)
        take_pre = min(len(pre_pick), need - take_post)
        print(f"plan: {take_post} post-cutoff + {take_pre} pre-cutoff")

        chosen = post_pick[:take_post] + pre_pick[:take_pre]

        # ---- outcome balancing ----
        # Balance overall YES base rate toward 0.3-0.7 by trimming from the over-represented side.
        yes_items = [x for x in chosen if x[0]["resolution"] == "YES"]
        no_items = [x for x in chosen if x[0]["resolution"] == "NO"]
        print(f"chosen before balance: {len(chosen)} (YES={len(yes_items)}, NO={len(no_items)})")
        # Keep as close to 50/50 as supply allows, and respect strata proportions
        from collections import Counter
        strat_yes = Counter(x[1] > cutoff for x in yes_items)
        strat_no = Counter(x[1] > cutoff for x in no_items)
        print(f"YES by stratum: post={strat_yes[True]} pre={strat_yes[False]}  NO by stratum: post={strat_no[True]} pre={strat_no[False]}")

        # ---- baseline reconstruction (paced: Manifold 500 req/min, we use ~2/s) ----
        print("reconstructing crowd baselines from bets ...")
        records = []
        sem = asyncio.Semaphore(4)
        t0 = dt.datetime.now()

        async def build(m, rdate):
            async with sem:
                try:
                    prob = await fetch_last_prob_before(client, m["id"], m["resolutionTime"])
                except Exception as e:
                    print(f"  bets fetch failed {m['id']}: {e}", flush=True)
                    prob = None
            if prob is None:
                return None
            return Question(
                qid=f"manifold-{m['id']}",
                source="manifold",
                title=m["question"],
                description="",
                resolution_criteria=(
                    "Binary market on Manifold; resolves YES/NO by the stated question. "
                    "Resolution per Manifold market mechanics."
                ),
                open_date=ms_to_date(m.get("createdTime")),
                close_date=ms_to_date(m.get("closeTime")),
                resolve_date=rdate,
                outcome=1 if m["resolution"] == "YES" else 0,
                baseline_crowd_prob=round(prob, 4),
                stratum="post_cutoff" if rdate > cutoff else "pre_cutoff",
                n_forecasters=m.get("uniqueBettorCount") or 0,
                volume=float(m.get("volume") or 0),
                url=m.get("url") or "",
            )

        tasks = [build(m, rd) for m, rd in chosen]
        results = await asyncio.gather(*tasks)
        records = [r for r in results if r is not None]
        print(f"baselines reconstructed for {len(records)}/{len(chosen)} in {(dt.datetime.now()-t0).total_seconds():.0f}s")

    # ---- balance AFTER baseline reconstruction (drop only fully-formed records) ----
    yes_rec = [r for r in records if r.outcome == 1]
    no_rec = [r for r in records if r.outcome == 0]
    random.shuffle(yes_rec)
    random.shuffle(no_rec)
    target_yes = min(args.target_yes, len(yes_rec), len(no_rec))  # at most the smaller side
    target_yes = max(target_yes, 1)
    target_no = min(len(no_rec), target_yes)  # near 50/50
    yes_rec = yes_rec[:target_yes]
    no_rec = no_rec[:target_no]
    final = yes_rec + no_rec
    random.shuffle(final)
    print(f"final: {len(final)} questions (YES={len(yes_rec)} NO={len(no_rec)})")

    # sort by resolve date for stable ordering; question-major run order comes later
    final.sort(key=lambda q: (q.stratum, q.resolve_date))

    with open(args.out, "w", encoding="utf-8") as f:
        for q in final:
            f.write(q.model_dump_json() + "\n")

    # ---- summary ----
    n = len(final)
    base_yes = sum(q.outcome for q in final) / n
    post_n = sum(1 for q in final if q.stratum == "post_cutoff")
    dates = sorted(q.resolve_date for q in final)
    print("=== QUESTION SET SUMMARY ===")
    print(f"rows: {n}")
    print(f"resolved-YES base rate: {base_yes:.3f}")
    print(f"pre_cutoff: {n - post_n}   post_cutoff: {post_n}")
    print(f"resolve dates: {dates[0]} .. {dates[-1]}")
    crowd_probs = [q.baseline_crowd_prob for q in final]
    print(f"crowd baseline: min={min(crowd_probs):.3f} med={sorted(crowd_probs)[len(crowd_probs)//2]:.3f} max={max(crowd_probs):.3f}")
    print(f"n_forecasters: min={min(q.n_forecasters for q in final)} med={sorted(q.n_forecasters for q in final)[len(final)//2]}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
