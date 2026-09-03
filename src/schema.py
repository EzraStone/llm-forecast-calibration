"""Pydantic models for every record type in the study."""
from datetime import date

from pydantic import BaseModel, Field


class Question(BaseModel):
    """One resolved binary question, as committed in data/questions.jsonl."""

    qid: str
    source: str = "manifold"
    title: str
    description: str = ""
    resolution_criteria: str = Field(default="", description="How the question resolves; here: market resolution mechanics")
    open_date: date | None = None
    close_date: date | None = None
    resolve_date: date
    outcome: int = Field(ge=0, le=1)
    baseline_crowd_prob: float = Field(ge=0.0, le=1.0)
    stratum: str = Field(pattern="^(pre_cutoff|post_cutoff)$")
    n_forecasters: int = Field(ge=0)
    volume: float = Field(default=0.0, ge=0.0)
    url: str = ""


class ForecastCall(BaseModel):
    """Metadata for one raw API call, as committed in data/raw/{condition}.jsonl."""

    qid: str
    condition: str
    sample_idx: int = Field(ge=0)
    model: str
    reasoning_effort: str
    temperature: float
    prompt_version: str
    requested_at: str
    latency_s: float
    attempt: int = Field(ge=1)
    usage: dict
    raw_response: dict
    error: str | None = None


class ParsedRow(BaseModel):
    """One row of data/parsed/parsed.jsonl: parse outcome per call."""

    qid: str
    condition: str
    sample_idx: int = Field(ge=0)
    probability: float | None = None
    parse_status: str
    stratum: str
    outcome: int
