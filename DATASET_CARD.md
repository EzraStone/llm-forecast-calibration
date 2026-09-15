---
license: other
license_name: mixed-rights-research-dataset
license_link: https://huggingface.co/datasets/ezra77/llm-forecast-calibration/blob/main/DATA_LICENSE
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
configs:
- config_name: questions
  default: true
  data_files:
  - split: test
    path: questions.jsonl
- config_name: forecasts
  data_files:
  - split: test
    path: parsed/parsed.jsonl
---

# LLM Forecast Calibration Study — GLM-5.3 on resolved Manifold Markets questions

Raw generation data for the study "Does sampling K times beat thinking harder?
A controlled study of LLM forecast calibration on resolved binary questions."

Source repo: [EzraStone/llm-forecast-calibration](https://github.com/EzraStone/llm-forecast-calibration).
Data mirrored from GitHub commit [`0f12f71a2c2ec8c54cafeb4231fecb87e705e660`](https://github.com/EzraStone/llm-forecast-calibration/tree/0f12f71a2c2ec8c54cafeb4231fecb87e705e660).
All eight JSONL files match the source data byte for byte. The source repository
remains canonical for analysis code, results, figures, and archived pilot data.

## Version and file layout

Version **1.0.0**, released **2026-09-15**; GitHub release tag **v1.0**; Hugging Face data pinned to an immutable commit.
See [release notes](https://github.com/EzraStone/llm-forecast-calibration/blob/v1.0/RELEASE_NOTES.md).
Paths below describe the Hugging Face mirror. In GitHub, the same dataset files
live under `data/`; `DATASET_CARD.md` is copied verbatim to the Hugging Face
`README.md` by `scripts/publish_hf.py`.

## Load the dataset

The `questions` and `forecasts` configurations have different schemas and are
loaded separately. Both use a single `test` split because this is an evaluation
study; there is no predefined training/validation partition.

```python
from datasets import load_dataset

repo = "ezra77/llm-forecast-calibration"
revision = "4283938acdd97b5fa41dcf673795ad0d38b019ca"  # fixed release snapshot
questions = load_dataset(repo, "questions", split="test", revision=revision)  # 212 rows
forecasts = load_dataset(repo, "forecasts", split="test", revision=revision)  # 4,026 rows
post_cutoff_questions = questions.filter(lambda row: row["stratum"] == "post_cutoff")
```

Raw responses remain available as downloadable JSONL files under `raw/`. They
are excluded from the automatic viewer configuration so their nested schema is
not mixed with the question or forecast tables.

The parsed table includes retries and dead-letter records; rows are not
independent forecasts. To reproduce the published analysis, retain `ok` and
`synonym_key` rows, then keep the first row for each
`(qid, condition, sample_idx)`, preserving file order. The source analysis
excludes `ok_deadletter` rows. Join on `qid` to retrieve question text and crowd
baselines. See [`src/analyze.py`](https://github.com/EzraStone/llm-forecast-calibration/blob/0f12f71a2c2ec8c54cafeb4231fecb87e705e660/src/analyze.py)
for the exact aggregation and paired-bootstrap procedure.

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
  `raw/dead_letter.jsonl` (232 failed/retried attempt records, including recoverable content). Every record carries:
  `qid`, `condition`, `sample_idx`, `model` (z-ai/glm-5.3-free),
  `reasoning_effort` (low/high/max), `temperature`, `prompt_version` hash,
  `requested_at` (UTC), `latency_s`, `attempt`, `usage` (prompt/completion/
  reasoning tokens), `raw_response`, `error`.
- `parsed/parsed.jsonl` — 4,026 per-call/attempt rows with the extracted probability:
  `qid`, `condition`, `sample_idx`, `probability`, `parse_status`
  (ok / synonym_key / ok_deadletter / dead_letter), `stratum`, `outcome`.

Parsed row counts: `ok` 3,795; `synonym_key` 77; `ok_deadletter` 44;
`dead_letter` 110. Missing probabilities are stored as null. Raw files may
include calls on questions later dropped from the final 212-question set.

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

## Licenses and third-party rights

This is a **mixed-rights dataset**, labeled `other` in the Hub metadata.
Code and project-authored documentation are MIT-licensed. CC BY 4.0 applies only
to project contributions to the extent Ezra Stone holds the relevant rights;
it does not relicense Manifold question text, market data, or other third-party
material. Read [DATA_LICENSE](https://huggingface.co/datasets/ezra77/llm-forecast-calibration/blob/main/DATA_LICENSE)
and [LICENSE](https://huggingface.co/datasets/ezra77/llm-forecast-calibration/blob/main/LICENSE).

Manifold's [API licensing guidance](https://docs.manifold.markets/api#licensing)
permits academic research, personal projects, and non-commercial use, while
requiring a data license for commercial AI/ML training with API data. Its
[Terms of Service](https://docs.manifold.markets/terms) also apply.
**No separate written redistribution or relicensing permission from Manifold
has been obtained for this release.** That scope remains unconfirmed; public
availability and research-use permission do not establish broader downstream
rights. These source terms were reviewed on 2026-09-14.

## Citation

Stone, Ezra (2026). *LLM Forecast Calibration Study: GLM-5.3 on Resolved Manifold
Markets Questions*. Version 1.0.0. Hugging Face dataset and GitHub research
repository.

Machine-readable citations: [CITATION.cff](https://huggingface.co/datasets/ezra77/llm-forecast-calibration/blob/main/CITATION.cff)
and [CITATION.bib](https://huggingface.co/datasets/ezra77/llm-forecast-calibration/blob/main/CITATION.bib).
When reproducing results, cite this version and load `revision="4283938acdd97b5fa41dcf673795ad0d38b019ca"`.

```bibtex
@misc{stone2026llmforecastcalibration,
  author = {Stone, Ezra},
  title = {{LLM Forecast Calibration Study}: {GLM-5.3} on Resolved {Manifold Markets} Questions},
  year = {2026},
  month = sep,
  howpublished = {Hugging Face dataset and GitHub research repository},
  url = {https://huggingface.co/datasets/ezra77/llm-forecast-calibration/tree/4283938acdd97b5fa41dcf673795ad0d38b019ca},
  note = {Version 1.0.0; GitHub release tag v1.0}
}
```
