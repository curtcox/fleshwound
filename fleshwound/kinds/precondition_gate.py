"""Built-in catalog kind: precondition_gate."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("precondition_gate", convention="predicate-gated delegation")
def precondition_gate(input: dict[str, Any], ctx: Any) -> Any:
    ok = bool(monty_run(str(input.get("predicate", "False")), input.get("inner_input"), ctx))
    if not ok:
        return {"gated": True, "reason": "predicate false"}
    return ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"))

