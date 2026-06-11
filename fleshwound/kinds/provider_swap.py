"""Built-in catalog kind: provider_swap."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("provider_swap", convention="delegates with supplied provider object if present")
def provider_swap(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    provider = input.get("inner_provider") or ctx.provider
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"), provider=provider)}

