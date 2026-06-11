"""Built-in catalog kind: function_map_editor.

Pure-data transform applying remove/add/update edits to a function map with
explicit ``removed`` / ``added`` keys.

When to use: incremental map maintenance without regenerating unchanged functions.

Similar kinds: ``function_map_writer``; ``patch_set_writer``; ``convention_adapter``.

Prefer alternatives when: use ``function_map_writer`` for greenfield generation; use
LLM kinds when edits need semantic reasoning."""

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

