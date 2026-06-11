"""Built-in catalog kind: ensemble."""

from __future__ import annotations

import json

from typing import Any

from ..catalog import register
from ._shared import request


@register("ensemble", convention="run inner_kind n times and aggregate with llm")
def ensemble(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    n = max(0, int(input.get("n", 1)))
    candidates = [ctx.step(input.get("inner_input"), request(ctx, n + 1), kind=input.get("inner_kind")) for _ in range(n)]
    ok_values = [r["value"] for r in candidates if r["outcome"] == "ok"]
    chosen = ok_values[0] if ok_values else None
    if ok_values and input.get("aggregator_prompt"):
        result = ctx.llm(f"{input['aggregator_prompt']}\nCandidates: {json.dumps(ok_values, sort_keys=True)}")
        chosen = result.get("text") or chosen
    return {"chosen": chosen, "candidates": ok_values}

