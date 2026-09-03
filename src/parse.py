"""Phase 3: offline parser. Reads data/raw/*.jsonl, emits data/parsed/parsed.jsonl.

One row per call: qid, condition, sample_idx, probability, parse_status, stratum, outcome.
Parse failures are counted and reported, never silently dropped. Dead-lettered calls
are marked status='dead_letter'. Probabilities are NOT clipped here (clipping is
log-loss-only, applied in analyze).
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, ".")
from src.schema import ParsedRow


def _strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        nl = t.find("\n")
        if nl > 0 and t[:nl].strip().lower() in ("json", ""):
            t = t[nl + 1:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def parse_content(content):
    """Extract a probability in [0,1] from model content. Raises ValueError on failure.

    Handles: plain JSON, code-fenced JSON, JSON embedded in prose,
    percentage-valued probability, bare NN% in prose.
    """
    if content is None:
        raise ValueError("no content")
    if not isinstance(content, str):
        content = str(content)
    text = _strip_fences(content)

    # 1) whole-text JSON
    try:
        obj = json.loads(text)
        return _prob_from_obj(obj)
    except (json.JSONDecodeError, ValueError):
        pass
    # 2) any {...} span embedded in prose
    for m in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
        try:
            obj = json.loads(m.group(0))
            return _prob_from_obj(obj)
        except (json.JSONDecodeError, ValueError):
            continue
    # 3) percentage forms
    pm = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text)
    if pm:
        val = float(pm.group(1)) / 100.0
        if 0.0 <= val <= 1.0:
            return val
    raise ValueError(f"unparseable content: {text[:120]!r}")


def _prob_from_obj(obj):
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    p = obj.get("probability")
    if p is None:
        raise ValueError("no probability key")
    if isinstance(p, str):
        s = p.strip()
        m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*%?", s)
        if not m:
            raise ValueError(f"probability not numeric: {p!r}")
        p = float(m.group(1))
        if s.rstrip().endswith("%") or p > 1.0:
            p = p / 100.0
    p = float(p)
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"probability out of range: {p}")
    return p


def main(raw_dir="data/raw", out_path="data/parsed/parsed.jsonl",
         questions_path="data/questions.jsonl"):
    qs = {q["qid"]: q for q in (json.loads(l) for l in open(questions_path))}
    rows = []
    statuses = Counter()

    def add(qid, cond, sidx, prob, status):
        q = qs.get(qid)
        rows.append(ParsedRow(
            qid=qid, condition=cond, sample_idx=sidx,
            probability=None if prob is None else round(float(prob), 6),
            parse_status=status,
            stratum=q["stratum"] if q else "dropped",
            outcome=q["outcome"] if q else -1,
        ))
        statuses[(cond, status)] += 1

    for cond in "ABCDE":
        path = os.path.join(raw_dir, f"{cond}.jsonl")
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn line; runner redoes these
            if rec.get("error"):
                continue  # dead letters handled below
            if rec["qid"] not in qs:
                # sunk calls on questions dropped at Gate-2 dedupe; skip entirely
                continue
            try:
                content = rec["raw_response"]["choices"][0]["message"]["content"]
                prob = parse_content(content)
                add(rec["qid"], cond, rec["sample_idx"], prob, "ok")
            except Exception:
                add(rec["qid"], cond, rec["sample_idx"], None, "parse_fail")

    # dead letters get their own status rows (no probability); skip dropped qids
    dl = os.path.join(raw_dir, "dead_letter.jsonl")
    if os.path.exists(dl):
        for line in open(dl, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec["qid"] not in qs:
                continue
            add(rec["qid"], rec["condition"], rec["sample_idx"], None, "dead_letter")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")

    # report
    print("=== PARSE REPORT (per condition) ===")
    total = Counter()
    for (cond, status), n in sorted(statuses.items()):
        total[cond] += n
        print(f"  {cond} {status}: {n}")
    print("=== parse failure rate per condition ===")
    for cond in "ABCDE":
        t = total.get(cond, 0)
        if t == 0:
            continue
        fails = statuses.get((cond, "parse_fail"), 0) + statuses.get((cond, "dead_letter"), 0)
        print(f"  {cond}: {fails}/{t} = {fails / t:.1%}  (halt threshold: 5%)")
    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
