"""Built-in catalog kind: tournament."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("tournament", convention="pairwise preference bracket")
def tournament(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    candidates = list(input.get("candidates") or [])
    bracket = []
    while len(candidates) > 1:
        a, b, *rest = candidates
        result = ctx.step({"a": a, "b": b, "criterion": "best"}, request(ctx), kind=input.get("judge_kind"))
        winner = a if result["outcome"] != "ok" or result["value"].get("winner") != "b" else b
        bracket.append({"a": a, "b": b, "result": result})
        candidates = [winner] + rest
    return {"winner": candidates[0] if candidates else None, "bracket": bracket}

