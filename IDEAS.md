# IDEAS.md

Out-of-scope ideas parked here per spec rule #6 (scope discipline). Nothing in this file is implemented.

## Data
- Multi-question-set replication: repeat the whole design on Manifold to test platform-selection effects.
- Continuous-range questions (not just binary) for a full distributional calibration analysis.
- Long-horizon questions (resolve >6 months out) to test true forecasting vs. near-term resolution.

## Methods
- Logit-space aggregation (mean of logits) as a fourth aggregator alongside median/mean/trimmed-mean.
- Per-question optimal-K estimation: does the flattening point of the Brier-vs-K curve vary with question difficulty (crowd |p−0.5|)?
- Verbalized confidence ("confidence_note" field) as a second uncertainty signal, compared against sampling-based confidence.
- Weight by inverse reasoning-token count: are short-reasoning samples more or less calibrated?

## Analysis
- Regress per-question Brier on question features (topic, duration, forecaster count) to find where the model beats the crowd.
- Anchor-point analysis: distribution of probabilities at p=0.5 exactly (reasoning models may cluster there).
- Compare ECE equal-width vs. equal-mass variants formally, report which is more stable at this N.
- Skill scores: Brier skill score vs. climatology baseline for each condition.

## Infrastructure
- Publish a small PyPI package wrapping the runner for other models (out of scope: one model, one set).
