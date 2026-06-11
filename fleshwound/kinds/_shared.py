"""Shared helpers for built-in catalog kinds."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from ..errors import HostError
from ..monty_limits import is_monty_limit_error, limit_error_message, monty_limits_from_compute


def request(ctx: Any, parts: int = 1) -> dict[str, int]:
    snap = ctx.budget()
    steps = max(1, snap["steps_remaining"] // max(parts, 1))
    depth = max(1, snap["depth_remaining"] - 1)
    return {
        "tokens": max(0, snap["tokens_remaining"] // max(parts, 1)),
        "steps": steps,
        "depth": depth,
        "tool_calls": max(0, snap["tool_calls_remaining"] // max(parts, 1)),
        "compute": max(0, snap["compute_remaining"] // max(parts, 1)),
    }


def monty_run(code: str, input: Any, ctx: Any) -> Any:
    try:
        import pydantic_monty
        from pydantic_monty import ResourceLimits
    except ImportError as exc:
        raise RuntimeError("pydantic_monty is required for Monty-backed kinds") from exc

    compute_remaining = int(ctx.budget()["compute_remaining"])
    if compute_remaining <= 0:
        raise HostError("budget_exhausted", "Compute budget exhausted.")

    m = pydantic_monty.Monty(code, inputs=["input"])
    try:
        complete = m.run(
            inputs={"input": input},
            external_functions={
                "llm": ctx.llm,
                "step": ctx.step,
                "ask_user": ctx.ask_user,
                "budget": ctx.budget,
                "catalog": lambda: dict(ctx.catalog),
            },
            limits=cast(ResourceLimits, monty_limits_from_compute(compute_remaining)),
        )
    except pydantic_monty.MontyRuntimeError as exc:
        if is_monty_limit_error(exc):
            ctx.ledger.exhaust_compute(ctx.budget_id, "monty resource limit")
            raise HostError("budget_exhausted", limit_error_message(exc)) from exc
        raise
    ctx.ledger.charge_compute(ctx.budget_id, 1, "monty_run")
    return getattr(complete, "output", complete)


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
