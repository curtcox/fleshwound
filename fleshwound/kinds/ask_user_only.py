"""Built-in catalog kind: ask_user_only."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("ask_user_only", convention="question -> {'answer'} or unavailable note")
def ask_user_only(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    if ctx.ask_user is None:
        return {"answer": None, "notes": "ask_user unavailable"}
    return {"answer": ctx.ask_user(str(input.get("question", "")))}

