"""Built-in catalog kind: cascade."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("cascade", convention="try kinds in order until one succeeds")
def cascade(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    tried = []
    result = None
    stop_predicate = input.get("stop_predicate")
    for kind in input.get("kinds", []):
        tried.append(kind)
        result = ctx.step(input.get("inner_input"), request(ctx, len(input.get("kinds", [])) or 1), kind=kind)
        if result["outcome"] != "ok":
            continue
        if not stop_predicate or monty_run(str(stop_predicate), result.get("value"), ctx):
            return {"chosen_kind": kind, "result": result, "tried": tried}
    return {"chosen_kind": None, "result": result, "tried": tried}

