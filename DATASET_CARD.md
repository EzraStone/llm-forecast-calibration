---
license: mit
task_categories:
- question-answering
language:
- en
tags:
- llm-evaluation
- calibration
- forecasting
- brier-score
- uncertainty-quantification
- reproducible-research
size_categories:
- 1K<n<10K
---

# LLM Forecast Calibration Study — GLM-5.3 on resolved Manifold Markets questions

Raw generation data for the study "Does sampling K times beat thinking harder?
A controlled study of LLM forecast calibration on resolved binary questions."

Source repo: https://github.com/EzraStone/llm-forecast-calibration

## Contents

- `questions.jsonl` — 212 resolved binary questions from Manifold Markets
  (106 YES / 106 NO; 110 resolved before / 102 after the assumed GLM-5.3
  training cutoff of 2026-08-15). Fields: `qid` (manifold-{market id}),
  `source`, `title`, `description` (market resolution criteria), 
  `resolution_criteria`, `open_date`, `close_date`, `resolve_date`, `outcome`
  (1=YES, 0=NO), `baseline_crowd_prob` (last trade probability before
  resolution — see contamination caveat), `stratum` (pre_cutoff/post_cutoff),
  `n_forecasters`, `volume`, `url`.
- `raw/` — 3,831 successful API responses (verbatim provider JSON), plus
  `dead_letter.jsonl` for permanently failed calls. Every record carries:
  `qid`, `condition`, `sample_idx`, `model` (z-ai/glm-5.3-free),
  `reasoning_effort` (low/high/max), `temperature`, `prompt_version` hash,
  `requested_at` (UTC), `latency_s`, `attempt`, `usage` (prompt/completion/
  reasoning tokens), `raw_response`, `error`.
- `parsed/parsed.jsonl` — one row per call with the extracted probability:
  `qid`, `condition`, `sample_idx`, `probability`, `parse_status`
  (ok / synonym_key / dead_letter), `stratum`, `outcome`.

## Generation parameters (five conditions)

| id | effort | K samples | temperature | prompt |
|----|--------|-----------|-------------|--------|
| A  | low    | 1  | 0.0 | standard (std-v1-b0e8b9) |
| B  | high   | 1  | 0.0 | standard |
| C  | max    | 1  | 0.0 | standard |
| D  | high   | 10 | 1.0 | standard |
| E  | high   | 5  | 1.0 | base-rate elicitation (br-v2-6e9d2f) |

Prompts gave title, description, resolution criteria, and the fact that the
question had resolved — never the outcome. Max output tokens: 8,192 (low) /
12,288 (high, max). Provider: TokenRouter free tier (8 req/min incl. failures).

## Contamination caveat (read before using)

Questions resolving before 2026-08-15 (the assumed — not disclosed — GLM-5.3
training cutoff) may have their outcomes in training data. The study found every
condition substantially worse on post-cutoff questions (e.g. Brier 0.18 pre vs
0.27 post for condition A), consistent with outcome memorization. **Use the
post_cutoff stratum for honest evaluation of forecasting skill.** Additionally,
the crowd baseline (`baseline_crowd_prob`) is the last trade before resolution
and can embed near-resolving information — treat it as an upper bound on
ex-ante crowd skill, not a fair competitor.

## Headline result

Median-of-10 sampling did not beat a single high-effort forecast
(ΔBrier +0.001, 95% CI [−0.012, +0.014]); effort low→high helped
(−0.018 [−0.034, −0.003]); a forced base-rate prompt hurt
(+0.011 [+0.000, +0.022]). Full analysis in the source repo (`make all`
regenerates every metric and figure offline).

## Licenses

Code and dataset card: MIT. Data (`questions.jsonl`, `raw/`, `parsed/`):
CC BY 4.0. Question text and market data originate from Manifold Markets and
are republished per their API terms for non-commercial academic research.
