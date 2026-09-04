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


class _SynonymKey(Exception):
    """Raised when probability was recovered from an observed synonym key."""

    def __init__(self, value):
        self.value = value


def parse_content_loose(content):
    """Like parse_content, but accepts observed synonym keys for probability.

    Returns (probability, used_synonym: bool). Used ONLY to re-examine
    dead-lettered schema violations; every recovered row is marked
    parse_status='synonym_key' in parsed.jsonl.
    """
    if content is None:
        raise ValueError("no content")
    text = _strip_fences(content)
    for m in [None] + list(re.finditer(r"\{[^{}]*\}", text, re.DOTALL)):
        candidate = text if m is None else m.group(0)
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return _prob_from_obj(obj, allow_synonyms=False), False
        except ValueError as e:
            if "no probability key" in str(e):
                try:
                    return _prob_from_obj(obj, allow_synonyms=True), True
                except ValueError:
                    continue
            continue
    # percentage fallback
    pm = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text)
    if pm:
        val = float(pm.group(1)) / 100.0
        if 0.0 <= val <= 1.0:
            return val, False
    raise ValueError("unparseable")


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


def _prob_from_obj(obj, allow_synonyms=False):
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    p = obj.get("probability")
    if p is None and allow_synonyms:
        # Observed key-name drift (documented; rate reported in parse output):
        # the model sometimes emits a synonym for the probability field. Only
        # synonyms actually seen in raw data are accepted. Recovered rows are
        # marked parse_status='synonym_key' for auditability.
        for alt in ("prediction", "forecast", "external_forecast", "p", "prob"):
            if alt in obj:
                p = obj[alt]
                break
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

    # dead letters: re-examine content under the loose parser; recovered
    # synonym-key rows carry a probability; the rest stay dead_letter.
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
            try:
                content = rec["raw_response"]["choices"][0]["message"]["content"]
                prob, used_syn = parse_content_loose(content)
                if used_syn:
                    add(rec["qid"], rec["condition"], rec["sample_idx"], prob, "synonym_key")
                else:
                    # parseable content but was dead-lettered (e.g. retried-then-ok elsewhere)
                    add(rec["qid"], rec["condition"], rec["sample_idx"], prob, "ok_deadletter")
            except Exception:
                add(rec["qid"], rec["condition"], rec["sample_idx"], None, "dead_letter")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")

    # report (counts unique expected keys, not attempts)
    print("=== PARSE REPORT (per condition, unique keys) ===")
    K = {"A": 1, "B": 1, "C": 1, "D": 10, "E": 5}
    n_questions = len(qs)
    usable_keys = {}
    for r in rows:
        if r.parse_status in ("ok", "synonym_key", "ok_deadletter"):
            usable_keys[(r.qid, r.condition, r.sample_idx)] = True
    for cond in "ABCDE":
        expected = K[cond] * n_questions
        if expected == 0:
            continue
        got = sum(1 for k in usable_keys if k[1] == cond)
        dead = expected - got
        print(f"  {cond}: {got}/{expected} usable = {got/expected:.1%}"
              f"  (dead: {dead} = {dead/expected:.1%}; halt threshold 5%)")
    from collections import Counter as _C
    st = _C(r.parse_status for r in rows)
    print(f"row statuses: {dict(st)}")
    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
