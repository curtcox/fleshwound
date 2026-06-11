"""Built-in catalog kind: content_hash_memo.

Hashes ``(inner_kind, inner_input)``; returns cached value from caller ``memo`` or
runs one child step and updates memo in the value.

When to use: legal within-run memoization (cache explicit in input/output).

Similar kinds: ``dedup_then_map``; ``retry_wrapper``; excluded cross-run ``cached``.

Prefer alternatives when: use ``dedup_then_map`` for list fan-out dedup; omit memo
when every call must be fresh."""

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

