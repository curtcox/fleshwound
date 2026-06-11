"""Built-in catalog kind: content_hash_memo."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, content_hash

@register("content_hash_memo", convention="explicit input/output memoization")
def content_hash_memo(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    key = content_hash({"kind": input.get("inner_kind"), "input": input.get("inner_input")})
    memo = dict(input.get("memo") or {})
    if key in memo:
        return {"hash": key, "value": memo[key], "hit": True, "memo": memo}
    result = ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"))
    value = result.get("value") if result["outcome"] == "ok" else result
    memo[key] = value
    return {"hash": key, "value": value, "hit": False, "memo": memo}

