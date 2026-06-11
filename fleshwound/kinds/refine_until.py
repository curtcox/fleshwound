"""Built-in catalog kind: refine_until.

Alternates ``inner_kind`` and ``judge_kind`` up to ``max_rounds``, stopping when
verdict JSON contains ``"pass"``.

When to use: iterative improvement with an explicit judge kind.

Similar kinds: ``retry_wrapper``; ``rlm_loop``; ``tournament``.

Prefer alternatives when: use ``retry_wrapper`` for transient failures; use
``rlm_loop`` for richer action protocols; use ``ensemble`` for parallel drafts."""

from __future__ import annotations

import json

from typing import Any

from ..catalog import register
from ._shared import request


@register("refine_until", convention="iterative refine/judge loop")
def refine_until(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    history = []
    final = None
    for _ in range(max(0, int(input.get("max_rounds", 1)))):
        candidate = ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"))
        verdict = ctx.step(candidate, request(ctx), kind=input.get("judge_kind"))
        history.append({"candidate": candidate, "verdict": verdict})
        final = candidate.get("value")
        if verdict["outcome"] == "ok" and "pass" in json.dumps(verdict["value"]).lower():
            break
    return {"rounds": len(history), "history": history, "final": final}

