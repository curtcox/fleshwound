"""Built-in catalog kind: budget_hog.

Burns one budget dimension (``tokens``, ``steps``, or ``tool_calls``) to zero,
then attempts one more primitive call to observe ``budget_exhausted``.

When to use: contract tests for mid-execution budget exhaustion at host boundaries.

Similar kinds: ``infinite_descent``; ``always_host_error``; ``noop_fail``.

Prefer alternatives when: use ``infinite_descent`` for depth-floor ``budget_denied``;
use ``always_host_error`` for other codes."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("budget_hog", convention="burns target budget and observes exhaustion")
def budget_hog(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    target = input.get("target")
    if target == "tokens":
        ctx.llm("x " * (ctx.budget()["tokens_remaining"] + 1))
    elif target == "tool_calls":
        ctx.ledger.charge_tool_call(ctx.budget_id, "budget_hog")
    elif target == "steps":
        result = ctx.step({}, {"tokens": 0, "steps": ctx.budget()["steps_remaining"] + 1, "depth": 1, "tool_calls": 0}, kind="echo")
        return {"target": target, "result": result}
    return {"target": target, "budget": ctx.budget()}

