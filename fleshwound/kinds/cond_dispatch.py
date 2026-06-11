"""Built-in catalog kind: cond_dispatch."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("cond_dispatch", convention="first true Monty predicate dispatches")
def cond_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("default_kind")
    for branch in input.get("branches", []):
        if monty_run(str(branch.get("when", "False")), input.get("inner_input"), ctx):
            chosen = branch.get("kind")
            break
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), request(ctx), kind=chosen)}

