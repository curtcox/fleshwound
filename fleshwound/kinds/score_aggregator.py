"""Built-in catalog kind: score_aggregator.

Pure Monty reduction aggregating ``{score, weight}`` rows by policy
(``weighted_mean``, ``median``, or ``min``).

When to use: deterministic combine step after ``rubric_grader`` without inline
parent math.

Similar kinds: ``rubric_grader``; ``calibration``; ``monty_exec``.

Prefer alternatives when: use ``rubric_grader`` when scores do not exist yet; use
``monty_exec`` for custom policies."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("score_aggregator", convention="aggregate scores by weighted_mean, median, or min")
def score_aggregator(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    scores = list(input.get("scores") or [])
    values = [float(s.get("score", 0)) for s in scores]
    policy = input.get("policy", "weighted_mean")
    if not values:
        aggregate = 0.0
    elif policy == "min":
        aggregate = min(values)
    elif policy == "median":
        aggregate = sorted(values)[len(values) // 2]
    else:
        total_w = sum(float(s.get("weight", 1)) for s in scores) or 1.0
        aggregate = sum(float(s.get("score", 0)) * float(s.get("weight", 1)) for s in scores) / total_w
    return {"aggregate": aggregate, "n": len(values)}

