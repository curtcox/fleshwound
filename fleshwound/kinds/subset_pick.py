"""Built-in catalog kind: subset_pick."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("subset_pick", convention="delegate using random_from_subset default policy")
def subset_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=None, default_policy={"random_from_subset": input.get("subset", [])})}

