# Version 1.0.0 (tag: v1.0)

Released 2026-09-15.

This release records the completed calibration study and a reproducible dataset
snapshot. The main-study data are unchanged from GitHub commit
`0f12f71a2c2ec8c54cafeb4231fecb87e705e660`.

## Included data

- 212 resolved binary questions (106 YES / 106 NO).
- 3,831 successful raw API responses across conditions A-E.
- 232 raw failed/retried attempt records in `raw/dead_letter.jsonl`.
- 4,026 parsed records, including retries and dead-letter records; these are not
  4,026 independent forecasts.
- Separate Hugging Face `questions` and `forecasts` configurations, each with
  a `test` split. The GitHub repository also includes analysis code, results,
  figures, tests, and archived pilot data.

## Publication changes

- Synchronize the GitHub dataset card and Hugging Face README.
- Document loading, parsing statuses, and retry deduplication.
- Add `CITATION.cff` and `CITATION.bib`.
- Clarify project licensing and Manifold-origin material in `DATA_LICENSE`.
- Include licenses, citations, and these notes in the publishing script.

## Versioned access

GitHub uses the `v1.0` release tag. Hugging Face data access is pinned to the
immutable commit shown below; updated documentation is available on `main`.

- [GitHub release](https://github.com/EzraStone/llm-forecast-calibration/releases/tag/v1.0)
- [Hugging Face snapshot](https://huggingface.co/datasets/ezra77/llm-forecast-calibration/tree/4283938acdd97b5fa41dcf673795ad0d38b019ca)

```python
from datasets import load_dataset

questions = load_dataset(
    "ezra77/llm-forecast-calibration", "questions", split="test", revision="4283938acdd97b5fa41dcf673795ad0d38b019ca"
)
forecasts = load_dataset(
    "ezra77/llm-forecast-calibration", "forecasts", split="test", revision="4283938acdd97b5fa41dcf673795ad0d38b019ca"
)
```

## Scope and permissions

Code and project-authored documentation are MIT-licensed. CC BY 4.0 applies only
to project contributions to the extent the author holds the relevant rights.
Manifold-origin material retains its source terms. No separate written
redistribution or relicensing permission from Manifold has been obtained for
this release; that scope remains unconfirmed. See [DATA_LICENSE](DATA_LICENSE).

The assumed model training cutoff is not documented by the provider, and the
crowd baseline has an information advantage. Results concern a single model,
provider, question platform, and study period; see the dataset card and the
GitHub repository's `LIMITATIONS.md`.
