"""Built-in catalog kind: random_pick."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("random_pick", convention="delegate using random default policy")
def random_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=None, default_policy="random")}

