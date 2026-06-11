"""Built-in catalog kind: infinite_descent."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("infinite_descent", convention="descends until child allocation is denied")
def infinite_descent(input: Any, ctx: Any) -> dict[str, Any]:
    result = ctx.step({}, request(ctx), kind="infinite_descent")
    return {"result": result}

