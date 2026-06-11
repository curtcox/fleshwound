"""Built-in catalog kind: refine_until."""

from __future__ import annotations

import json

from typing import Any

from ..catalog import register
from ._shared import request


@register("refine_until", convention="iterative refine/judge loop")
def refine_until(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    history = []
    final = None
    for _ in range(max(0, int(input.get("max_rounds", 1)))):
        candidate = ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"))
        verdict = ctx.step(candidate, request(ctx), kind=input.get("judge_kind"))
        history.append({"candidate": candidate, "verdict": verdict})
        final = candidate.get("value")
        if verdict["outcome"] == "ok" and "pass" in json.dumps(verdict["value"]).lower():
            break
    return {"rounds": len(history), "history": history, "final": final}

