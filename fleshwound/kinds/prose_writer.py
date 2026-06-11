"""Built-in catalog kind: prose_writer."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("prose_writer", convention="task/context -> {'text', 'notes'} using ctx.llm")
def prose_writer(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    result = ctx.llm(f"Write prose for task: {input.get('task')}\nContext: {input.get('context')}")
    return {"text": result.get("text", ""), "notes": "model_error" if result["status"] == "error" else ""}

