"""Built-in catalog kind: function_map_editor."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("function_map_editor", convention="edit function map data")
def function_map_editor(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    updated = dict(input.get("current") or {})
    removed, added = [], []
    for edit in input.get("edits", []):
        name = edit.get("name")
        if edit.get("instruction") == "remove" and name in updated:
            removed.append(name)
            updated.pop(name)
        elif name:
            added.append(name) if name not in updated else None
            updated[name] = {"source": edit.get("instruction", updated.get(name, {}).get("source", ""))}
    return {"updated": updated, "removed": removed, "added": added}

