"""Built-in catalog kind: dedup_then_map."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, content_hash

@register("dedup_then_map", convention="run inner_kind once per unique item hash")
def dedup_then_map(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    items = list(input.get("items") or [])
    item_hashes = [content_hash(item) for item in items]
    results = {}
    for item_hash, item in zip(item_hashes, items):
        if item_hash not in results:
            results[item_hash] = ctx.step(item, request(ctx, len(set(item_hashes)) or 1), kind=input.get("inner_kind"))
    return {"results_by_hash": results, "items_to_hash": item_hashes}

