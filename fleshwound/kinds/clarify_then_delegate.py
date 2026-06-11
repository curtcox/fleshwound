"""Built-in catalog kind: clarify_then_delegate."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("clarify_then_delegate", convention="optionally ask then delegate")
def clarify_then_delegate(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    q = f"Clarify task: {input.get('task')}"
    a = ctx.ask_user(q) if ctx.ask_user else None
    result = ctx.step({"task": input.get("task"), "clarification": a}, request(ctx), kind=input.get("child_kind"))
    return {"clarification_q": q if ctx.ask_user else None, "clarification_a": a, "result": result}

