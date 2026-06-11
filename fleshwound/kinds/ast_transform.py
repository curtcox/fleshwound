"""Built-in catalog kind: ast_transform."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("ast_transform", convention="return transformed AST data")
def ast_transform(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"ast": input.get("ast", {}), "changes": [str(input.get("transform", ""))]}

