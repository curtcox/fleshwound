"""Built-in catalog kind: pipeline.

Runs ``stages[]`` sequentially, threading each ok stage's ``value`` as the next
input.

When to use: fixed multi-step workflows with caller-defined kind order.

Similar kinds: ``meta_planner``; ``chain_with_adapter``; ``transformer``.

Prefer alternatives when: use ``meta_planner`` for LLM-defined plans; use
``chain_with_adapter`` when conventions must be translated mid-pipeline."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("pipeline", convention="sequential stage composition")
def pipeline(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    current = input.get("initial")
    stages = []
    for stage in input.get("stages", []):
        result = ctx.step(current, request(ctx), kind=stage.get("kind"))
        stages.append(result)
        if result["outcome"] == "ok":
            current = result["value"]
    return {"stages": stages, "final": current}

