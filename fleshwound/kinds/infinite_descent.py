"""Built-in catalog kind: infinite_descent.

Recursively self-calls with shrinking budget until child allocation fails with
``budget_denied``.

When to use: confirm depth floor halts chains distinct from ``budget_exhausted``.

Similar kinds: ``inherit_chain``; ``budget_hog``.

Prefer alternatives when: use ``inherit_chain`` for explicit kind traces; use
``budget_hog`` for exhaustion inside a leaf."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("infinite_descent", convention="descends until child allocation is denied")
def infinite_descent(input: Any, ctx: Any) -> dict[str, Any]:
    result = ctx.step({}, request(ctx), kind="infinite_descent")
    return {"result": result}

