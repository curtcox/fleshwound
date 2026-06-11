"""Built-in catalog kind: inherit_chain."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("inherit_chain", convention="recursively calls same kind until depth expires")
def inherit_chain(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    depth = int(input.get("depth", 0))
    trace = [ctx.kind]
    if depth <= 0:
        return {"trace": trace}
    result = ctx.step({"task": input.get("task"), "depth": depth - 1}, request(ctx), kind=None)
    if result["outcome"] == "ok":
        trace.extend(result["value"].get("trace", []))
    else:
        trace.append(result["host_error"]["code"])
    return {"trace": trace}

