"""Built-in catalog kind: pipeline."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("pipeline", convention="sequential stage composition")
def pipeline(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    current = input.get("initial")
    stages = []
    for stage in input.get("stages", []):
        result = ctx.step(current, request(ctx), kind=stage.get("kind"))
        stages.append(result)
        if result["outcome"] == "ok":
            current = result["value"]
    return {"stages": stages, "final": current}

