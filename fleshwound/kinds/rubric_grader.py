"""Built-in catalog kind: rubric_grader.

LLM grades a candidate against a weighted rubric; returns per-criterion scores and
``weighted_total``.

When to use: multi-criterion evaluation upstream of ``tournament``, ``refine_until``,
or ``calibration``.

Similar kinds: ``judge``; ``pairwise_preference``; ``score_aggregator``.

Prefer alternatives when: use ``judge`` for pass/fail; use ``score_aggregator`` when
scores already exist."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "rubric_grader",
    "Grade using the rubric.",
    lambda i, t: {"scores": [], "weighted_total": 0, "notes": t},
    convention="candidate/rubric -> scores/weighted_total via ctx.llm",
)
