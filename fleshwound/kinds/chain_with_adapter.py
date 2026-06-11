"""Built-in catalog kind: chain_with_adapter."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("chain_with_adapter", convention="first -> adapter -> second")
def chain_with_adapter(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    first = ctx.step(input.get("first_input"), request(ctx), kind=input.get("first_kind"))
    adapted = ctx.step({"source_kind": input.get("first_kind"), "target_kind": input.get("second_kind"), "source_value": first.get("value")}, request(ctx), kind="convention_adapter")
    second_input = adapted.get("value", {}).get("target_input") if adapted["outcome"] == "ok" else None
    second = ctx.step(second_input, request(ctx), kind=input.get("second_kind"))
    return {"first_result": first, "adapted_input": second_input, "second_result": second}

