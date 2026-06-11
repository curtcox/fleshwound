"""Built-in catalog kind: dynamic_dispatch."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("dynamic_dispatch", convention="choose kind literally or by llm then delegate")
def dynamic_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("literal_kind")
    if input.get("chooser") == "llm":
        chosen = ctx.llm(f"Choose one kind from {sorted(ctx.catalog)} for {input.get('task_for_chooser')}").get("text", "").strip()
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), request(ctx), kind=chosen)}

