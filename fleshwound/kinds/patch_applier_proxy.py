"""Built-in catalog kind: patch_applier_proxy."""

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

