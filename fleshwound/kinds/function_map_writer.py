"""Built-in catalog kind: function_map_writer.

For each ``signatures`` entry, calls ``program_writer`` and returns generated
sources keyed by name with ``missing`` tracking.

When to use: generating many related Monty functions from signature specs.

Similar kinds: ``program_writer``; ``function_map_editor``; ``directory_input``.

Prefer alternatives when: use ``program_writer`` for one function; use
``function_map_editor`` for incremental edits."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("function_map_writer", convention="write functions for signatures")
def function_map_writer(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    functions = {}
    for name, spec in (input.get("signatures") or {}).items():
        result = ctx.step({"task": f"Write {spec}", "context": input.get("context")}, request(ctx), kind="program_writer")
        if result["outcome"] == "ok":
            functions[name] = {"source": result["value"].get("program", ""), "notes": result["value"].get("notes", "")}
    return {"functions": functions, "missing": [name for name in (input.get("signatures") or {}) if name not in functions]}

