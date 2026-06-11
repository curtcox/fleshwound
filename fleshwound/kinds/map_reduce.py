"""Built-in catalog kind: map_reduce.

Maps each item through ``map_kind`` sequentially, optionally reduces via
``reduce_kind``; records per-item error indices.

When to use: homogeneous fan-out where individual child failures should not abort
the map.

Similar kinds: ``dedup_then_map``; ``repo_walker``; ``pipeline``.

Prefer alternatives when: use ``dedup_then_map`` for duplicate items; use
``repo_walker`` for path-keyed fan-out; use ``pipeline`` for dependent stages."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("map_reduce", convention="map items through map_kind; optional reduce_kind")
def map_reduce(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    items = list(input.get("items") or [])
    mapped, errors = [], []
    parts = len(items) + (1 if input.get("reduce_kind") else 0)
    for idx, item in enumerate(items):
        result = ctx.step(item, request(ctx, parts), kind=input.get("map_kind"))
        mapped.append(result.get("value") if result["outcome"] == "ok" else None)
        if result["outcome"] != "ok":
            errors.append(idx)
    reduced = None
    if input.get("reduce_kind"):
        reduced_result = ctx.step(mapped, request(ctx, parts), kind=input["reduce_kind"])
        reduced = reduced_result.get("value") if reduced_result["outcome"] == "ok" else None
    return {"mapped": mapped, "reduced": reduced, "errors": errors}

