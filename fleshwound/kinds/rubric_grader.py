"""Built-in catalog kind: rubric_grader."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "rubric_grader",
    "Grade using the rubric.",
    lambda i, t: {"scores": [], "weighted_total": 0, "notes": t},
)
