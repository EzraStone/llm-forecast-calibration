# LIMITATIONS

Written honestly, before results are known. This file grows as constraints are discovered.

## Training-data contamination (assumed cutoff)

z.ai publishes no training-data cutoff for GLM-5.3 or its GLM-5.2 base (checked 2026-09-02
against docs.z.ai and the GLM-5.3/GLM-5.2 model pages). GLM-5.3 was released 2026-08-14 and
its post-training ran until roughly that date, so we anchor the assumed cutoff at
**2026-08-15**, the day after release: questions resolving after that date are the
"post_cutoff" stratum (plausibly unseen), earlier resolutions are "pre_cutoff"
(plausibly in training). This is an assumption, not a documented fact. Two additional
caveats: (1) an earlier draft anchored the cutoff at 2026-06-01, but the Manifold
resolve-date pagination floor (2026-07-01) makes a pre-July stratum unfetchable, so the
usable pre-cutoff window is Jul 1–Aug 14, roughly six weeks; (2) even post-cutoff
questions were *open* and being discussed before the cutoff, so question text and
context may be in training even when the resolution is not. The pre/post split is a
proxy, reported whether or not it is flattering.

## Provider constraints (TokenRouter free tier, measured 2026-09-02)

- **Hard rate limit: 8 requests per 1-minute window, including failed attempts.**
  This reshapes the study design: the spec's nominal 18,900 calls (300 questions, K=30)
  would take ~45 hours at this limit and cannot finish before the 2026-09-04 deadline.
  K is adjusted downward (see runner config); the spec explicitly anticipated this
  ("adjust K downward if the run will not finish with 6+ hours of slack").
- **503 `cache_only_cold`**: free-tier admission control rejects cold/overloaded requests
  sporadically. These are retried and count against the rate limit like any attempt.
- **Structured output is not strictly enforced**: the provider accepts a JSON schema in
  `response_format` but the model can omit required fields (observed: a response containing
  only `{"probability": 0.5}` where the schema required four fields) and sometimes wraps
  output in markdown code fences. The parser must strip fences and tolerate missing
  non-probability fields; missing/out-of-range probability is a parse failure handled by
  the dead-letter path.
- **Transient 200-with-empty/non-JSON-body responses** occur under rate pressure (observed
  5 times in 5 paced high-effort calls, then 0 times in 4 calls minutes later). The client
  treats an unparseable 200 body as retryable, subject to the normal attempt cap.
- **Empty content at small max_tokens**: with `reasoning_effort=high` and `max_tokens=4096`,
  roughly half of preflight calls returned empty content (reasoning consumed the budget).
  The runner uses a larger `max_tokens` for high/max-effort conditions; truncation
  (`finish_reason=length`) is recorded per call.
- Free-tier latency is highly variable (2-84 s observed for a single low-effort call).
  Latency is recorded per call; throughput is dominated by the rate limit, not latency.

## Question-set selection

Metaculus/Manifold questions are not a random sample of forecastable propositions; they
skew toward topics the platform's users find interesting. The resolved-YES base rate is
controlled by design (0.3-0.7 target) but topic mix is uncontrolled.

## Scope

Single model (GLM-5.3 via TokenRouter), single provider, single time window. No claim
generalizes across models. Two prompts is not a prompt-robustness study.

## Crowd baseline advantage

Metaculus forecasters had information the model was not given (live news, discussion), and
the model may have seen question text or resolution discussion in training. The comparison
is suggestive, not clean.

## To be added as phases complete

- Parse failure rates by condition (Phase 3).
- Underpowered comparisons, named with their CIs (Phase 4).
- Any condition/top-up that could not complete within the API window (Phase 2).
