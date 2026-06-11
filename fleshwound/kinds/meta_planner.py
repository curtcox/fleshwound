"""Built-in catalog kind: meta_planner."""

from __future__ import annotations

import json

from typing import Any

from ..catalog import register
from ._shared import request


@register("meta_planner", convention="LLM JSON plan then sequential execution")
def meta_planner(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    text = ctx.llm(f"Plan task with catalog {sorted(ctx.catalog)}: {input.get('task')}").get("text", "[]")
    try:
        plan = json.loads(text)
    except Exception:
        plan = []
    results = [ctx.step(item.get("input"), request(ctx, len(plan) or 1), kind=item.get("kind")) for item in plan]
    return {"plan": plan, "results": results}

