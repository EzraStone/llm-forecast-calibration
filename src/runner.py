"""Phase 2 runner: the overnight generation job.

Design decisions (locked at Gate 0, 2026-09-02):
- 220 questions x 18 calls: A(low,1) B(high,1) C(max,1) D(high,K=10,temp1) E(high,K=5,baserate)
- question-major ordering: all 18 calls for q1 before q2, so a truncated run still yields
  complete questions
- token bucket at 7 calls/min (free-tier hard limit is 8 incl. failed attempts)
- concurrency 3 (latency ~20-90s/call dominates; the bucket is the real constraint)
- RQ3 comparison: E (K=5, baserate prompt) vs first-5-subsample of D (same effort, temp)

Non-negotiables implemented (spec section 5):
- append-before-parse: raw response written+flushed immediately
- resumable: completed (qid, condition, sample_idx) keys are skipped on restart
- hard timeout 180s per request, retries with backoff+jitter on 429/5xx/timeout/bad-200
- schema violation retried once, then dead-letter
- dead-letter file for permanent failures; failures never crash the run
- watchdog: error rate over rolling 200-call window > 25% => loud halt
- progress line every 60s
- full metadata per record (model, effort, temp, prompt hash, ts, latency, usage, attempt)
"""
import argparse
import asyncio
import json
import os
import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, ".")
from src.client import AttemptExhausted, completion
from src.config import BASE_URL, MAX_ATTEMPTS, MODEL_SLUG, REQUEST_TIMEOUT_S
from src.prompts import FORECAST_SCHEMA, build_messages

CONDITIONS = {
    "A": {"effort": "low", "k": 1, "temperature": 0.0, "prompt": "std"},
    "B": {"effort": "high", "k": 1, "temperature": 0.0, "prompt": "std"},
    "C": {"effort": "max", "k": 1, "temperature": 0.0, "prompt": "std"},
    "D": {"effort": "high", "k": 10, "temperature": 1.0, "prompt": "std"},
    "E": {"effort": "high", "k": 5, "temperature": 1.0, "prompt": "baserate"},
}

RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "forecast", "schema": FORECAST_SCHEMA}}

# Effort-dependent output budget, co-designed with REQUEST_TIMEOUT_S=300s.
# Measured free-tier decode speed ~40-60 tok/s (non-streaming): 12288 tokens
# takes up to ~5min; larger caps cannot finish inside the timeout and turn into
# ReadTimeout dead letters. 8192 low / 12288 high-max is the coherent envelope.
# Truncation risk at these caps is real but rare (pilot: 8139 reasoning tokens
# was the worst low-effort case; high effort is typically 2-4K).
MAX_TOKENS = {"low": 8192, "high": 12288, "max": 12288}


class TokenBucket:
    """7 calls/min steady, small burst headroom for clock jitter."""

    def __init__(self, rate_per_min=7.0, capacity=7):
        self.rate = rate_per_min / 60.0
        self.capacity = capacity
        self.tokens = float(capacity)
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(max(wait, 0.5))


class Watchdog:
    def __init__(self, window=200, threshold=0.25):
        self.window = window
        self.threshold = threshold
        self.recent = deque(maxlen=window)  # True=error
        self.total_errors = 0
        self.total_calls = 0

    def record(self, is_error):
        self.recent.append(is_error)
        self.total_calls += 1
        if is_error:
            self.total_errors += 1
        if len(self.recent) >= self.window:
            rate = sum(self.recent) / len(self.recent)
            if rate > self.threshold:
                raise RuntimeError(
                    f"WATCHDOG HALT: error rate {rate:.1%} over last {len(self.recent)} calls"
                )


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_questions(path):
    qs = [json.loads(l) for l in open(path, encoding="utf-8")]
    return qs


def completed_keys(raw_dir):
    """Scan existing raw files for (qid, condition, sample_idx) that are already done."""
    done = set()
    if not os.path.isdir(raw_dir):
        return done
    for fn in sorted(os.listdir(raw_dir)):
        if not fn.endswith(".jsonl"):
            continue
        with open(os.path.join(raw_dir, fn), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # torn tail line from a crash mid-write; will be redone
                if rec.get("error"):
                    continue  # errored calls are retried on restart
                done.add((rec["qid"], rec["condition"], rec["sample_idx"]))
    return done


class Runner:
    def __raw_path(self, condition):
        return os.path.join(self.raw_dir, f"{condition}.jsonl")

    def __dead_path(self):
        return os.path.join(self.raw_dir, "dead_letter.jsonl")

    def __init__(self, questions, raw_dir, concurrency=3, bucket_rate=7.0, stop_after=None,
                 stop_file="STOP_RUN"):
        self.questions = questions
        self.raw_dir = raw_dir
        self.concurrency = concurrency
        self.bucket = TokenBucket(bucket_rate)
        self.watchdog = Watchdog()
        self.stop_after = stop_after
        self.stop_file = stop_file
        self.done = completed_keys(raw_dir)
        self.files = {c: open(self.__raw_path(c), "a", encoding="utf-8") for c in CONDITIONS}
        self.dead = open(self.__dead_path(), "a", encoding="utf-8")
        self.started = time.monotonic()
        self.n_ok = 0
        self.n_err = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.reasoning_tokens = 0
        self._halt = None
        self._last_report = 0.0
        # plan: question-major, condition order fixed for reproducibility
        self.plan = []
        for q in questions:
            for cond in ("A", "B", "C", "D", "E"):
                spec = CONDITIONS[cond]
                for s in range(spec["k"]):
                    key = (q["qid"], cond, s)
                    if key not in self.done:
                        self.plan.append((q, cond, s))

    def progress_line(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_report < 60.0:
            return
        self._last_report = now
        total = len(self.plan) + len(self.done)
        completed = len(self.done) + self.n_ok + self.n_err
        # note: n_ok counts new successes this session; done counts prior sessions
        calls_done = self.n_ok + self.n_err
        elapsed_min = max((now - self.started) / 60.0, 1e-9)
        cpm = calls_done / elapsed_min
        remaining = len(self.plan) - calls_done
        eta_h = remaining / max(cpm, 1e-9) / 60.0
        err_rate = (self.n_err / calls_done) if calls_done else 0.0
        print(
            f"[{now_iso()}] {completed}/{total} complete | this-session {calls_done} calls "
            f"({self.n_ok} ok, {self.n_err} err) | {cpm:.1f} calls/min | ETA {eta_h:.1f}h | "
            f"err {err_rate:.1%} | tokens in={self.tokens_in} out={self.tokens_out} "
            f"reasoning={self.reasoning_tokens} | plan remaining {remaining}",
            flush=True,
        )

    async def write_record(self, qid, cond, sample_idx, spec, messages, prompt_ver, attempt,
                           latency, body, error):
        usage = {}
        if body and isinstance(body, dict):
            u = body.get("usage") or {}
            usage = {
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            }
            self.tokens_in += usage["prompt_tokens"] or 0
            self.tokens_out += usage["completion_tokens"] or 0
            self.reasoning_tokens += usage["reasoning_tokens"] or 0
        rec = {
            "qid": qid,
            "condition": cond,
            "sample_idx": sample_idx,
            "model": MODEL_SLUG,
            "reasoning_effort": spec["effort"],
            "temperature": spec["temperature"],
            "prompt_version": prompt_ver,
            "requested_at": now_iso(),
            "latency_s": round(latency, 2),
            "attempt": attempt,
            "usage": usage,
            "raw_response": body,
            "error": error,
        }
        line = json.dumps(rec, ensure_ascii=False)
        f = self.files[cond] if error is None else self.dead
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())

    async def one_call(self, q, cond, sample_idx):
        spec = CONDITIONS[cond]
        messages, prompt_ver = build_messages(q, spec["prompt"])
        # schema-violation retry is handled inside: completion() retries transport-level
        # failures; a 200 that violates the schema is retried once here.
        for schema_retry in range(2):
            try:
                body, latency, attempt = await completion(
                    messages,
                    temperature=spec["temperature"],
                    reasoning_effort=spec["effort"],
                    response_format=RESPONSE_FORMAT,
                    max_tokens=MAX_TOKENS[spec["effort"]],
                    bucket=self.bucket,
                )
            except AttemptExhausted as e:
                await self.write_record(q["qid"], cond, sample_idx, spec, messages, prompt_ver,
                                        MAX_ATTEMPTS, 0.0, None, f"attempt_exhausted: {e}")
                self.watchdog.record(True)
                self.n_err += 1
                self.progress_line()
                return
            # validate schema cheaply: probability present and in range
            content = None
            try:
                content = body["choices"][0]["message"]["content"]
                p = json.loads(content)["probability"]
                ok = isinstance(p, (int, float)) and 0.0 <= p <= 1.0
            except Exception:
                ok = False
            truncated = False
            try:
                truncated = body["choices"][0].get("finish_reason") == "length"
            except Exception:
                pass
            if ok:
                await self.write_record(q["qid"], cond, sample_idx, spec, messages, prompt_ver,
                                        attempt, latency, body, None)
                self.watchdog.record(False)
                self.n_ok += 1
                self.progress_line()
                return
            # schema violation: retry once, then dead-letter with the raw body.
            # Skip the retry when the generation hit the token cap: a temp-0 re-run
            # truncates identically and just burns ~5 more minutes.
            if schema_retry == 0 and not truncated:
                continue
            await self.write_record(q["qid"], cond, sample_idx, spec, messages, prompt_ver,
                                    attempt, latency, body, "schema_violation_after_retry")
            self.watchdog.record(True)
            self.n_err += 1
            self.progress_line()
            return

    async def stop_requested(self):
        return os.path.exists(self.stop_file)

    async def run(self):
        print(f"[{now_iso()}] runner starting: {len(self.plan)} calls to make, "
              f"{len(self.done)} already complete", flush=True)
        print(f"conditions: {json.dumps({c: CONDITIONS[c] for c in CONDITIONS})}", flush=True)
        # Bounded worker pool over the plan queue: workers pull in plan order,
        # so question-major ordering is preserved even with concurrency > 1.
        queue = asyncio.Queue()
        for item in self.plan:
            queue.put_nowait(item)
        total = len(self.plan)
        made = 0

        async def worker(wid):
            nonlocal made
            while True:
                try:
                    q, cond, s = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if await self.stop_requested():
                    queue.put_nowait((q, cond, s))  # leave it for the resume pass
                    return
                if self.stop_after and made >= self.stop_after:
                    queue.put_nowait((q, cond, s))
                    while True:
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                try:
                    await self.one_call(q, cond, s)
                except RuntimeError as halt:
                    self._halt = halt
                    # drain the queue so all workers exit
                    while True:
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                finally:
                    made += 1
                    self.progress_line()

        workers = [asyncio.create_task(worker(i)) for i in range(self.concurrency)]
        try:
            await asyncio.gather(*workers)
            if self._halt:
                raise self._halt
        finally:
            self.progress_line(force=True)
            for f in self.files.values():
                f.close()
            self.dead.close()
            print(f"[{now_iso()}] runner exiting: ok={self.n_ok} err={self.n_err}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="data/questions.jsonl")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--conditions", default="A,B,C,D,E",
                    help="comma list; subset runs are resumable")
    ap.add_argument("--limit", type=int, default=None, help="only first N questions")
    ap.add_argument("--concurrency", type=int, default=14,
                    help="workers; sized so the 7/min bucket binds (avg latency ~100s)")
    ap.add_argument("--bucket-rate", type=float, default=7.0)
    ap.add_argument("--stop-after", type=int, default=None,
                    help="stop after N new calls (for the 20-question pilot check)")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    if args.limit:
        questions = questions[:args.limit]

    global CONDITIONS
    CONDITIONS = {c: CONDITIONS[c] for c in args.conditions.split(",")}

    runner = Runner(questions, args.raw_dir, concurrency=args.concurrency,
                    bucket_rate=args.bucket_rate, stop_after=args.stop_after)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
