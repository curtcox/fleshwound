"""Built-in catalog kind: patch_applier_proxy.

Pure-data simulation of patch application: validates paths/diffs and returns
applied vs rejected lists without disk access.

When to use: test patch shapes with caller-side real appliers.

Similar kinds: ``patch_set_writer``; ``diff_writer``; ``function_map_editor``.

Prefer alternatives when: use writer kinds to generate patches; caller owns FS
mutation in v1."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("patch_applier_proxy", convention="pure-data patch apply simulation")
def patch_applier_proxy(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    applied = []
    rejected = []
    for patch in input.get("patches", []):
        path = patch.get("path", "")
        diff = patch.get("diff", "")
        if not path:
            rejected.append({"path": path, "reason": "missing path"})
        elif not diff:
            rejected.append({"path": path, "reason": "missing diff"})
        else:
            applied.append(path)
    return {"applied": applied, "rejected": rejected}

