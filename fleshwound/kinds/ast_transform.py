"""Built-in catalog kind: ast_transform.

Round-trips a JSON-encoded AST and records the transform string as ``changes``
(placeholder for real transform pipelines).

When to use: nested JSON serialization tests; starting point before wiring real
transform logic.

Similar kinds: ``transformer``; ``monty_exec``; ``function_map_editor``.

Prefer alternatives when: use ``transformer`` or ``monty_exec`` for real
transforms; use ``function_map_editor`` for named function map edits."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("ast_transform", convention="return transformed AST data")
def ast_transform(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"ast": input.get("ast", {}), "changes": [str(input.get("transform", ""))]}

