"""Built-in catalog kind: judge.

One LLM call evaluates a candidate against prose criteria and returns pass/fail
plus rationale.

When to use: binary acceptance in ``refine_until`` and manual pipelines.

Similar kinds: ``rubric_grader``; ``pairwise_preference``; ``classifier``.

Prefer alternatives when: use ``rubric_grader`` for weighted scores; use
``pairwise_preference`` in brackets; use ``classifier`` for label sets."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("judge", convention="candidate/criteria -> pass/fail/rationale")
def judge(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    result = ctx.llm(f"Judge pass or fail.\nCriteria: {input.get('criteria')}\nCandidate: {input.get('candidate')}")
    text = result.get("text", "")
    return {"verdict": "pass" if "pass" in text.lower() else "fail", "rationale": text}

