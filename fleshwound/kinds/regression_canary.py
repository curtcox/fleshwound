"""Built-in catalog kind: regression_canary."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, content_hash

@register("regression_canary", convention="hash child value and compare to expected")
def regression_canary(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    result = ctx.step(input.get("frozen_input"), request(ctx), kind=input.get("frozen_kind"))
    actual = content_hash(result.get("value")) if result["outcome"] == "ok" else content_hash(result)
    return {"passed": actual == input.get("expected_value_hash"), "actual_hash": actual, "result": result}

