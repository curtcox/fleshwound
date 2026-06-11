"""Built-in catalog kind: inherit_chain.

Recursively calls itself with ``same_as_parent`` until depth bottoms out, building
a trace of visited kind names.

When to use: depth decrement, ``same_as_parent``, and ``budget_denied`` tests.

Similar kinds: ``infinite_descent``; ``pipeline``.

Prefer alternatives when: use ``infinite_descent`` for step-budget vs depth stress;
use ``pipeline`` when each hop changes kind."""

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

