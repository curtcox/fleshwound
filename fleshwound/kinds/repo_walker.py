"""Built-in catalog kind: repo_walker.

Filters virtual ``tree`` paths with a Monty ``predicate``, then runs
``per_file_kind`` once per match.

When to use: large fan-out over files with separate budget per match.

Similar kinds: ``map_reduce``; ``dedup_then_map``; ``pipeline``.

Prefer alternatives when: use ``map_reduce`` for homogeneous lists; size child
budgets carefully to avoid parent ``budget_denied``."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("repo_walker", convention="run per_file_kind for matching virtual files")
def repo_walker(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    tree = input.get("tree") or {}
    predicate = str(input.get("predicate", "True"))
    matching: list[tuple[str, Any]] = []
    skipped = []
    for path, data in tree.items():
        child_input = {"path": path, "data": data}
        try:
            include = bool(monty_run(predicate, child_input, ctx))
        except Exception:
            skipped.append({"path": path, "reason": "predicate_error"})
            continue
        if include:
            matching.append((path, data))
        else:
            skipped.append({"path": path, "reason": "predicate_false"})

    per_file = {}
    for path, data in matching:
        per_file[path] = ctx.step({"path": path, "data": data}, request(ctx, len(matching) or 1), kind=input.get("per_file_kind"))
    result: dict[str, Any] = {"per_file": per_file}
    if skipped:
        result["skipped"] = skipped
    return result

