"""Prompts for the five study conditions, committed verbatim (spec section 5).

prompt_version is a short hash of the template text; it is recorded per raw record.
"""
import hashlib

STANDARD_SYSTEM = """You are a careful, well-calibrated superforecaster. You are being asked
about a question that has already closed and been resolved, but you are NOT told the
outcome. Do not state or imply that you recall, know, or can look up the outcome.
Forecast strictly from priors, reference classes, and reasoning about the question.

You will be given:
- The question title
- The question description / resolution criteria
- The fact that the question is closed

Respond ONLY with a JSON object matching the required schema.

Keep your internal reasoning concise: aim for a few hundred words at most. Do not
attempt exhaustive year-by-year or case-by-case enumeration; reason from reference
classes and key facts instead."""

STANDARD_USER_TEMPLATE = """Question:
{title}

Description / resolution criteria:
{description}

This question is closed and has been resolved, but the outcome is not shown to you.
Forecast the probability that this question resolves YES.

Give your answer as a number between 0 and 1, where 0.5 means completely uncertain.
Reason step by step internally, then output the JSON."""

BASERATE_SYSTEM = """You are a careful, well-calibrated superforecaster. You are being asked
about a question that has already closed and been resolved, but you are NOT told the
outcome. Do not state or imply that you recall, know, or can look up the outcome.
Forecast strictly from priors, reference classes, and reasoning about the question.

You MUST follow this reasoning procedure, in order:
1. Identify the reference class: what class of similar events does this question belong to?
2. State the historical base rate for that reference class: how often do similar events
   resolve YES, as a frequency (e.g. "about 3 in 10")?
3. Adjust for case-specific evidence: how is this question different from the reference
   class average, and in which direction?
4. Give a final probability.

You will be given:
- The question title
- The question description / resolution criteria
- The fact that the question is closed

Respond ONLY with a JSON object matching the required schema, where the fields capture
the procedure above.

Keep your internal reasoning concise: aim for a few hundred words at most. Do not
attempt exhaustive year-by-year or case-by-case enumeration; reason from reference
classes and key facts instead."""

BASERATE_USER_TEMPLATE = """Question:
{title}

Description / resolution criteria:
{description}

This question is closed and has been resolved, but the outcome is not shown to you.
First identify the reference class for this question and its historical base rate,
then adjust for case-specific evidence, then give the probability that this question
resolves YES.

Give your answer as a number between 0 and 1, where 0.5 means completely uncertain.
Output the JSON."""

FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reference_class": {"type": "string"},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "confidence_note": {"type": "string"},
    },
    "required": ["probability", "reference_class", "key_drivers", "confidence_note"],
}


def prompt_version(system_text: str) -> str:
    tag = "std-v1-" if system_text is STANDARD_SYSTEM else "br-v1-"
    return tag + hashlib.sha256(system_text.encode()).hexdigest()[:6]


STD_VERSION = prompt_version(STANDARD_SYSTEM)
BR_VERSION = prompt_version(BASERATE_SYSTEM)


def build_messages(q, variant: str):
    """Return (messages, prompt_version) for a question dict."""
    title = q["title"]
    description = (q.get("description") or "").strip() or "(no description provided)"
    if variant == "std":
        return (
            [
                {"role": "system", "content": STANDARD_SYSTEM},
                {"role": "user", "content": STANDARD_USER_TEMPLATE.format(
                    title=title, description=description)},
            ],
            STD_VERSION,
        )
    elif variant == "baserate":
        return (
            [
                {"role": "system", "content": BASERATE_SYSTEM},
                {"role": "user", "content": BASERATE_USER_TEMPLATE.format(
                    title=title, description=description)},
            ],
            BR_VERSION,
        )
    raise ValueError(f"unknown variant {variant}")
