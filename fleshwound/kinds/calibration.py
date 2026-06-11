"""Built-in catalog kind: calibration.

Runs ``grader_kind`` on each labeled example, compares predicted scores to
``gold_score``, returns agreement and bias stats.

When to use: meta-evaluation of graders; fan-out budget-sizing exercises.

Similar kinds: ``regression_canary``; ``catalog_self_test``; ``rubric_grader``.

Prefer alternatives when: use ``regression_canary`` for single golden hashes; use
``rubric_grader`` directly when not comparing to gold labels."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("calibration", convention="compare grader outputs to gold scores")
def calibration(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    per = []
    for example in input.get("examples", []):
        result = ctx.step(example.get("item"), request(ctx), kind=input.get("grader_kind"))
        predicted = result.get("value", {}).get("weighted_total", 0) if result["outcome"] == "ok" else 0
        per.append({"predicted": predicted, "gold": example.get("gold_score", 0)})
    agreement = sum(1 for row in per if row["predicted"] == row["gold"]) / (len(per) or 1)
    return {"agreement": agreement, "per_example": per, "bias": 0.0}

