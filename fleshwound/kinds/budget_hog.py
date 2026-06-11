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
from ..errors import HostError


def _maybe_stop(stop_on_exhaustion: bool, code: str, message: str) -> None:
    if stop_on_exhaustion:
        raise HostError(code, message)


@register("budget_hog", convention="burns target budget and observes exhaustion")
def budget_hog(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    target = input.get("target")
    stop_on_exhaustion = bool(input.get("stop_on_exhaustion"))
    if target == "tokens":
        llm_result = ctx.llm("x " * (ctx.budget()["tokens_remaining"] + 1))
        error = llm_result.get("error") or {}
        if llm_result.get("status") == "error" and error.get("code") == "budget_exhausted":
            _maybe_stop(
                stop_on_exhaustion,
                "budget_exhausted",
                str(error.get("message", "Token budget exhausted.")),
            )
        return {"target": target, "llm": llm_result, "budget": ctx.budget()}
    if target == "tool_calls":
        charged = ctx.tool_call("budget_hog")
        if not charged:
            _maybe_stop(stop_on_exhaustion, "budget_exhausted", "Tool-call budget exhausted.")
        return {"target": target, "tool_call_charged": charged, "budget": ctx.budget()}
    if target == "steps":
        result = ctx.step(
            {},
            {
                "tokens": 0,
                "steps": ctx.budget()["steps_remaining"] + 1,
                "depth": 1,
                "tool_calls": 0,
            },
            kind="echo",
        )
        if result["outcome"] == "host_error":
            host_error = result["host_error"]
            _maybe_stop(
                stop_on_exhaustion,
                host_error["code"],
                host_error["message"],
            )
        return {"target": target, "result": result}
    return {"target": target, "budget": ctx.budget()}
