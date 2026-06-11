"""Built-in catalog kind: transformer."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("transformer", convention="preprocess/delegate/postprocess wrapper")
def transformer(input: dict[str, Any], ctx: Any) -> Any:
    inner_input = input.get("inner_input_template")
    if input.get("preprocess"):
        inner_input = monty_run(input["preprocess"], inner_input, ctx)
    result = ctx.step(inner_input, request(ctx), kind=input.get("inner_kind"))
    if input.get("postprocess"):
        return monty_run(input["postprocess"], result, ctx)
    return result

